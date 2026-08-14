"""
`MultiInputTransformationManager` — transformação cognitiva
multi-input (`E3.4.2`).

## Por que este módulo existe

`VersionManager.derive()` e `revise()` são **mono-input**: ambos
recebem um único `source` e gravam `input_refs=[str(source.id)]`. Até
aqui, a única demonstração de uma transformação com várias entradas
vivia dentro de um teste (`E3.12`, cenário `G1`), construída à mão com
`session.add()` direto e produzindo **dois** `TransformationRecord`
mutuamente incoerentes para uma mesma operação — um `DERIVATION` com
uma só entrada e um `REVISION` com duas. Cenário de teste não é
contrato público, e essa lacuna é da E3, não de quem a consome.

Este módulo fecha a lacuna com um mecanismo público, tipado, coberto e
transacional, dentro de `app/cognitive` — que é e continua sendo o
único dono do patrimônio cognitivo:

    COGNITIVE PATRIMONY WRITER = app/cognitive

## O que ele não é

    IS NOT E4.5           IS NOT GOVERNANCE      IS NOT RETRIEVAL
    IS NOT LEARNING       IS NOT SOURCE SELECTION
    IS NOT ARTIFACT STORAGE

Ele **registra a estrutura** de uma transformação deliberadamente
solicitada. Não sintetiza conteúdo, não chama provider, não pontua, não
ranqueia, não elege fonte vencedora e não resolve divergência:

    SOURCE ORDER != SOURCE RANKING
    COUT INFORMS; DOES NOT DECIDE

## Preservação

Nenhuma fonte é tocada. Não muda `clid`, `accessibility`,
`revision_status`, `deleted_at`, nem é apagada ou sobrescrita:

    MULTI-INPUT DERIVATION != SOURCE REPLACEMENT
    MERGE != IDENTITY COLLAPSE

## Transação

Todas as escritas participam da `UnitOfWork` do chamador. O manager não
cria sessão, não abre transação, não commita e não absorve exceção de
persistência — ou tudo persiste, ou o rollback do chamador não deixa
nada para trás.
"""

import uuid
from collections.abc import Iterable
from datetime import datetime

from app.cognitive.errors.exceptions import (
    CausalPredecessorNotFoundError,
    CausalPredecessorSubjectMismatchError,
    MultiInputSourceNotFoundError,
)
from app.cognitive.models.causal_history import CausalHistoryEvent
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import CausalEventType, LineageRelation, TransformationKind
from app.cognitive.models.transformation_record import TransformationRecord
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.transformation_repository import TransformationRepository
from app.cognitive.schemas.multi_input_transformation import MultiInputTransformationReceipt
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.clid_manager import ClidManager
from app.utils.logger import get_logger

logger = get_logger("app.cognitive.services.multi_input_transformation_manager")

_OPERATION_TYPE_MAX_LENGTH = 64
"""Capacidade real da coluna `transformation_records.operation_type`
(`String(64)`). Validado no preflight para que um valor longo demais
falhe **antes** de qualquer escrita, e não como erro de banco no meio
de uma operação já parcialmente aplicada."""

_POLICY_REF_MAX_LENGTH = 255
"""Capacidade real da coluna `transformation_records.policy_ref`
(`String(255)`), pela mesma razão — corretivo E3.4.2.1.

Sem esta checagem o resultado de um `policy_ref` longo demais dependeria
do comportamento específico do banco ou do driver (truncar em silêncio,
recusar, ou variar por dialeto), e a exigência de validação integral
antes da primeira escrita ficaria furada exatamente no campo mais fácil
de passar despercebido.

O valor é validado, **nunca normalizado**: nada de `strip()` no que se
persiste, nada de truncar. `DECLARED VALUE != NORMALIZED VALUE` — o
`.strip()` que aparece abaixo é apenas predicado para detectar string
em branco, e não toca a declaração original."""


def _declaracoes(campo: str, valor: object, *, obrigatorio: bool) -> list[str]:
    """Materializa e valida uma coleção de declarações textuais.

    `str` é recusado explicitamente mesmo sendo iterável: aceitá-lo
    transformaria `"perdeu contexto"` numa lista de caracteres, e a
    declaração de perda viraria ruído em vez de erro.
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
            f"{campo} é obrigatório numa transformação multi-input "
            "(DECLARED_LOSS_ON_MULTI_INPUT_CONSOLIDATION = MANDATORY): uma síntese "
            "que não declara o que perdeu afirma não ter perdido nada, o que é quase "
            "sempre falso — e preencher automaticamente com 'none' seria a mesma "
            "afirmação, só que escondida"
        )
    return itens


class MultiInputTransformationManager:
    """Deriva um novo `CognitiveObject` a partir de **N fontes**.

    Compõe primitivas existentes da E3 e não introduz nenhuma entidade
    persistente, tabela, coluna, migração ou enum:

        NEW PERSISTENT ENTITY = NO      MIGRATION_REQUIRED = NO

    `ClidManager` é usado **exclusivamente** para atribuir CLID ao
    alvo. `inherit()` não é chamado aqui, e a razão é substantiva: ele
    gera e grava CLID no *parent* quando o parent não tem — o que
    mutaria uma fonte e fabricaria continuidade onde não havia
    (`SOURCE CLID GENERATION = FORBIDDEN`).
    """

    def __init__(
        self,
        object_repository: ObjectRepository,
        clid_manager: ClidManager,
        lineage_repository: LineageRepository,
        transformation_repository: TransformationRepository,
        causal_history_manager: CausalHistoryManager,
        causal_history_repository: CausalHistoryRepository,
    ) -> None:
        self._objects = object_repository
        self._clid = clid_manager
        self._lineage = lineage_repository
        self._transformations = transformation_repository
        self._causal = causal_history_manager
        self._causal_repository = causal_history_repository

    def derive_many(
        self,
        *,
        source_coids: Iterable[uuid.UUID],
        operation_type: str,
        declared_losses: Iterable[str],
        declared_preservations: Iterable[str] = (),
        actor_ref: uuid.UUID | None = None,
        policy_ref: str | None = None,
        predecessor_event_ids: Iterable[uuid.UUID] = (),
        occurred_at: datetime | None = None,
    ) -> MultiInputTransformationReceipt:
        """Cria um alvo derivado de N fontes, preservando todas elas.

        Produz, exatamente:

        - **1** `CognitiveObject` alvo, com COID novo;
        - **N** `LineageEdge` com `relation_type=MERGE`, uma por fonte;
        - **1** `TransformationRecord` `DERIVATION` multi-input;
        - **1** evento causal raiz, ou **N** eventos quando N
          predecessores forem declarados explicitamente.

        Ordem canônica: as fontes são ordenadas por valor de UUID, e
        essa mesma ordem vale para `input_refs`, para as edges e para o
        recibo. Assim `(M1, M2, M3)` e `(M3, M1, M2)` produzem o mesmo
        registro — ordem de digitação não é informação semântica, e
        tratá-la como se fosse faria a mesma operação parecer duas.

        **Todo o preflight ocorre antes da primeira escrita**
        (`DATABASE_WRITES = 0` em qualquer erro de validação): a
        alternativa seria descobrir uma fonte inexistente depois de já
        ter criado o alvo, deixando ao rollback um trabalho que a
        validação faz de graça.

        Não commita. A transação é do chamador (`UnitOfWork`), mesma
        disciplina de todos os managers desde `E3.3`.
        """
        # --- Preflight (§6.1) — nada abaixo escreve ------------------
        fontes_ordenadas = self._preflight_fontes(source_coids)
        operacao = self._preflight_operation_type(operation_type)
        perdas = _declaracoes("declared_losses", declared_losses, obrigatorio=True)
        preservacoes = _declaracoes(
            "declared_preservations", declared_preservations, obrigatorio=False
        )
        predecessores = self._preflight_predecessores_tipos(predecessor_event_ids)
        self._preflight_opcionais(actor_ref, policy_ref, occurred_at)

        objetos_fonte = self._carregar_fontes(fontes_ordenadas)
        eventos_predecessores = self._carregar_predecessores(predecessores, set(fontes_ordenadas))

        # --- Escrita — a partir daqui tudo participa da UnitOfWork ---
        alvo = self._objects.add(CognitiveObject())

        clid_alvo = self._resolver_clid_do_alvo(objetos_fonte)
        if clid_alvo is not None:
            self._clid.assign(alvo, clid_alvo)

        edges = tuple(
            self._lineage.add_edge(
                parent_coid=coid, child_coid=alvo.id, relation_type=LineageRelation.MERGE
            )
            for coid in fontes_ordenadas
        )

        registro = self._transformations.add(
            TransformationRecord(
                operation_type=operacao,
                transformation_kind=TransformationKind.DERIVATION,
                input_refs=[str(coid) for coid in fontes_ordenadas],
                output_refs=[str(alvo.id)],
                actor_ref=actor_ref,
                policy_ref=policy_ref,
                declared_preservations=list(preservacoes),
                declared_losses=list(perdas),
            )
        )

        eventos = self._registrar_causalidade(
            alvo_coid=alvo.id,
            transformation_id=registro.id,
            predecessores=eventos_predecessores,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )

        logger.info(
            "multi_input_transformation_recorded",
            extra={
                "source_coids": [str(coid) for coid in fontes_ordenadas],
                "target_coid": str(alvo.id),
                "target_clid": None if alvo.clid is None else str(alvo.clid),
                "transformation_id": str(registro.id),
                "operation_type": operacao,
                "lineage_edges": len(edges),
                "causal_events": len(eventos),
            },
        )

        return MultiInputTransformationReceipt(
            source_coids=fontes_ordenadas,
            target_coid=alvo.id,
            target_clid=alvo.clid,
            transformation_id=registro.id,
            lineage_edge_ids=tuple(edge.id for edge in edges),
            causal_event_ids=tuple(evento.id for evento in eventos),
            predecessor_event_ids=predecessores,
        )

    # --- Preflight -----------------------------------------------------

    @staticmethod
    def _preflight_fontes(source_coids: Iterable[uuid.UUID]) -> tuple[uuid.UUID, ...]:
        """Materializa uma única vez, valida tipo/cardinalidade/duplicata
        e devolve em ordem canônica.

        Duplicata é **erro**, nunca desduplicação silenciosa
        (`DUPLICATE SOURCE = INVALID INPUT`): esconder a repetição
        entregaria N-1 edges para N fontes declaradas, e o chamador
        nunca saberia que sua lista estava errada.
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
                "uma transformação multi-input exige ao menos duas fontes distintas — "
                "com uma única fonte a operação correta é VersionManager.derive()"
            )
        if len(set(materializado)) != len(materializado):
            raise ValueError(
                "source_coids contém COIDs duplicados; duplicata é entrada inválida e "
                "não é desduplicada silenciosamente"
            )
        return tuple(sorted(materializado))

    @staticmethod
    def _preflight_operation_type(operation_type: str) -> str:
        if not isinstance(operation_type, str):
            raise TypeError(
                f"operation_type deve ser str, recebido {type(operation_type).__name__}"
            )
        if not operation_type.strip():
            raise ValueError("operation_type não pode ser vazio")
        if len(operation_type) > _OPERATION_TYPE_MAX_LENGTH:
            raise ValueError(
                f"operation_type excede a capacidade real da coluna "
                f"({_OPERATION_TYPE_MAX_LENGTH} caracteres): {len(operation_type)}"
            )
        return operation_type

    @staticmethod
    def _preflight_predecessores_tipos(
        predecessor_event_ids: Iterable[uuid.UUID],
    ) -> tuple[uuid.UUID, ...]:
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
        return tuple(sorted(materializado))

    @staticmethod
    def _preflight_opcionais(
        actor_ref: uuid.UUID | None, policy_ref: str | None, occurred_at: datetime | None
    ) -> None:
        """Valida os campos opcionais.

        Ausência continua ausência: `None` é aceito em todos os três, e
        nada é preenchido por conveniência — em particular `occurred_at`
        jamais recebe `created_at`, porque isso afirmaria saber quando o
        fato ocorreu (`EPISTEMIC NON-FABRICATION`, E3.9).
        """
        if actor_ref is not None and not isinstance(actor_ref, uuid.UUID):
            raise TypeError(
                f"actor_ref deve ser uuid.UUID ou None, recebido {type(actor_ref).__name__}"
            )
        if policy_ref is not None:
            if not isinstance(policy_ref, str):
                raise TypeError(
                    f"policy_ref deve ser str ou None, recebido {type(policy_ref).__name__}"
                )
            if not policy_ref.strip():
                raise ValueError("policy_ref, quando informado, não pode ser vazio")
            if len(policy_ref) > _POLICY_REF_MAX_LENGTH:
                raise ValueError(
                    f"policy_ref excede a capacidade real da coluna "
                    f"({_POLICY_REF_MAX_LENGTH} caracteres): {len(policy_ref)}"
                )
        if occurred_at is not None and not isinstance(occurred_at, datetime):
            raise TypeError(
                f"occurred_at deve ser datetime ou None, recebido {type(occurred_at).__name__}"
            )

    def _carregar_fontes(
        self, fontes_ordenadas: tuple[uuid.UUID, ...]
    ) -> tuple[CognitiveObject, ...]:
        """Carrega todas as fontes com `include_deleted=True`.

        Uma fonte com exclusão lógica **existe** e é fonte legítima:

            SOFT_DELETED != NEVER EXISTED
            SOFT_DELETED != SUBJECT_NOT_FOUND
            SOFT_DELETED != HISTORICAL ERASURE

        Ela é referenciada, aparece em `input_refs` e continua endpoint
        de `LineageEdge` — e nada aqui a recupera nem toca seu
        `deleted_at`. Este módulo é mecanismo cognitivo, não
        autorização de uso: incluir um objeto soft-deleted numa
        transformação não decide nada sobre acesso a ele.
        """
        carregados: list[CognitiveObject] = []
        ausentes: list[uuid.UUID] = []
        for coid in fontes_ordenadas:
            objeto = self._objects.get_by_id(coid, include_deleted=True)
            if objeto is None:
                ausentes.append(coid)
            else:
                carregados.append(objeto)
        if ausentes:
            raise MultiInputSourceNotFoundError(tuple(ausentes))
        return tuple(carregados)

    def _carregar_predecessores(
        self, predecessores: tuple[uuid.UUID, ...], fontes: set[uuid.UUID]
    ) -> tuple[uuid.UUID, ...]:
        """Valida existência e pertencimento causal dos predecessores.

        Cada predecessor precisa pertencer à história causal de **uma
        das fontes declaradas**. Predecessor cross-history continua
        legítimo — várias fontes, várias histórias — mas um evento de
        objeto estranho ligaria o alvo a algo que não participou da
        transformação, o que é fabricar causalidade.

        Nada aqui infere: nenhum "último evento" é escolhido, nenhuma
        ordenação por `created_at` participa da decisão
        (`TEMPORAL PRECEDENCE != CAUSALITY`).
        """
        if not predecessores:
            return ()

        ausentes: list[uuid.UUID] = []
        for event_id in predecessores:
            evento = self._causal_repository.get_event(event_id)
            if evento is None:
                ausentes.append(event_id)
                continue
            historia = self._causal_repository.get_by_id(evento.history_id)
            sujeito = None if historia is None else historia.subject_coid
            if sujeito not in fontes:
                raise CausalPredecessorSubjectMismatchError(event_id, sujeito)
        if ausentes:
            raise CausalPredecessorNotFoundError(tuple(ausentes))
        return predecessores

    # --- Escrita -------------------------------------------------------

    @staticmethod
    def _resolver_clid_do_alvo(fontes: tuple[CognitiveObject, ...]) -> uuid.UUID | None:
        """Regra de CLID multi-origem congelada em E3.4.2:

            IF all sources have the same single non-null CLID:
                target.clid = that CLID
            ELSE:
                target.clid = None

        `None` não é falha, é a resposta honesta: quando as fontes
        vêm de continuidades diferentes — ou de nenhuma —, inventar um
        CLID comum afirmaria uma continuidade que não existe.

            MIXED HISTORIES != SINGLE CONTINUITY
            MIXED CLID != AUTHORIZATION TO CREATE NEW SHARED CLID
            COMMON CLID REQUIRES COMMON CONTINUITY

        E a edge de merge não depende disso: `MERGE EDGE != CLID
        EQUALITY` — a origem fica registrada na linhagem de qualquer
        modo.
        """
        clids = {fonte.clid for fonte in fontes}
        if len(clids) == 1:
            unico = next(iter(clids))
            if unico is not None:
                return unico
        return None

    def _registrar_causalidade(
        self,
        *,
        alvo_coid: uuid.UUID,
        transformation_id: uuid.UUID,
        predecessores: tuple[uuid.UUID, ...],
        actor_ref: uuid.UUID | None,
        occurred_at: datetime | None,
    ) -> tuple[CausalHistoryEvent, ...]:
        """Registra a história causal do alvo.

        Sem predecessor declarado, grava **um** evento-raiz. Isso não
        fabrica história anterior: registra apenas o fato comprovado de
        que esta transformação ocorreu.

            OPERATION OCCURRENCE = KNOWN FACT
            MISSING PREDECESSOR != MISSING OPERATION
            MISSING HISTORY != AUTHORIZATION TO INVENT PREDECESSOR

        Com N predecessores declarados, grava N eventos — um por
        predecessor, porque `CausalHistoryEvent` admite no máximo um
        `predecessor_event_id` e representar múltiplas origens de outra
        forma exigiria ampliar contrato da E3.

        `payload_ref` referencia o `TransformationRecord`: é
        **referência**, nunca conteúdo (`CAUSAL_TRACE != TRANSCRIPT`).
        """
        payload_ref = str(transformation_id)
        if not predecessores:
            return (
                self._causal.record(
                    subject_coid=alvo_coid,
                    event_type=CausalEventType.TRANSFORMED,
                    actor_ref=actor_ref,
                    payload_ref=payload_ref,
                    predecessor=None,
                    occurred_at=occurred_at,
                ),
            )

        eventos: list[CausalHistoryEvent] = []
        for event_id in predecessores:
            predecessor = self._causal_repository.get_event(event_id)
            eventos.append(
                self._causal.record(
                    subject_coid=alvo_coid,
                    event_type=CausalEventType.TRANSFORMED,
                    actor_ref=actor_ref,
                    payload_ref=payload_ref,
                    predecessor=predecessor,
                    occurred_at=occurred_at,
                )
            )
        return tuple(eventos)
