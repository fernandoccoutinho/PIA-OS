"""
`AuditOpinion` — parecer separado, jamais escrita no artefato (`E7.3`).

```text
AUDITOR_WRITE_ON_AUDITED_ARTIFACT = FORBIDDEN
AUDITOR_OUTPUT = SEPARATE_APPEND_ONLY_OPINION
AI_SELF_PASS_FINAL = FORBIDDEN
```

O sujeito é **exclusivamente** um `HandoffResult`, por chave estrangeira
direta. Uma referência polimórfica `subject_kind + subject_id` não teria
FK, e uma referência sem integridade a um artefato imutável é uma opinião
sobre algo que o banco não garante existir.

Parecer negativo **preserva** o resultado: `dissent` não apaga, não marca,
não reabre e não altera nada do que auditou. Múltiplas opiniões
independentes podem coexistir — divergência entre auditores é informação,
não conflito a resolver por sobrescrita.

`PASS_FINAL` não existe no enum, na matriz, no banco nem na resposta. Um
parecer produzido por execução de IA que pudesse declarar aprovação final
tornaria a auditoria independente decorativa.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator, TypeEngine

from app.models.base_model import BaseModel
from app.orchestration.models.enums import (
    AUDIT_OPINION_REASON_MATRIX,
    AuditOpinionKind,
    AuditReasonCode,
)
from app.orchestration.schemas.envelope import MAX_REF_LENGTH


def canonical_audit_reason_codes(valor: object) -> tuple[str, ...]:
    """Ordena, remove duplicata e valida contra o vocabulário fechado."""
    if valor is None or isinstance(valor, str | bytes):
        raise ValueError("reason_codes deve ser uma sequência de códigos")
    codigos: tuple[object, ...] = tuple(valor)  # type: ignore[arg-type]
    if not codigos:
        raise ValueError("um parecer sem motivo não é um parecer")
    permitidos = {codigo.value for codigo in AuditReasonCode}
    for codigo in codigos:
        texto = codigo.value if isinstance(codigo, AuditReasonCode) else codigo
        if not isinstance(texto, str) or texto not in permitidos:
            raise ValueError(f"reason_code fora do vocabulário fechado: {codigo!r}")
    return tuple(sorted({c.value if isinstance(c, AuditReasonCode) else str(c) for c in codigos}))


def assert_opinion_matrix(opinion: AuditOpinionKind, codigos: tuple[str, ...]) -> None:
    """Opinião e motivo têm de concordar.

    Um `concur` justificado por `contract_nonconformity` seria uma linha
    que contradiz a si mesma, e nenhuma leitura posterior saberia em qual
    metade acreditar.
    """
    admitidos = {codigo.value for codigo in AUDIT_OPINION_REASON_MATRIX[opinion]}
    fora = set(codigos) - admitidos
    if fora:
        raise ValueError(f"motivo incompatível com o parecer {opinion.value!r}: {sorted(fora)}")


class AuditReasonCodesType(TypeDecorator[tuple[str, ...]]):
    """`JSONB` no PostgreSQL, canônico em memória."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())  # type: ignore[no-untyped-call]
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: object, dialect: Dialect) -> list[str]:
        if value is None:
            raise ValueError("reason_codes não admite None")
        return list(canonical_audit_reason_codes(value))

    def process_result_value(self, value: object, dialect: Dialect) -> tuple[str, ...]:
        if value is None:
            raise ValueError("reason_codes não admite None")
        return canonical_audit_reason_codes(value)


class AuditOpinion(BaseModel):
    """Parecer imutável sobre um `HandoffResult`."""

    __tablename__ = "audit_opinions"

    __table_args__ = (
        CheckConstraint(
            "length(btrim(auditor_execution_ref)) > 0",
            name="ck_audit_opinions_auditor_ref_not_blank",
        ),
        CheckConstraint(
            "length(btrim(issued_by_principal_ref)) > 0",
            name="ck_audit_opinions_principal_not_blank",
        ),
        CheckConstraint(
            "opinion IN ('concur', 'dissent', 'insufficient_evidence', 'out_of_scope')",
            name="ck_audit_opinions_opinion_vocabulary",
        ),
        Index("ix_audit_opinions_result", "handoff_result_id"),
    )
    """Sem `UNIQUE` em `handoff_result_id`: opiniões independentes coexistem.

    A matriz opinião×motivo e a exclusão de `PASS_FINAL` vivem em `CHECK`
    na migration, onde `jsonb` está disponível.
    """

    handoff_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handoff_results.id", name="fk_audit_opinions_result"), nullable=False
    )

    opinion: Mapped[AuditOpinionKind] = mapped_column(
        SAEnum(
            AuditOpinionKind,
            name="orchestration_audit_opinion",
            native_enum=False,
            length=24,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    reason_codes: Mapped[tuple[str, ...]] = mapped_column(AuditReasonCodesType, nullable=False)

    auditor_execution_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Referência opaca à execução auditora. Não é identidade verificada."""

    issued_by_principal_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
