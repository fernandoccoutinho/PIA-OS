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
    PersistenceEvidence,
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


LINEAGE_MERGE_QUALIFIER = "merge"
"""Token **exatamente como persistido** em `lineage_edges.relation_type`.

Minúsculo porque a E3.3 mapeia o enum com `values_callable`, gravando o
`.value` de `LineageRelation.MERGE`.

    CONSOLIDATION REQUIRES LineageEdge(MERGE)
    BRANCH != MERGE      DIVERGENCE != CONSOLIDATION
"""

CAUSAL_TRANSFORMED_QUALIFIER = "TRANSFORMED"
"""Token **exatamente como persistido** em `causal_history_events.event_type`.

Maiúsculo porque a E3.9 **não** usa `values_callable`, gravando o NOME
do membro de `CausalEventType.TRANSFORMED`.

    CONSOLIDATION REQUIRES CausalHistoryEvent(TRANSFORMED)
    EVENT IDENTITY != EVENT TYPE

A diferença de capitalização entre os dois tokens não é descuido: são
contratos persistidos distintos, conhecidos e registrados desde a E4.4.

    PERSISTED ENUM ASYMMETRY = KNOWN AND PRESERVED
    ASYMMETRY != AUTHORIZATION TO IGNORE SEMANTICS

A comparação é de **igualdade exata**, sem `lower()`, `upper()` ou
qualquer normalização — a E4.4.1 congelou que `qualifier` carrega o
token como está gravado, e é justamente isso que torna a igualdade
exata verificável aqui sem importar enum algum da E3.
"""


def verificar_coerencia_consolidacao(
    *,
    source_coids: tuple[uuid.UUID, ...],
    target_coid: uuid.UUID,
    target_clid: uuid.UUID | None,
    transformation_id: uuid.UUID,
    lineage_edge_ids: tuple[uuid.UUID, ...],
    causal_event_ids: tuple[uuid.UUID, ...],
    assessment: PersistenceAssessment,
) -> tuple[str, ...]:
    """Confronta uma consolidação declarada com o `PersistenceAssessment`.

    **Única** implementação da semântica de coerência (corretivo
    E4.5.1). É usada pelos dois caminhos:

    - `ConsolidationResult.__post_init__`, que recusa construção direta
      incoerente com `ValueError`;
    - `ConsolidationManager`, que converte divergência pós-escrita em
      `ConsolidationVerificationError` (`PIA-8032`).

    Duas implementações independentes da mesma regra divergem com o
    tempo — e foi exatamente o que aconteceu na E4.5, onde o manager
    verificava sete coisas e o value object apenas três.

    Devolve **todos** os motivos, não o primeiro: uma divergência
    raramente vem sozinha, e parar na primeira obrigaria a auditoria a
    descobrir as demais uma execução por vez. Tupla vazia significa
    coerente.

    Função pura: não lê banco, não escreve, não repara e não
    reclassifica nada.

        MISSING EVIDENCE != AUTHORIZATION TO FABRICATE HISTORY
    """
    motivos: list[str] = []

    # --- 1 a 3: identidade e estado do sujeito ------------------------
    if assessment.coid != target_coid:
        motivos.append(
            f"assessment é sobre {assessment.coid}, não sobre o alvo {target_coid} — "
            "avaliação de outro objeto não prova nada sobre este"
        )
    if assessment.outcome is PersistenceOutcome.SUBJECT_NOT_FOUND:
        motivos.append(
            "SUBJECT_NOT_FOUND significa que não há linha com este COID, o que "
            "contradiz o recibo de uma escrita recém-realizada"
        )
    elif assessment.outcome is not PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE:
        motivos.append(
            f"outcome {assessment.outcome} — uma consolidação verificada exige "
            "RECORDED_CONTINUITY_EVIDENCE"
        )
    if assessment.subject_deleted:
        motivos.append(
            "alvo recém-criado aparece como soft-deleted — a E4.5 não apaga nada, "
            "nem o que acabou de criar"
        )

    # --- 4 a 8: linhagem ----------------------------------------------
    linhagem = assessment.evidence_of(PersistenceEvidenceKind.LINEAGE_PARENT)
    if len(linhagem) != len(source_coids):
        motivos.append(f"{len(linhagem)} evidências LINEAGE_PARENT para {len(source_coids)} fontes")
    if {e.related_coid for e in linhagem} != set(source_coids):
        motivos.append("conjunto de fontes na linhagem difere do declarado")
    if {e.reference for e in linhagem} != {str(e) for e in lineage_edge_ids}:
        motivos.append("ids das edges na linhagem diferem dos declarados")

    # Pareamento POSICIONAL: os dois conjuntos acima podem bater com o
    # pareamento trocado, e uma consolidação em que a edge de M1 aponta
    # para M2 registra uma origem que nunca existiu.
    por_referencia = {e.reference: e for e in linhagem}
    for fonte, edge_id in zip(source_coids, lineage_edge_ids, strict=False):
        evidencia = por_referencia.get(str(edge_id))
        if evidencia is not None and evidencia.related_coid != fonte:
            motivos.append(
                f"edge {edge_id} deveria apontar para a fonte {fonte}, mas aponta "
                f"para {evidencia.related_coid}"
            )

    divergentes = sorted(
        {e.qualifier for e in linhagem if e.qualifier != LINEAGE_MERGE_QUALIFIER},
        key=str,
    )
    if divergentes:
        motivos.append(
            f"linhagem com qualifier {divergentes} — consolidação exige "
            f"LineageEdge({LINEAGE_MERGE_QUALIFIER!r}); BRANCH != MERGE"
        )

    # --- 9 e 10: transformação ----------------------------------------
    saidas = assessment.evidence_of(PersistenceEvidenceKind.TRANSFORMATION_OUTPUT)
    if len(saidas) != 1:
        motivos.append(f"{len(saidas)} evidências TRANSFORMATION_OUTPUT — esperada exatamente 1")
    elif saidas[0].reference != str(transformation_id):
        motivos.append(
            f"transformação registrada {saidas[0].reference} difere da declarada "
            f"{transformation_id}"
        )

    # --- 11 a 13: causalidade -----------------------------------------
    causais = assessment.evidence_of(PersistenceEvidenceKind.CAUSAL_EVENT)
    # Cardinalidade ANTES do conjunto: comparar só conjuntos mascararia
    # eventos repetidos ou sobrando.
    if len(causais) != len(causal_event_ids):
        motivos.append(
            f"{len(causais)} evidências CAUSAL_EVENT para {len(causal_event_ids)} "
            "eventos declarados"
        )
    if {e.reference for e in causais} != {str(e) for e in causal_event_ids}:
        motivos.append("eventos causais registrados diferem dos declarados")

    tipos_divergentes = sorted(
        {e.qualifier for e in causais if e.qualifier != CAUSAL_TRANSFORMED_QUALIFIER},
        key=str,
    )
    if tipos_divergentes:
        motivos.append(
            f"evento causal com qualifier {tipos_divergentes} — consolidação exige "
            f"CausalHistoryEvent({CAUSAL_TRANSFORMED_QUALIFIER!r})"
        )

    # --- 14: CLID ------------------------------------------------------
    # A E4.5 não DECIDE CLID (a regra é da E3.4.2); aqui só se confere
    # que os dois lados contam a mesma história. `None` dos dois lados é
    # coerência, não falha.
    if assessment.clid != target_clid:
        motivos.append(
            f"CLID do assessment ({assessment.clid}) difere do declarado ({target_clid})"
        )

    return tuple(motivos)


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
        """Delega à função pura compartilhada (corretivo E4.5.1).

        Antes desta correção só três regras viviam aqui — alvo, outcome e
        `subject_deleted` — enquanto a coerência **material** (qualifier
        de linhagem, pareamento posicional, referência da transformação,
        identidade e tipo dos eventos causais, CLID) existia apenas no
        `ConsolidationManager`. O construtor direto, que é API pública de
        qualquer dataclass, contornava tudo isso, e o docstring desta
        classe afirmava "já escrito **e já verificado**" — uma afirmação
        que a própria API contradizia.

        É a mesma classe de defeito corrigida em E4.2.1, E4.3.2, E4.4.1 e
        E3.4.2.1:

            INVARIANT IN MANAGER ONLY != VALUE OBJECT INVARIANT
            PUBLIC CONSTRUCTOR        != BYPASS PATH

        Agora existe **uma** implementação da semântica, usada pelos dois
        caminhos. Duas implementações independentes divergem com o
        tempo — e divergiram.
        """
        if not isinstance(self.persistence_assessment, PersistenceAssessment):
            raise TypeError(
                "persistence_assessment deve ser um PersistenceAssessment, recebido "
                f"{type(self.persistence_assessment).__name__}"
            )
        motivos = verificar_coerencia_consolidacao(
            source_coids=self.source_coids,
            target_coid=self.target_coid,
            target_clid=self.target_clid,
            transformation_id=self.transformation_id,
            lineage_edge_ids=self.lineage_edge_ids,
            causal_event_ids=self.causal_event_ids,
            assessment=self.persistence_assessment,
        )
        if motivos:
            raise ValueError(
                "assessment incoerente com a consolidação declarada: " + "; ".join(motivos)
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

    def evidence_of(self, kind: PersistenceEvidenceKind) -> tuple[PersistenceEvidence, ...]:
        """Atalho para a evidência do assessment, por tipo."""
        return self.persistence_assessment.evidence_of(kind)
