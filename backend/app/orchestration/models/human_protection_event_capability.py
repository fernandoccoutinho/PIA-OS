"""
`HumanProtectionEventCapability` — capacidades de um bloqueio (`E7.4-1 B1a`).

Tabela filha, append-only, com chave primária composta `(event_id, ordinal)`.
O ordinal preserva a **cardinalidade e a ordem** das capacidades bloqueadas:

```text
COLLECTION_REDUCED_TO_ONE = INVENTED_SELECTION_RULE
```

Os três invariantes que ligam pai e filha — bloqueio exige ao menos uma
capacidade, não-bloqueio não carrega nenhuma, ordinais são exatamente
`0..n-1` — **não** vivem aqui nem em código: um `CHECK` não cruza tabelas, e
avaliá-los em Python daria a duas fontes a chance de divergir. Eles são
avaliados no `COMMIT` pelos dois constraint triggers diferidos criados na
migration.

```text
DB_LEVEL cardinalidade e ordinais, no COMMIT
```
"""

import uuid

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.orchestration.models.human_protection_event import (
    CHECKS_DA_CAPACIDADE,
    TABELA_CAPACIDADE,
)


class HumanProtectionEventCapability(Base):
    """Uma capacidade crítica bloqueada, na sua posição ordinal."""

    __tablename__ = TABELA_CAPACIDADE

    __table_args__ = (
        UniqueConstraint("event_id", "critical_capability", name="uq_hpec_event_capability"),
        *(CheckConstraint(sa.text(sql), name=nome) for nome, sql in CHECKS_DA_CAPACIDADE),
    )
    """O `UNIQUE` impede a mesma capacidade duas vezes no mesmo evento —
    duplicata inflaria a contagem sem acrescentar fato."""

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("human_protection_events.id", name="fk_hpec_event"),
        primary_key=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    critical_capability: Mapped[str] = mapped_column(String(64), nullable=False)
    """Valor canônico de `CriticalCapability` (E4), por valor.

    Sem enum próprio da E7: `DUPLICATE_PROTECTION_CATEGORY_OWNER = PROHIBITED`.
    """
