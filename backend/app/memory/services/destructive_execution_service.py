"""
`DestructiveExecutionService` — a composição final da E4.9 (`E4.9.9.d`).

```text
aprovação persistida
→ re-resolução fresca e observacional
→ comparação com o snapshot aprovado
→ consumo durável e atômico
→ tentativa pela porta de efeito
→ recibo somente após tentativa material observada
```

Este é o primeiro consumidor de produção de `resolve_target`,
`consume_once`, `attempt_effect` e `append_observed`. Até aqui os quatro
contratos existiam sem chamador, e isso era o estado correto: compor um
escritor de recibo antes de existir resolvedor, aprovação e efeito
criaria um caminho capaz de fabricar recibos de apagamentos que nunca
aconteceram.

## O que este serviço **não** é

```text
PRODUCTION_EFFECT_ADAPTER = NONE
AUTHENTICATOR = NONE
PUBLIC_API = NONE
REAL_USER_FILE_ERASURE = NOT_EXECUTED
```

Nenhum adaptador concreto de storage, conector, autenticador, endpoint,
worker, scheduler, fila, outbox ou saga existe no repositório. O serviço
recebe portas injetadas e não sabe implementá-las.

```text
INTERNAL_COMPOSITION_COMPLETE != PRODUCTION_DELETION_AVAILABLE
```

## At-most-once, declarado e não disfarçado

```text
CONSUMPTION_COMMITTED_BEFORE_EFFECT = REQUIRED
CRASH_AFTER_CONSUMPTION_MAY_BURN_APPROVAL = DECLARED
CRASH_DURING_EFFECT_MAY_LEAVE_UNKNOWN_STATE = DECLARED
REPLAY_WITH_SAME_APPROVAL = REFUSED
```

Efeito externo e banco **não** são atomicamente transacionais, e não há
tentativa de fingir que são. O consumo commita **antes** do efeito
porque a falha aceitável é queimar uma aprovação sem apagar nada; a
inaceitável é apagar e não ter registro de que a autorização foi usada.

## Retenção informa, não autoriza

```text
RETENTION_ASSESSMENT != DELETION_AUTHORITY
LEGACY_PROTECTION = USER_BINDING, NOT AUTOMATIC_EFFECT
```

`avaliar_retencao` **não** é chamado aqui, e a ausência é a garantia.
Acoplá-lo ao executor o transformaria numa segunda autorização, e a
autoridade continua sendo a aprovação humana. A avaliação é etapa
anterior, de informação.
"""

import uuid
from collections.abc import Callable

from app.memory.errors.exceptions import (
    ApprovalRecordNotUsableError,
    ApprovalRecordPersistedRowInvalidError,
    DestructiveExecutionAdapterContractViolationError,
    DestructiveExecutionUnknownMaterialStateError,
    ErasureReceiptNotPersistedError,
)
from app.memory.models.approval_enums import DestructiveOperation
from app.memory.models.destructive_execution_enums import (
    AdapterContractViolation,
    PreConsumptionRefusalReason,
    SnapshotDivergenceField,
)
from app.memory.ports.erasure_effect import ErasureEffectPort
from app.memory.ports.erasure_target import ErasureTargetResolverPort
from app.memory.repositories.approval_record_repository import ApprovalRecordRepository
from app.memory.repositories.erasure_record_repository import ErasureRecordRepository
from app.memory.schemas.destructive_approval import SafeTargetSnapshot
from app.memory.schemas.destructive_execution import (
    ApprovalConsumptionRefusal,
    DestructiveExecutionReport,
    DestructiveExecutionRequest,
    DestructiveExecutionResult,
    GovernanceProvenance,
    PartialExecutionEvidence,
    PreConsumptionRefusal,
    TargetAttempted,
    TargetExecutionOutcome,
    TargetNotAttempted,
    referencia_de_resolucao_de_governanca,
)
from app.memory.schemas.erasure_effect import (
    ConsumedApprovalEvidence,
    ErasureEffectRequest,
    MaterialAttemptNotStarted,
    ObservedAttemptResult,
)
from app.memory.schemas.erasure_record import ErasureRecordAppend
from app.memory.schemas.erasure_target import (
    ErasureTargetDescriptor,
    ErasureTargetReference,
    TargetResolutionRefusal,
)
from app.memory.schemas.governance import GovernanceResolution
from app.repositories.exceptions import TransactionError
from app.repositories.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]
"""Como o serviço abre cada transação.

Fábrica, e não `UnitOfWork` já aberta: o serviço abre **três** escopos
transacionais distintos — o consumo e um por recibo —, e receber uma
transação pronta faria os três virarem um só. O commit do consumo
arrastaria os recibos, e a ordem que esta fatia existe para provar
deixaria de ser observável.
"""

CAMPOS_DO_BINDING: tuple[tuple[SnapshotDivergenceField, str], ...] = (
    (SnapshotDivergenceField.TARGET_CLASS, "target_class"),
    (SnapshotDivergenceField.SUBJECT_COID, "subject_coid"),
    (SnapshotDivergenceField.CONTROL_SCOPE, "control_scope"),
    (SnapshotDivergenceField.CUSTODY_NAMESPACE, "custody_namespace"),
    (SnapshotDivergenceField.ORIGIN, "origin"),
    (SnapshotDivergenceField.LEGACY_PROTECTION_STATE, "legacy_protection_state"),
    (SnapshotDivergenceField.VERSION_ETAG, "version_etag"),
)
"""Os sete campos comparados, em ordem fixa e **enumerados literalmente**.

`dataclasses.fields` daria a mesma lista hoje e mudaria sozinho amanhã:
um campo novo em `SafeTargetSnapshot` entraria na comparação sem que
ninguém decidisse, e um campo removido sairia dela em silêncio. A
enumeração literal segue o precedente do `EMPTY_OPERATIONS_SCOPE_V1` da
E4.3.3, e uma guarda estática fixa esta lista contra os campos reais do
snapshot.
"""


class DestructiveExecutionService:
    """Compõe os contratos aprovados da E4.9 — e nada além deles.

    Todas as dependências são **injetadas**. Nenhum singleton global,
    nenhuma sessão importada de módulo, nenhuma fábrica escondida: um
    serviço que instanciasse a própria `Session` tornaria impossível
    provar, no teste, que o consumo commitou antes do efeito.

    Os repositórios são instanciados **dentro** de cada `UnitOfWork`,
    sobre a sessão daquela transação. Compartilhar um repositório entre
    transações compartilharia a sessão, e o commit de uma escreveria a
    outra.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        target_resolver: ErasureTargetResolverPort,
        effect_port: ErasureEffectPort,
    ) -> None:
        if not callable(unit_of_work_factory):
            raise TypeError(
                "unit_of_work_factory deve ser chamável — o serviço abre uma "
                "transação por fase e não pode receber uma já aberta"
            )
        if not isinstance(target_resolver, ErasureTargetResolverPort):
            raise TypeError(
                "target_resolver deve satisfazer ErasureTargetResolverPort — "
                "RUNTIME_CHECKABLE != SIGNATURE_PROOF, e a assinatura é provada "
                "estaticamente pelo mypy"
            )
        if not isinstance(effect_port, ErasureEffectPort):
            raise TypeError("effect_port deve satisfazer ErasureEffectPort")
        self._unit_of_work_factory = unit_of_work_factory
        self._target_resolver = target_resolver
        self._effect_port = effect_port

    # ------------------------------------------------------------------
    # Fluxo canônico
    # ------------------------------------------------------------------

    def execute(self, request: DestructiveExecutionRequest) -> DestructiveExecutionResult:
        """Executa a ordem canônica A → B → C, e para no primeiro impedimento.

        ```text
        A  resolver todos e comparar os sete campos    sem escrita alguma
        B  consume_once em UoW exclusivo e COMMIT      antes de qualquer efeito
        C  attempt_effect por alvo                     recibo só após observação
        ```

        As três fases vivem nesta função de propósito: `commit()` precede
        `attempt_effect` **lexical e estruturalmente**, e essa ordem é a
        garantia central da fatia. Distribuí-la entre helpers tornaria a
        precedência verificável só por leitura de várias funções, e uma
        guarda estática mede o que está escrito aqui.
        """
        if not isinstance(request, DestructiveExecutionRequest):
            raise TypeError(
                f"execute exige DestructiveExecutionRequest validado, recebido "
                f"{type(request).__name__} — dicionário livre admitiria campo "
                "não declarado"
            )

        envelope = request.envelope
        operacao = request.operation
        aprovados = envelope.proposal.targets

        # ---------- Fase A — pré-consumo, sem escrita ----------
        recusa = self._validar_lote(request, aprovados)
        if recusa is not None:
            return recusa
        proveniencia = self._proveniencia(envelope.proposal.governance_resolution)
        if proveniencia is None:  # pragma: no cover - `_validar_lote` já recusou
            raise ApprovalRecordPersistedRowInvalidError(
                request.approval_id,
                "governance_resolution",
                "proveniência de governança incompleta após a validação do lote",
            )

        frescos: list[ErasureTargetDescriptor] = []
        for posicao, referencia in enumerate(request.references):
            resultado = self._target_resolver.resolve_target(referencia)
            if isinstance(resultado, TargetResolutionRefusal):
                return PreConsumptionRefusal(
                    approval_id=request.approval_id,
                    operation=operacao,
                    reason=PreConsumptionRefusalReason.TARGET_RESOLUTION_REFUSED,
                    position=posicao,
                    resolution_refusal=resultado.reason,
                )
            fresco = SafeTargetSnapshot.from_descriptor(resultado)
            divergente = self._comparar(fresco, aprovados[posicao])
            if divergente is not None:
                return PreConsumptionRefusal(
                    approval_id=request.approval_id,
                    operation=operacao,
                    reason=PreConsumptionRefusalReason.FRESH_SNAPSHOT_DIVERGED,
                    position=posicao,
                    diverged_field=divergente,
                )
            frescos.append(resultado)

        # ---------- Fase B — consumo durável ----------
        with self._unit_of_work_factory() as uow:
            try:
                registro = ApprovalRecordRepository(uow.session).consume_once(envelope)
            except ApprovalRecordNotUsableError as exc:
                return ApprovalConsumptionRefusal(
                    approval_id=request.approval_id,
                    operation=operacao,
                    reason=exc.reason,
                )
            uow.commit()
            consumido_em = registro.consumed_at

        if consumido_em is None:  # pragma: no cover — a trigger impede a transição vazia
            raise ApprovalRecordPersistedRowInvalidError(
                request.approval_id,
                "consumed_at",
                "transição para CONSUMED sem instante de consumo",
            )

        autorizacao = ConsumedApprovalEvidence(
            approval_id=request.approval_id,
            operation=operacao,
            tenant_id=envelope.context.tenant_id,
            workspace_id=envelope.context.workspace_id,
            principal_ref=envelope.identity.principal_ref,
            consumed_at=consumido_em,
        )

        # ---------- Fase C — efeito e recibo ----------
        desfechos: list[TargetExecutionOutcome] = []
        for posicao, descritor in enumerate(frescos):
            pedido = ErasureEffectRequest(descriptor=descritor, authorization=autorizacao)
            try:
                observado = self._effect_port.attempt_effect(pedido)
            except Exception as exc:
                raise DestructiveExecutionUnknownMaterialStateError(
                    self._evidencia_parcial(request.approval_id, posicao, descritor, desfechos)
                ) from exc

            self._verificar_correspondencia(request, posicao, descritor, observado, desfechos)

            if isinstance(observado, MaterialAttemptNotStarted):
                desfechos.append(
                    TargetNotAttempted(
                        position=posicao,
                        subject_coid=observado.subject_coid,
                        reason=observado.reason,
                        observed_at=observado.observed_at,
                    )
                )
                continue

            try:
                recibo_id = self._registrar_recibo(observado, operacao, proveniencia)
            except TransactionError as exc:
                # `AGGREGATE_LISTS_ONLY_COMMITTED_RECEIPTS`. Nenhum
                # `TargetAttempted` é construído: o efeito ocorreu, a
                # evidência não ficou, e o erro diz as duas coisas sem
                # alegar recibo nem desfazer o efeito no papel.
                raise ErasureReceiptNotPersistedError(
                    observado.outcome,
                    self._evidencia_parcial(request.approval_id, posicao, descritor, desfechos),
                ) from exc
            desfechos.append(
                TargetAttempted(
                    position=posicao,
                    subject_coid=observado.subject_coid,
                    target_class=observado.target_class,
                    outcome=observado.outcome,
                    erasure_record_id=recibo_id,
                    attempted_at=observado.attempted_at,
                    completed_at=observado.completed_at,
                )
            )

        return DestructiveExecutionReport(
            approval_id=request.approval_id,
            operation=operacao,
            consumed_at=consumido_em,
            targets=tuple(desfechos),
        )

    # ------------------------------------------------------------------
    # Fase A — validação e comparação
    # ------------------------------------------------------------------

    def _validar_lote(
        self,
        request: DestructiveExecutionRequest,
        aprovados: tuple[SafeTargetSnapshot, ...],
    ) -> PreConsumptionRefusal | None:
        """Cardinalidade, duplicata, correspondência posicional e governança."""
        operacao = request.operation
        if len(request.references) != len(aprovados):
            return PreConsumptionRefusal(
                approval_id=request.approval_id,
                operation=operacao,
                reason=PreConsumptionRefusalReason.BATCH_CARDINALITY_MISMATCH,
            )

        vistos: set[uuid.UUID] = set()
        for posicao, referencia in enumerate(request.references):
            if referencia.subject_coid in vistos:
                return PreConsumptionRefusal(
                    approval_id=request.approval_id,
                    operation=operacao,
                    reason=PreConsumptionRefusalReason.DUPLICATE_SUBJECT_IN_BATCH,
                    position=posicao,
                )
            vistos.add(referencia.subject_coid)
            if not self._referencia_corresponde(referencia, aprovados[posicao]):
                return PreConsumptionRefusal(
                    approval_id=request.approval_id,
                    operation=operacao,
                    reason=PreConsumptionRefusalReason.REFERENCE_DOES_NOT_MATCH_APPROVED_TARGET,
                    position=posicao,
                )

        if self._proveniencia(request.envelope.proposal.governance_resolution) is None:
            return PreConsumptionRefusal(
                approval_id=request.approval_id,
                operation=operacao,
                reason=PreConsumptionRefusalReason.GOVERNANCE_PROVENANCE_INCOMPLETE,
            )
        return None

    @staticmethod
    def _referencia_corresponde(
        referencia: ErasureTargetReference, aprovado: SafeTargetSnapshot
    ) -> bool:
        """A referência descreve o alvo aprovado **desta** posição?

        Compara sujeito, origem, controle e — quando presente — o
        namespace esperado. `expected_namespace=None` é legítimo: a maior
        parte das referências da E3 não diz onde o conteúdo vive, e exigir
        que dissesse recusaria lotes válidos.

        Localizador e capacidade não entram: a referência não os tem, e o
        snapshot aprovado também não.
        """
        if referencia.subject_coid != aprovado.subject_coid:
            return False
        if referencia.origin != aprovado.origin:
            return False
        if referencia.control_scope != aprovado.control_scope:
            return False
        if referencia.expected_namespace is None:
            return True
        return referencia.expected_namespace == aprovado.custody_namespace

    @staticmethod
    def _comparar(
        fresco: SafeTargetSnapshot, aprovado: SafeTargetSnapshot
    ) -> SnapshotDivergenceField | None:
        """Igualdade estrutural nos sete campos, nos **dois** sentidos.

        ```text
        FRESH_DESCRIPTOR != APPROVED_SNAPSHOT -> NO_CONSUMPTION
        LEGACY_PROTECTED_CHANGED_IN_EITHER_DIRECTION -> NO_CONSUMPTION
        ```

        A comparação é por igualdade exata de cada campo, e nenhuma
        direção é privilegiada: `NOT_PROTECTED → PROTECTED` e
        `PROTECTED → NOT_PROTECTED` divergem igualmente. Um `!=` sobre o
        objeto inteiro daria o mesmo veredito, mas não diria **qual**
        campo mudou, e a recusa precisa dizer.
        """
        for rotulo, atributo in CAMPOS_DO_BINDING:
            if getattr(fresco, atributo) != getattr(aprovado, atributo):
                return rotulo
        return None

    @staticmethod
    def _proveniencia(resolucao: GovernanceResolution) -> GovernanceProvenance | None:
        """Estreita as quatro fontes, ou devolve `None`.

        ```text
        MISSING_GOVERNANCE_PROVENANCE -> REFUSE_BEFORE_EFFECT
        NEVER_COMPLETE_WITH_DEFAULT
        ```

        Os quatro campos são opcionais no tipo da E4.3 e obrigatórios
        aqui, porque o recibo os cita. Completar qualquer um com default
        gravaria uma proveniência que ninguém aplicou — e o recibo é
        append-only: uma citação errada não se corrige depois.

        Devolve um **tipo estreitado**, e não um booleano: um predicado
        deixaria os quatro campos opcionais na hora de montar o recibo, e
        fechar isso exigiria `cast` ou `type: ignore`. O estreitamento
        vive no tipo.
        """
        if (
            resolucao.policy_id is None
            or resolucao.policy_key is None
            or resolucao.policy_version is None
            or resolucao.matched_rule_id is None
        ):
            return None
        return GovernanceProvenance(
            policy_id=resolucao.policy_id,
            policy_key=resolucao.policy_key,
            policy_version=resolucao.policy_version,
            matched_rule_id=resolucao.matched_rule_id,
        )

    # ------------------------------------------------------------------
    # Fase C — correspondência, recibo e evidência parcial
    # ------------------------------------------------------------------

    def _verificar_correspondencia(
        self,
        request: DestructiveExecutionRequest,
        posicao: int,
        descritor: ErasureTargetDescriptor,
        observado: MaterialAttemptNotStarted | ObservedAttemptResult,
        desfechos: list[TargetExecutionOutcome],
    ) -> None:
        """O resultado devolvido descreve **este** pedido?

        Aprovação e sujeito são exigidos dos dois desfechos; a classe do
        alvo só existe quando houve tentativa observada, e cobrá-la de uma
        não-tentativa seria cobrar informação que o tipo não carrega.
        """
        violacao: AdapterContractViolation | None = None
        if observado.approval_id != request.approval_id:
            violacao = AdapterContractViolation.APPROVAL_MISMATCH
        elif observado.subject_coid != descritor.subject_coid:
            violacao = AdapterContractViolation.SUBJECT_MISMATCH
        elif (
            isinstance(observado, ObservedAttemptResult)
            and observado.target_class is not descritor.target_class
        ):
            violacao = AdapterContractViolation.TARGET_CLASS_MISMATCH
        if violacao is None:
            return
        raise DestructiveExecutionAdapterContractViolationError(
            violacao,
            self._evidencia_parcial(request.approval_id, posicao, descritor, desfechos),
        )

    def _registrar_recibo(
        self,
        observado: ObservedAttemptResult,
        operacao: DestructiveOperation,
        proveniencia: GovernanceProvenance,
    ) -> uuid.UUID:
        """Grava **um** recibo, em `UnitOfWork` próprio, e commita.

        ```text
        OBSERVED_ATTEMPT -> EXACTLY_ONE_ERASURE_RECORD
        ```

        Transação própria por alvo, commitada imediatamente após o
        resultado observado. Acumular recibos numa transação única faria
        uma falha no último alvo descartar os recibos dos anteriores — e
        apagamentos que já ocorreram ficariam sem registro.

        O trio de retenção é `NULL` nesta composição: a avaliação de
        retenção **informa** e não autoriza, e citá-la aqui sugeriria que
        o vencimento fundamentou o apagamento.
        """
        entrada = ErasureRecordAppend(
            subject_identifier=str(observado.subject_coid),
            target_class=observado.target_class,
            scope_token=operacao.value,
            outcome=observado.outcome,
            governance_policy_id=proveniencia.policy_id,
            governance_policy_key=proveniencia.policy_key,
            governance_policy_version=proveniencia.policy_version,
            governance_rule_id=proveniencia.matched_rule_id,
            governance_resolution_ref=referencia_de_resolucao_de_governanca(observado.approval_id),
            approval_ref=str(observado.approval_id),
            executor_ref=observado.executor_ref,
            attempted_at=observado.attempted_at,
            completed_at=observado.completed_at,
            failure_code=observado.failure_code,
        )
        with self._unit_of_work_factory() as uow:
            recibo = ErasureRecordRepository(uow.session).append_observed(entrada)
            uow.commit()
            return recibo.id

    @staticmethod
    def _evidencia_parcial(
        approval_id: uuid.UUID,
        posicao: int,
        descritor: ErasureTargetDescriptor,
        desfechos: list[TargetExecutionOutcome],
    ) -> PartialExecutionEvidence:
        """Quanto já era **fato** antes da ambiguidade.

        Conta o que foi confirmado; nada é inferido sobre o alvo em que o
        estado ficou desconhecido.
        """
        observados = [alvo for alvo in desfechos if isinstance(alvo, TargetAttempted)]
        return PartialExecutionEvidence(
            approval_id=approval_id,
            failed_position=posicao,
            subject_coid=descritor.subject_coid,
            attempts_observed=len(observados),
            receipts_persisted=len(observados),
            targets_not_attempted=len(desfechos) - len(observados),
        )
