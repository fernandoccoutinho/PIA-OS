"""
`ConsolidationResult` — resultado transitório de uma consolidação
(`E4.5`).

Value object imutável, **não persistido**, como `MemoryContext` (E4.2),
`GovernanceResolution` (E4.3.1) e `PersistenceAssessment` (E4.4). Ele
descreve o que foi escrito e o que a verificação independente
constatou; não é uma nova fonte da verdade, e não existe tabela por
trás dele:

    NEW PERSISTENT ENTITY = NO

Carrega apenas identificadores e o `PersistenceAssessment` — nenhuma
instância ORM, nenhuma `Session`, nenhum repositório. Quem recebe o
resultado não deve herdar a capacidade de alterar patrimônio por
acidente ao segurar uma referência.

**Invariantes são impostos em `__post_init__`**, não prometidos em
docstring:

    frozen=True ALONE != DEEP IMMUTABILITY

O projeto pagou quatro vezes por essa lição — E4.2.1 (`MemoryContext`),
E4.3.2 (`GovernanceResolution`, `SafetyAssessment`), E4.4.1
(`PersistenceAssessment`) e E3.4.2.1 (ordem canônica do recibo) —
sempre pelo mesmo motivo: `frozen` protege a referência, não o
conteúdo, e o construtor direto é API pública de qualquer dataclass.
"""

import uuid
from dataclasses import dataclass

from app.memory.schemas.persistence import (
    PersistenceAssessment,
    PersistenceEvidenceKind,
    PersistenceOutcome,
)


def _uuid_tuple(campo: str, valor: object) -> tuple[uuid.UUID, ...]:
    """Converte uma coleção de UUIDs em tupla defensiva, validando tipos.

    `str` e `bytes` são recusados explicitamente: ambos são iteráveis, e
    aceitá-los transformaria `"abc"` numa coleção de caracteres em vez
    de um erro.
    """
    if isinstance(valor, str | bytes) or not hasattr(valor, "__iter__"):
        raise TypeError(
            f"{campo} deve ser uma coleção de uuid.UUID, recebido {type(valor).__name__}"
        )
    itens = tuple(valor)
    for item in itens:
        if not isinstance(item, uuid.UUID):
            raise TypeError(
                f"{campo} aceita apenas uuid.UUID, recebido {type(item).__name__}: {item!r}"
            )
    return itens


def _uuid_field(campo: str, valor: object) -> uuid.UUID:
    if not isinstance(valor, uuid.UUID):
        raise TypeError(f"{campo} deve ser uuid.UUID, recebido {type(valor).__name__}")
    return valor


@dataclass(frozen=True)
class ConsolidationResult:
    """Resultado de uma consolidação já escrita **e já verificada**.

    A presença de `persistence_assessment` não é decorativa: um
    resultado só é construível se a avaliação independente da E4.4
    confirmar que o alvo existe, não está soft-deleted e tem
    continuidade registrada. Um `ConsolidationResult` que existisse sem
    isso afirmaria uma consolidação que ninguém verificou.
    """

    source_coids: tuple[uuid.UUID, ...]
    target_coid: uuid.UUID
    target_clid: uuid.UUID | None
    transformation_id: uuid.UUID
    lineage_edge_ids: tuple[uuid.UUID, ...]
    causal_event_ids: tuple[uuid.UUID, ...]
    persistence_assessment: PersistenceAssessment
    predecessor_event_ids: tuple[uuid.UUID, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_coids", _uuid_tuple("source_coids", self.source_coids))
        object.__setattr__(
            self, "lineage_edge_ids", _uuid_tuple("lineage_edge_ids", self.lineage_edge_ids)
        )
        object.__setattr__(
            self, "causal_event_ids", _uuid_tuple("causal_event_ids", self.causal_event_ids)
        )
        object.__setattr__(
            self,
            "predecessor_event_ids",
            _uuid_tuple("predecessor_event_ids", self.predecessor_event_ids),
        )
        object.__setattr__(self, "target_coid", _uuid_field("target_coid", self.target_coid))
        object.__setattr__(
            self, "transformation_id", _uuid_field("transformation_id", self.transformation_id)
        )
        if self.target_clid is not None:
            object.__setattr__(self, "target_clid", _uuid_field("target_clid", self.target_clid))

        self._validar_estrutura()
        self._validar_assessment()

    # --- Estrutura -----------------------------------------------------

    def _validar_estrutura(self) -> None:
        if len(self.source_coids) < 2:
            raise ValueError(
                "uma consolidação exige ao menos duas fontes — com uma única fonte não há "
                "o que consolidar, e a operação correta é uma derivação simples"
            )
        if len(set(self.source_coids)) != len(self.source_coids):
            raise ValueError(
                "fontes duplicadas não são desduplicadas silenciosamente: "
                "DUPLICATE SOURCE = INVALID INPUT"
            )
        if list(self.source_coids) != sorted(self.source_coids):
            raise ValueError(
                "source_coids deve estar em ordem canônica estrita por UUID. O resultado "
                "NÃO reordena: `lineage_edge_ids` mantém correspondência posicional com as "
                "fontes, e reordenar apenas os COIDs separaria cada fonte da sua edge, "
                "fabricando um pareamento inexistente"
            )
        if self.target_coid in self.source_coids:
            raise ValueError(
                "o alvo de uma consolidação é um CognitiveObject novo — nunca uma das "
                "próprias fontes (CONSOLIDATION != DELETION; MERGE != IDENTITY COLLAPSE)"
            )
        if len(self.lineage_edge_ids) != len(self.source_coids):
            raise ValueError(
                f"esperada exatamente uma LineageEdge(MERGE) por fonte: "
                f"{len(self.source_coids)} fontes, {len(self.lineage_edge_ids)} edges"
            )
        if len(set(self.lineage_edge_ids)) != len(self.lineage_edge_ids):
            raise ValueError("lineage_edge_ids não pode conter repetições")
        if not self.causal_event_ids:
            raise ValueError(
                "toda consolidação registra ao menos um evento causal: a ocorrência da "
                "própria operação é fato conhecido (OPERATION OCCURRENCE = KNOWN FACT)"
            )
        if len(set(self.causal_event_ids)) != len(self.causal_event_ids):
            raise ValueError("causal_event_ids não pode conter repetições")
        if len(set(self.predecessor_event_ids)) != len(self.predecessor_event_ids):
            raise ValueError(
                "predecessor_event_ids não pode conter repetições — declarar o mesmo "
                "evento duas vezes duplicaria a história sem acrescentar fato"
            )

        if not self.predecessor_event_ids:
            if len(self.causal_event_ids) != 1:
                raise ValueError(
                    "sem predecessor declarado, exatamente um evento-raiz é registrado; "
                    f"recebidos {len(self.causal_event_ids)} eventos"
                )
        elif len(self.causal_event_ids) != len(self.predecessor_event_ids):
            raise ValueError(
                f"com predecessores declarados espera-se um evento por predecessor: "
                f"{len(self.predecessor_event_ids)} predecessores, "
                f"{len(self.causal_event_ids)} eventos"
            )

    # --- Verificação independente (E4.4) --------------------------------

    def _validar_assessment(self) -> None:
        """O assessment precisa ser sobre **este** alvo e confirmá-lo.

        Estas quatro regras vivem aqui, e não apenas no
        `ConsolidationManager`, porque o construtor direto é API pública:
        um resultado montado à mão com o assessment de outro objeto — ou
        com `SUBJECT_NOT_FOUND` — afirmaria uma consolidação verificada
        que nunca foi verificada.
        """
        if not isinstance(self.persistence_assessment, PersistenceAssessment):
            raise TypeError(
                "persistence_assessment deve ser um PersistenceAssessment, recebido "
                f"{type(self.persistence_assessment).__name__}"
            )
        if self.persistence_assessment.coid != self.target_coid:
            raise ValueError(
                f"o assessment é sobre {self.persistence_assessment.coid}, não sobre o "
                f"alvo {self.target_coid} — avaliação de outro objeto não prova nada "
                "sobre este"
            )
        if self.persistence_assessment.outcome is PersistenceOutcome.SUBJECT_NOT_FOUND:
            raise ValueError(
                "o alvo acabou de ser escrito nesta transação; SUBJECT_NOT_FOUND "
                "significa que não há linha com este COID, o que contradiz o recibo"
            )
        if self.persistence_assessment.outcome is not (
            PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE
        ):
            raise ValueError(
                "uma consolidação verificada exige RECORDED_CONTINUITY_EVIDENCE: sem "
                "evidência registrada, `S1 ← {M1, ..., Mn}` não ficou materializado"
            )
        if self.persistence_assessment.subject_deleted:
            raise ValueError(
                "o alvo de uma consolidação recém-criada não pode aparecer como "
                "soft-deleted — a E4.5 não apaga nada, nem o que acabou de criar"
            )

    # --- Consultas ------------------------------------------------------

    @property
    def source_count(self) -> int:
        """Quantidade de fontes consolidadas."""
        return len(self.source_coids)

    def lineage_edge_for(self, source_coid: uuid.UUID) -> uuid.UUID:
        """Edge correspondente a uma fonte, pela posição.

        Existe para que consumidores leiam a correspondência
        fonte ↔ edge sem reimplementar o pareamento posicional por
        conta própria — e errá-lo.
        """
        try:
            posicao = self.source_coids.index(source_coid)
        except ValueError:
            raise ValueError(f"{source_coid} não é uma das fontes desta consolidação") from None
        return self.lineage_edge_ids[posicao]

    def evidence_of(self, kind: PersistenceEvidenceKind) -> tuple[object, ...]:
        """Atalho para a evidência do assessment, por tipo."""
        return self.persistence_assessment.evidence_of(kind)
