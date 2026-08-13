"""
Metadados da API — versão do backend, da API, do PIA-OS, e timestamp de
geração do schema OpenAPI.

Embutidos como extensão `x-metadata` no objeto `info` do OpenAPI (campo
`x-*` é o mecanismo padrão da especificação para extensões customizadas
— não inventa uma estrutura fora do padrão).
"""

from datetime import UTC, datetime
from typing import TypedDict

from app.config.constants import API_VERSION, PIA_OS_VERSION
from app.config.settings import Settings


class APIMetadata(TypedDict):
    api_version: str
    backend_version: str
    pia_os_version: str
    generated_at: str


def build_api_metadata(settings: Settings) -> APIMetadata:
    return APIMetadata(
        api_version=API_VERSION,
        backend_version=settings.app_version,
        pia_os_version=PIA_OS_VERSION,
        generated_at=datetime.now(UTC).isoformat(),
    )
