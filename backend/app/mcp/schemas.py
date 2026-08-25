"""
Schemas das cinco tools MCP — fechados, tipados e versionados.

```text
UNKNOWN_FIELD = REFUSED
```

`extra="forbid"` em toda entrada. Campo desconhecido é recusa, não aviso:
um campo ignorado em silêncio é um cliente acreditando ter pedido algo
que não foi lido — e, num boundary de segurança, é a diferença entre
"filtrei" e "achei que tinha filtrado".

## Versionamento por hash

`SCHEMA_VERSION` é derivado do próprio conteúdo dos schemas. Mudar
qualquer campo muda o hash, e o hash entra nas provas: schema alterado
sem ninguém perceber deixa de ser possível.

## Redação estrutural na saída

Nenhuma resposta carrega principal interno, token, segredo, prompt bruto,
contexto bruto ou conteúdo de retorno persistido. As projeções aqui são
construídas por **lista de campos permitidos**, nunca por exclusão de
proibidos: uma lista de exclusão esquece o campo que ainda não existe.

```text
ALLOWLIST_SURVIVES_NEW_FIELDS · DENYLIST_DOES_NOT
```
"""

import hashlib
import json
import uuid
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

SCHEMA_CONTRACT_VERSION: Final = "e7.4-2.v1"


class _Fechado(BaseModel):
    """Base de toda entrada: proíbe campo desconhecido."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ScheduleReadInput(_Fechado):
    schedule_id: uuid.UUID


class AttemptsListInput(_Fechado):
    schedule_id: uuid.UUID


class GovernanceReadInput(_Fechado):
    schedule_id: uuid.UUID


class HandoffExportInput(_Fechado):
    """Sem `request_sha256`.

    O `CommandReceiptService` **deriva** a impressão digital canônica a
    partir da operação e dos identificadores. Aceitá-la do cliente
    deixaria quem chama escolher a chave de idempotência do servidor — e
    duas requisições materialmente diferentes poderiam se declarar a
    mesma.

    ```text
    CLIENT_SUPPLIED_FINGERPRINT = CLIENT_CHOOSES_WHAT_COUNTS_AS_SAME
    ```
    """

    schedule_id: uuid.UUID
    step_id: uuid.UUID
    command_key: str


class ReturnImportInput(_Fechado):
    """Campos tipados, nunca `payload: dict` genérico.

    Um dicionário livre atravessaria o schema fechado carregando o que
    quisesse: os campos que o `ReturnValidationService` exige ficariam
    sem validação de fronteira, e os que ele não conhece entrariam junto.

    ```text
    GENERIC_PAYLOAD = CLOSED_SCHEMA_WITH_AN_OPEN_HOLE
    ```
    """

    command_key: str
    schedule_id: uuid.UUID
    step_id: uuid.UUID
    attempt_id: uuid.UUID
    media_type: str
    content: str
    declared_instance_id: str
    declared_output_ref: str | None = None
    declared_provider_id: str | None = None
    declared_model_id: str | None = None


ENTRADAS: Final[dict[str, type[_Fechado]]] = {
    "schedule.read": ScheduleReadInput,
    "attempts.list": AttemptsListInput,
    "governance.read": GovernanceReadInput,
    "handoff.export": HandoffExportInput,
    "return.import": ReturnImportInput,
}


def _digest() -> str:
    corpo = {nome: modelo.model_json_schema() for nome, modelo in sorted(ENTRADAS.items())}
    return hashlib.sha256(
        json.dumps(corpo, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


SCHEMA_SHA256: Final = _digest()
SCHEMA_VERSION: Final = f"{SCHEMA_CONTRACT_VERSION}:{SCHEMA_SHA256[:12]}"

CAMPOS_PROIBIDOS_NA_SAIDA: Final[frozenset[str]] = frozenset(
    {
        "token",
        "access_token",
        "bearer",
        "secret",
        "credential",
        "prompt",
        "raw_prompt",
        "raw_context",
        "context",
        "payload",
        "return_payload",
        "content",
        "control_principal_ref",
        "principal_ref",
    }
)
"""Verificado nas provas contra o que as tools realmente devolvem.

A allowlist de projeção é a defesa; esta lista é o alarme que dispara se
alguém trocar a allowlist por um `dict()` inteiro.
"""


def projetar_schedule(vista: Any) -> dict[str, Any]:
    """Allowlist. Nunca `vars()`, nunca `model_dump()` do objeto interno."""
    return {
        "schedule_id": str(vista.schedule_id),
        "state": str(getattr(vista.state, "value", vista.state)),
        "schema_version": SCHEMA_VERSION,
    }


def projetar_tentativa(projecao: Any) -> dict[str, Any]:
    """Tentativa sem conteúdo de retorno persistido."""
    return {
        "attempt_id": str(projecao.attempt_id),
        "state": str(getattr(projecao.state, "value", projecao.state)),
        "outcome": (
            str(getattr(projecao.outcome, "value", projecao.outcome))
            if getattr(projecao, "outcome", None) is not None
            else None
        ),
    }


def projetar_governanca(projecao: Any) -> dict[str, Any]:
    """Governança em contagens e estados, nunca em conteúdo."""
    return {
        "schedule_id": str(projecao.schedule_id),
        "schedule_state": str(getattr(projecao.schedule_state, "value", projecao.schedule_state)),
        "delegation_count": len(getattr(projecao, "delegations", ()) or ()),
        "event_count": len(getattr(projecao, "events", ()) or ()),
        "schema_version": SCHEMA_VERSION,
    }
