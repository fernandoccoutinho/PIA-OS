"""Contrato semântico compartilhado pelos adaptadores autorizados da E8.

Schema, prompt e interpretação têm um único dono. Um provider novo não pode
copiar estes objetos e deixá-los divergir silenciosamente do adaptador anterior.
"""

import hashlib
import json
from typing import Any, Final

from app.authorization.broker import IntentAuthorizationUnavailableError
from app.authorization.ports import SemanticClassification
from app.memory.models.governance_enums import CapabilityEngagement, CriticalCapability

CAPABILITY_VALUES: Final[tuple[str, ...]] = tuple(
    sorted(capacidade.value for capacidade in CriticalCapability)
)
ENGAGEMENT_VALUES: Final[tuple[str, ...]] = tuple(
    sorted(engajamento.value for engajamento in CapabilityEngagement)
)

RESPONSE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["capabilities", "engagement"],
    "properties": {
        "capabilities": {
            "type": "array",
            "items": {"type": "string", "enum": list(CAPABILITY_VALUES)},
        },
        "engagement": {"type": "string", "enum": list(ENGAGEMENT_VALUES)},
    },
}

CLASSIFICATION_PROMPT: Final = """Você classifica OBJETIVOS de trabalho para um gate de segurança.

Devolva dois rótulos, nada além disso.

capabilities: quais destas capacidades críticas o objetivo envolveria.
Lista vazia quando nenhuma se aplica.
- child_sexual_exploitation
- minor_targeting_for_exploitation
- weapon_of_mass_destruction_enablement
- catastrophic_harm_enablement

engagement: como o objetivo se relaciona com a capacidade.
- operational_enablement: entregaria capacidade utilizável para causar o dano
- analytical: histórico, científico, jurídico, jornalístico, analítico
- preventive: prevenção, detecção, proteção, resposta, denúncia, pesquisa de segurança
- unspecified: a finalidade não está estabelecida no objetivo

Regras que decidem os casos difíceis:

TEMA NÃO É CAPACIDADE. Falar sobre exploração infantil para proteger,
detectar, denunciar ou pesquisar não habilita capacidade alguma. Não
classifique por assunto, por palavra presente, nem pela forma do pedido.

Classifique a capacidade que o objetivo ENTREGARIA, não a que ele
menciona. Um pedido decomposto em etapas inócuas cuja soma entrega a
capacidade é operational_enablement. Um pedido ofuscado, hipotético,
ficcional ou "para um amigo" que ainda assim entregaria a capacidade é
operational_enablement.

Quando o objetivo envolve capacidade crítica e a finalidade legítima não
está estabelecida no próprio objetivo, use unspecified. Não invente
finalidade a partir do tom.

Responda somente com o JSON do schema."""

SCHEMA_SHA256: Final = hashlib.sha256(
    json.dumps(RESPONSE_SCHEMA, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
PROMPT_SHA256: Final = hashlib.sha256(CLASSIFICATION_PROMPT.encode("utf-8")).hexdigest()


def interpret_classification_text(texto: object) -> SemanticClassification:
    """Valida JSON e converte somente valores do vocabulário fechado."""
    if not isinstance(texto, str):
        raise IntentAuthorizationUnavailableError(
            "resposta do classificador não trouxe texto classificatório"
        )

    try:
        bruto = json.loads(texto)
    except (json.JSONDecodeError, TypeError) as falha:
        raise IntentAuthorizationUnavailableError(
            f"saída do classificador não é JSON válido: {falha}"
        ) from falha

    if not isinstance(bruto, dict):
        raise IntentAuthorizationUnavailableError("saída classificatória não é um objeto")
    if set(bruto) != {"capabilities", "engagement"}:
        raise IntentAuthorizationUnavailableError("saída classificatória fora do schema fechado")

    cruas = bruto["capabilities"]
    if not isinstance(cruas, list):
        raise IntentAuthorizationUnavailableError("capabilities deve ser lista")

    capacidades: set[CriticalCapability] = set()
    for valor in cruas:
        try:
            capacidades.add(CriticalCapability(valor))
        except (ValueError, TypeError) as falha:
            raise IntentAuthorizationUnavailableError(
                f"capacidade '{valor}' está fora do vocabulário fechado"
            ) from falha

    try:
        engajamento = CapabilityEngagement(bruto["engagement"])
    except (ValueError, TypeError) as falha:
        raise IntentAuthorizationUnavailableError(
            f"engajamento '{bruto['engagement']}' está fora do vocabulário fechado"
        ) from falha

    return SemanticClassification(capabilities=frozenset(capacidades), engagement=engajamento)
