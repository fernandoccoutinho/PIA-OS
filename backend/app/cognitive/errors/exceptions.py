"""
Exceções de domínio do LIB-01 (CognitiveObject + Object Repository).

Toda exceção de domínio de E3 herda de `PIAOSException` (§17 do módulo
E3.1) — nenhum sistema paralelo de exceptions é criado.
"""

import uuid

from app.cognitive.errors.codes import (
    PIA_8001_IDENTITY_IMMUTABLE,
    PIA_8002_CLID_ALREADY_SET,
    PIA_8003_COID_INVALID,
    PIA_8004_COID_COLLISION,
    PIA_8005_CLID_INVALID,
    PIA_8006_LINEAGE_SELF_LINK,
    PIA_8007_LINEAGE_DUPLICATE_EDGE,
    PIA_8008_LINEAGE_ENDPOINT_NOT_FOUND,
    PIA_8009_LINEAGE_EDGE_IMMUTABLE,
    PIA_8010_TRANSFORMATION_RECORD_IMMUTABLE,
    PIA_8011_REVISION_STATUS_INVALID_TRANSITION,
    PIA_8012_REVISION_CURRENT_UNIQUENESS_VIOLATION,
    PIA_8013_RELATIONSHIP_SELF_LINK,
    PIA_8014_RELATIONSHIP_DUPLICATE,
    PIA_8015_RELATIONSHIP_ENDPOINT_NOT_FOUND,
    PIA_8016_RELATIONSHIP_IMMUTABLE,
    PIA_8017_PROVENANCE_RECORD_IMMUTABLE,
    PIA_8018_ACCESSIBILITY_INVALID_TRANSITION,
    PIA_8019_SEARCH_CRITERIA_INVALID,
    PIA_8020_CAUSAL_HISTORY_IMMUTABLE,
    PIA_8021_CAUSAL_EVENT_SELF_PREDECESSOR,
    PIA_8022_SYNC_PACKAGE_INVALID,
)
from app.exceptions.base import PIAOSException


class CognitiveObjectIdentityImmutableError(PIAOSException):
    """O COID (`id`) de um `CognitiveObject` já persistido não pode ser
    reatribuído."""

    error_code = PIA_8001_IDENTITY_IMMUTABLE

    def __init__(self, current_id: uuid.UUID | None, attempted_id: uuid.UUID | None) -> None:
        self.current_id = current_id
        self.attempted_id = attempted_id
        super().__init__(
            message=(
                f"COID {current_id} não pode ser reatribuído para {attempted_id} "
                "— identidade de CognitiveObject é permanente após persistência."
            ),
            detail={"current_id": str(current_id), "attempted_id": str(attempted_id)},
        )


class CognitiveObjectClidAlreadySetError(PIAOSException):
    """O `clid` de um `CognitiveObject` já foi atribuído e não pode ser
    sobrescrito por esta via nesta fase (LIB-03 CLID Manager ainda não
    existe)."""

    error_code = PIA_8002_CLID_ALREADY_SET

    def __init__(
        self,
        coid: uuid.UUID | None,
        current_clid: uuid.UUID,
        attempted_clid: uuid.UUID | None,
    ) -> None:
        self.coid = coid
        self.current_clid = current_clid
        self.attempted_clid = attempted_clid
        super().__init__(
            message=(
                f"CLID de CognitiveObject {coid} já é {current_clid} — não pode ser "
                f"sobrescrito para {attempted_clid} fora do CLID Manager (E3.3)."
            ),
            detail={
                "coid": str(coid),
                "current_clid": str(current_clid),
                "attempted_clid": str(attempted_clid) if attempted_clid else None,
            },
        )


class CoidInvalidError(PIAOSException):
    """Valor apresentado como COID não é um UUID válido — nem instância
    `uuid.UUID` nem string parseável como UUID (E3.2/LIB-02)."""

    error_code = PIA_8003_COID_INVALID

    def __init__(self, value: object) -> None:
        self.value = value
        super().__init__(
            message=f"Valor não é um COID válido: {value!r}.",
            detail={"value": repr(value)},
        )


class CoidCollisionError(PIAOSException):
    """Um COID já existe (ativo ou soft-deleted) e não pode ser
    reutilizado para outro `CognitiveObject` (E3.2/LIB-02).

    Identidade nunca é reciclada — mesmo um objeto soft-deleted
    continua "ocupando" seu COID permanentemente."""

    error_code = PIA_8004_COID_COLLISION

    def __init__(self, coid: uuid.UUID | None) -> None:
        self.coid = coid
        super().__init__(
            message=f"COID {coid} já existe — não pode ser reutilizado para outro objeto.",
            detail={"coid": str(coid) if coid is not None else None},
        )


class ClidInvalidError(PIAOSException):
    """Valor apresentado como CLID não é um UUID válido — nem instância
    `uuid.UUID` nem string parseável como UUID (E3.3/LIB-03)."""

    error_code = PIA_8005_CLID_INVALID

    def __init__(self, value: object) -> None:
        self.value = value
        super().__init__(
            message=f"Valor não é um CLID válido: {value!r}.",
            detail={"value": repr(value)},
        )


class LineageSelfLinkError(PIAOSException):
    """Tentativa de criar uma `LineageEdge` com `parent_coid == child_coid`
    (E3.3/LIB-03)."""

    error_code = PIA_8006_LINEAGE_SELF_LINK

    def __init__(self, coid: uuid.UUID) -> None:
        self.coid = coid
        super().__init__(
            message=f"CognitiveObject {coid} não pode ser seu próprio descendente direto.",
            detail={"coid": str(coid)},
        )


class LineageDuplicateEdgeError(PIAOSException):
    """A tripla `(parent_coid, child_coid, relation_type)` já existe
    (E3.3/LIB-03)."""

    error_code = PIA_8007_LINEAGE_DUPLICATE_EDGE

    def __init__(self, parent_coid: uuid.UUID, child_coid: uuid.UUID, relation_type: str) -> None:
        self.parent_coid = parent_coid
        self.child_coid = child_coid
        self.relation_type = relation_type
        super().__init__(
            message=(f"LineageEdge ({parent_coid} -> {child_coid}, {relation_type}) já existe."),
            detail={
                "parent_coid": str(parent_coid),
                "child_coid": str(child_coid),
                "relation_type": str(relation_type),
            },
        )


class LineageEndpointNotFoundError(PIAOSException):
    """`parent_coid` ou `child_coid` de uma `LineageEdge` não
    corresponde a nenhum `CognitiveObject` existente (E3.3/LIB-03)."""

    error_code = PIA_8008_LINEAGE_ENDPOINT_NOT_FOUND

    def __init__(self, coid: uuid.UUID) -> None:
        self.coid = coid
        super().__init__(
            message=f"CognitiveObject {coid} não existe — não pode ser endpoint de LineageEdge.",
            detail={"coid": str(coid)},
        )


class LineageEdgeImmutableError(PIAOSException):
    """Tentativa de atualizar ou remover uma `LineageEdge` já
    persistida — `LineageEdge` é append-only por decisão de domínio
    (E3.3/LIB-03, correção E3.3.1)."""

    error_code = PIA_8009_LINEAGE_EDGE_IMMUTABLE

    def __init__(self, edge_id: uuid.UUID, operation: str) -> None:
        self.edge_id = edge_id
        self.operation = operation
        super().__init__(
            message=(f"LineageEdge {edge_id} é append-only — operação '{operation}' rejeitada."),
            detail={"edge_id": str(edge_id), "operation": operation},
        )


class TransformationRecordImmutableError(PIAOSException):
    """Tentativa de atualizar ou remover um `TransformationRecord` já
    persistido — histórico append-only (E3.4/LIB-04)."""

    error_code = PIA_8010_TRANSFORMATION_RECORD_IMMUTABLE

    def __init__(self, record_id: uuid.UUID, operation: str) -> None:
        self.record_id = record_id
        self.operation = operation
        super().__init__(
            message=(
                f"TransformationRecord {record_id} é append-only — "
                f"operação '{operation}' rejeitada."
            ),
            detail={"record_id": str(record_id), "operation": operation},
        )


class RevisionStatusInvalidTransitionError(PIAOSException):
    """Transição inválida de `revision_status` em `CognitiveObject`
    (correção E3.4.0) — `SUPERSEDED` nunca volta a `CURRENT`/`None`;
    `CURRENT` nunca volta a `None`."""

    error_code = PIA_8011_REVISION_STATUS_INVALID_TRANSITION

    def __init__(self, coid: uuid.UUID | None, current: object, attempted: object) -> None:
        self.coid = coid
        self.current = current
        self.attempted = attempted
        super().__init__(
            message=(
                f"CognitiveObject {coid}: transição de revision_status "
                f"'{current}' -> '{attempted}' não é permitida."
            ),
            detail={"coid": str(coid), "current": str(current), "attempted": str(attempted)},
        )


class RevisionCurrentUniquenessViolationError(PIAOSException):
    """Tentativa de tornar `CURRENT` um `CognitiveObject` quando outro
    objeto com o mesmo CLID já é `CURRENT` (correção E3.4.1) — viola
    `COUNT(CURRENT) <= 1` por CLID."""

    error_code = PIA_8012_REVISION_CURRENT_UNIQUENESS_VIOLATION

    def __init__(
        self, clid: uuid.UUID | None, existing_current_coid: uuid.UUID | None = None
    ) -> None:
        self.clid = clid
        self.existing_current_coid = existing_current_coid
        detail_suffix = (
            f" (já ocupado por {existing_current_coid})" if existing_current_coid else ""
        )
        super().__init__(
            message=(
                f"CLID {clid} já possui um CognitiveObject CURRENT{detail_suffix} — "
                "no máximo um CURRENT por CLID."
            ),
            detail={
                "clid": str(clid),
                "existing_current_coid": (
                    str(existing_current_coid) if existing_current_coid else None
                ),
            },
        )


class RelationshipSelfLinkError(PIAOSException):
    """Tentativa de criar `Relationship` com `source_coid == target_coid`
    (E3.5/LIB-05)."""

    error_code = PIA_8013_RELATIONSHIP_SELF_LINK

    def __init__(self, coid: uuid.UUID) -> None:
        self.coid = coid
        super().__init__(
            message=f"CognitiveObject {coid} não pode se relacionar consigo mesmo.",
            detail={"coid": str(coid)},
        )


class RelationshipDuplicateError(PIAOSException):
    """A relação já existe — tripla `(source, target, type)` para
    tipos direcionados, ou par não ordenado para tipos simétricos
    (E3.5/LIB-05)."""

    error_code = PIA_8014_RELATIONSHIP_DUPLICATE

    def __init__(
        self, source_coid: uuid.UUID, target_coid: uuid.UUID, relationship_type: str
    ) -> None:
        self.source_coid = source_coid
        self.target_coid = target_coid
        self.relationship_type = relationship_type
        super().__init__(
            message=(
                f"Relationship ({source_coid} -> {target_coid}, " f"{relationship_type}) já existe."
            ),
            detail={
                "source_coid": str(source_coid),
                "target_coid": str(target_coid),
                "relationship_type": str(relationship_type),
            },
        )


class RelationshipEndpointNotFoundError(PIAOSException):
    """`source_coid` ou `target_coid` de uma `Relationship` não
    corresponde a nenhum `CognitiveObject` existente (E3.5/LIB-05)."""

    error_code = PIA_8015_RELATIONSHIP_ENDPOINT_NOT_FOUND

    def __init__(self, coid: uuid.UUID) -> None:
        self.coid = coid
        super().__init__(
            message=f"CognitiveObject {coid} não existe — não pode ser endpoint de Relationship.",
            detail={"coid": str(coid)},
        )


class RelationshipImmutableError(PIAOSException):
    """Tentativa de `update`/`delete` físico de uma `Relationship` já
    persistida — histórico append-only (E3.5/LIB-05)."""

    error_code = PIA_8016_RELATIONSHIP_IMMUTABLE

    def __init__(self, relationship_id: uuid.UUID, operation: str) -> None:
        self.relationship_id = relationship_id
        self.operation = operation
        super().__init__(
            message=(
                f"Relationship {relationship_id} é append-only — "
                f"operação '{operation}' rejeitada."
            ),
            detail={"relationship_id": str(relationship_id), "operation": operation},
        )


class ProvenanceRecordImmutableError(PIAOSException):
    """Tentativa de `update`/`delete` físico de um `ProvenanceRecord`
    já persistido — histórico append-only (E3.6/LIB-06)."""

    error_code = PIA_8017_PROVENANCE_RECORD_IMMUTABLE

    def __init__(self, provenance_id: uuid.UUID, operation: str) -> None:
        self.provenance_id = provenance_id
        self.operation = operation
        super().__init__(
            message=(
                f"ProvenanceRecord {provenance_id} é append-only — "
                f"operação '{operation}' rejeitada."
            ),
            detail={"provenance_id": str(provenance_id), "operation": operation},
        )


class AccessibilityInvalidTransitionError(PIAOSException):
    """Tentativa de transicionar `AccessibilityState` para
    `CAUSALLY_EXTINCT` sem um `reason` explícito (E3.6/LIB-06).

    O Domain Model Draft exige que essa transição específica "sempre
    tem um evento causal associado, nunca é o valor default nem um
    efeito colateral de query" — o mecanismo formal para isso
    (`CausalHistoryEvent`) é `E3.9`, ainda não implementado. Como
    proxy interino, honesto e genuinamente aplicável hoje,
    `AccessibilityManager.transition()` exige um `reason` não-vazio
    especificamente para este alvo — não é o mesmo que um evento
    causal referenciado, mas garante que a transição nunca é
    silenciosa/automática. Ver `E3_6_LIB06_PROVENANCE_ACCESSIBILITY.md`
    para a limitação documentada."""

    error_code = PIA_8018_ACCESSIBILITY_INVALID_TRANSITION

    def __init__(self, coid: uuid.UUID) -> None:
        self.coid = coid
        super().__init__(
            message=(
                f"CognitiveObject {coid}: transição para CAUSALLY_EXTINCT "
                "exige um 'reason' explícito e não-vazio."
            ),
            detail={"coid": str(coid)},
        )


class SearchCriteriaError(PIAOSException):
    """Critérios de busca malformados (E3.8/LIB-08).

    Levantada antes de qualquer acesso ao banco — uma consulta
    malformada não deve nem chegar a ser executada. Conjunto vazio de
    resultados **não** é erro: é a resposta correta de uma consulta
    bem-formada que nenhum objeto satisfaz, e não implica inexistência
    (`SEARCH MISS != NON-EXISTENCE`).
    """

    error_code = PIA_8019_SEARCH_CRITERIA_INVALID

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(
            message=f"Critérios de busca inválidos: {reason}",
            detail={"reason": reason},
        )


class CausalHistoryImmutableError(PIAOSException):
    """`update`/`delete` físico de história causal já persistida
    (E3.9/LIB-09) — sempre rejeitado.

    O registro histórico é ele próprio um rastro preservado: apagá-lo
    não simula a extinção de um rastro físico, apenas destrói a
    evidência que o sistema deveria guardar.
    """

    error_code = PIA_8020_CAUSAL_HISTORY_IMMUTABLE

    def __init__(self, entity_id: uuid.UUID, *, operation: str, entity: str) -> None:
        self.entity_id = entity_id
        self.operation = operation
        self.entity = entity
        super().__init__(
            message=(
                f"{entity} {entity_id}: '{operation}' não é permitido — "
                "história causal é append-only."
            ),
            detail={"id": str(entity_id), "operation": operation, "entity": entity},
        )


class CausalEventSelfPredecessorError(PIAOSException):
    """Evento causal apontado como predecessor de si mesmo
    (E3.9/LIB-09)."""

    error_code = PIA_8021_CAUSAL_EVENT_SELF_PREDECESSOR

    def __init__(self, event_id: uuid.UUID) -> None:
        self.event_id = event_id
        super().__init__(
            message=f"CausalHistoryEvent {event_id} não pode ser predecessor de si mesmo.",
            detail={"event_id": str(event_id)},
        )


class SyncPackageInvalidError(PIAOSException):
    """Pacote de sincronização inutilizável (E3.11/LIB-11).

    Levantada **antes** de qualquer escrita: um pacote malformado não
    deve conseguir aplicar nada, nem parcialmente. Conflito de
    identidade não passa por aqui — é resultado, não erro.
    """

    error_code = PIA_8022_SYNC_PACKAGE_INVALID

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(
            message=f"Pacote de sincronização inválido: {reason}",
            detail={"reason": reason},
        )
