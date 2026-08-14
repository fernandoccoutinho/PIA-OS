"""
`IntegrityFinding` / `IntegrityReport` — modelo de diagnóstico de
`E3.10`/`LIB-10`.

Um *finding* é **observação**, não decisão, não conhecimento e não
aprendizado:

```text
FINDING  = OBSERVATION
FINDING != KNOWLEDGE
ERROR    = POSSIBLE_EVIDENCE
ERROR   != LEARNING
```

Por isso nada aqui é persistido e nada aqui tem identidade cognitiva:
sem COID, sem CLID, sem lifecycle, sem lineage, sem provenance
própria. Um finding descreve uma condição encontrada no patrimônio e
aponta onde ela está — quem decide o que fazer com ela é a governança,
que pertence a `E4` e não existe nesta entrega.

`IntegrityReport` também é transitório. Não há score, percentual de
integridade nem métrica agregada inventada: o status é binário
(`PASS`/`FAIL`) e os `counts` apenas contam findings por categoria,
para leitura humana.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.core.error_codes import ErrorSeverity


class IntegrityStatus(StrEnum):
    """Resultado global de uma auditoria. Binário de propósito —
    `97% de integridade` não significaria nada verificável."""

    PASS = "pass"
    FAIL = "fail"


class IntegrityCategory(StrEnum):
    """Área do patrimônio a que o finding se refere.

    Os três grafos permanecem em namespaces distintos
    (`LINEAGE_GRAPH`, `CAUSAL_GRAPH`, `RELATIONSHIP_GRAPH`) — nenhum
    grafo universal artificial é construído, e nenhuma categoria
    converte relação semântica em causalidade.
    """

    IDENTITY = "identity"
    LINEAGE = "lineage"
    RELATIONSHIP = "relationship"
    VERSION = "version"
    PROVENANCE = "provenance"
    CAUSAL_HISTORY = "causal_history"


class IntegrityCode(StrEnum):
    """Códigos de finding.

    Deliberadamente **não** são `ErrorCode`/`PIA-8xxx`: um ciclo
    encontrado é resultado válido da auditoria, não exceção
    (§44 do módulo). Exceções continuam reservadas a falhas de
    execução, não a condições detectadas.
    """

    LINEAGE_CYCLE = "INTEGRITY-LIN-001"
    LINEAGE_SELF_LINK = "INTEGRITY-LIN-002"
    LINEAGE_DANGLING_ENDPOINT = "INTEGRITY-LIN-003"

    RELATIONSHIP_SELF_LINK = "INTEGRITY-REL-001"
    RELATIONSHIP_NON_CANONICAL_SYMMETRIC = "INTEGRITY-REL-002"
    RELATIONSHIP_DUPLICATE_ACTIVE = "INTEGRITY-REL-003"
    RELATIONSHIP_DANGLING_ENDPOINT = "INTEGRITY-REL-004"

    VERSION_MULTIPLE_CURRENT_PER_CLID = "INTEGRITY-VER-001"

    PROVENANCE_DANGLING_COID = "INTEGRITY-PRV-001"

    CAUSAL_CYCLE = "INTEGRITY-CAU-001"
    CAUSAL_SELF_PREDECESSOR = "INTEGRITY-CAU-002"
    CAUSAL_MULTIPLE_HISTORIES_PER_SUBJECT = "INTEGRITY-CAU-003"
    CAUSAL_DANGLING_REFERENCE = "INTEGRITY-CAU-004"


@dataclass(frozen=True)
class IntegrityFinding:
    """Uma condição detectada, localizada e classificada.

    `evidence` carrega o material diagnóstico necessário para um
    humano investigar — por exemplo o `cycle_path` completo de um
    ciclo, nunca apenas `cycle = true`. Nada de conteúdo, payload ou
    transcript entra aqui: os invariantes auditados são estruturais.
    """

    code: IntegrityCode
    category: IntegrityCategory
    severity: ErrorSeverity
    entity_type: str
    entity_refs: tuple[uuid.UUID, ...]
    message: str
    evidence: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class IntegrityReport:
    """Resultado transitório de uma auditoria.

    `status` é derivado dos findings, nunca informado pelo chamador:
    qualquer finding torna o relatório `FAIL`. Relatório `PASS`
    significa "os invariantes atualmente declarados e auditáveis
    estão satisfeitos" — nunca "o patrimônio é verdadeiro sobre a
    realidade" (`INTERNALLY_CONSISTENT != TRUE_ABOUT_REALITY`).
    """

    findings: tuple[IntegrityFinding, ...]
    audited_at: datetime
    scope: str = "full"

    @property
    def status(self) -> IntegrityStatus:
        return IntegrityStatus.FAIL if self.findings else IntegrityStatus.PASS

    @property
    def counts(self) -> dict[IntegrityCategory, int]:
        """Findings por categoria. Contagem, não score."""
        return dict(Counter(finding.category for finding in self.findings))
