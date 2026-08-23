"""
`ScheduleStep` — a etapa, seus papéis e o contexto mínimo declarado.

```text
CONTEXT = MINIMUM_NECESSARY_DECLARED_PER_STEP
ARTIFACT_REF = {uri_ou_id, sha256, bytes}
INLINE_CONTENT_WITHOUT_HASH = FORBIDDEN
```

As duas colunas JSON atravessam `TypeDecorator` tipado, no precedente de
`EvidenceRefsType` (E4.11): o objeto **carregado** e o **gravado** usam a
mesma representação congelada, de modo que o conteúdo do envelope não
dependa de quem leu a linha nem de quando.
"""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator, TypeEngine

from app.models.base_model import BaseModel
from app.orchestration.models.enums import StepState
from app.orchestration.schemas.envelope import (
    MAX_REF_LENGTH,
    MAX_ROLE_LENGTH,
    ConstraintPairs,
    ContextRef,
    canonical_constraints,
    constraints_as_mapping,
    parse_context_refs,
)


class ContextRefsType(TypeDecorator[tuple[ContextRef, ...]]):
    """`JSONB` no PostgreSQL, `JSON` nos demais — sempre tipado em memória."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())  # type: ignore[no-untyped-call]
        return dialect.type_descriptor(JSON())

    def process_bind_param(
        self, value: "tuple[ContextRef, ...] | None", dialect: Dialect
    ) -> list[dict[str, object]]:
        """`None` é recusado aqui, e não delegado ao `NOT NULL`.

        Deixar o banco reclamar transformaria uma violação de domínio numa
        violação de constraint, longe de onde ela nasceu.
        """
        if value is None:
            raise ValueError("context_refs não admite None")
        return [referencia.as_content() for referencia in parse_context_refs(value)]

    def process_result_value(self, value: object, dialect: Dialect) -> tuple[ContextRef, ...]:
        if value is None:
            raise ValueError("context_refs não admite None")
        return parse_context_refs(value)


class ConstraintsType(TypeDecorator[ConstraintPairs]):
    """Restrições como mapa no disco, pares ordenados em memória."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())  # type: ignore[no-untyped-call]
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: object, dialect: Dialect) -> dict[str, str]:
        if value is None:
            raise ValueError("constraints não admite None; use um mapa vazio")
        return constraints_as_mapping(canonical_constraints(value))

    def process_result_value(self, value: object, dialect: Dialect) -> ConstraintPairs:
        if value is None:
            raise ValueError("constraints não admite None")
        return canonical_constraints(value)


class ScheduleStep(BaseModel):
    """Uma etapa do trabalho: papel, instrução, contexto e contrato de saída."""

    __tablename__ = "schedule_steps"

    __table_args__ = (
        UniqueConstraint("schedule_id", "position", name="uq_schedule_steps_position"),
        UniqueConstraint("id", "schedule_id", name="uq_schedule_steps_id_schedule"),
        CheckConstraint("position >= 1", name="ck_schedule_steps_position_positive"),
        CheckConstraint("length(btrim(role)) > 0", name="ck_schedule_steps_role_not_blank"),
        CheckConstraint(
            "length(btrim(instruction_ref)) > 0",
            name="ck_schedule_steps_instruction_ref_not_blank",
        ),
        CheckConstraint(
            "length(btrim(expected_output_contract)) > 0",
            name="ck_schedule_steps_output_contract_not_blank",
        ),
    )
    """A unicidade `(schedule_id, position)` é o que torna a composição uma
    **ordem**, e não um conjunto com um número decorativo ao lado.

    `uq_schedule_steps_id_schedule` é redundante em cardinalidade — `id`
    já é a chave primária — e obrigatória em referência: é o alvo da
    chave estrangeira composta que `handoff_attempts` usa para provar,
    no banco, que a etapa pertence àquele Schedule (corretivo R1).

    O `CHECK` de canonicidade de `context_refs` é criado pela migration e
    não aparece aqui: ele chama uma função PL/pgSQL, e `CHECK` do
    metadata precisa ser legível por todo dialeto que crie estas tabelas.
    """

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedules.id", name="fk_schedule_steps_schedule"), nullable=False
    )
    """FK real — a etapa não existe fora do seu trabalho.

    Sem `ondelete`: apagar um Schedule com etapas deve falhar, não
    propagar. Não há remoção de Schedule na E7.1, e a ausência de CASCADE
    é o que impede que ela apareça por acidente depois.
    """

    position: Mapped[int] = mapped_column(Integer, nullable=False)

    role: Mapped[str] = mapped_column(String(MAX_ROLE_LENGTH), nullable=False)
    """Papel no trabalho — **não** é quem executa (MAI §2).

    ```text
    ROLE != AGENT
    ```
    """

    instruction_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Referência à instrução, nunca a instrução embutida.

    ```text
    LOG_NEVER_CONTAINS = prompt, resposta, segredo, contexto
    ```
    """

    context_refs: Mapped[tuple[ContextRef, ...]] = mapped_column(ContextRefsType, nullable=False)

    expected_output_contract: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Contrato que o retorno deverá cumprir.

    A E7.1 apenas o declara e o inclui no conteúdo selado. **Validar** o
    retorno contra ele é E7.2 — antecipar aqui seria implementar o
    `ReturnValidationSvc` de outra entrega.
    """

    constraints: Mapped[ConstraintPairs] = mapped_column(ConstraintsType, nullable=False)

    state: Mapped[StepState] = mapped_column(
        SAEnum(
            StepState,
            name="orchestration_step_state",
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=StepState.PENDING,
    )
    """Nasce `PENDING` e assim permanece na E7.1.

    ```text
    SEALED != DISPATCHED
    ```
    """
