"""
`SyncRepository` — leitura e escrita do patrimônio para transmissão
(`E3.11`/`LIB-11`).

Duas responsabilidades, nenhuma delas decisória:

1. **ler** o patrimônio de forma determinística, para exportar;
2. **inserir** registros novos, preservando integralmente os
   identificadores e timestamps que vieram no pacote.

Nunca atualiza e nunca apaga. Não existe `UPDATE` neste módulo: um
registro já presente é ignorado (idempotência) ou vira conflito
(`TRANSMISSION != OVERWRITE`).

A ordem de importação é **derivada das FKs reais**, via
`Base.metadata.sorted_tables` — não escolhida por intuição. Dentro de
`causal_history_events` há ainda a auto-referência
`predecessor_event_id`, resolvida por ordenação topológica própria:
o PostgreSQL valida FK por linha na inserção, então um evento precisa
entrar depois do seu predecessor, inclusive quando o predecessor está
na história de outro sujeito (`E3.9.1` —
`history boundary != causal boundary`).
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.cognitive.schemas.synchronization import SECTION_BY_TABLE, encode_row
from app.database.base import Base


def ordered_tables() -> list[sa.Table]:
    """Tabelas cognitivas em ordem de dependência de FK.

    `Base.metadata.sorted_tables` faz a ordenação topológica a partir
    das FKs declaradas; o filtro mantém apenas as tabelas que compõem
    o patrimônio cognitivo transmissível.
    """
    return [table for table in Base.metadata.sorted_tables if table.name in SECTION_BY_TABLE]


def topologically_ordered_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ordena eventos causais de modo que todo predecessor venha antes.

    Necessário porque a FK de `predecessor_event_id` aponta para a
    própria tabela e é validada linha a linha. Eventos cujo predecessor
    **não está no pacote** (por exemplo, já presente no destino) não são
    adiados: entram na ordem natural, e a FK do banco decide.

    Determinístico: parte da ordem canônica recebida
    (`created_at ASC, id ASC`) e só adia o que precisa ser adiado.
    """
    by_id = {str(row["id"]): row for row in rows}
    ordered: list[dict[str, Any]] = []
    placed: set[str] = set()

    def place(row: dict[str, Any], guard: set[str]) -> None:
        row_id = str(row["id"])
        if row_id in placed or row_id in guard:
            return
        guard.add(row_id)
        predecessor = row.get("predecessor_event_id")
        if predecessor is not None:
            parent = by_id.get(str(predecessor))
            if parent is not None:
                place(parent, guard)
        if row_id not in placed:
            ordered.append(row)
            placed.add(row_id)

    for row in rows:
        place(row, set())
    return ordered


class SyncRepository:
    """Acesso ao patrimônio para export/import."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # --- Export -------------------------------------------------------

    def read_table(self, table: sa.Table) -> list[dict[str, Any]]:
        """Todas as linhas de uma tabela, em ordem determinística.

        `created_at ASC, id ASC` — a convenção canônica do projeto
        desde `E3.1.2`. Sem ordem total, dois exports do mesmo
        patrimônio poderiam diferir apenas na ordem, e a comparação
        canônica do round-trip perderia o sentido.
        """
        stmt = sa.select(table).order_by(table.c.created_at.asc(), table.c.id.asc())
        return [encode_row(row) for row in self._session.execute(stmt).all()]

    def read_rows_by_id(self, table: sa.Table, ids: list[uuid.UUID]) -> dict[str, dict[str, Any]]:
        """Representação canônica das linhas já presentes no destino —
        matéria-prima da comparação que distingue idempotência de
        conflito.

        Sem guarda para lista vazia: `_classify` já retorna cedo quando
        a seção não tem registros, e uma guarda inalcançável seria
        código que nenhum teste consegue exercitar honestamente."""
        stmt = sa.select(table).where(table.c.id.in_(ids))
        return {
            str(row._mapping["id"]): encode_row(row) for row in self._session.execute(stmt).all()
        }

    def read_causal_edges(self) -> dict[str, str | None]:
        """Arestas causais já presentes no destino: `id → predecessor`.

        Lê **globalmente**, sem filtrar por história:
        `HISTORY_BOUNDARY != CAUSAL_BOUNDARY` (`E3.9.1`), e um
        predecessor legítimo pode estar na história de outro sujeito.
        Auditar por história perderia exatamente esses elos.

        Somente leitura — o preflight analisa, não altera nada
        (`PREFLIGHT_DOMAIN_WRITE_COUNT = 0`).
        """
        events = Base.metadata.tables["causal_history_events"]
        stmt = sa.select(events.c.id, events.c.predecessor_event_id)
        return {
            str(row[0]): (None if row[1] is None else str(row[1]))
            for row in self._session.execute(stmt).all()
        }

    # --- Import -------------------------------------------------------

    def insert_rows(self, table: sa.Table, rows: list[dict[str, Any]]) -> int:
        """Insere registros **novos**, com id e timestamps explícitos.

        Nenhum valor é regenerado: `id`, `created_at` e `updated_at`
        vêm do pacote. É isso que faz do import uma *transmissão* e não
        uma recriação — `IMPORT MUST NOT REGENERATE COGNITIVE IDENTITY`.

        Não commita: a transação é do chamador, e o import inteiro é
        uma transação só.
        """
        if not rows:
            return 0
        self._session.execute(sa.insert(table), rows)
        return len(rows)
