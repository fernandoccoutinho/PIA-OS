"""
`HandoffResult` — o veredito sobre um retorno não confiável (`E7.2`).

```text
AI_OUTPUT != CONTROL_CHANNEL
VALIDATED_RESULT != AUTHORIZATION
RESULT_REJECTED != RESULT_DISCARDED
RESULT_STATUS != STEP_STATE
```

Uma linha por tentativa importada, **inclusive quando rejeitada**. Recusa
que não deixa rastro é recusa que ninguém pode auditar depois: o resultado
rejeitado é exatamente o registro de que uma IA respondeu fora do contrato,
e apagá-lo faria a etapa parecer nunca ter sido tentada.

O conteúdo bruto **não** entra aqui.

```text
RAW_OUTPUT_IN_DATABASE = FORBIDDEN
TRANSCRIPT_PERSISTENCE = NONE_IN_E7_2
```

Persistem-se apenas o hash, o tamanho canônico, o media type, o contrato
esperado, a referência declarada opcional, o status e os códigos. Guardar
a resposta transformaria a orquestração em arquivo de transcrições sem
que ninguém tivesse decidido isso — e `AUTOMATIC_MATERIALIZATION` é
proibida no programa inteiro.

Append-only em três camadas, no precedente medido de `seal_receipts`:
produtor único, repositório que recusa, triggers de UPDATE/DELETE/TRUNCATE.
"""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator, TypeEngine

from app.models.base_model import BaseModel
from app.orchestration.models.attempt import SHA256_HEX_LENGTH
from app.orchestration.models.enums import HandoffResultStatus
from app.orchestration.schemas.envelope import MAX_REF_LENGTH

MAX_MEDIA_TYPE_LENGTH = 64
MAX_DECLARED_REF_LENGTH = 1024


class ValidationCodesType(TypeDecorator[tuple[str, ...]]):
    """Códigos canônicos: ordenados, sem duplicata, tipados em memória.

    Mesmo precedente de `CanonicalScopeArray` (E6.2). Ordenar na escrita
    faz duas rejeições pelos mesmos motivos terem a mesma forma
    persistida, então comparar veredito nunca depende da ordem em que o
    validador acumulou os códigos.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())  # type: ignore[no-untyped-call]
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: object, dialect: Dialect) -> list[str]:
        from app.orchestration.schemas.output_contract import canonical_validation_codes

        if value is None:
            raise ValueError("validation_codes não admite None; use uma lista vazia")
        return list(canonical_validation_codes(value))

    def process_result_value(self, value: object, dialect: Dialect) -> tuple[str, ...]:
        from app.orchestration.schemas.output_contract import canonical_validation_codes

        if value is None:
            raise ValueError("validation_codes não admite None")
        return canonical_validation_codes(value)


class HandoffResult(BaseModel):
    """Veredito de validação de um retorno, imutável desde a criação."""

    __tablename__ = "handoff_results"

    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_handoff_results_attempt"),
        CheckConstraint(
            f"length(output_sha256) = {SHA256_HEX_LENGTH}",
            name="ck_handoff_results_output_sha256_length",
        ),
        CheckConstraint("output_bytes >= 0", name="ck_handoff_results_output_bytes_non_negative"),
        CheckConstraint(
            "length(btrim(expected_output_contract)) > 0",
            name="ck_handoff_results_contract_not_blank",
        ),
        CheckConstraint(
            "length(btrim(output_media_type)) > 0",
            name="ck_handoff_results_media_type_not_blank",
        ),
        Index("ix_handoff_results_status", "status"),
    )
    """`attempt_id` único materializa `Attempt 1 -> 0..1 Result`.

    Dois vereditos para a mesma tentativa seriam duas verdades sobre o
    mesmo ato. Retry legítimo abre tentativa nova, e a nova tentativa tem
    o seu próprio resultado — é assim que o histórico cresce sem
    sobrescrever.

    A coerência entre `status` e `validation_codes` é imposta por `CHECK`
    na migration, onde `jsonb_array_length` existe; aqui ficam apenas as
    restrições portáveis.
    """

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handoff_attempts.id", name="fk_handoff_results_attempt"), nullable=False
    )

    status: Mapped[HandoffResultStatus] = mapped_column(
        SAEnum(
            HandoffResultStatus,
            name="orchestration_handoff_result_status",
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    expected_output_contract: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Contrato contra o qual o retorno foi medido, copiado no ato.

    Copiar em vez de derivar da etapa é o que faz o veredito continuar
    verdadeiro: ele diz contra o que se julgou **naquele** momento.
    """

    output_media_type: Mapped[str] = mapped_column(String(MAX_MEDIA_TYPE_LENGTH), nullable=False)

    output_sha256: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    """Hash dos bytes canônicos. É o que resta do conteúdo — de propósito."""

    output_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    declared_output_ref: Mapped[str | None] = mapped_column(
        String(MAX_DECLARED_REF_LENGTH), nullable=True
    )
    """Referência a um artefato externo, **declarada** pelo cliente.

    ```text
    DECLARED_REF != VERIFIED_ARTIFACT
    ```

    A E7 não busca, não resolve e não valida essa URI — resolver seria
    rede, e rede é proibida nesta entrega.
    """

    validation_codes: Mapped[tuple[str, ...]] = mapped_column(ValidationCodesType, nullable=False)
    """Vazio quando `VALIDATED`; ao menos um código quando `REJECTED`.

    São **dados canônicos**, não códigos de exceção: descrevem por que um
    retorno não cumpriu o contrato, e o veredito é resposta bem-sucedida
    da API, não erro de schema.
    """
