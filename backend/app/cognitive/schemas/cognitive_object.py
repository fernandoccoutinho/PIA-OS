"""
Schemas Pydantic de `CognitiveObject` — apenas os estritamente
necessários ao LIB-01 (§23 do módulo E3.1).

Nomes seguem a convenção `<Entidade><Ação>` (`Create`/`Read`/`Update`)
— não há convenção prévia no projeto para schemas de domínio (E1/E2
só definem schemas genéricos em `app.schemas.common`/`app.schemas.error`),
então esta é a primeira instância; segue o padrão usual do ecossistema
Pydantic/FastAPI.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.cognitive.models.enums import AccessibilityState


class CognitiveObjectCreate(BaseModel):
    """Payload de criação. `accessibility` não é aceito aqui — todo
    `CognitiveObject` novo nasce `ACTIVE`; nenhuma política de estado
    inicial diferente é implementada em E3.1 (isso é E3.6)."""

    clid: uuid.UUID | None = Field(
        default=None,
        description=(
            "Continuidade conceitual/linhagem, se já conhecida no momento da "
            "criação (ex.: importação de um objeto com linhagem externa "
            "preexistente). Normalmente None — populado depois por LIB-03 "
            "CLID Manager (E3.3)."
        ),
    )


class CognitiveObjectRead(BaseModel):
    """Representação de leitura — espelha as colunas persistidas."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="COID — identidade permanente do CognitiveObject.")
    clid: uuid.UUID | None = Field(
        default=None, description="Continuidade conceitual/linhagem, se atribuída."
    )
    accessibility: AccessibilityState = Field(
        description="Estado de acessibilidade estrutural (política completa é E3.6)."
    )
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = Field(
        default=None, description="Timestamp de exclusão lógica (soft delete), se aplicável."
    )
    is_deleted: bool = Field(description="Derivado de deleted_at is not None.")


class CognitiveObjectUpdate(BaseModel):
    """Payload de atualização. Deliberadamente NÃO inclui `id` (COID é
    imutável — nunca aceito em um payload de update) nem
    `accessibility` (nenhuma política de transição existe em E3.1).

    Único campo atualizável: `clid`, e apenas de `None` para um valor
    — uma sobrescrita de um `clid` já definido é rejeitada pelo
    repositório/modelo (`CognitiveObjectClidAlreadySetError`), não por
    este schema (a validação de "já setado" depende do estado
    persistido atual, que o schema sozinho não conhece).
    """

    clid: uuid.UUID = Field(
        description="Valor a atribuir ao CLID — só aceito se o objeto ainda não tiver um."
    )
