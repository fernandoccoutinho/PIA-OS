"""
CoidManager — LIB-02, identidade permanente (COID) de `CognitiveObject`.

`app.cognitive.services` existe pela primeira vez a partir deste
módulo — E3.1 deliberadamente não criou essa camada porque
`ObjectRepository` cobria tudo que era necessário (§4 do módulo E3.1:
"não crie service vazio apenas por simetria"). `CoidManager` tem
responsabilidade real que não pertence a um repositório: geração,
validação de formato e política de colisão são regras de domínio, não
acesso a dados — o repositório continua sendo o único ponto que fala
com o banco.

Responsabilidade única: identidade permanente do objeto. `CoidManager`
nunca persiste, nunca commita, não conhece CLID, provenance, lineage,
provider de IA, busca semântica, deduplicação de conteúdo, seleção de
objetos ou equivalência causal (§7 do módulo E3.2).
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.cognitive.errors.exceptions import CoidCollisionError, CoidInvalidError
from app.cognitive.repositories.object_repository import ObjectRepository
from app.utils.logger import get_logger

logger = get_logger("app.cognitive.services.coid_manager")


class ImportedCoidStatus(StrEnum):
    """Classificação mínima de um COID importado — contrato exigido
    pelo módulo E3.2 mesmo antes do Synchronization Manager completo
    (E3.11)."""

    VALID = "valid"
    INVALID = "invalid"
    COLLISION = "collision"


@dataclass(frozen=True)
class ImportedCoidValidation:
    """Resultado de `CoidManager.validate_imported_coid()`.

    `coid` é `None` apenas quando `status == INVALID` (não havia um
    UUID válido para reportar)."""

    status: ImportedCoidStatus
    coid: uuid.UUID | None


class CoidManager:
    """Geração, validação e política de unicidade de COID.

    Depende de `ObjectRepository` apenas para consultar existência —
    nunca para persistir (`add`/`update`/`delete` continuam de
    responsabilidade exclusiva de quem controla a `UnitOfWork`).
    """

    def __init__(self, object_repository: ObjectRepository) -> None:
        self._repository = object_repository

    def generate(self) -> uuid.UUID:
        """Gera um COID candidato — local, independente de provider,
        payload, sessão ou modelo de IA (§8, §15, §16 do módulo E3.2).
        Mesmo mecanismo já usado por `UUIDMixin` (`uuid.uuid4`) — não
        introduz um segundo algoritmo de geração de identidade.

        Não garante unicidade sozinho — combine com `assert_unique()`
        ou use `generate_unique()`.
        """
        return uuid.uuid4()

    def generate_unique(self, *, max_attempts: int = 5) -> uuid.UUID:
        """Gera um COID e garante, por pré-checagem, que ainda não
        existe — repete em caso de colisão (defesa em profundidade;
        colisão real de UUID v4 gerado localmente é, na prática,
        desprezível, ~2^-122). Usar apenas para geração local
        automática — COID importado nunca passa por aqui, sempre por
        `validate_imported_coid()`.

        Continua sujeito a corrida (TOCTOU) entre a pré-checagem e a
        persistência real — a garantia final vem da constraint de PK
        em `ObjectRepository.add()` (§22, §23 do módulo E3.2).

        Levanta `CoidCollisionError` se esgotar `max_attempts` — sinal
        de algo genuinamente anômalo, não de operação normal.
        """
        last_candidate: uuid.UUID | None = None
        for _ in range(max_attempts):
            last_candidate = self.generate()
            try:
                self.assert_unique(last_candidate)
            except CoidCollisionError:
                logger.warning(
                    "coid_generation_collision_retry", extra={"candidate": str(last_candidate)}
                )
                continue
            return last_candidate
        raise CoidCollisionError(last_candidate)

    def validate(self, value: object) -> uuid.UUID:
        """Valida formato — aceita `uuid.UUID` diretamente ou `str`
        parseável como UUID. Já normaliza para `uuid.UUID` no retorno
        (não existe um `normalize()` separado — seria redundante,
        `validate()` já resolve isso; §25/V5 do módulo E3.2: "não crie
        normalização desnecessária se UUID já resolve isso").

        Levanta `CoidInvalidError` para qualquer outro tipo/formato.
        """
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str):
            try:
                return uuid.UUID(value)
            except ValueError as exc:
                raise CoidInvalidError(value) from exc
        raise CoidInvalidError(value)

    def assert_unique(self, coid: uuid.UUID) -> None:
        """Levanta `CoidCollisionError` se já existir um
        `CognitiveObject` — ativo **ou soft-deleted** — com este COID.
        Identidade nunca é reciclada: um objeto apagado logicamente
        continua "ocupando" seu COID permanentemente (`include_deleted=True`).

        Pré-checagem apenas — sujeita a TOCTOU; a garantia final é a
        constraint de PK em `ObjectRepository.add()`.
        """
        if self._repository.get_by_id(coid, include_deleted=True) is not None:
            raise CoidCollisionError(coid)

    def validate_imported_coid(self, value: object) -> ImportedCoidValidation:
        """Contrato mínimo de validação de COID importado (§11 do
        módulo E3.2) — classifica em `VALID`/`INVALID`/`COLLISION`,
        sem side effects, sem persistir, **sem auto-remap silencioso**
        (§12): um COID colidente nunca é trocado por outro aqui —
        apenas classificado. Remapeamento auditável, se algum dia
        existir, pertence a `LIB-11 Synchronization Manager` (E3.11).
        """
        try:
            coid = self.validate(value)
        except CoidInvalidError:
            logger.warning("imported_coid_invalid", extra={"value": repr(value)})
            return ImportedCoidValidation(status=ImportedCoidStatus.INVALID, coid=None)

        existing = self._repository.get_by_id(coid, include_deleted=True)
        if existing is not None:
            logger.warning("imported_coid_collision", extra={"coid": str(coid)})
            return ImportedCoidValidation(status=ImportedCoidStatus.COLLISION, coid=coid)

        return ImportedCoidValidation(status=ImportedCoidStatus.VALID, coid=coid)
