"""
`ValidatedExperience` — registro persistente e imutável (`E4.11`).

```text
ValidatedExperience != ProvenanceRecord
ValidatedExperience != CausalHistoryEvent
ValidatedExperience != ComplianceFinding
ValidatedExperience != LearningEngine
```

A E3 tem `ProvenanceRecord` (de onde veio) e `CausalHistoryEvent` (o que
aconteceu), mas nenhum dos dois registra **validação** — que é um juízo
posterior sobre um evento, não o evento. É a única razão pela qual esta
primitiva existe.

## O que este registro nunca faz o sistema fazer

```text
IF REMOVING THE RECORD CHANGES SYSTEM BEHAVIOR
THEN IT IS A LEARNING ENGINE
```

Nenhum módulo de produção lê esta tabela para decidir coisa alguma, e
uma guarda estática mede isso por chamada e por ramificação, não só por
import. Apagar uma linha aqui apaga evidência auditável — nunca muda
uma decisão.

## Append-only em três camadas

```text
1. value object congelado    (schemas/validated_experience.py)
2. repositório recusa        update / delete / soft_delete / bulk_*
3. trigger PostgreSQL        BEFORE UPDATE OR DELETE
```

A E3 declara explicitamente que **não** impõe append-only no banco para
`ProvenanceRecord` (`GLOBAL_DB_CYCLE_PROTECTION = NOT_REQUIRED_IN_E3_9`,
e nenhuma trigger). O precedente forte é o da E4.9.5, e é o que esta
tabela segue: SQL arbitrário fora do repositório também é recusado.

## Identidade própria, fornecida pelo chamador

```text
EXPERIENCE_ID != COID
EXPERIENCE_ID != CLID
EXPERIENCE_ID != CAUSAL_EVENT_ID
```

O `id` não é gerado no `flush`, ao contrário do `UUIDMixin`: ele entra
no contrato de append, porque a idempotência é **por identidade**, e o
chamador precisa poder repetir a mesma chamada sabendo que é a mesma.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import JSON, TypeDecorator, TypeEngine

from app.memory.models.validated_experience_enums import (
    CriterionOriginKind,
    EvidenceKind,
    ExperienceSubjectKind,
    ValidatorKind,
)
from app.memory.schemas.validated_experience import (
    MAX_CRITERION_KEY_LENGTH,
    MAX_REF_LENGTH,
    MAX_TOKEN_LENGTH,
    EvidenceReference,
)
from app.models.base_model import BaseModel


def _canonizar(referencias: object) -> tuple[EvidenceReference, ...]:
    """Contrato ÚNICO de validação do lastro, na ida e na volta do disco.

    ```text
    NON_EMPTY · NO_DUPLICATES · CANONICAL_ORDER
    ```

    Chamado pelo `TypeDecorator` **e** pelo `@validates`, para que as
    duas fronteiras não voltem a divergir — a lição literal da E4.9.6.2,
    onde o decorador cobria disco e a atribuição direta escapava.
    """
    if isinstance(referencias, str) or not isinstance(referencias, tuple | list):
        raise TypeError("evidence_refs deve ser uma sequência de EvidenceReference")
    itens = tuple(referencias)
    if not itens:
        raise ValueError("evidence_refs não pode ser vazia: EXPERIENCE -> EVIDENCE -> VALIDATION")
    for indice, item in enumerate(itens):
        if not isinstance(item, EvidenceReference):
            raise TypeError(f"evidence_refs[{indice}] deve ser um EvidenceReference")
    chaves = [item.sort_key() for item in itens]
    if len(set(chaves)) != len(chaves):
        raise ValueError("evidence_refs repetida")
    if chaves != sorted(chaves):
        raise ValueError("evidence_refs fora da ordem canônica (kind, ref)")
    return itens


class EvidenceRefsType(TypeDecorator[tuple[EvidenceReference, ...]]):
    """Fronteira de congelamento do lastro de evidência.

    ```text
    PERSISTENT IMMUTABILITY != DEEP READ IMMUTABILITY
    BOTH ARE REQUIRED
    ```

    Faz o objeto **carregado** e o objeto **gravado** usarem a mesma
    representação tipada, de modo que todo método herdado de
    `BaseRepository` devolva a estrutura já congelada. Sem isto, uma
    lista de dicionários carregada do banco seria mutável em memória e
    duas leituras na mesma sessão poderiam divergir.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())  # type: ignore[no-untyped-call]
        return dialect.type_descriptor(JSON())

    def process_bind_param(
        self, value: "tuple[EvidenceReference, ...] | None", dialect: Dialect
    ) -> list[dict[str, str]]:
        """Lastro tipado → JSON canônico, na ida para o disco.

        `None` é recusado aqui, e não delegado ao `NOT NULL`: a coluna
        nunca admite `NULL`, então devolver `None` transformaria uma
        violação de domínio numa violação de constraint, longe de onde
        ela nasceu.
        """
        if value is None:
            raise ValueError("evidence_refs não admite None")
        return [
            {"kind": referencia.kind.value, "ref": str(referencia.ref)}
            for referencia in _canonizar(value)
        ]

    def process_result_value(
        self, value: object, dialect: Dialect
    ) -> tuple[EvidenceReference, ...]:
        """JSON → lastro tipado, na volta do disco."""
        if value is None:
            raise ValueError("evidence_refs não admite None")
        if not isinstance(value, list):
            raise TypeError("evidence_refs persistida em formato inesperado")
        return _canonizar(
            tuple(
                EvidenceReference(kind=EvidenceKind(item["kind"]), ref=uuid.UUID(item["ref"]))
                for item in value
            )
        )


class ValidatedExperience(BaseModel):
    """Uma validação ocorrida: sobre o quê, com que resultado, por quem,
    contra qual critério, com qual lastro, quando — e de qual origem.

    Nenhuma coluna expressa score, confiança, peso, ranking,
    generalização ou recomendação. Todas seriam inferência, e inferência
    automática sobre experiência é exatamente o motor proibido.
    """

    __tablename__ = "validated_experiences"

    __table_args__ = (
        CheckConstraint(
            "length(btrim(validator_ref)) > 0",
            name="ck_validated_experiences_validator_ref_not_blank",
        ),
        CheckConstraint(
            "length(btrim(criterion_key)) > 0",
            name="ck_validated_experiences_criterion_key_not_blank",
        ),
        CheckConstraint(
            "length(btrim(outcome_token)) > 0",
            name="ck_validated_experiences_outcome_token_not_blank",
        ),
        CheckConstraint(
            "criterion_version >= 1",
            name="ck_validated_experiences_criterion_version_positive",
        ),
        CheckConstraint(
            "observed_at <= validated_at",
            name="ck_validated_experiences_observed_before_validated",
        ),
        Index(
            "ix_validated_experiences_subject",
            "subject_kind",
            "subject_ref",
        ),
        CheckConstraint(
            "validated_experience_evidence_is_canonical("
            "evidence_refs, primary_evidence_kind::text, primary_evidence_ref::text)",
            name="ck_validated_experiences_evidence_refs_canonical",
        ),
        Index(
            "ix_validated_experiences_criterion",
            "criterion_key",
            "criterion_version",
            "criterion_origin",
        ),
    )
    """Seis `CHECK` e dois índices.

    O sexto `CHECK` chama a função `validated_experience_evidence_is_
    canonical`, criada pela migration: `CHECK` não aceita subconsulta, e
    os invariantes do lastro exigem percorrer o array.

    ```text
    APP_TYPED_BOUNDARY != DATABASE_INTEGRITY
    JSONB_NOT_NULL     != CLOSED_EVIDENCE_SCHEMA
    ```

    Acrescentado na auditoria da cadeia 96: `NOT NULL` sozinho deixava
    SQL bruto gravar array vazio, chave `url` ou `credential`, `kind`
    inventado, duplicata, ordem não canônica e evidência primária fora do
    conjunto. Numa tabela append-only, uma linha assim fica permanente.

    `observed_at <= validated_at` é o único invariante temporal imposto,
    e é o correto: observa-se antes de validar. O inverso descreveria uma
    validação sobre o que ainda não foi observado.

    Não há `UNIQUE` semântico sobre sujeito/critério/validador, e a
    ausência é decisão medida: **repetição pode ser evidência**. Duas
    validações do mesmo sujeito, contra o mesmo critério, pelo mesmo
    validador, em instantes diferentes, são dois fatos — fundi-las
    apagaria a distinção que a repetição constitui.

    ```text
    REPETITION_IS_EVIDENCE
    SEMANTIC_UNIQUENESS_WOULD_ERASE_IT
    ```

    A unicidade que existe é a da chave primária, e é sobre ela que a
    idempotência se apoia.
    """

    subject_kind: Mapped[ExperienceSubjectKind] = mapped_column(
        SAEnum(
            ExperienceSubjectKind,
            name="experience_subject_kind",
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    """Discriminador do sujeito. `SAME_UUID_DIFFERENT_UNIVERSE`."""

    subject_ref: Mapped[uuid.UUID] = mapped_column(nullable=False)
    """Identidade do sujeito — **sem FK**.

    ```text
    REFERENCE != FOREIGN_KEY
    ```

    Uma FK exigiria que o alvo exista neste banco. Evidência sobre um
    objeto já removido deixaria de ser registrável, e a garantia que o
    registro dá — que a validação ocorreu — não depende de o sujeito
    continuar existindo.
    """

    outcome_token: Mapped[str] = mapped_column(String(MAX_TOKEN_LENGTH), nullable=False)
    """Resultado observado, em gramática fechada.

    Lido **contra** o `criterion_ref`; não constitui ontologia universal.
    """

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    primary_evidence_kind: Mapped[EvidenceKind] = mapped_column(
        SAEnum(
            EvidenceKind,
            name="validated_experience_evidence_kind",
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    primary_evidence_ref: Mapped[uuid.UUID] = mapped_column(nullable=False)
    """A evidência que sustenta o resultado — sempre presente no lastro."""

    validator_kind: Mapped[ValidatorKind] = mapped_column(
        SAEnum(
            ValidatorKind,
            name="validated_experience_validator_kind",
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    validator_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Referência **atribuída** ao validador.

    ```text
    ATTRIBUTED = YES · AUTHENTICATED = NO
    ```

    Não existe coluna `verified` nem `signature`, e a ausência é a
    garantia: nenhuma linha pode alegar identidade comprovada.
    """

    criterion_key: Mapped[str] = mapped_column(String(MAX_CRITERION_KEY_LENGTH), nullable=False)
    criterion_version: Mapped[int] = mapped_column(Integer, nullable=False)
    criterion_origin: Mapped[CriterionOriginKind] = mapped_column(
        SAEnum(
            CriterionOriginKind,
            name="validated_experience_criterion_origin",
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    evidence_refs: Mapped[tuple[EvidenceReference, ...]] = mapped_column(
        EvidenceRefsType(), nullable=False
    )
    """Lastro completo, canonicalizado e não vazio."""

    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    origin_ref: Mapped[uuid.UUID] = mapped_column(nullable=False)
    """Instalação de origem — atribuída, nunca autenticada.

    ```text
    ORIGIN_LOCALITY_PERSISTED = NO
    ```

    Não há coluna de localidade. "Local" é relativo a quem lê, e um
    booleano persistido passaria a mentir depois do transporte.
    """

    @validates("evidence_refs")
    def _validar_lastro(self, _campo: str, valor: object) -> tuple[EvidenceReference, ...]:
        """Fronteira de **atribuição**.

        ```text
        TYPE DECORATOR BOUNDARY != ORM ASSIGNMENT BOUNDARY
        ```

        O `TypeDecorator` cobre disco; este `@validates` cobre
        `ValidatedExperience(evidence_refs=[...])`, que nunca passa por
        `process_bind_param` antes do flush. Os dois chamam a mesma
        função, para que não voltem a divergir.
        """
        return _canonizar(valor)
