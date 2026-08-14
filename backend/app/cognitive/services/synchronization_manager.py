"""
`SynchronizationManager` — transmissão de patrimônio cognitivo entre
instâncias (`E3.11`/`LIB-11`).

```text
COGNITIVE PATRIMONY (A) → PACKAGE → COGNITIVE PATRIMONY (B)
```

O que o módulo garante, e que uma cópia de linhas não garantiria:

```text
COUT-P1  distinção existente não desaparece silenciosamente
COUT-P2  continuidade (CLID) sobrevive à transmissão
COUT-P3  provenance nunca é apagada nem substituída em silêncio
COUT-P4  histórias distintas não são colapsadas por estado parecido
COUT-P5  transformações e suas declarações sobrevivem ao round-trip
COUT-P6  ACTIVE/LATENT/INACCESSIBLE/CAUSALLY_EXTINCT são transmitidos
         como estados existentes — ausência no pacote nunca vira
         CAUSALLY_EXTINCT
COUT-P7  equivalência não autoriza deduplicação destrutiva
COUT-P8  conflito pode permanecer sem resolução
COUT-P9  COUT informa; não decide
COUT-P10 identidade cognitiva pertence ao PIA, não ao provider
```

E as três regras que decidem o comportamento em cada caso duvidoso:

```text
TRANSMISSION            != OVERWRITE
CONFLICT DETECTION      != CONFLICT RESOLUTION
SAME CURRENT STATE      != SAME CAUSAL HISTORY
```

O que o módulo **não** é: não faz merge, não resolve conflito, não
governa, não repara, não deduplica, não aprende, não guarda artefato e
não fala com nenhum provider.

```text
SYNCHRONIZATION_IS_LEARNING    = FALSE
SYNCHRONIZATION_IS_GOVERNANCE  = FALSE
SYNCHRONIZATION_IS_REPAIR      = FALSE
CONFLICT_RESOLUTION            = NOT_IMPLEMENTED
ARTIFACT_STORAGE               = DEFERRED
```
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa

from app.cognitive.errors.exceptions import SyncPackageInvalidError
from app.cognitive.repositories.sync_repository import (
    SyncRepository,
    ordered_tables,
    topologically_ordered_events,
)
from app.cognitive.schemas.synchronization import (
    SECTION_BY_TABLE,
    SYNC_FORMAT,
    SYNC_SCHEMA_VERSION,
    SyncConflict,
    SyncReport,
    decode_value,
)
from app.cognitive.services.integrity_manager import find_cycle


class SynchronizationManager:
    """Exporta e importa patrimônio cognitivo sem sobrescrever nada."""

    def __init__(self, repository: SyncRepository) -> None:
        self._repository = repository

    # --- Export -------------------------------------------------------

    def export_package(self) -> dict[str, Any]:
        """Empacota o patrimônio inteiro, de forma determinística.

        Só transporta estruturas **realmente implementadas** em `E3`:
        `CognitiveDistinction`, `CausalComparison` e `CausalClassRef`
        continuam `DEFERRED` e não aparecem no pacote — inventar seções
        vazias para elas seria fingir contrato que não existe.
        """
        package: dict[str, Any] = {
            "format": SYNC_FORMAT,
            "schema_version": SYNC_SCHEMA_VERSION,
            "exported_at": datetime.now(UTC).isoformat(),
        }
        for table in ordered_tables():
            package[SECTION_BY_TABLE[table.name]] = self._repository.read_table(table)
        return package

    # --- Import -------------------------------------------------------

    def import_package(self, package: dict[str, Any]) -> SyncReport:
        """Aplica um pacote **em uma única transação lógica**.

        Três resultados possíveis por registro:

        - id ausente no destino → **novo**, aplicado;
        - id presente com representação idêntica → **idempotente**,
          ignorado (importar duas vezes não duplica nada);
        - id presente com representação divergente → **conflito**.

        Havendo qualquer conflito, **nada é aplicado**: o import inteiro
        é abortado antes de escrever, e o relatório devolve as duas
        representações de cada colisão. Não existe vencedor automático —
        nem destino, nem origem, nem "mais novo", nem prioridade de
        provider, nem score.

        Não commita: quem chama controla a transação (`UnitOfWork`), e é
        isso que torna o rollback completo possível.
        """
        self._validate_envelope(package)
        self._assert_causal_acyclicity(package)

        conflicts: list[SyncConflict] = []
        planned: list[tuple[sa.Table, list[dict[str, Any]]]] = []
        skipped: Counter[str] = Counter()

        for table in ordered_tables():
            section = SECTION_BY_TABLE[table.name]
            rows = self._section_rows(package, section)
            new_rows, section_conflicts, section_skipped = self._classify(table, section, rows)
            conflicts.extend(section_conflicts)
            skipped[section] += section_skipped
            planned.append((table, new_rows))

        if conflicts:
            # Conflito não é falha de execução — é resultado. E não
            # aplica nada: import parcial deixaria linhagem incompleta,
            # provenance pela metade ou eventos causais órfãos.
            return SyncReport(
                conflicts=tuple(conflicts),
                applied={},
                skipped=dict(skipped),
                overwrite_count=0,
            )

        applied: dict[str, int] = {}
        for table, rows in planned:
            if table.name == "causal_history_events":
                rows = topologically_ordered_events(rows)
            count = self._repository.insert_rows(table, rows)
            if count:
                applied[SECTION_BY_TABLE[table.name]] = count
        return SyncReport(conflicts=(), applied=applied, skipped=dict(skipped), overwrite_count=0)

    # --- Preflight causal (E3.11.1) -----------------------------------

    def _assert_causal_acyclicity(self, package: dict[str, Any]) -> None:
        """Rejeita, **antes de qualquer escrita**, um pacote que
        introduziria ciclo no grafo causal global.

        Por que isto existe: `E3.9.1a` congelou
        `APPLICATION_STRUCTURAL_DAG = TRUE` porque, pelo caminho
        autorizado original, todo predecessor já estava persistido e
        nenhuma operação legítima redirecionava aresta antiga. `E3.11`
        abriu um **novo caminho autorizado de escrita** (import direto
        em tabela), e um caminho novo não pode enfraquecer o invariante
        anterior:

        ```text
        SYNCHRONIZATION_IMPORT MUST PRESERVE APPLICATION_STRUCTURAL_DAG
        SYNCHRONIZATION MUST NOT CREATE A CAUSAL HISTORY THAT THE
        AUTHORIZED SOURCE CONTRACT COULD NOT HAVE PRODUCED
        TRANSMISSION != STRUCTURAL MUTATION
        ```

        E **não** se apoia no banco para isso:

        ```text
        DB_FK_GUARANTEE               = TRUE
        DB_SELF_PREDECESSOR_GUARANTEE = TRUE
        DB_LEVEL_GLOBAL_DAG_GUARANTEE = FALSE
        FK + NO_SELF != GLOBAL_CYCLE_PROTECTION
        ```

        O grafo candidato é `destino ∪ pacote`, montado **globalmente**
        — nunca por história isolada, porque
        `CROSS_HISTORY_PREDECESSOR = ALLOWED` e
        `HISTORY_BOUNDARY != CAUSAL_BOUNDARY`. As arestas do pacote
        sobrescrevem as homônimas do destino ao montar o candidato: se
        houver divergência de representação isso também é conflito, e o
        conflito aborta o import de qualquer modo — mas o candidato
        precisa refletir o pior caso analisável.

        Reutiliza o detector **puro** de `E3.10` (`find_cycle`,
        DFS iterativo colorido, `O(V + E)`). Reutilizar a função não
        acopla Sync ao `IntegrityManager` como serviço de decisão:
        nenhum `IntegrityReport` é produzido nem consultado aqui.
        """
        edges: dict[str, str | None] = dict(self._repository.read_causal_edges())
        for row in self._section_rows(package, SECTION_BY_TABLE["causal_history_events"]):
            # `_section_rows` já rejeita registro sem `id`, com
            # mensagem própria — aqui todo registro tem identificador.
            predecessor = row.get("predecessor_event_id")
            edges[str(row["id"])] = None if predecessor is None else str(predecessor)

        adjacency: dict[uuid.UUID, list[uuid.UUID]] = {}
        for event_id, predecessor in edges.items():
            node = _as_uuid(event_id)
            if node is None:
                continue
            adjacency.setdefault(node, [])
            parent = _as_uuid(predecessor) if predecessor is not None else None
            if parent is not None:
                adjacency.setdefault(parent, [])
                adjacency[node].append(parent)

        cycle = find_cycle(adjacency)
        if cycle is not None:
            raise SyncPackageInvalidError(
                "o pacote introduziria ciclo no grafo causal global "
                f"({' -> '.join(str(event_id) for event_id in cycle)}); nenhum "
                "registro foi aplicado"
            )

    # --- Internals ----------------------------------------------------

    @staticmethod
    def _validate_envelope(package: dict[str, Any]) -> None:
        """Rejeita pacote inutilizável **antes** de qualquer escrita.

        Formato ou versão desconhecidos não são interpretados "na
        melhor das hipóteses": um pacote que não sabemos ler não pode
        aplicar nada.
        """
        if not isinstance(package, dict):
            raise SyncPackageInvalidError("pacote não é um objeto")
        if package.get("format") != SYNC_FORMAT:
            raise SyncPackageInvalidError(f"formato desconhecido: {package.get('format')!r}")
        if package.get("schema_version") != SYNC_SCHEMA_VERSION:
            raise SyncPackageInvalidError(
                f"versão de schema não suportada: {package.get('schema_version')!r}"
            )
        for section in SECTION_BY_TABLE.values():
            if section not in package:
                raise SyncPackageInvalidError(f"seção ausente: {section}")
            if not isinstance(package[section], list):
                raise SyncPackageInvalidError(f"seção {section} não é uma lista")

    @staticmethod
    def _section_rows(package: dict[str, Any], section: str) -> list[dict[str, Any]]:
        rows = package[section]
        for row in rows:
            if not isinstance(row, dict) or "id" not in row:
                raise SyncPackageInvalidError(f"registro sem 'id' na seção {section}")
        return list(rows)

    def _classify(
        self, table: sa.Table, section: str, rows: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[SyncConflict], int]:
        """Separa registros novos, idênticos e conflitantes.

        A comparação é entre **representações canônicas** — o que veio
        no pacote contra o que o destino tem, ambos no mesmo formato de
        serialização. Comparar objetos ORM levaria a falsos conflitos
        por diferenças de tipo/dialeto que não são diferenças de fato.
        """
        if not rows:
            return [], [], 0

        try:
            ids = [uuid.UUID(str(row["id"])) for row in rows]
        except ValueError as exc:
            raise SyncPackageInvalidError(f"id inválido na seção {section}: {exc}") from exc

        existing = self._repository.read_rows_by_id(table, ids)
        new_rows: list[dict[str, Any]] = []
        conflicts: list[SyncConflict] = []
        skipped = 0

        for row in rows:
            row_id = str(row["id"])
            current = existing.get(row_id)
            if current is None:
                new_rows.append(self._decode_row(table, section, row))
                continue
            if self._same_representation(row, current):
                skipped += 1
                continue
            conflicts.append(
                SyncConflict(
                    section=section,
                    entity_id=uuid.UUID(row_id),
                    incoming=dict(row),
                    existing=dict(current),
                )
            )
        return new_rows, conflicts, skipped

    @staticmethod
    def _same_representation(incoming: dict[str, Any], existing: dict[str, Any]) -> bool:
        return all(incoming.get(key) == existing.get(key) for key in set(incoming) | set(existing))

    @staticmethod
    def _decode_row(table: sa.Table, section: str, row: dict[str, Any]) -> dict[str, Any]:
        """Converte a representação de transporte de volta aos tipos da
        coluna, campo a campo, pelo tipo real declarado no modelo."""
        decoded: dict[str, Any] = {}
        for key, value in row.items():
            column = table.c.get(key)
            if column is None:
                raise SyncPackageInvalidError(f"campo desconhecido '{key}' na seção {section}")
            try:
                decoded[key] = decode_value(column, value)
            except (ValueError, TypeError, KeyError) as exc:
                raise SyncPackageInvalidError(
                    f"valor inválido para '{key}' na seção {section}: {exc}"
                ) from exc
        return decoded


def _as_uuid(value: str) -> uuid.UUID | None:
    """Converte um identificador em `UUID`, ou devolve `None` quando
    não é conversível.

    Recebe sempre `str`: o grafo candidato é montado com identificadores
    normalizados por `str()`, venham eles do pacote (texto) ou do
    destino (`UUID`).

    Identificador malformado não derruba o preflight — ele apenas não
    participa do grafo, e a rejeição específica vem depois, de
    `_decode_row`. O preflight verifica **aciclicidade**, não sintaxe.
    """
    try:
        return uuid.UUID(value)
    except ValueError:
        return None
