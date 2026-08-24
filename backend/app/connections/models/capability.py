"""
Capacidade, entitlement e evidência — três registros, três confianças.

```text
CURADORIA   famílias para navegação
DESCOBERTA  catálogo corrente por fonte oficial; TTL; vencer -> DEGRADED
EXECUÇÃO    recibo e atribuição; a melhor evidência da rota usada
```

Nenhum dos três decide sozinho, e `EvaluationEvidence` não decide de
forma alguma: não há coluna de ranking, score soberano ou ordem
preferencial nesta camada, e essa ausência é a mitigação.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.connections.models.catalog import MAX_SLUG_LENGTH
from app.connections.models.connection_profile import MAX_REF_LENGTH
from app.connections.models.enums import (
    CapabilitySource,
    EntitlementOrigin,
    EntitlementState,
    EvidenceCategory,
)
from app.models.base_model import BaseModel


def _json_type() -> sa.types.TypeEngine[object]:
    """JSON portátil com variante JSONB no PostgreSQL — precedente da E7.3."""
    return sa.JSON().with_variant(
        JSONB(astext_type=sa.Text()),  # type: ignore[no-untyped-call]
        "postgresql",
    )


class CapabilitySnapshot(BaseModel):
    """O que uma conexão declarou saber fazer, **num instante**, com validade.

    Append-only: um snapshot descreve uma observação já terminada. Se a
    capacidade mudou, o fato é um snapshot novo — sobrescrever apagaria a
    evidência de que ela era outra.

    ```text
    discovery stale DEGRADA, não substitui
    ```

    `valid_until` no passado significa vencido. Vencido é lido e
    **rotulado**; nunca é apagado nem trocado por um palpite corrente.
    """

    __tablename__ = "connection_capability_snapshots"

    __table_args__ = (
        ForeignKeyConstraint(
            ["connection_id", "control_principal_ref"],
            ["connection_profiles.id", "connection_profiles.control_principal_ref"],
            name="fk_capability_snapshots_connection_within_principal",
        ),
        CheckConstraint("valid_until > observed_at", name="ck_capability_snapshots_ttl_positive"),
        CheckConstraint(
            "length(btrim(control_principal_ref)) > 0",
            name="ck_capability_snapshots_principal_not_blank",
        ),
        CheckConstraint(
            "source IN ('official_discovery', 'user_declared_endpoint', 'execution_observed')",
            name="ck_capability_snapshots_source_vocabulary",
        ),
        UniqueConstraint(
            "connection_id", "observed_at", name="uq_capability_snapshots_connection_instant"
        ),
        Index("ix_capability_snapshots_connection", "connection_id"),
    )
    """A FK é **composta**, e não simples, pela mesma razão do recibo:
    duas referências válidas isoladamente não provam que o snapshot e a
    conexão pertencem ao mesmo dono.

    ```text
    TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE
    ```
    """

    connection_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), nullable=False)
    control_principal_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Copiado no ato, nunca derivado por join — é ele que fecha o vínculo."""

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source: Mapped[CapabilitySource] = mapped_column(
        SAEnum(
            CapabilitySource,
            name="connection_capability_source",
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    capabilities: Mapped[object] = mapped_column(_json_type(), nullable=False)
    """Lista fechada de rótulos de capacidade. Nunca resposta de provedor."""


class EntitlementClaim(BaseModel):
    """Alegação de direito de uso — declarada ou descoberta oficialmente.

    ```text
    MUTAR o registro declarado                 = PROIBIDO
    CRIAR registro oficial que o SUPERSEDA     = CAMINHO NORMAL
    ```

    Se `USER_DECLARED` nunca pudesse ser superado, o usuário jamais
    conseguiria verificar depois o plano que declarou antes, e a
    declaração honesta viraria uma prisão. A sucessão preserva origem,
    instante e conteúdo do antecedente: a história mostra "o usuário
    disse X, e depois a integração oficial confirmou X" — que é
    informação, não ruído.
    """

    __tablename__ = "connection_entitlement_claims"

    __table_args__ = (
        UniqueConstraint("id", "control_principal_ref", name="uq_entitlement_claims_id_principal"),
        ForeignKeyConstraint(
            ["superseded_by_id", "control_principal_ref"],
            [
                "connection_entitlement_claims.id",
                "connection_entitlement_claims.control_principal_ref",
            ],
            name="fk_entitlement_claims_successor_within_principal",
            use_alter=True,
        ),
        UniqueConstraint("superseded_by_id", name="uq_entitlement_claims_single_antecedent"),
        CheckConstraint(
            "superseded_by_id IS NULL OR superseded_by_id <> id",
            name="ck_entitlement_claims_no_self_succession",
        ),
        CheckConstraint(
            "(state = 'superseded') = (superseded_by_id IS NOT NULL)",
            name="ck_entitlement_claims_superseded_coherent",
        ),
        CheckConstraint(
            "origin IN ('user_declared', 'officially_discovered')",
            name="ck_entitlement_claims_origin_vocabulary",
        ),
        CheckConstraint(
            "state IN ('active', 'superseded', 'expired', 'revoked', 'not_confirmed')",
            name="ck_entitlement_claims_state_vocabulary",
        ),
        CheckConstraint(
            "length(btrim(control_principal_ref)) > 0",
            name="ck_entitlement_claims_principal_not_blank",
        ),
        Index("ix_entitlement_claims_principal", "control_principal_ref"),
    )
    """`uq_entitlement_claims_single_antecedent` materializa "um sucessor
    supera **no máximo um** antecedente": sem ela, um único registro
    oficial poderia ser apontado como sucessor de vários declarados, e a
    história deixaria de dizer qual alegação foi de fato confirmada.

    A FK do sucessor é composta e `use_alter=True` porque é
    autorreferente — a tabela precisa existir antes de a restrição
    apontar para ela.
    """

    control_principal_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)

    provider_family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connection_provider_families.id", name="fk_entitlement_claims_family"),
        nullable=False,
    )

    plan_ref: Mapped[str] = mapped_column(String(MAX_SLUG_LENGTH), nullable=False)
    """O que foi alegado. **Imutável** — imposto por trigger."""

    origin: Mapped[EntitlementOrigin] = mapped_column(
        SAEnum(
            EntitlementOrigin,
            name="connection_entitlement_origin",
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    state: Mapped[EntitlementState] = mapped_column(
        SAEnum(
            EntitlementState,
            name="connection_entitlement_state",
            native_enum=False,
            length=24,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """Instante histórico da alegação. Preservado na sucessão."""

    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(), nullable=True)


class EvaluationEvidence(BaseModel):
    """Evidência externa de avaliação. Append-only, e **nunca** decide.

    ```text
    BENCHMARK EXTERNO NÃO SOBREPÕE PREFERÊNCIA NEM AUTORIDADE
    ```

    Não há coluna de score soberano, ranking ou ordem preferencial, e não
    há serviço que leia esta tabela para escolher conexão. A garantia é
    estrutural: não existe o caminho, e uma guarda estática reprova quem
    o criar.
    """

    __tablename__ = "connection_evaluation_evidence"

    __table_args__ = (
        CheckConstraint(
            "length(btrim(source_slug)) > 0",
            name="ck_evaluation_evidence_source_not_blank",
        ),
        CheckConstraint(
            "category IN ('external_evaluation', 'scientific_reference', "
            "'operator_announcement')",
            name="ck_evaluation_evidence_category_vocabulary",
        ),
        UniqueConstraint(
            "source_slug", "category", "observed_at", name="uq_evaluation_evidence_identity"
        ),
        Index("ix_evaluation_evidence_source", "source_slug"),
    )

    source_slug: Mapped[str] = mapped_column(String(MAX_SLUG_LENGTH), nullable=False)
    category: Mapped[EvidenceCategory] = mapped_column(
        SAEnum(
            EvidenceCategory,
            name="connection_evidence_category",
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[object] = mapped_column(_json_type(), nullable=False)
    is_authoritative: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    """Sempre falso, e imposto por `CHECK` na migration.

    A coluna existe para que a proibição seja **legível** no schema em vez
    de apenas ausente dele: quem for tentar dar autoridade a um benchmark
    encontra a recusa escrita, não um vazio para preencher.
    """
