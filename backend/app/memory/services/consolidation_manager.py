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
from app.memory.schemas.consolidation import (
    ConsolidationResult,
    verificar_coerencia_consolidacao,
    verificar_fidelidade_pedido_recibo,
)
from app.memory.schemas.persistence import PersistenceAssessment
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

        # Fidelidade pedido↔recibo ANTES de consultar o alvo: uma
        # divergência já demonstrada não precisa do assessment para
        # valer, e chamar `assess()` aqui só produziria trabalho cujo
        # resultado seria descartado.
        self._verificar_fidelidade(recibo, fontes, predecessores)

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
        # Canonicalização por UUID, idêntica à do writer oficial
        # (`MultiInputTransformationManager._preflight_predecessores_tipos`,
        # E3.4.2, que faz `tuple(sorted(...))`).
        #
        # DIVERGÊNCIA REGISTRADA (E4.5.2): o prompt do corretivo pede que
        # a E4.5 "não ordene" predecessores e compare preservando a ordem
        # do chamador. Isso é inalcançável ponta a ponta, porque a E3 já
        # canonicaliza — o recibo devolve a tupla ordenada,
        # independentemente da ordem pedida. Comparar contra a ordem
        # bruta faria toda consolidação com predecessores fora de ordem
        # falhar com PIA-8032, o que seria recusar operação legítima.
        # Canonicalizar dos dois lados preserva a verificação onde ela
        # discrimina — substituição, remoção, acréscimo e recibo fora da
        # ordem canônica — sem inventar uma garantia de ordem que a E3
        # não oferece. Corrigir isso na E3 seria Stop Condition (§13.1).
        return tuple(sorted(materializado))

    # --- Fidelidade pedido↔recibo (E4.5.2) ------------------------------

    @staticmethod
    def _verificar_fidelidade(
        recibo: MultiInputTransformationReceiptPort,
        fontes_validadas: tuple[uuid.UUID, ...],
        predecessores_validados: tuple[uuid.UUID, ...],
    ) -> None:
        """Confronta o recibo com o **pedido validado** (corretivo E4.5.2).

        Fronteira distinta da verificada por
        `verificar_coerencia_consolidacao`, e nenhuma substitui a outra:

            REQUEST ↔ RECEIPT   preserva a intenção operacional recebida
            RECEIPT ↔ ASSESSMENT prova o patrimônio efetivamente observado

            REQUEST FIDELITY != PERSISTENCE COHERENCE
            BOTH ARE REQUIRED

        Sem esta camada, recibo e banco podem concordar perfeitamente
        entre si enquanto **ambos** descrevem uma operação diferente da
        solicitada — foi exatamente o defeito que a auditoria da cadeia
        49 reproduziu: pedido `(A, B)`, recibo `(C, D)`, assessment
        coerente com `(C, D)`, nenhuma exceção.

            REQUESTED SOURCES != AUTHORIZATION TO SUBSTITUTE SOURCES
            CONSOLIDATION OF {A,B} != CONSOLIDATION OF {C,D}
            TRANSMISSION != OVERWRITE

        Comparação **exata por tupla**, ordem inclusa. Para as fontes, o
        pedido já foi canonicalizado antes da porta, então o recibo deve
        devolver exatamente a tupla canônica. Para os predecessores, a
        ordem é semântica: `(P1, P2)` e `(P2, P1)` declaram
        correspondências causais diferentes, e comparar conjuntos
        aceitaria a troca em silêncio.

            EXPLICIT PREDECESSOR != INTERCHANGEABLE PREDECESSOR

        Nada é reordenado, desduplicado, substituído ou inferido aqui —
        divergência é diagnóstico, nunca conserto.
        """
        motivos = verificar_fidelidade_pedido_recibo(
            source_coids_solicitadas=fontes_validadas,
            predecessores_solicitados=predecessores_validados,
            source_coids_do_recibo=tuple(recibo.source_coids),
            predecessores_do_recibo=tuple(recibo.predecessor_event_ids),
        )
        if motivos:
            raise ConsolidationVerificationError(recibo.target_coid, motivos)

    # --- Verificação independente (E4.4) --------------------------------

    @staticmethod
    def _verificar(
        recibo: MultiInputTransformationReceiptPort,
        assessment: PersistenceAssessment,
    ) -> None:
        """Confronta o recibo com a leitura independente do patrimônio.

        Delega à função pura `verificar_coerencia_consolidacao`, a
        **mesma** que `ConsolidationResult.__post_init__` usa (corretivo
        E4.5.1). Antes, o manager tinha implementação própria e mais
        completa que a do value object — duas implementações da mesma
        semântica, que divergiram exatamente como se espera que
        divirjam.

        Converte qualquer divergência em `ConsolidationVerificationError`
        (`PIA-8032`, categoria `SYSTEM`). A verificação acontece **antes**
        de construir o `ConsolidationResult`, então nenhum `ValueError`
        cru do value object escapa por este caminho: quem chama a E4.5
        recebe sempre o erro de domínio.

        Nada é reparado, reclassificado ou absorvido — a exceção sobe e o
        rollback da `UnitOfWork` do chamador desfaz a consolidação
        inteira.

            AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN
            MISMATCH != AUTHORIZATION TO FABRICATE OR REPAIR HISTORY
        """
        motivos = verificar_coerencia_consolidacao(
            source_coids=tuple(recibo.source_coids),
            target_coid=recibo.target_coid,
            target_clid=recibo.target_clid,
            transformation_id=recibo.transformation_id,
            lineage_edge_ids=tuple(recibo.lineage_edge_ids),
            causal_event_ids=tuple(recibo.causal_event_ids),
            assessment=assessment,
        )
        if motivos:
            raise ConsolidationVerificationError(recibo.target_coid, motivos)
