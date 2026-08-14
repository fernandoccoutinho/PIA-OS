"""
`IntegrityManager` — auditoria global read-only (`E3.10`/`LIB-10`).

Responde a uma pergunta e só a ela:

> O patrimônio cognitivo persistido continua satisfazendo os
> invariantes estruturais e históricos **atualmente declarados** pelo
> PIA-OS?

```text
INTEGRITY = OBSERVATION + VERIFICATION + DIAGNOSIS
INTEGRITY != DECISION + REPAIR
```

O módulo **detecta, localiza, classifica e reporta**. Não repara, não
governa, não arbitra, não sincroniza, não resolve conflito, não muda
política, não toca no Kernel e não inventa história.

```text
AUTOMATIC_REPAIR        = NOT_IMPLEMENTED
AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN
GOVERNANCE_ENGINE       = OUT_OF_SCOPE_E3   (E4)
SYNCHRONIZATION         = E3.11
MULTI_AI_ORCHESTRATION  = E7
```

E um limite que é fácil de atravessar por acidente e que fica
explícito aqui: **finding não é aprendizado**.

```text
FINDING = OBSERVATION      FINDING != KNOWLEDGE
ERROR   = POSSIBLE_EVIDENCE  ERROR != LEARNING
PIA_LEARNING_SOURCE = VALIDATED_EXPERIENCE
```

Um finding pode virar evidência num fluxo futuro
(`experiência → evidência → avaliação → validação → aprendizado →
proposta de melhoria → governança → evolução controlada`), mas nenhuma
parte executável desse ciclo pertence a `E3.10`, e erro nunca é fonte
automática de aprendizado — resultado repetidamente superior,
descoberta nova, comparação Multi-IA e evidência externa também
produzem evidência.

Princípios COUT que o módulo precisa respeitar para não gerar falso
positivo:

```text
DETECTED INCONSISTENCY != AUTHORIZATION TO ERASE HISTORY
CURRENT INVALIDITY     != HISTORICAL NON-EXISTENCE
DISTINCTION EXTINCTION != HISTORICAL ERASURE
INTEGRITY FAILURE      != EPISTEMIC NON-EXISTENCE
MISSING EVIDENCE       != AUTHORIZATION TO FABRICATE
INTERNALLY_CONSISTENT  != TRUE_ABOUT_REALITY
```
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime

from app.cognitive.repositories.integrity_repository import IntegrityRepository
from app.cognitive.schemas.integrity import (
    IntegrityCategory,
    IntegrityCode,
    IntegrityFinding,
    IntegrityReport,
)
from app.core.error_codes import ErrorSeverity

#: Cores do DFS iterativo. `GRAY` = em processamento na pilha atual;
#: reencontrar um nó `GRAY` fecha um ciclo.
_WHITE, _GRAY, _BLACK = 0, 1, 2


def find_cycle(adjacency: Mapping[uuid.UUID, Sequence[uuid.UUID]]) -> list[uuid.UUID] | None:
    """Encontra **um** ciclo dirigido, se existir, e devolve o caminho
    fechado (`[A, B, C, A]`). `None` quando o grafo é acíclico.

    Algoritmo: DFS iterativo com coloração branco/cinza/preto.
    Complexidade `O(V + E)`, memória `O(V)`. Iterativo de propósito —
    a versão recursiva estouraria o limite de recursão do Python em
    cadeias de linhagem longas, e um `RecursionError` durante uma
    auditoria seria a pior forma possível de "resultado".

    Determinístico: a iteração segue a ordem em que as arestas foram
    lidas do banco (`created_at ASC, id ASC`), então o mesmo
    patrimônio devolve sempre o mesmo ciclo.

    Função pura: não conhece banco, sessão nem domínio — recebe
    adjacência, devolve caminho. É o que permite testá-la
    exaustivamente sem precisar corromper um banco real.
    """
    color: dict[uuid.UUID, int] = {}
    parent: dict[uuid.UUID, uuid.UUID | None] = {}

    for root in adjacency:
        if color.get(root, _WHITE) != _WHITE:
            continue
        stack: list[tuple[uuid.UUID, int]] = [(root, 0)]
        color[root] = _GRAY
        parent[root] = None
        while stack:
            node, index = stack[-1]
            neighbours = adjacency.get(node, ())
            if index >= len(neighbours):
                color[node] = _BLACK
                stack.pop()
                continue
            stack[-1] = (node, index + 1)
            neighbour = neighbours[index]
            state = color.get(neighbour, _WHITE)
            if state == _GRAY:
                return _rebuild_cycle(parent, node, neighbour)
            if state == _WHITE:
                color[neighbour] = _GRAY
                parent[neighbour] = node
                stack.append((neighbour, 0))
    return None


def _rebuild_cycle(
    parent: Mapping[uuid.UUID, uuid.UUID | None], node: uuid.UUID, target: uuid.UUID
) -> list[uuid.UUID]:
    """Reconstrói o caminho fechado subindo pelos pais até `target`."""
    path = [node]
    current = node
    while current != target:
        previous = parent[current]
        if previous is None:  # pragma: no cover - alcançável só com pai ausente
            break
        current = previous
        path.append(current)
    path.reverse()
    path.append(target)
    return path


def _adjacency(edges: Iterable[tuple[uuid.UUID, uuid.UUID]]) -> dict[uuid.UUID, list[uuid.UUID]]:
    adjacency: dict[uuid.UUID, list[uuid.UUID]] = {}
    for source, target in edges:
        adjacency.setdefault(source, []).append(target)
        adjacency.setdefault(target, [])
    return adjacency


class IntegrityManager:
    """Auditoria global do patrimônio cognitivo — read-only."""

    def __init__(self, repository: IntegrityRepository) -> None:
        self._repository = repository

    def audit(self) -> IntegrityReport:
        """Executa todas as verificações e devolve o relatório.

        Não levanta exceção por condição detectada: um ciclo
        encontrado é **resultado válido** da auditoria, não falha de
        execução. Relatório vazio significa `PASS`.
        """
        findings: list[IntegrityFinding] = []
        findings.extend(self._audit_lineage())
        findings.extend(self._audit_relationships())
        findings.extend(self._audit_versions())
        findings.extend(self._audit_provenance())
        findings.extend(self._audit_causal_history())
        return IntegrityReport(findings=tuple(findings), audited_at=datetime.now(UTC))

    # --- Lineage ------------------------------------------------------

    def _audit_lineage(self) -> list[IntegrityFinding]:
        findings: list[IntegrityFinding] = []
        edges = self._repository.lineage_edges()

        # FULL_DAG — o débito que E3.3 deixou explicitamente para E3.10.
        cycle = find_cycle(_adjacency([(parent, child) for _, parent, child in edges]))
        if cycle is not None:
            involved = set(cycle)
            edge_ids = [
                edge_id
                for edge_id, parent, child in edges
                if parent in involved and child in involved
            ]
            findings.append(
                IntegrityFinding(
                    code=IntegrityCode.LINEAGE_CYCLE,
                    category=IntegrityCategory.LINEAGE,
                    severity=ErrorSeverity.ERROR,
                    entity_type="LineageEdge",
                    entity_refs=tuple(edge_ids),
                    message=(
                        "Ciclo detectado no grafo de linhagem — derivação não pode " "ser circular."
                    ),
                    evidence={
                        "cycle_path": [str(coid) for coid in cycle],
                        "involved_coids": [str(coid) for coid in cycle[:-1]],
                        "involved_edge_ids": [str(edge_id) for edge_id in edge_ids],
                        "cycle_length": len(cycle) - 1,
                    },
                )
            )

        self_links = self._repository.lineage_self_links()
        if self_links:
            findings.append(
                IntegrityFinding(
                    code=IntegrityCode.LINEAGE_SELF_LINK,
                    category=IntegrityCategory.LINEAGE,
                    severity=ErrorSeverity.ERROR,
                    entity_type="LineageEdge",
                    entity_refs=tuple(self_links),
                    message="Aresta de linhagem com parent_coid == child_coid.",
                )
            )

        dangling = self._repository.lineage_dangling_endpoints()
        if dangling:
            findings.append(
                IntegrityFinding(
                    code=IntegrityCode.LINEAGE_DANGLING_ENDPOINT,
                    category=IntegrityCategory.LINEAGE,
                    severity=ErrorSeverity.ERROR,
                    entity_type="LineageEdge",
                    entity_refs=tuple(dangling),
                    message=(
                        "Aresta de linhagem referencia CognitiveObject inexistente. "
                        "O objeto ausente NÃO é criado: referência pendente é "
                        "diagnóstico, não autorização para fabricar."
                    ),
                )
            )
        return findings

    # --- Relationship -------------------------------------------------

    def _audit_relationships(self) -> list[IntegrityFinding]:
        """Auditoria de `Relationship`.

        `RELATIONSHIP_DAG = NOT_APPLICABLE`: relações podem formar
        ciclos legitimamente (`A RELATED_TO B`, `B RELATED_TO A` é o
        caso trivial), e relações contraditórias entre os mesmos
        objetos são permitidas pelo contrato — `RelationshipEngine`
        nunca arbitrou conflito. Só invariantes realmente congelados
        são auditados aqui.
        """
        findings: list[IntegrityFinding] = []

        self_links = self._repository.relationship_self_links()
        if self_links:
            findings.append(
                IntegrityFinding(
                    code=IntegrityCode.RELATIONSHIP_SELF_LINK,
                    category=IntegrityCategory.RELATIONSHIP,
                    severity=ErrorSeverity.ERROR,
                    entity_type="Relationship",
                    entity_refs=tuple(self_links),
                    message="Relação com source_coid == target_coid.",
                )
            )

        non_canonical = self._repository.non_canonical_symmetric_relationships()
        if non_canonical:
            findings.append(
                IntegrityFinding(
                    code=IntegrityCode.RELATIONSHIP_NON_CANONICAL_SYMMETRIC,
                    category=IntegrityCategory.RELATIONSHIP,
                    severity=ErrorSeverity.ERROR,
                    entity_type="Relationship",
                    entity_refs=tuple(non_canonical),
                    message=(
                        "RELATED_TO gravada fora da ordem canônica (source < target), "
                        "quebrando a normalização de simetria de E3.5.1."
                    ),
                )
            )

        duplicates = self._repository.duplicate_active_relationships()
        if duplicates:
            findings.append(
                IntegrityFinding(
                    code=IntegrityCode.RELATIONSHIP_DUPLICATE_ACTIVE,
                    category=IntegrityCategory.RELATIONSHIP,
                    severity=ErrorSeverity.ERROR,
                    entity_type="Relationship",
                    entity_refs=(),
                    message=(
                        "Mais de uma relação ATIVA para a mesma tripla "
                        "(source, target, type). Relações já retiradas podem "
                        "repetir a tripla — isso é o lifecycle previsto, não "
                        "corrupção."
                    ),
                    evidence={
                        "duplicates": [
                            {
                                "source_coid": str(source),
                                "target_coid": str(target),
                                "relationship_type": str(relationship_type),
                                "active_count": count,
                            }
                            for source, target, relationship_type, count in duplicates
                        ]
                    },
                )
            )

        dangling = self._repository.relationship_dangling_endpoints()
        if dangling:
            findings.append(
                IntegrityFinding(
                    code=IntegrityCode.RELATIONSHIP_DANGLING_ENDPOINT,
                    category=IntegrityCategory.RELATIONSHIP,
                    severity=ErrorSeverity.ERROR,
                    entity_type="Relationship",
                    entity_refs=tuple(dangling),
                    message="Relação referencia CognitiveObject inexistente.",
                )
            )
        return findings

    # --- Version ------------------------------------------------------

    def _audit_versions(self) -> list[IntegrityFinding]:
        duplicates = self._repository.clids_with_multiple_current()
        if not duplicates:
            return []
        return [
            IntegrityFinding(
                code=IntegrityCode.VERSION_MULTIPLE_CURRENT_PER_CLID,
                category=IntegrityCategory.VERSION,
                severity=ErrorSeverity.ERROR,
                entity_type="CognitiveObject",
                entity_refs=tuple(clid for clid, _ in duplicates),
                message=(
                    "Mais de um objeto CURRENT para o mesmo CLID — invariante "
                    "COUNT(CURRENT) <= 1 por CLID violado. Objetos SUPERSEDED "
                    "continuam patrimônio legítimo e não são contados aqui."
                ),
                evidence={
                    "clids": [
                        {"clid": str(clid), "current_count": count} for clid, count in duplicates
                    ]
                },
            )
        ]

    # --- Provenance ---------------------------------------------------

    def _audit_provenance(self) -> list[IntegrityFinding]:
        """Auditoria de `ProvenanceRecord` — apenas invariantes
        congelados.

        `provider_id`/`model_id` ausentes **nunca** são finding: são
        opcionais por contrato desde `E3.6`, inclusive para
        `actor_type = AGENT`. E nenhuma proveniência faltante é
        inventada.
        """
        dangling = self._repository.provenance_dangling_coids()
        if not dangling:
            return []
        return [
            IntegrityFinding(
                code=IntegrityCode.PROVENANCE_DANGLING_COID,
                category=IntegrityCategory.PROVENANCE,
                severity=ErrorSeverity.ERROR,
                entity_type="ProvenanceRecord",
                entity_refs=tuple(dangling),
                message="ProvenanceRecord ancorado em CognitiveObject inexistente.",
            )
        ]

    # --- Causal history -----------------------------------------------

    def _audit_causal_history(self) -> list[IntegrityFinding]:
        """Auditoria do grafo causal **global**.

        `E3.9.1a` classificou a aciclicidade como
        `APPLICATION_STRUCTURAL_DAG = TRUE` /
        `DB_LEVEL_GLOBAL_DAG_GUARANTEE = FALSE`. Esta auditoria é a
        defesa diagnóstica correspondente — e **não** altera aquela
        classificação: `INTEGRITY_AUDIT != DB_CONSTRAINT`.

        O grafo é auditado globalmente porque
        `HISTORY_BOUNDARY != CAUSAL_BOUNDARY`: predecessor em outra
        história é legítimo (`E3.9.1`) e nunca é finding por si só.
        Precedência temporal também não vira causalidade aqui —
        `created_at`/`occurred_at` não são usados para inferir aresta
        alguma.
        """
        findings: list[IntegrityFinding] = []
        edges = self._repository.causal_edges()

        cycle = find_cycle(_adjacency(edges))
        if cycle is not None:
            findings.append(
                IntegrityFinding(
                    code=IntegrityCode.CAUSAL_CYCLE,
                    category=IntegrityCategory.CAUSAL_HISTORY,
                    severity=ErrorSeverity.ERROR,
                    entity_type="CausalHistoryEvent",
                    entity_refs=tuple(cycle[:-1]),
                    message=(
                        "Ciclo detectado no grafo causal global — um evento não "
                        "pode ser causalmente anterior a si mesmo."
                    ),
                    evidence={
                        "cycle_path": [str(event_id) for event_id in cycle],
                        "involved_event_ids": [str(event_id) for event_id in cycle[:-1]],
                        "cycle_length": len(cycle) - 1,
                    },
                )
            )

        self_predecessors = self._repository.causal_self_predecessors()
        if self_predecessors:
            findings.append(
                IntegrityFinding(
                    code=IntegrityCode.CAUSAL_SELF_PREDECESSOR,
                    category=IntegrityCategory.CAUSAL_HISTORY,
                    severity=ErrorSeverity.ERROR,
                    entity_type="CausalHistoryEvent",
                    entity_refs=tuple(self_predecessors),
                    message="Evento causal declarado como predecessor de si mesmo.",
                )
            )

        subjects = self._repository.subjects_with_multiple_histories()
        if subjects:
            findings.append(
                IntegrityFinding(
                    code=IntegrityCode.CAUSAL_MULTIPLE_HISTORIES_PER_SUBJECT,
                    category=IntegrityCategory.CAUSAL_HISTORY,
                    severity=ErrorSeverity.ERROR,
                    entity_type="CausalHistory",
                    entity_refs=tuple(subject for subject, _ in subjects),
                    message=(
                        "Mais de uma CausalHistory para o mesmo sujeito — "
                        "ONE_HISTORY_PER_SUBJECT violado."
                    ),
                    evidence={
                        "subjects": [
                            {"subject_coid": str(subject), "history_count": count}
                            for subject, count in subjects
                        ]
                    },
                )
            )

        dangling = self._repository.causal_dangling_subjects()
        dangling_predecessors = self._repository.causal_dangling_predecessors()
        if dangling or dangling_predecessors:
            findings.append(
                IntegrityFinding(
                    code=IntegrityCode.CAUSAL_DANGLING_REFERENCE,
                    category=IntegrityCategory.CAUSAL_HISTORY,
                    severity=ErrorSeverity.ERROR,
                    entity_type="CausalHistory/CausalHistoryEvent",
                    entity_refs=tuple(dangling) + tuple(dangling_predecessors),
                    message=(
                        "História ou evento causal referencia entidade inexistente. "
                        "Nada é fabricado para preencher a lacuna."
                    ),
                    evidence={
                        "dangling_history_subjects": [str(i) for i in dangling],
                        "dangling_event_predecessors": [str(i) for i in dangling_predecessors],
                    },
                )
            )
        return findings
