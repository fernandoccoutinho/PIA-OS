"""
CognitiveObject — unidade persistente fundamental da Biblioteca
Cognitiva (`E3.1` / `LIB-01`).

Contrato: `E3_DOMAIN_MODEL_DRAFT.md`, seção "0. CognitiveObject".
Nenhum campo além de `coid` (= `id`, herdado de `BaseModel`), `clid`,
`accessibility` e os timestamps herdados é definido aqui — o Draft não
prevê um campo de conteúdo/payload nesta fase, e nada é inventado além
do contrato (ver `E3_1_LIB01_OBJECT_REPOSITORY.md`, seção
"Limitações", para a discussão completa dessa ausência).

`CognitiveObject` é genérico por construção: não é documento, mensagem,
memória, prompt nem resposta de IA especificamente — é a unidade de
identidade e ciclo de vida sobre a qual features futuras (E3.2+)
constroem.
"""

import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.cognitive.errors.exceptions import (
    CognitiveObjectClidAlreadySetError,
    CognitiveObjectIdentityImmutableError,
)
from app.cognitive.models.enums import AccessibilityState
from app.models.base_model import BaseModel
from app.models.mixins import SoftDeleteMixin


class CognitiveObject(BaseModel, SoftDeleteMixin):
    """Unidade persistente genérica do patrimônio cognitivo.

    Identidade: `id` (herdado de `BaseModel`/`UUIDMixin`) É o COID —
    nenhum segundo mecanismo de chave primária é criado (§7 do módulo
    E3.1: "Se a baseline já fornece UUID primário por BaseModel: use-a
    conforme contrato"). A propriedade `coid` abaixo é só um alias de
    leitura para usar a linguagem ubíqua do domínio sem duplicar a
    coluna.

    Exclusão: usa `SoftDeleteMixin` (mecanismo já aprovado na baseline)
    — exclusão física é evitada porque destruiria identidade/histórico
    que módulos futuros (E3.3 Lineage, E3.9 CausalHistory) precisarão
    reconstruir.
    """

    __tablename__ = "cognitive_objects"

    clid: Mapped[uuid.UUID | None] = mapped_column(nullable=True, default=None)
    """Continuidade conceitual/linhagem — `None` até ser atribuído por
    `LIB-03 CLID Manager` (E3.3). Gravável de `None` para um valor uma
    única vez; ver `_reject_clid_overwrite` abaixo. Este módulo (E3.1)
    não implementa geração, unicidade nem semântica de branching/merge
    de CLID — apenas preserva a coluna."""

    accessibility: Mapped[AccessibilityState] = mapped_column(
        SAEnum(
            AccessibilityState,
            name="accessibility_state",
            native_enum=False,
            length=32,
            # Por padrão sa.Enum persiste o NOME do membro ("ACTIVE"),
            # não o `.value` ("active") — values_callable troca para
            # persistir o `.value`, para o valor gravado no banco não
            # depender da convenção de nomenclatura Python do enum e
            # para bater com `server_default` abaixo (que usa `.value`).
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=AccessibilityState.ACTIVE,
        server_default=AccessibilityState.ACTIVE.value,
    )
    """Ver `app.cognitive.models.enums.AccessibilityState` — campo
    estrutural exigido pelo Domain Model; nenhuma política de transição
    é aplicada por este módulo (isso é E3.6)."""

    @property
    def coid(self) -> uuid.UUID | None:
        """Alias de leitura de `id` — COID é o nome do domínio para a
        identidade permanente; a coluna real continua sendo `id` (não
        há dois mecanismos de identidade)."""
        return self.id

    @validates("clid")
    def _reject_clid_overwrite(self, key: str, value: uuid.UUID | None) -> uuid.UUID | None:
        """Permite `None` → valor (primeira atribuição, tipicamente por
        `LIB-03 CLID Manager`) e valor → mesmo valor (idempotente).
        Rejeita valor → valor diferente — essa mudança só pode
        acontecer via `TransformationRecord`/`LineageEdge` explícito
        (E3.4/E3.3), que não existem ainda em E3.1.
        """
        if self.clid is not None and value is not None and value != self.clid:
            raise CognitiveObjectClidAlreadySetError(
                coid=self.id, current_clid=self.clid, attempted_clid=value
            )
        return value


@event.listens_for(CognitiveObject, "before_update")
def _reject_coid_reassignment(mapper: object, connection: object, target: CognitiveObject) -> None:
    """Rejeita qualquer UPDATE que altere `id` (COID) de um
    `CognitiveObject` já persistido.

    Usa o evento de mapper `before_update` (não `@validates`) de
    propósito: `@validates` também dispararia durante a geração do
    valor default no primeiro INSERT e durante hidratação de leitura,
    exigindo lógica extra para distinguir "primeira atribuição" de
    "reatribuição". `before_update` só dispara quando o SQLAlchemy já
    determinou, por um UPDATE pendente no flush, que a linha existente
    está sendo modificada — o cenário exato descrito no módulo E3.1,
    §8: "create → persist → retrieve → attempt identity mutation →
    REJECTED".
    """
    history = sa_inspect(target).attrs.id.history
    if history.has_changes():
        old_value = history.deleted[0] if history.deleted else None
        raise CognitiveObjectIdentityImmutableError(current_id=old_value, attempted_id=target.id)
