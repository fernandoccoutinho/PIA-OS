"""
`ConsolidationManager` — E4.5.

## O que este módulo é

Orquestração, disciplina e **verificação**. Não é uma nova fonte da
verdade:

```
NEW PERSISTENT ENTITY = NO    NEW TABLE = NO
NEW COLUMN            = NO    NEW MIGRATION = NO
```

O alvo consolidado continua sendo um `CognitiveObject` da E3; a origem
continua sendo `LineageEdge(MERGE)`; a operação continua sendo um
`TransformationRecord(DERIVATION)`; a ocorrência continua sendo um
`CausalHistoryEvent(TRANSFORMED)`. Toda escrita pertence à E3.

```
fontes M1...Mn → E4.5 valida → porta → E3.4.2 grava
               → E4.4 avalia → E4.5 verifica → ConsolidationResult
```

## O que ela preserva

```
CONSOLIDATION != DELETION
SUMMARY       != SOURCE REPLACEMENT
MERGE         != IDENTITY COLLAPSE
NO SILENT SOURCE ERASURE
DECLARED_LOSS_ON_CONSOLIDATION = MANDATORY
```

Nenhuma fonte é tocada: nem COID, CLID, `RevisionStatus`,
`AccessibilityState`, `deleted_at`, proveniência, história causal ou
membership de domínio. Fontes soft-deleted participam estruturalmente
sem serem recuperadas — `SOFT_DELETED != NEVER EXISTED` — e isso é
mecanismo, não autorização de acesso.

## O que ela não faz

Não gera resumo, não chama provider, não escolhe a melhor fonte, não
ranqueia, não resolve divergência, não calcula similaridade, não usa
embedding nem vector DB, não executa Search nem Retrieval, não altera
domínio ou acessibilidade, não inicia retenção, não promove nada a
aprendizado, não guarda transcript nem artifact.

```
SYNTHESIS CONTENT GENERATION = OUTSIDE E4_5
COUT INFORMS; DOES NOT DECIDE
```

Também não decide autorização. A matriz G congela
`E4.5 hard deps = {E3, E4.0, E4.4}`, e receber uma `GovernanceResolution`
só para parecer governada seria pior que não recebê-la:

```
PERMISSION TO CONSOLIDATE != CONSOLIDATION IMPLEMENTATION
```

## Fronteira estrutural

`app/memory` não importa `app.cognitive`. O writer chega pela porta
`MultiInputTransformationPort`, satisfeita estruturalmente pelo
`MultiInputTransformationManager` real (E3.4.2) e injetada pelo
compositor.
"""

import uuid
from collections.abc import Iterable
from datetime import datetime

from app.memory.errors.exceptions import ConsolidationVerificationError
from app.memory.ports.consolidation import (
    MultiInputTransformationPort,
    MultiInputTransformationReceiptPort,
)
from app.memory.schemas.consolidation import ConsolidationResult
from app.memory.schemas.persistence import (
    PersistenceAssessment,
    PersistenceEvidenceKind,
    PersistenceOutcome,
)
from app.memory.services.persistence_manager import PersistenceManager
from app.utils.logger import get_logger

logger = get_logger("app.memory.services.consolidation_manager")

CONSOLIDATION_OPERATION_TYPE = "consolidate"
"""`operation_type` estável gravado no `TransformationRecord`.

Fixo de propósito, e não parâmetro do chamador: quem invoca a E4.5
solicitou uma **consolidação**. Deixar a mesma API gravar nomes
arbitrários faria o registro do patrimônio deixar de identificar a
operação que de fato ocorreu, e a própria palavra perderia significado
na auditoria posterior."""


def _declaracoes(campo: str, valor: object, *, obrigatorio: bool) -> list[str]:
    """Materializa e valida uma coleção de declarações textuais.

    `str` é recusado mesmo sendo iterável: aceitá-lo transformaria
    `"perdeu contexto"` numa lista de caracteres, e a declaração viraria
    ruído em vez de erro.

    `strip()` aparece **apenas como predicado** de branco. O texto
    encaminhado é exatamente o que o chamador declarou — normalizar uma
    declaração é alterá-la.
    """
    if isinstance(valor, str | bytes) or not hasattr(valor, "__iter__"):
        raise TypeError(f"{campo} deve ser uma coleção de strings, recebido {type(valor).__name__}")
    itens = list(valor)
    for item in itens:
        if not isinstance(item, str):
            raise TypeError(f"{campo} aceita apenas strings, recebido {type(item).__name__}")
        if not item.strip():
            raise ValueError(f"{campo} não aceita declaração vazia ou só com espaços")
    if obrigatorio and not itens:
        raise ValueError(
            f"{campo} é obrigatório numa consolidação "
            "(DECLARED_LOSS_ON_CONSOLIDATION = MANDATORY). Uma lista vazia afirmaria "
            "que nada foi perdido, e preencher automaticamente com 'none' ou 'sem "
            "perdas' seria a mesma afirmação, só que escondida: "
            "MISSING LOSS DECLARATION != LOSSLESS EQUIVALENCE"
        )
    return itens


class ConsolidationManager:
    """Consolida N fontes num alvo novo, preservando todas elas.

    Não cria `Session`, não cria `UnitOfWork`, não commita, não faz
    rollback, não captura erro para continuar e não escreve em tabela
    alguma:

    ```
    DATABASE_WRITES_BY_APP_MEMORY_DIRECTLY = 0
    INTERNAL_COMMIT = 0
    ```

    A porta E3 e o `PersistenceManager` precisam ser compostos sobre a
    **mesma** `Session`/`UnitOfWork` — sem isso a avaliação não enxerga
    as escritas ainda não commitadas e a verificação se torna vazia.
    """

    def __init__(
        self,
        transformation_port: MultiInputTransformationPort,
        persistence_manager: PersistenceManager,
    ) -> None:
        self._transformation = transformation_port
        self._persistence = persistence_manager

    def consolidate(
        self,
        *,
        source_coids: Iterable[uuid.UUID],
        declared_losses: Iterable[str],
        declared_preservations: Iterable[str] = (),
        actor_ref: uuid.UUID | None = None,
        policy_ref: str | None = None,
        predecessor_event_ids: Iterable[uuid.UUID] = (),
        occurred_at: datetime | None = None,
    ) -> ConsolidationResult:
        """Consolida `{M1, ..., Mn}` em `S1`, deixando `S1 ← {M1..Mn}`
        permanentemente reconstruível.

        A verificação posterior não é redundância: o recibo é a palavra
        de quem escreveu, e o `PersistenceAssessment` é a leitura
        independente do patrimônio, dentro da mesma transação. Concluir
        só com o recibo seria aceitar a afirmação sem a prova.
        """
        fontes = self._validar_fontes(source_coids)
        perdas = _declaracoes("declared_losses", declared_losses, obrigatorio=True)
        preservacoes = _declaracoes(
            "declared_preservations", declared_preservations, obrigatorio=False
        )
        predecessores = self._validar_predecessores(predecessor_event_ids)

        recibo = self._transformation.derive_many(
            source_coids=fontes,
            operation_type=CONSOLIDATION_OPERATION_TYPE,
            declared_losses=perdas,
            declared_preservations=preservacoes,
            actor_ref=actor_ref,
            policy_ref=policy_ref,
            predecessor_event_ids=predecessores,
            occurred_at=occurred_at,
        )

        assessment = self._persistence.assess(recibo.target_coid)
        self._verificar(recibo, assessment)

        logger.info(
            "consolidation_recorded",
            extra={
                "source_coids": [str(c) for c in recibo.source_coids],
                "target_coid": str(recibo.target_coid),
                "target_clid": None if recibo.target_clid is None else str(recibo.target_clid),
                "transformation_id": str(recibo.transformation_id),
                "lineage_edges": len(recibo.lineage_edge_ids),
                "causal_events": len(recibo.causal_event_ids),
            },
        )

        return ConsolidationResult(
            source_coids=recibo.source_coids,
            target_coid=recibo.target_coid,
            target_clid=recibo.target_clid,
            transformation_id=recibo.transformation_id,
            lineage_edge_ids=recibo.lineage_edge_ids,
            causal_event_ids=recibo.causal_event_ids,
            predecessor_event_ids=recibo.predecessor_event_ids,
            persistence_assessment=assessment,
        )

    # --- Validação do pedido -------------------------------------------

    @staticmethod
    def _validar_fontes(source_coids: Iterable[uuid.UUID]) -> tuple[uuid.UUID, ...]:
        """Materializa **uma única vez**, valida e canonicaliza.

        Um generator consumido duas vezes entregaria vazio na segunda —
        por isso a materialização acontece antes de qualquer checagem.

        A ordem em que o chamador listou as fontes não é informação
        semântica (`SOURCE ORDER != SOURCE RANKING`), então é
        canonicalizada por UUID. Duplicata, ao contrário, **é** erro:
        desduplicar em silêncio entregaria N−1 edges para N fontes
        declaradas e o chamador nunca saberia.
        """
        if isinstance(source_coids, str | bytes) or not hasattr(source_coids, "__iter__"):
            raise TypeError(
                f"source_coids deve ser uma coleção de uuid.UUID, "
                f"recebido {type(source_coids).__name__}"
            )
        materializado = tuple(source_coids)
        for item in materializado:
            if not isinstance(item, uuid.UUID):
                raise TypeError(
                    f"source_coids aceita apenas uuid.UUID, recebido {type(item).__name__}"
                )
        if len(materializado) < 2:
            raise ValueError(
                "uma consolidação exige ao menos duas fontes distintas — com uma única "
                "fonte não há o que consolidar"
            )
        if len(set(materializado)) != len(materializado):
            raise ValueError(
                "source_coids contém COIDs duplicados; duplicata é entrada inválida e "
                "não é desduplicada silenciosamente"
            )
        return tuple(sorted(materializado))

    @staticmethod
    def _validar_predecessores(
        predecessor_event_ids: Iterable[uuid.UUID],
    ) -> tuple[uuid.UUID, ...]:
        """Predecessores são sempre **explícitos**.

        Nada é selecionado por tempo, recência ou "último evento":
        `TEMPORAL PRECEDENCE != CAUSALITY`. A existência e o
        pertencimento causal de cada um são verificados pela E3, que é
        quem tem a história — a E4.5 só garante a forma.
        """
        if isinstance(predecessor_event_ids, str | bytes) or not hasattr(
            predecessor_event_ids, "__iter__"
        ):
            raise TypeError(
                f"predecessor_event_ids deve ser uma coleção de uuid.UUID, "
                f"recebido {type(predecessor_event_ids).__name__}"
            )
        materializado = tuple(predecessor_event_ids)
        for item in materializado:
            if not isinstance(item, uuid.UUID):
                raise TypeError(
                    f"predecessor_event_ids aceita apenas uuid.UUID, "
                    f"recebido {type(item).__name__}"
                )
        if len(set(materializado)) != len(materializado):
            raise ValueError(
                "predecessor_event_ids contém repetições — declarar o mesmo evento duas "
                "vezes duplicaria a história sem acrescentar fato algum"
            )
        return materializado

    # --- Verificação independente (E4.4) --------------------------------

    def _verificar(
        self,
        recibo: MultiInputTransformationReceiptPort,
        assessment: PersistenceAssessment,
    ) -> None:
        """Confronta o recibo com a leitura independente do patrimônio.

        Acumula **todos** os motivos antes de levantar: uma divergência
        raramente vem sozinha, e reportar só a primeira obrigaria a
        auditoria a descobrir as demais uma execução por vez.

        A correspondência de linhagem é feita por `reference` (id da
        edge) e `related_coid` (a fonte), **nunca** por `qualifier`. A
        E3 persiste enums com duas convenções — `relation_type` grava o
        `.value` e `event_type` grava o NOME (achado registrado na
        E4.4) — e casar por essa string faria a E4.5 herdar uma
        assimetria que não é dela.

        Nada é reparado aqui. `AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN`.
        """
        motivos: list[str] = []

        if assessment.coid != recibo.target_coid:
            motivos.append(
                f"assessment é sobre {assessment.coid}, não sobre o alvo " f"{recibo.target_coid}"
            )
        if assessment.outcome is not PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE:
            motivos.append(f"outcome {assessment.outcome} — esperado RECORDED_CONTINUITY_EVIDENCE")
        if assessment.subject_deleted:
            motivos.append("alvo recém-criado aparece como soft-deleted")

        motivos.extend(self._verificar_linhagem(recibo, assessment))
        motivos.extend(self._verificar_transformacao(recibo, assessment))
        motivos.extend(self._verificar_causalidade(recibo, assessment))
        motivos.extend(self._verificar_clid(recibo, assessment))

        if motivos:
            raise ConsolidationVerificationError(recibo.target_coid, tuple(motivos))

    @staticmethod
    def _verificar_linhagem(
        recibo: MultiInputTransformationReceiptPort, assessment: PersistenceAssessment
    ) -> list[str]:
        """Uma `LINEAGE_PARENT` por fonte, com pareamento posicional."""
        motivos: list[str] = []
        evidencias = assessment.evidence_of(PersistenceEvidenceKind.LINEAGE_PARENT)

        if len(evidencias) != len(recibo.source_coids):
            motivos.append(
                f"{len(evidencias)} evidências LINEAGE_PARENT para "
                f"{len(recibo.source_coids)} fontes"
            )

        relacionados = {e.related_coid for e in evidencias}
        if relacionados != set(recibo.source_coids):
            motivos.append(
                "conjunto de fontes na linhagem difere do recibo: "
                f"{sorted(str(c) for c in relacionados)}"
            )

        referencias = {e.reference for e in evidencias}
        esperadas = {str(e) for e in recibo.lineage_edge_ids}
        if referencias != esperadas:
            motivos.append("ids das edges na linhagem diferem dos do recibo")

        # Correspondência posicional: a edge da posição i tem de apontar
        # para a fonte da posição i. Sem esta checagem, os dois conjuntos
        # poderiam bater com o pareamento trocado.
        por_referencia = {e.reference: e.related_coid for e in evidencias}
        for fonte, edge_id in zip(recibo.source_coids, recibo.lineage_edge_ids, strict=False):
            registrado = por_referencia.get(str(edge_id))
            if registrado is not None and registrado != fonte:
                motivos.append(
                    f"edge {edge_id} deveria apontar para a fonte {fonte}, "
                    f"mas aponta para {registrado}"
                )
        return motivos

    @staticmethod
    def _verificar_transformacao(
        recibo: MultiInputTransformationReceiptPort, assessment: PersistenceAssessment
    ) -> list[str]:
        """Exatamente uma `TRANSFORMATION_OUTPUT`, a do recibo."""
        motivos: list[str] = []
        evidencias = assessment.evidence_of(PersistenceEvidenceKind.TRANSFORMATION_OUTPUT)
        if len(evidencias) != 1:
            motivos.append(
                f"{len(evidencias)} evidências TRANSFORMATION_OUTPUT — esperada exatamente 1"
            )
        elif evidencias[0].reference != str(recibo.transformation_id):
            motivos.append(
                f"transformação registrada {evidencias[0].reference} difere da do recibo "
                f"{recibo.transformation_id}"
            )
        return motivos

    @staticmethod
    def _verificar_causalidade(
        recibo: MultiInputTransformationReceiptPort, assessment: PersistenceAssessment
    ) -> list[str]:
        """Os eventos causais do alvo são exatamente os do recibo."""
        evidencias = assessment.evidence_of(PersistenceEvidenceKind.CAUSAL_EVENT)
        registrados = {e.reference for e in evidencias}
        esperados = {str(e) for e in recibo.causal_event_ids}
        if registrados != esperados:
            return ["eventos causais registrados diferem dos do recibo"]
        return []

    @staticmethod
    def _verificar_clid(
        recibo: MultiInputTransformationReceiptPort, assessment: PersistenceAssessment
    ) -> list[str]:
        """CLID coerente entre recibo e assessment.

        A E4.5 **não decide** CLID: a regra é da E3.4.2 (todas as fontes
        com o mesmo CLID não nulo → o alvo herda; qualquer divergência →
        `None`). Aqui só se confere que os dois lados contam a mesma
        história — `None` dos dois lados é coerência, não falha.

            MIXED HISTORIES != SINGLE CONTINUITY
        """
        if assessment.clid != recibo.target_clid:
            return [
                f"CLID do assessment ({assessment.clid}) difere do recibo "
                f"({recibo.target_clid})"
            ]
        return []
