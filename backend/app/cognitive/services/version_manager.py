"""
VersionManager — LIB-04, versionamento cognitivo via transformação
explícita entre `CognitiveObject`s.

Regra canônica (§3 do módulo E3.4): versionar nunca significa alterar
o mesmo `CognitiveObject`. `A --transformação--> B` implica
`COID_A != COID_B` sempre, e `CLID_A == CLID_B` quando `B` representa
continuidade de `A`. `A` permanece preservado; `B` é um novo objeto.
`A.id = B.id` é proibido — não há caminho no código que permita isso
(o COID de `B` vem de `UUIDMixin.default=uuid.uuid4`, nunca copiado de
`A`).

**REVISION vs DERIVATION** (correção E3.4.0): duas operações
distintas, nunca um parâmetro booleano obscuro.

- `derive()` — **DERIVATION**. Novo objeto derivado de outro; `source`
  permanece a representação vigente do que representa (não vira
  `SUPERSEDED`). Exemplos: resumo, tradução, crítica, síntese
  alternativa. Pode gerar branches naturalmente (`A` derivando `B` e
  `C` simultaneamente).
- `revise()` — **REVISION**. Nova revisão controlada do MESMO
  patrimônio lógico; `target` torna-se `RevisionStatus.CURRENT`,
  `source` torna-se `RevisionStatus.SUPERSEDED`. Uma revisão
  `SUPERSEDED` nunca é apagada — continua identificável, auditável,
  rastreável (§17 do prompt corretivo).

Nenhuma das duas operações classifica a outra automaticamente — a
distinção vem sempre de qual método o chamador invoca explicitamente
(§20 do prompt corretivo: "COUT preserva história e relações; não
decide sozinho qual conteúdo deve substituir outro").

**Workspace vs Controlled Asset**: `VersionManager` não promove nada
automaticamente. Chamar `derive()`/`revise()` é sempre uma decisão
explícita do chamador — nenhum objeto se torna `CURRENT`/`SUPERSEDED`
"sozinho", nenhuma saída de IA vira patrimônio controlado sem uma
chamada explícita a `revise()`. `PROMOTION_POLICY_STATUS = DEFERRED`
— a política completa de promoção Workspace→Asset pertence a uma fase
posterior (§18 do prompt corretivo); este módulo só fornece o
mecanismo, não decide quando usá-lo.

`VersionManager` não commita, não gera mecanismo paralelo de COID/CLID
(reutiliza `ObjectRepository`/`ClidManager` integralmente), não
implementa provenance, não conhece provider/IA (§5, §12, §13 do
módulo E3.4).
"""

from app.cognitive.errors.exceptions import RevisionStatusInvalidTransitionError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import LineageRelation, RevisionStatus, TransformationKind
from app.cognitive.models.lineage_edge import LineageEdge
from app.cognitive.models.transformation_record import TransformationRecord
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.transformation_repository import TransformationRepository
from app.cognitive.services.clid_manager import ClidManager
from app.utils.logger import get_logger

logger = get_logger("app.cognitive.services.version_manager")


class VersionManager:
    """Cria novas versões/derivações de `CognitiveObject` por
    transformação explícita, preservando o objeto de origem.

    Depende de `ObjectRepository` (criar o novo `CognitiveObject`),
    `ClidManager` (propagação de CLID + criação da `LineageEdge` —
    reaproveitado por inteiro, nenhuma lógica de CLID/lineage
    duplicada aqui) e `TransformationRepository` (histórico
    append-only).

    **Decisões em aberto, documentadas (não inventadas)**:
    - `derive()`/`revise()` sempre estabelecem continuidade (chamam
      `ClidManager.inherit()`, que garante `CLID_A == CLID_B`). O caso
      "transformação que deliberadamente NÃO representa continuidade"
      (ex.: possíveis operações futuras de import/export) não está
      definido no Domain Model/EDR para esta fase — não implementado.
    - `revise()` trata `source.revision_status is None` como entrada
      implícita na cadeia controlada (equivalente a uma "Rev.0" nunca
      formalmente marcada `CURRENT`) — `source` vai direto para
      `SUPERSEDED`. Ver `E3_4_LIB04_VERSION_TRANSFORMATION.md`.
    - `revise()` confia que o chamador passa o `source` correto (o
      objeto atualmente `CURRENT` da linha de revisão) — não busca "o
      CURRENT" por CLID sozinho; a mesma convenção já usada por
      `inherit(parent, child)`, que também recebe objetos já
      carregados, não COIDs crus.
    """

    def __init__(
        self,
        object_repository: ObjectRepository,
        clid_manager: ClidManager,
        transformation_repository: TransformationRepository,
    ) -> None:
        self._objects = object_repository
        self._clid = clid_manager
        self._transformations = transformation_repository

    def derive(
        self,
        source: CognitiveObject,
        *,
        operation_type: str,
        declared_preservations: list[str] | None = None,
        declared_losses: list[str] | None = None,
        policy_ref: str | None = None,
        relation_type: LineageRelation = LineageRelation.TRANSFORMED_FROM,
    ) -> tuple[CognitiveObject, LineageEdge, TransformationRecord]:
        """Cria um novo `CognitiveObject` (`target`) **derivado** de
        `source` por uma transformação explícita — `source` **não**
        se torna `SUPERSEDED` (§5 do prompt corretivo: "uma derivação
        NÃO deve automaticamente tornar o source SUPERSEDED"); seu
        `revision_status` (se algum) permanece inalterado.

        Ordem atômica (§6 do módulo E3.4, nenhum passo commita —
        commit permanece do chamador via `UnitOfWork`):

        1. `target` é criado e persistido (`ObjectRepository.add`) —
           COID novo, gerado pelo mecanismo já existente
           (`UUIDMixin`), nunca copiado de `source`.
        2. `ClidManager.inherit(source, target, relation_type=...)` —
           bloqueia `source`/`target` (`refresh_for_update`, correção
           E3.3.1), resolve/propaga CLID, e registra a `LineageEdge`
           correspondente. Reaproveitado integralmente — nenhuma
           lógica de CLID/lineage/concorrência duplicada aqui.
        3. `TransformationRecord` é criado
           (`transformation_kind=DERIVATION`) referenciando
           `source.id`/`target.id` em `input_refs`/`output_refs`.

        Sobre concorrência (§11 do módulo E3.4): esta operação nunca
        bloqueia mais de um `CognitiveObject` já existente — `target`
        é sempre uma linha nova, criada e ainda não commitada dentro
        desta mesma transação, portanto invisível a outras transações
        e sem risco de deadlock por ordem de lock; apenas `source`
        (via `inherit()`) é uma linha pré-existente bloqueada. Não há
        cenário, neste método, de bloquear múltiplos objetos
        pré-existentes em ordem potencialmente divergente entre
        chamadas concorrentes.

        Levanta `ValueError` se `operation_type` for vazio — validação
        de argumento simples, mesma convenção já usada em
        `CoidManager.generate_unique`/`ObjectRepository.paginate`
        (nenhum `PIA-8xxx` novo para isso).
        """
        if not operation_type:
            raise ValueError("operation_type não pode ser vazio")

        target = self._objects.add(CognitiveObject())

        edge = self._clid.inherit(source, target, relation_type=relation_type)

        record = TransformationRecord(
            operation_type=operation_type,
            transformation_kind=TransformationKind.DERIVATION,
            input_refs=[str(source.id)],
            output_refs=[str(target.id)],
            declared_preservations=list(declared_preservations or []),
            declared_losses=list(declared_losses or []),
            policy_ref=policy_ref,
        )
        record = self._transformations.add(record)

        logger.info(
            "cognitive_object_derived",
            extra={
                "source_coid": str(source.id),
                "target_coid": str(target.id),
                "clid": str(target.clid),
                "operation_type": operation_type,
                "relation_type": str(relation_type),
                "transformation_id": str(record.id),
            },
        )
        return target, edge, record

    def revise(
        self,
        source: CognitiveObject,
        *,
        operation_type: str,
        declared_preservations: list[str] | None = None,
        declared_losses: list[str] | None = None,
        policy_ref: str | None = None,
        relation_type: LineageRelation = LineageRelation.TRANSFORMED_FROM,
    ) -> tuple[CognitiveObject, LineageEdge, TransformationRecord]:
        """Cria uma nova **revisão controlada** (`target`) do mesmo
        patrimônio lógico de `source` — `target` torna-se
        `RevisionStatus.CURRENT`; `source` torna-se
        `RevisionStatus.SUPERSEDED` (§4 do prompt corretivo).

        `source.revision_status` deve ser `CURRENT` ou `None` (entrada
        implícita na cadeia — ver docstring da classe). Se já for
        `SUPERSEDED`, a operação é rejeitada
        (`RevisionStatusInvalidTransitionError`, `PIA-8011`) — não é
        possível criar a "próxima revisão" a partir de uma revisão já
        superada (isso poderia produzir uma segunda linha de revisão
        para a mesma continuidade, violando o invariante "no máximo um
        `CURRENT`").

        `source` **não é apagado** — `SUPERSEDED != DELETED` (§17 do
        prompt corretivo): continua identificável, auditável,
        recuperável por COID, ligado por lineage e por
        `TransformationRecord`.

        Ordem atômica (mesmo padrão de `derive()`, nenhum passo
        commita):

        1. `target` é criado e persistido — COID novo.
        2. `source` é bloqueado (`ObjectRepository.refresh_for_update`
           — reaproveita a proteção de concorrência de E3.3.1) e
           recarregado; seu `revision_status` pós-lock é reavaliado
           **antes** de qualquer transição, para que duas transações
           concorrentes revisando o mesmo `source` nunca produzam dois
           `CURRENT` (§12-13 do prompt corretivo — ver
           `E3_4_LIB04_VERSION_TRANSFORMATION.md`, seção Concurrency,
           para o cenário testado contra PostgreSQL real).
        3. Se `source.revision_status == SUPERSEDED` pós-lock: rejeita.
        4. `ClidManager.inherit(source, target, relation_type=...)` —
           CLID + `LineageEdge`, reaproveitado integralmente.
        5. `target.revision_status = CURRENT`;
           `source.revision_status = SUPERSEDED`.
        6. `TransformationRecord` é criado
           (`transformation_kind=REVISION`).

        Levanta `ValueError` se `operation_type` for vazio (mesma
        convenção de `derive()`).
        """
        if not operation_type:
            raise ValueError("operation_type não pode ser vazio")

        self._objects.refresh_for_update(source)
        if source.revision_status == RevisionStatus.SUPERSEDED:
            raise RevisionStatusInvalidTransitionError(
                coid=source.id,
                current=source.revision_status,
                attempted=RevisionStatus.SUPERSEDED,
            )

        target = self._objects.add(CognitiveObject())

        edge = self._clid.inherit(source, target, relation_type=relation_type)

        target.revision_status = RevisionStatus.CURRENT
        self._objects.update(target)
        source.revision_status = RevisionStatus.SUPERSEDED
        self._objects.update(source)

        record = TransformationRecord(
            operation_type=operation_type,
            transformation_kind=TransformationKind.REVISION,
            input_refs=[str(source.id)],
            output_refs=[str(target.id)],
            declared_preservations=list(declared_preservations or []),
            declared_losses=list(declared_losses or []),
            policy_ref=policy_ref,
        )
        record = self._transformations.add(record)

        logger.info(
            "cognitive_object_revised",
            extra={
                "source_coid": str(source.id),
                "target_coid": str(target.id),
                "clid": str(target.clid),
                "operation_type": operation_type,
                "relation_type": str(relation_type),
                "transformation_id": str(record.id),
            },
        )
        return target, edge, record
