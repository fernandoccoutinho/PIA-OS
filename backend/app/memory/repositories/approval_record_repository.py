"""
`ApprovalRecordRepository` — persistência, consumo e revogação atômicos
(`E4.9.9.a`).

```text
PERSISTED_APPROVAL != EXECUTION
CONSUMED_APPROVAL  != OBSERVED_ERASURE_ATTEMPT
```

Este repositório **não** executa, não move para lixeira, não apaga, não
autentica e não escreve recibo. Ele torna durável e de uso único uma
decisão que já foi tomada.

## A autoridade é o banco, não o Python

```text
clock_timestamp()   instante decisório
UPDATE ... WHERE ... RETURNING   comando único
```

`now()` seria o instante de **início da transação**: duas sessões abertas
antes do vencimento poderiam consumir depois dele. `clock_timestamp()` é
lido no momento da avaliação da linha.

O chamador **nunca** fornece o instante que o autoriza. Aceitá-lo seria
deixar quem pede o consumo escolher se a aprovação ainda vale.

## Por que não `SELECT` e depois `UPDATE`

Duas decisões separadas: ambas as sessões leriam `ACTIVE` e ambas
escreveriam. Um único `UPDATE` condicional deixa o banco arbitrar, e
`RETURNING` diz quem venceu.

```text
ZERO_ROWS_RETURNED = LOST_OR_INELIGIBLE
DIAGNOSTIC_READ_NEVER_CONVERTS_DEFEAT_INTO_SUCCESS
```

Quando o `UPDATE` devolve zero linhas, uma releitura **diagnóstica**
descobre o motivo. Ela nunca muda o desfecho: se a linha ainda parecer
utilizável, o motivo é `LOST_CONCURRENT_RACE`, porque outra sessão venceu
no intervalo.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import and_, exists, func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.memory.errors.exceptions import (
    ApprovalRecordNotUsableError,
    ApprovalRecordPersistedRowInvalidError,
)
from app.memory.models.approval_lifecycle_enums import (
    ApprovalLifecycleState,
    ApprovalUsageRefusalReason,
    GovernanceItemKind,
)
from app.memory.models.approval_record import (
    ApprovalRecord,
    ApprovalRecordGovernanceItem,
    ApprovalRecordTarget,
)
from app.memory.schemas.destructive_approval import (
    ApprovalContext,
    DestructiveApprovalEnvelope,
    DestructiveApprovalProposal,
    IdentityEvidence,
    PresentedImpact,
    SafeTargetSnapshot,
    SafeVoiceProvenance,
)
from app.memory.schemas.erasure_target import (
    ControlScope,
    CustodyNamespace,
    ReferenceProvenance,
)
from app.memory.schemas.governance import GovernanceResolution
from app.repositories.base_repository import BaseRepository

_TEXTUAIS = {
    GovernanceItemKind.ADMISSIBLE_ALTERNATIVE: "admissible_alternatives",
    GovernanceItemKind.CONSTRAINT: "constraints",
    GovernanceItemKind.DECLARED_PRESERVATION: "declared_preservations",
    GovernanceItemKind.DECLARED_LOSS: "declared_losses",
}
"""Correspondência entre `kind` textual e o campo da resolução.

Fonte única: usada tanto para persistir quanto para reconstruir, de modo
que um `kind` novo sem entrada aqui falha nos dois sentidos em vez de
sumir silenciosamente em um deles.
"""


class ApprovalRecordRepository(BaseRepository[ApprovalRecord]):
    """Aprovação persistente com ciclo de vida de uso único."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ApprovalRecord)

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------

    def append_approved(self, envelope: DestructiveApprovalEnvelope) -> ApprovalRecord:
        """Persiste uma aprovação a partir do **envelope público válido**.

        O nome é deliberado, como `append_observed` na E4.9.5: não é
        `create` nem `save`, porque a pré-condição é ter um envelope que
        já passou por todos os bindings da E4.9.8 e E4.9.8.1.

        Recebe o contrato, nunca um dicionário livre — `**kwargs`
        aceitaria campo desconhecido e, com ele, o campo proibido que este
        modelo existe para não ter.
        """
        if not isinstance(envelope, DestructiveApprovalEnvelope):
            raise TypeError(
                "append_approved exige DestructiveApprovalEnvelope validado — "
                "dicionário livre admitiria campo não declarado"
            )

        proposta = envelope.proposal
        resolucao = proposta.governance_resolution

        registro = ApprovalRecord(
            id=envelope.approval_id,
            nonce=envelope.nonce,
            state=ApprovalLifecycleState.ACTIVE,
            operation=proposta.operation,
            principal_ref=envelope.identity.principal_ref,
            assurance_level=envelope.identity.assurance_level,
            authenticated_at=envelope.identity.authenticated_at,
            tenant_id=envelope.context.tenant_id,
            workspace_id=envelope.context.workspace_id,
            domain_id=envelope.context.domain_id,
            purpose_ref=envelope.context.purpose_ref,
            channel=envelope.provenance.channel,
            voice_review=envelope.provenance.voice_review,
            impact_item_count=proposta.impact.item_count,
            impact_volume_kind=proposta.impact.volume_kind,
            impact_bytes_total=proposta.impact.bytes_total,
            governance_outcome=resolucao.outcome,
            governance_operation=resolucao.operation,
            governance_actor_ref=resolucao.context_actor_ref,
            governance_purpose=resolucao.context_purpose,
            governance_safety_boundary_version=resolucao.safety_boundary_version,
            governance_safety_rationale=resolucao.safety_rationale,
            governance_preserved_intent=resolucao.preserved_intent,
            governance_policy_key=resolucao.policy_key,
            governance_policy_version=resolucao.policy_version,
            governance_policy_id=resolucao.policy_id,
            governance_matched_rule_id=resolucao.matched_rule_id,
            governance_policy_rationale=resolucao.policy_rationale,
            materialized_at=proposta.materialized_at,
            issued_at=envelope.issued_at,
            confirmed_at=envelope.confirmed_at,
            expires_at=envelope.expires_at,
        )
        self._session.add(registro)

        # O lote, na ordem confirmada. `enumerate` sobre a tupla — a ordem
        # vem do contrato, não de uma reordenação de conveniência.
        for posicao, alvo in enumerate(proposta.targets):
            self._session.add(
                ApprovalRecordTarget(
                    approval_record_id=envelope.approval_id,
                    position=posicao,
                    target_class=alvo.target_class,
                    subject_coid=alvo.subject_coid,
                    control_workspace_id=alvo.control_scope.workspace_id,
                    control_tenant_id=alvo.control_scope.tenant_id,
                    control_principal_ref=alvo.control_scope.control_principal_ref,
                    custody_provider=alvo.custody_namespace.provider,
                    custody_namespace=alvo.custody_namespace.namespace,
                    origin_kind=alvo.origin.origin,
                    origin_position=alvo.origin.position,
                    legacy_protection_state=alvo.legacy_protection_state,
                    version_etag=alvo.version_etag,
                )
            )

        for item in self._itens_de_governanca(envelope.approval_id, resolucao):
            self._session.add(item)

        self._session.flush()
        return registro

    @staticmethod
    def _itens_de_governanca(
        approval_id: uuid.UUID, resolucao: GovernanceResolution
    ) -> list[ApprovalRecordGovernanceItem]:
        """As seis tuplas ordenadas, uma linha por elemento."""
        itens: list[ApprovalRecordGovernanceItem] = []
        for posicao, dominio in enumerate(resolucao.context_domain_ids):
            itens.append(
                ApprovalRecordGovernanceItem(
                    approval_record_id=approval_id,
                    kind=GovernanceItemKind.DOMAIN_ID,
                    position=posicao,
                    value_uuid=dominio,
                )
            )
        # `blocked_capabilities` é SEMPRE vazio aqui, e isso é medido, não
        # suposto: a E4.3 recusa `ADMISSIBLE` que carregue capacidade
        # bloqueada — "capacidade bloqueada é a marca da fronteira" — e a
        # proposta da E4.9.8 exige `ADMISSIBLE`.
        #
        # ```text
        # ADMISSIBLE + BLOCKED_CAPABILITIES = UNCONSTRUCTIBLE
        # ```
        #
        # O laço permanece por fidelidade ao contrato: `GovernanceItemKind`
        # cobre as SEIS tuplas da resolução, e omitir uma faria a
        # persistência divergir da fonte se a E4.3 mudar. Fica declarado
        # como inalcançável em vez de coberto por um teste que fabricasse
        # um estado que os construtores públicos recusam.
        for posicao, capacidade in enumerate(
            resolucao.blocked_capabilities
        ):  # pragma: no cover — inalcançável por envelope válido (ver acima)
            itens.append(
                ApprovalRecordGovernanceItem(
                    approval_record_id=approval_id,
                    kind=GovernanceItemKind.BLOCKED_CAPABILITY,
                    position=posicao,
                    value_enum=capacidade,
                )
            )
        for kind, atributo in _TEXTUAIS.items():
            for posicao, texto in enumerate(getattr(resolucao, atributo)):
                itens.append(
                    ApprovalRecordGovernanceItem(
                        approval_record_id=approval_id,
                        kind=kind,
                        position=posicao,
                        value_text=texto,
                    )
                )
        return itens

    # ------------------------------------------------------------------
    # Leitura e reconstituição
    # ------------------------------------------------------------------

    def get_materialized(self, approval_id: uuid.UUID) -> DestructiveApprovalEnvelope | None:
        """Reconstrói o envelope pelos **construtores públicos**.

        ```text
        INVALID_ROW != USABLE_APPROVAL
        ```

        Sem `pickle`, sem `object.__new__`, sem escrita em `__dict__`, sem
        `cast`. Toda invariante da E4.9.8 é reexecutada: se a linha não
        formar contrato válido, a falha é controlada e tipada, e nada
        utilizável sai daqui.
        """
        registro = self._session.get(ApprovalRecord, approval_id)
        if registro is None:
            return None
        return self._reconstruir(registro)

    def _reconstruir(self, registro: ApprovalRecord) -> DestructiveApprovalEnvelope:
        alvos = self._session.scalars(
            select(ApprovalRecordTarget)
            .where(ApprovalRecordTarget.approval_record_id == registro.id)
            .order_by(ApprovalRecordTarget.position)
        ).all()
        itens = self._session.scalars(
            select(ApprovalRecordGovernanceItem)
            .where(ApprovalRecordGovernanceItem.approval_record_id == registro.id)
            .order_by(
                ApprovalRecordGovernanceItem.kind,
                ApprovalRecordGovernanceItem.position,
            )
        ).all()

        try:
            resolucao = self._reconstruir_governanca(registro, itens)
            snapshots = tuple(
                SafeTargetSnapshot(
                    target_class=alvo.target_class,
                    subject_coid=alvo.subject_coid,
                    control_scope=ControlScope(
                        workspace_id=alvo.control_workspace_id,
                        tenant_id=alvo.control_tenant_id,
                        control_principal_ref=alvo.control_principal_ref,
                    ),
                    custody_namespace=CustodyNamespace(
                        provider=alvo.custody_provider,
                        namespace=alvo.custody_namespace,
                    ),
                    origin=ReferenceProvenance(
                        origin=alvo.origin_kind, position=alvo.origin_position
                    ),
                    legacy_protection_state=alvo.legacy_protection_state,
                    version_etag=alvo.version_etag,
                )
                for alvo in alvos
            )
            contexto = ApprovalContext(
                tenant_id=registro.tenant_id,
                workspace_id=registro.workspace_id,
                domain_id=registro.domain_id,
                purpose_ref=registro.purpose_ref,
            )
            proveniencia = SafeVoiceProvenance(
                channel=registro.channel, voice_review=registro.voice_review
            )
            proposta = DestructiveApprovalProposal(
                operation=registro.operation,
                targets=snapshots,
                impact=PresentedImpact(
                    item_count=registro.impact_item_count,
                    volume_kind=registro.impact_volume_kind,
                    bytes_total=registro.impact_bytes_total,
                ),
                governance_resolution=resolucao,
                context=contexto,
                provenance=proveniencia,
                blockers=(),
                materialized_at=registro.materialized_at,
            )
            return DestructiveApprovalEnvelope(
                proposal=proposta,
                approval_id=registro.id,
                nonce=registro.nonce,
                identity=IdentityEvidence(
                    principal_ref=registro.principal_ref,
                    assurance_level=registro.assurance_level,
                    authenticated_at=registro.authenticated_at,
                ),
                context=contexto,
                provenance=proveniencia,
                issued_at=registro.issued_at,
                confirmed_at=registro.confirmed_at,
                expires_at=registro.expires_at,
            )
        except (TypeError, ValueError) as erro:
            raise ApprovalRecordPersistedRowInvalidError(
                registro.id, "envelope", str(erro)
            ) from erro

    @staticmethod
    def _reconstruir_governanca(
        registro: ApprovalRecord,
        itens: Sequence[ApprovalRecordGovernanceItem],
    ) -> GovernanceResolution:
        """Remonta as seis tuplas a partir de `position`.

        O ORM devolve `list`; o contrato exige `tuple`. A conversão é
        explícita aqui — um `list` que escapasse tornaria mutável uma
        coleção que a E4.3 declara imutável.
        """
        por_kind: dict[GovernanceItemKind, list[ApprovalRecordGovernanceItem]] = {
            kind: [] for kind in GovernanceItemKind
        }
        for item in itens:
            por_kind[item.kind].append(item)
        for lista in por_kind.values():
            lista.sort(key=lambda i: i.position)

        dominios = tuple(
            i.value_uuid for i in por_kind[GovernanceItemKind.DOMAIN_ID] if i.value_uuid is not None
        )
        capacidades = tuple(
            i.value_enum
            for i in por_kind[GovernanceItemKind.BLOCKED_CAPABILITY]
            if i.value_enum is not None
        )
        textuais = {
            atributo: tuple(i.value_text for i in por_kind[kind] if i.value_text is not None)
            for kind, atributo in _TEXTUAIS.items()
        }
        return GovernanceResolution(
            outcome=registro.governance_outcome,
            operation=registro.governance_operation,
            context_domain_ids=dominios,
            context_actor_ref=registro.governance_actor_ref,
            context_purpose=registro.governance_purpose,
            safety_boundary_version=registro.governance_safety_boundary_version,
            safety_rationale=registro.governance_safety_rationale,
            blocked_capabilities=capacidades,
            preserved_intent=registro.governance_preserved_intent,
            policy_key=registro.governance_policy_key,
            policy_version=registro.governance_policy_version,
            policy_id=registro.governance_policy_id,
            matched_rule_id=registro.governance_matched_rule_id,
            policy_rationale=registro.governance_policy_rationale,
            **textuais,
        )

    # ------------------------------------------------------------------
    # Ciclo de vida atômico
    # ------------------------------------------------------------------

    def consume_once(self, expected: DestructiveApprovalEnvelope) -> ApprovalRecord:
        """Consome a aprovação **uma vez**, com o binding **completo** no `WHERE`.

        ```text
        PARTIAL_BINDING_MATCH = FORBIDDEN
        FULL_STRUCTURAL_BINDING_IN_ATOMIC_DECISION = REQUIRED
        ```

        O chamador passa o envelope **exato** que acredita estar aprovado.
        Toda coluna escalar de binding entra na condição, e as duas
        tabelas-filhas entram por subconsulta correlacionada com igualdade
        de **cardinalidade, posição, tipo e valor**.

        Verificar parte do binding no `WHERE` e o resto em Python depois
        deixaria aberta a janela entre a decisão e a conferência — e um
        consumo com operação, impacto ou lote diferentes do aprovado é
        exatamente o que o binding existe para impedir.

        Sem JSON e sem digest: a comparação é relacional.

        Levanta `ApprovalRecordNotUsableError` com motivo fechado quando
        não vence.
        """
        return self._transicionar(expected, destino=ApprovalLifecycleState.CONSUMED)

    def revoke_once(self, expected: DestructiveApprovalEnvelope) -> ApprovalRecord:
        """Revoga a aprovação, disputando a **mesma** autoridade de estado.

        ```text
        REVOKED_BEFORE_CONSUMPTION -> NO_CONSUMPTION
        CONSUMED_BEFORE_REVOCATION -> REVOCATION_CANNOT_UNDO_CONSUMPTION
        REVOCATION = DURABLE_TRANSITION_TO_REVOKED, NEVER_ROW_REMOVAL
        ```

        Consumo e revogação concorrentes produzem exatamente um vencedor,
        porque ambos exigem `state = 'ACTIVE'` na mesma linha.

        Mesmo binding completo do consumo — quem retira precisa saber o
        que está retirando.

        **A expiração não entra na condição.** Retirar uma aprovação
        vencida é inócuo, e recusar por vencimento obrigaria o usuário a
        conviver com uma linha que ele já pediu para remover. A revogação
        é transição **durável** para `REVOKED`: a linha permanece, com o
        instante registrado. `DELETE` continua proibido pela trigger.
        """
        return self._transicionar(
            expected,
            destino=ApprovalLifecycleState.REVOKED,
            exigir_nao_vencida=False,
        )

    def _condicoes_de_binding(
        self, expected: DestructiveApprovalEnvelope
    ) -> list[ColumnElement[bool]]:
        """Todas as colunas escalares do binding, na condição do `UPDATE`."""
        proposta = expected.proposal
        resolucao = proposta.governance_resolution
        return [
            ApprovalRecord.id == expected.approval_id,
            ApprovalRecord.nonce == expected.nonce,
            ApprovalRecord.state == ApprovalLifecycleState.ACTIVE,
            # operação e finalidade
            ApprovalRecord.operation == proposta.operation,
            ApprovalRecord.purpose_ref == expected.context.purpose_ref,
            # identidade e assurance
            ApprovalRecord.principal_ref == expected.identity.principal_ref,
            ApprovalRecord.assurance_level == expected.identity.assurance_level,
            ApprovalRecord.authenticated_at == expected.identity.authenticated_at,
            # contexto
            ApprovalRecord.tenant_id == expected.context.tenant_id,
            ApprovalRecord.workspace_id == expected.context.workspace_id,
            ApprovalRecord.domain_id == expected.context.domain_id,
            # canal e revisão de voz
            ApprovalRecord.channel == expected.provenance.channel,
            ApprovalRecord.voice_review == expected.provenance.voice_review,
            # impacto
            ApprovalRecord.impact_item_count == proposta.impact.item_count,
            ApprovalRecord.impact_volume_kind == proposta.impact.volume_kind,
            ApprovalRecord.impact_bytes_total == proposta.impact.bytes_total,
            # governança, campos escalares
            ApprovalRecord.governance_outcome == resolucao.outcome,
            ApprovalRecord.governance_operation == resolucao.operation,
            ApprovalRecord.governance_actor_ref == resolucao.context_actor_ref,
            ApprovalRecord.governance_purpose == resolucao.context_purpose,
            ApprovalRecord.governance_safety_boundary_version == resolucao.safety_boundary_version,
            ApprovalRecord.governance_safety_rationale == resolucao.safety_rationale,
            ApprovalRecord.governance_preserved_intent == resolucao.preserved_intent,
            ApprovalRecord.governance_policy_key == resolucao.policy_key,
            ApprovalRecord.governance_policy_version == resolucao.policy_version,
            ApprovalRecord.governance_policy_id == resolucao.policy_id,
            ApprovalRecord.governance_matched_rule_id == resolucao.matched_rule_id,
            ApprovalRecord.governance_policy_rationale == resolucao.policy_rationale,
            # instantes
            ApprovalRecord.materialized_at == proposta.materialized_at,
            ApprovalRecord.issued_at == expected.issued_at,
            ApprovalRecord.confirmed_at == expected.confirmed_at,
            ApprovalRecord.expires_at == expected.expires_at,
        ]

    def _condicoes_das_filhas(
        self, expected: DestructiveApprovalEnvelope
    ) -> list[ColumnElement[bool]]:
        """Lote e governança por subconsulta **correlacionada**.

        Cardinalidade, posição, tipo e valor — sem JSON, sem digest.

        Duas metades, e as duas são necessárias:

        - cada elemento esperado **existe** na sua posição, com todos os
          campos iguais;
        - a **contagem** confere, senão uma linha a mais no banco passaria
          despercebida por só verificarmos o que esperávamos encontrar.
        """
        proposta = expected.proposal
        resolucao = proposta.governance_resolution
        condicoes: list[ColumnElement[bool]] = []

        for posicao, alvo in enumerate(proposta.targets):
            condicoes.append(
                exists()
                .where(
                    ApprovalRecordTarget.approval_record_id == ApprovalRecord.id,
                    ApprovalRecordTarget.position == posicao,
                    ApprovalRecordTarget.target_class == alvo.target_class,
                    ApprovalRecordTarget.subject_coid == alvo.subject_coid,
                    ApprovalRecordTarget.control_workspace_id == alvo.control_scope.workspace_id,
                    ApprovalRecordTarget.control_tenant_id == alvo.control_scope.tenant_id,
                    ApprovalRecordTarget.control_principal_ref
                    == alvo.control_scope.control_principal_ref,
                    ApprovalRecordTarget.custody_provider == alvo.custody_namespace.provider,
                    ApprovalRecordTarget.custody_namespace == alvo.custody_namespace.namespace,
                    ApprovalRecordTarget.origin_kind == alvo.origin.origin,
                    ApprovalRecordTarget.origin_position == alvo.origin.position,
                    ApprovalRecordTarget.legacy_protection_state == alvo.legacy_protection_state,
                    ApprovalRecordTarget.version_etag == alvo.version_etag,
                )
                .correlate(ApprovalRecord)
            )

        condicoes.append(
            select(func.count())
            .select_from(ApprovalRecordTarget)
            .where(ApprovalRecordTarget.approval_record_id == ApprovalRecord.id)
            .correlate(ApprovalRecord)
            .scalar_subquery()
            == len(proposta.targets)
        )

        esperados: list[tuple[GovernanceItemKind, int, dict[str, object]]] = []
        for posicao, dominio in enumerate(resolucao.context_domain_ids):
            esperados.append((GovernanceItemKind.DOMAIN_ID, posicao, {"value_uuid": dominio}))
        for posicao, capacidade in enumerate(
            resolucao.blocked_capabilities
        ):  # pragma: no cover — ver `_itens_de_governanca`
            esperados.append(
                (
                    GovernanceItemKind.BLOCKED_CAPABILITY,
                    posicao,
                    {"value_enum": capacidade},
                )
            )
        contagens: dict[GovernanceItemKind, int] = {
            GovernanceItemKind.DOMAIN_ID: len(resolucao.context_domain_ids),
            GovernanceItemKind.BLOCKED_CAPABILITY: len(resolucao.blocked_capabilities),
        }
        for kind, atributo in _TEXTUAIS.items():
            valores = getattr(resolucao, atributo)
            contagens[kind] = len(valores)
            for posicao, texto in enumerate(valores):
                esperados.append((kind, posicao, {"value_text": texto}))

        for kind, posicao, valor in esperados:
            (coluna, conteudo) = next(iter(valor.items()))
            condicoes.append(
                exists()
                .where(
                    ApprovalRecordGovernanceItem.approval_record_id == ApprovalRecord.id,
                    ApprovalRecordGovernanceItem.kind == kind,
                    ApprovalRecordGovernanceItem.position == posicao,
                    getattr(ApprovalRecordGovernanceItem, coluna) == conteudo,
                )
                .correlate(ApprovalRecord)
            )

        for kind, quantidade in contagens.items():
            condicoes.append(
                select(func.count())
                .select_from(ApprovalRecordGovernanceItem)
                .where(
                    ApprovalRecordGovernanceItem.approval_record_id == ApprovalRecord.id,
                    ApprovalRecordGovernanceItem.kind == kind,
                )
                .correlate(ApprovalRecord)
                .scalar_subquery()
                == quantidade
            )

        return condicoes

    def _transicionar(
        self,
        expected: DestructiveApprovalEnvelope,
        *,
        destino: ApprovalLifecycleState,
        exigir_nao_vencida: bool = True,
    ) -> ApprovalRecord:
        if not isinstance(expected, DestructiveApprovalEnvelope):
            raise TypeError(
                "a transição exige DestructiveApprovalEnvelope — o binding "
                "completo não se expressa em argumentos soltos"
            )

        approval_id = expected.approval_id
        agora = func.clock_timestamp()
        condicoes = self._condicoes_de_binding(expected)
        condicoes.extend(self._condicoes_das_filhas(expected))
        if exigir_nao_vencida:
            condicoes.append(ApprovalRecord.expires_at > agora)

        valores: dict[str, object] = {"state": destino}
        valores["consumed_at" if destino is ApprovalLifecycleState.CONSUMED else "revoked_at"] = (
            agora
        )

        resultado = self._session.execute(
            update(ApprovalRecord)
            .where(and_(*condicoes))
            .values(**valores)
            .returning(ApprovalRecord.id)
        )
        if resultado.scalar_one_or_none() is None:
            raise ApprovalRecordNotUsableError(
                approval_id, self._diagnosticar(approval_id, exigir_nao_vencida)
            )

        self._session.flush()
        registro = self._session.get(ApprovalRecord, approval_id)
        if registro is None:  # pragma: no cover — a linha acabou de ser escrita
            raise ApprovalRecordNotUsableError(approval_id, ApprovalUsageRefusalReason.NOT_FOUND)
        return registro

    def _diagnosticar(
        self, approval_id: uuid.UUID, exigir_nao_vencida: bool
    ) -> ApprovalUsageRefusalReason:
        """Descobre **por que** o comando não venceu, sem alterar o desfecho.

        ```text
        DIAGNOSTIC_READ_NEVER_CONVERTS_DEFEAT_INTO_SUCCESS
        ```

        Se a linha ainda parecer utilizável, o motivo é `BINDING_MISMATCH`
        ou corrida perdida — nunca "estava tudo bem".
        """
        registro = self._session.get(ApprovalRecord, approval_id)
        if registro is None:
            return ApprovalUsageRefusalReason.NOT_FOUND
        if registro.state is ApprovalLifecycleState.CONSUMED:
            return ApprovalUsageRefusalReason.ALREADY_CONSUMED
        if registro.state is ApprovalLifecycleState.REVOKED:
            return ApprovalUsageRefusalReason.REVOKED

        vencida = bool(
            self._session.execute(
                select(ApprovalRecord.id).where(
                    ApprovalRecord.id == approval_id,
                    ApprovalRecord.expires_at <= func.clock_timestamp(),
                )
            ).scalar_one_or_none()
        )
        if exigir_nao_vencida and vencida:
            return ApprovalUsageRefusalReason.EXPIRED
        return ApprovalUsageRefusalReason.BINDING_MISMATCH
