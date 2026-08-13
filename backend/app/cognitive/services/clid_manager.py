"""
ClidManager — LIB-03, continuidade (CLID) e fundação de lineage entre
`CognitiveObject`s distintos.

Regra canônica (§4-§5 do módulo E3.3): COID identifica um objeto,
único, nunca compartilhado. CLID identifica uma continuidade,
compartilhável por objetos distintos que pertencem à mesma linhagem
reconhecida. `COID_A != COID_B` pode coexistir com `CLID_A == CLID_B`
— e `COID identity != CLID continuity`.

`ClidManager` não persiste diretamente fora do que
`ObjectRepository`/`LineageRepository` já fazem, não commita, não
substitui nenhum dos dois repositórios, não decide similaridade
semântica e não infere CLID a partir de conteúdo/embedding/provider
(§6, §7, §9 do módulo E3.3).
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.cognitive.errors.exceptions import ClidInvalidError, CognitiveObjectClidAlreadySetError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import LineageRelation
from app.cognitive.models.lineage_edge import LineageEdge
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.utils.logger import get_logger

logger = get_logger("app.cognitive.services.clid_manager")


class ImportedClidStatus(StrEnum):
    """Classificação mínima de um CLID importado (§22 do módulo
    E3.3) — distinta de `ImportedCoidStatus` (E3.2): a situação de
    conflito para CLID não é "já pertence a outra identidade" (CLID é
    compartilhável por natureza), é "o objeto já está comprometido com
    uma continuidade diferente"."""

    VALID = "valid"
    INVALID = "invalid"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True)
class ImportedClidValidation:
    """Resultado de `ClidManager.validate_imported_clid()`. `clid` é
    `None` apenas quando `status == INVALID`."""

    status: ImportedClidStatus
    clid: uuid.UUID | None


class ClidManager:
    """Geração, validação, atribuição e herança de continuidade
    (CLID), e fundação de `LineageEdge`.

    Depende de `ObjectRepository` (consultar/atualizar `CognitiveObject`)
    e `LineageRepository` (registrar a relação de linhagem quando
    `inherit()` estabelece continuidade) — nunca substitui nenhum dos
    dois, nunca controla commit.
    """

    def __init__(
        self, object_repository: ObjectRepository, lineage_repository: LineageRepository
    ) -> None:
        self._objects = object_repository
        self._lineage = lineage_repository

    def generate(self) -> uuid.UUID:
        """Gera um CLID candidato — independente de conteúdo, hash,
        embedding, provider, modelo, sessão ou COID (§6, §8 do módulo
        E3.3). Mesmo mecanismo de `uuid.uuid4()` já usado para COID —
        não introduz um segundo algoritmo de geração de identidade."""
        return uuid.uuid4()

    def validate(self, value: object) -> uuid.UUID:
        """Valida formato — aceita `uuid.UUID` ou `str` parseável.
        Já normaliza no retorno (mesmo padrão de `CoidManager.validate`).
        """
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str):
            try:
                return uuid.UUID(value)
            except ValueError as exc:
                raise ClidInvalidError(value) from exc
        raise ClidInvalidError(value)

    def assert_assignable(self, entity: CognitiveObject, clid: uuid.UUID) -> None:
        """Levanta `CognitiveObjectClidAlreadySetError` (`PIA-8002`,
        reutilizado — §9, §30 do módulo E3.3) se `entity.clid` já
        estiver definido para um valor **diferente** de `clid`. Não
        levanta para `entity.clid is None` (primeira atribuição) nem
        para `entity.clid == clid` (idempotente).

        Puramente de leitura — ao contrário de `assign()`, nunca muta
        `entity` nem toca o guard do modelo; verifica a mesma condição
        que `@validates("clid")` aplicaria, sem o efeito colateral de
        tentar a atribuição de fato.
        """
        if entity.clid is not None and entity.clid != clid:
            raise CognitiveObjectClidAlreadySetError(
                coid=entity.id, current_clid=entity.clid, attempted_clid=clid
            )

    def assign(self, entity: CognitiveObject, clid: uuid.UUID) -> CognitiveObject:
        """Atribui `clid` a `entity` — `None → clid` (primeira
        atribuição) ou `clid → clid` (idempotente). Qualquer outra
        transição levanta `CognitiveObjectClidAlreadySetError`
        (`PIA-8002`) via o guard já existente no modelo (E3.1/E3.1.1)
        — nenhuma lógica de imutabilidade é duplicada aqui.

        Não persiste fora do `flush` implícito de
        `ObjectRepository.update()`; não commita.
        """
        entity.clid = clid
        return self._objects.update(entity)

    def inherit(
        self,
        parent: CognitiveObject,
        child: CognitiveObject,
        *,
        relation_type: LineageRelation = LineageRelation.DERIVED_FROM,
    ) -> LineageEdge:
        """Faz `child` participar da continuidade de `parent` e
        registra a `LineageEdge` correspondente — operação atômica
        dentro da `UnitOfWork` do chamador (nenhum passo aqui commita;
        §20 do módulo E3.3).

        Política (§11 do módulo E3.3, seguindo o Domain Model): se
        `parent` ainda não tem CLID, gera um novo, atribui a `parent` e
        a `child`. Se `parent` já tem CLID, atribui o mesmo a `child`.
        Em ambos os casos, `child.clid` só pode estar `None` ou já
        igual ao CLID resolvido — caso contrário
        `CognitiveObjectClidAlreadySetError` (`PIA-8002`) é levantado
        pelo guard do modelo (INH4).

        `parent.coid`/`child.coid` nunca são copiados ou alterados —
        apenas `clid` é propagado (INH2).
        """
        resolved_clid = parent.clid if parent.clid is not None else self.generate()

        if parent.clid is None:
            self.assign(parent, resolved_clid)
        self.assign(child, resolved_clid)

        edge = self._lineage.add_edge(
            parent_coid=parent.id, child_coid=child.id, relation_type=relation_type
        )
        logger.info(
            "clid_inherited",
            extra={
                "parent_coid": str(parent.id),
                "child_coid": str(child.id),
                "clid": str(resolved_clid),
                "relation_type": str(relation_type),
            },
        )
        return edge

    def validate_imported_clid(
        self, entity: CognitiveObject, value: object
    ) -> ImportedClidValidation:
        """Contrato mínimo de validação de CLID importado (§22 do
        módulo E3.3) — classifica em `VALID`/`INVALID`/`INCOMPATIBLE`,
        sem side effects, sem persistir, **sem auto-remap silencioso**:
        um valor incompatível nunca substitui o CLID atual do objeto
        aqui — apenas é classificado.
        """
        try:
            clid = self.validate(value)
        except ClidInvalidError:
            logger.warning("imported_clid_invalid", extra={"value": repr(value)})
            return ImportedClidValidation(status=ImportedClidStatus.INVALID, clid=None)

        if entity.clid is not None and entity.clid != clid:
            logger.warning(
                "imported_clid_incompatible",
                extra={"coid": str(entity.id), "current_clid": str(entity.clid)},
            )
            return ImportedClidValidation(status=ImportedClidStatus.INCOMPATIBLE, clid=clid)

        return ImportedClidValidation(status=ImportedClidStatus.VALID, clid=clid)
