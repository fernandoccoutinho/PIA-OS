"""
Único caminho de leitura/escrita do evento de proteção humana (`E7.4-1 B1a`).

```text
PERSISTENCE_ONLY_THROUGH_REPOSITORY = TRUE
IDEMPOTENT_WRITE_ACROSS_TWO_TABLES = READ_THE_WINNER_AND_VERIFY
```

## Por que o perdedor da corrida é lido e comparado

`ON CONFLICT DO NOTHING` sozinho diz apenas que **alguma** linha já ocupa a
chave. Não diz que ela descreve a mesma aplicação. Duas transações podem
disputar `(fingerprint, gate, binding)` carregando efeitos diferentes — e
aceitar a primeira delas em silêncio seria dar por registrada uma aplicação
que nunca ocorreu.

```text
WINNER_VERIFIED_BY_CAPABILITIES_ONLY = UNVERIFIED_APPLICATION
DIVERGENT_WINNER = TECHNICAL_FAILURE, nunca "já estava lá"
```

A comparação percorre os dezenove campos imutáveis **derivados do dataclass**
(`CAMPOS_IMUTAVEIS_DA_APLICACAO`) e a tupla ordenada de capacidades. Divergiu,
levanta `PIA-8069`: falha técnica, zero efeito, nunca permissão.

## Onde a transação começa e termina

O repositório **não** commita e não faz `rollback` da transação externa: a
`UnitOfWork` é a dona. A tentativa de inserção corre dentro de um
`begin_nested()` — o `SAVEPOINT` desfaz apenas o `INSERT` perdedor, e a
transação do chamador continua exatamente como estava. Correção medida na
auditoria da cadeia 96 (`SAVEPOINT_SCOPE != TRANSACTION_SCOPE`).

Nenhum `event_id` é derivado de hash: UUID fabricado a partir de conteúdo faz
duas aplicações distintas colidirem por construção.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.orchestration.errors.exceptions import HumanProtectionGateUnavailableError
from app.orchestration.models.human_protection_event import (
    UQ_IDEMPOTENCIA,
    HumanProtectionEvent,
)
from app.orchestration.models.human_protection_event_capability import (
    HumanProtectionEventCapability,
)
from app.orchestration.ports.governance_vocabulary import (
    BoundaryCapability,
    BoundaryEngagement,
    BoundaryOperation,
)
from app.orchestration.protection.decision import (
    CAMPOS_IMUTAVEIS_DA_APLICACAO,
    HumanProtectionApplication,
)
from app.orchestration.protection.vocabulary import GatePosition, ProtectionOutcome

_CHAVE_DE_IDEMPOTENCIA = ("decision_fingerprint", "gate_position", "binding_sha256")


class HumanProtectionRepository:
    """Escrita idempotente do par evento/capacidades e leitura do vencedor."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # --- escrita ----------------------------------------------------------

    def inserir_se_ausente(self, aplicacao: HumanProtectionApplication) -> uuid.UUID | None:
        """Insere evento e capacidades; devolve `None` se outro venceu.

        As duas tabelas são escritas na mesma transação e no mesmo
        `SAVEPOINT`. A coerência entre elas não é conferida aqui: os
        constraint triggers diferidos a avaliam no `COMMIT`, e reimplementá-la
        em Python criaria a segunda fonte de verdade que a E4.5.1 já provou
        divergir.
        """
        valores = self._valores(aplicacao)
        with self._session.begin_nested():
            criado = self._session.execute(
                pg_insert(HumanProtectionEvent)
                .values(**valores)
                .on_conflict_do_nothing(index_elements=list(_CHAVE_DE_IDEMPOTENCIA))
                .returning(HumanProtectionEvent.id)
            ).scalar_one_or_none()

            if criado is None:
                return None

            if aplicacao.blocked_capabilities:
                self._session.execute(
                    sa.insert(HumanProtectionEventCapability),
                    [
                        {
                            "event_id": criado,
                            "ordinal": posicao,
                            "critical_capability": capacidade.value,
                        }
                        for posicao, capacidade in enumerate(aplicacao.blocked_capabilities)
                    ],
                )
        return criado

    @staticmethod
    def _valores(aplicacao: HumanProtectionApplication) -> dict[str, object]:
        """Converte o value object tipado nas colunas, por VALOR.

        `id` é gerado aqui, e não derivado do conteúdo: dois fatos distintos
        precisam poder existir, e um identificador calculado por hash os
        fundiria.
        """
        engajamento = aplicacao.capability_engagement
        return {
            "id": uuid.uuid4(),
            "control_principal_ref": aplicacao.control_principal_ref,
            "schedule_id": aplicacao.schedule_id,
            "step_id": aplicacao.step_id,
            "attempt_id": aplicacao.attempt_id,
            "binding_attempt_id": aplicacao.binding_attempt_id,
            "objective_sha256": aplicacao.objective_sha256,
            "decision_fingerprint": aplicacao.decision_fingerprint,
            "fingerprint_algo_version": aplicacao.fingerprint_algo_version,
            "binding_sha256": aplicacao.binding_sha256,
            "binding_algo_version": aplicacao.binding_algo_version,
            "outcome": aplicacao.outcome.value,
            "capability_engagement": None if engajamento is None else engajamento.value,
            "boundary_version": aplicacao.boundary_version,
            "classifier_version": aplicacao.classifier_version,
            "cognitive_operation": aplicacao.cognitive_operation.value,
            "gate_position": aplicacao.gate_position.value,
            "producer_ref": aplicacao.producer_ref,
            "pause_applied": aplicacao.pause_applied,
            "delegations_revoked": aplicacao.delegations_revoked,
        }

    # --- leitura ----------------------------------------------------------

    def ler_aplicacao(
        self, *, decision_fingerprint: str, gate_position: GatePosition, binding_sha256: str
    ) -> HumanProtectionApplication | None:
        """Lê a linha da chave e a devolve como value object.

        As colunas são extraídas **dentro** da sessão e o retorno é um
        dataclass congelado: conservar a entidade ORM além do fim da
        `UnitOfWork` dá `DetachedInstanceError`, defeito reincidente desde a
        E4.5 e com teste de regressão próprio desde a E7.1.
        """
        linha = self._session.execute(
            sa.select(HumanProtectionEvent).where(
                HumanProtectionEvent.decision_fingerprint == decision_fingerprint,
                HumanProtectionEvent.gate_position == gate_position.value,
                HumanProtectionEvent.binding_sha256 == binding_sha256,
            )
        ).scalar_one_or_none()
        if linha is None:
            return None

        capacidades = self._session.execute(
            sa.select(HumanProtectionEventCapability.critical_capability)
            .where(HumanProtectionEventCapability.event_id == linha.id)
            .order_by(HumanProtectionEventCapability.ordinal)
        ).scalars()

        engajamento = linha.capability_engagement
        return HumanProtectionApplication(
            control_principal_ref=linha.control_principal_ref,
            schedule_id=linha.schedule_id,
            step_id=linha.step_id,
            attempt_id=linha.attempt_id,
            binding_attempt_id=linha.binding_attempt_id,
            objective_sha256=linha.objective_sha256,
            decision_fingerprint=linha.decision_fingerprint,
            fingerprint_algo_version=linha.fingerprint_algo_version,
            binding_sha256=linha.binding_sha256,
            binding_algo_version=linha.binding_algo_version,
            outcome=ProtectionOutcome(linha.outcome),
            capability_engagement=(
                None if engajamento is None else BoundaryEngagement(engajamento)
            ),
            boundary_version=linha.boundary_version,
            classifier_version=linha.classifier_version,
            cognitive_operation=BoundaryOperation(linha.cognitive_operation),
            gate_position=GatePosition(linha.gate_position),
            producer_ref=linha.producer_ref,
            pause_applied=linha.pause_applied,
            delegations_revoked=linha.delegations_revoked,
            blocked_capabilities=tuple(BoundaryCapability(valor) for valor in capacidades),
        )

    # --- verificação do vencedor ------------------------------------------

    def confirmar_vencedor(self, aplicacao: HumanProtectionApplication) -> None:
        """Exige que o vencedor da corrida descreva ESTA mesma aplicação.

        Qualquer divergência — inclusive na tupla de capacidades — é falha
        técnica, e não idempotência satisfeita.
        """
        vencedor = self.ler_aplicacao(
            decision_fingerprint=aplicacao.decision_fingerprint,
            gate_position=aplicacao.gate_position,
            binding_sha256=aplicacao.binding_sha256,
        )
        if vencedor is None:
            raise HumanProtectionGateUnavailableError(
                f"conflito em {UQ_IDEMPOTENCIA} sem linha legível para a chave — "
                "o gate não pode confirmar a aplicação registrada"
            )

        divergentes = [
            campo
            for campo in CAMPOS_IMUTAVEIS_DA_APLICACAO
            if getattr(vencedor, campo) != getattr(aplicacao, campo)
        ]
        if vencedor.blocked_capabilities != aplicacao.blocked_capabilities:
            divergentes.append("blocked_capabilities")
        if divergentes:
            raise HumanProtectionGateUnavailableError(
                "evento concorrente descreve outra aplicação para a mesma chave; "
                f"campos divergentes: {sorted(divergentes)}"
            )
