"""
`ErasureRecordRepository` — persistência append-only do recibo (`E4.9.5`).

Camada 2 de 3 da imutabilidade. A camada 1 são os eventos de mapper; a
camada 3 é a trigger no PostgreSQL, única que vale em SQL bruto.

**Este repositório não é composto por nenhum serviço.** Não há
produtor, orquestrador ou manager que o chame — por desenho:

```text
ERASURE_RECORD_RUNTIME_WRITER = NOT_COMPOSED
ERASURE_EFFECT = NONE
```

Compor o escritor antes de existir executor, resolvedor de alvo,
identidade e aprovação criaria um caminho capaz de fabricar recibos de
apagamentos que nunca aconteceram — que é a única coisa pior do que
não ter recibo nenhum.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.memory.errors.exceptions import ErasureRecordImmutableError
from app.memory.models.erasure_enums import ErasureOutcome
from app.memory.models.erasure_record import ErasureRecord
from app.memory.schemas.erasure_record import ErasureRecordAppend
from app.repositories.base_repository import BaseRepository

_DEFAULT_LIMIT = 50
"""Teto padrão das listagens. Consulta sem limite acabaria varrendo o
histórico inteiro de apagamentos numa única resposta."""


class ErasureRecordRepository(BaseRepository[ErasureRecord]):
    """Append e consulta de recibos. Nunca update, delete ou soft delete."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ErasureRecord)

    def append_observed(self, entrada: ErasureRecordAppend) -> ErasureRecord:
        """Registra uma tentativa **já observada**.

        O nome é deliberado. `create` ou `save` não diriam nada sobre a
        pré-condição; `append_observed` diz que o chamador precisa ter
        observado a tentativa material antes de chamar.

        Recebe entidade validada, nunca dicionário livre: um `**kwargs`
        aceitaria campo desconhecido e, com ele, o campo livre que este
        modelo existe para não ter.

        ```text
        NO_RECORD_BEFORE_OBSERVED_ATTEMPT
        NO_SUCCEEDED_WITHOUT_OBSERVED_EFFECT
        ```
        """
        if not isinstance(entrada, ErasureRecordAppend):
            raise TypeError(
                "append_observed exige ErasureRecordAppend validado — "
                "dicionário livre admitiria campo não declarado"
            )

        entity = ErasureRecord(
            subject_identifier=entrada.subject_identifier,
            target_class=entrada.target_class,
            scope_token=entrada.scope_token,
            outcome=entrada.outcome,
            governance_policy_id=entrada.governance_policy_id,
            governance_policy_key=entrada.governance_policy_key,
            governance_policy_version=entrada.governance_policy_version,
            governance_rule_id=entrada.governance_rule_id,
            governance_resolution_ref=entrada.governance_resolution_ref,
            approval_ref=entrada.approval_ref,
            executor_ref=entrada.executor_ref,
            attempted_at=entrada.attempted_at,
            completed_at=entrada.completed_at,
            retention_policy_id=entrada.retention_policy_id,
            retention_policy_key=entrada.retention_policy_key,
            retention_policy_version=entrada.retention_policy_version,
            failure_code=entrada.failure_code,
        )
        return self.add(entity)

    def list_by_subject_identifier(
        self, subject_identifier: str, *, limit: int = _DEFAULT_LIMIT, offset: int = 0
    ) -> list[ErasureRecord]:
        """Recibos de um sujeito, do mais recente para o mais antigo."""
        return self._listar(
            ErasureRecord.subject_identifier == subject_identifier, limit=limit, offset=offset
        )

    def list_by_approval_ref(
        self, approval_ref: str, *, limit: int = _DEFAULT_LIMIT, offset: int = 0
    ) -> list[ErasureRecord]:
        """Recibos vinculados a uma aprovação.

        Uma aprovação pode produzir vários recibos — um lote aprovado
        tem vários alvos, e cada tentativa tem desfecho próprio. É
        exatamente por isso que `PARTIAL` existe por recibo, e não por
        aprovação.
        """
        return self._listar(ErasureRecord.approval_ref == approval_ref, limit=limit, offset=offset)

    def list_by_outcome(
        self, outcome: ErasureOutcome, *, limit: int = _DEFAULT_LIMIT, offset: int = 0
    ) -> list[ErasureRecord]:
        """Recibos por desfecho observado."""
        return self._listar(ErasureRecord.outcome == outcome, limit=limit, offset=offset)

    def _listar(self, *criterios: object, limit: int, offset: int) -> list[ErasureRecord]:
        """Listagem com ordem **determinística**: `attempted_at DESC, id ASC`.

        O desempate por `id` não é enfeite. Recibos de um mesmo lote
        nascem no mesmo instante — e, como a E4.6.3 descobriu na
        prática, `now()` do PostgreSQL é o timestamp de **início da
        transação**, então vários registros de uma mesma transação têm
        `attempted_at` idêntico. Ordenar só por tempo faria a página
        seguinte repetir ou pular linhas conforme o humor do plano de
        execução.
        """
        if limit < 1:
            raise ValueError("limit deve ser >= 1")
        if offset < 0:
            raise ValueError("offset não pode ser negativo")

        stmt = (
            select(ErasureRecord)
            .where(*criterios)  # type: ignore[arg-type]
            .order_by(ErasureRecord.attempted_at.desc(), ErasureRecord.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.execute(stmt).scalars().all())

    def update(self, entity: ErasureRecord) -> ErasureRecord:
        """Sempre rejeita — recibos são append-only (`E4.9.5`)."""
        raise ErasureRecordImmutableError(entity.id, operation="update")

    def delete(self, entity: ErasureRecord) -> None:
        """Sempre rejeita — ver `update()`."""
        raise ErasureRecordImmutableError(entity.id, operation="delete")

    def soft_delete(self, entity: ErasureRecord) -> None:
        """Sempre rejeita.

        `ErasureRecord` não compõe `SoftDeleteMixin` e não tem coluna
        `deleted_at`, então este método não existiria por herança. Ele
        existe assim mesmo, explícito, para que uma tentativa futura
        de "só esconder da listagem" encontre uma recusa em vez de um
        `AttributeError` ambíguo.
        """
        raise ErasureRecordImmutableError(entity.id, operation="soft_delete")

    def bulk_update(self, *args: object, **kwargs: object) -> None:
        """Sempre rejeita — mutação em massa também é mutação."""
        raise ErasureRecordImmutableError(None, operation="bulk_update")

    def bulk_delete(self, *args: object, **kwargs: object) -> None:
        """Sempre rejeita — ver `bulk_update()`."""
        raise ErasureRecordImmutableError(None, operation="bulk_delete")
