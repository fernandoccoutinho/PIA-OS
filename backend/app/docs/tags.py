"""
Catálogo de tags OpenAPI.

Cada tag tem nome + descrição, usado em `openapi_tags` (Módulo 2.9). Os
grupos marcados "estrutura" existem apenas como placeholders — nenhum
endpoint os usa ainda; existem para que a navegação do Swagger/ReDoc já
reflita a organização final da API, mesmo antes desses módulos existirem.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TagInfo:
    name: str
    description: str
    placeholder: bool = False


TAG_SYSTEM = TagInfo(name="System", description="Informações gerais da plataforma PIA-OS.")
TAG_HEALTH = TagInfo(name="Health", description="Verificação de vivacidade (liveness) do processo.")
TAG_STATUS = TagInfo(
    name="Status",
    description="Verificação de prontidão (readiness) — aplicação, banco, ORM, configuração.",
)
TAG_VERSION = TagInfo(name="Version", description="Versões do backend, API, banco e PIA-OS.")
TAG_METRICS = TagInfo(name="Metrics", description="Métricas mínimas de processo.")
TAG_PREDICTIVE_EVALUATIONS = TagInfo(
    name="Predictive Evaluations",
    description=(
        "Acesso programático à avaliação preditiva governada (E6.2) — "
        "credencial de serviço, escopo técnico e cota por principal."
    ),
)

TAG_ADMINISTRATION = TagInfo(
    name="Administration",
    description="Administração da plataforma — estrutura para módulos futuros.",
    placeholder=True,
)
TAG_AUTHENTICATION = TagInfo(
    name="Authentication",
    description="Login, sessões e tokens — estrutura para módulos futuros.",
    placeholder=True,
)
TAG_OBJECTS = TagInfo(
    name="Objects",
    description="Objetos Cognitivos do PIA-OS — estrutura para módulos futuros.",
    placeholder=True,
)
TAG_SESSIONS = TagInfo(
    name="Sessions",
    description="Sessões de interação — estrutura para módulos futuros.",
    placeholder=True,
)

ALL_TAGS: tuple[TagInfo, ...] = (
    TAG_SYSTEM,
    TAG_HEALTH,
    TAG_STATUS,
    TAG_VERSION,
    TAG_METRICS,
    TAG_PREDICTIVE_EVALUATIONS,
    TAG_ADMINISTRATION,
    TAG_AUTHENTICATION,
    TAG_OBJECTS,
    TAG_SESSIONS,
)

ACTIVE_TAG_NAMES: frozenset[str] = frozenset(t.name for t in ALL_TAGS if not t.placeholder)
PLACEHOLDER_TAG_NAMES: frozenset[str] = frozenset(t.name for t in ALL_TAGS if t.placeholder)


def build_openapi_tags_metadata() -> list[dict[str, str]]:
    """Formato que `FastAPI(openapi_tags=...)` espera."""
    return [{"name": t.name, "description": t.description} for t in ALL_TAGS]
