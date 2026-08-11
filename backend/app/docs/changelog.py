"""
Changelog da API — fonte única, usada para gerar `CHANGELOG_API.md`
(`scripts/generate_changelog.py`) e o rodapé da descrição OpenAPI.

Cada entrada corresponde a um módulo/etapa da V1.0. Adicionar uma nova
entrada aqui é o único lugar que precisa mudar quando um módulo futuro
alterar a API publicamente.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChangelogEntry:
    version: str
    module: str
    changes: tuple[str, ...]


API_CHANGELOG: tuple[ChangelogEntry, ...] = (
    ChangelogEntry(
        version="0.1.0",
        module="Módulo 2.5 — APIs Básicas",
        changes=(
            "Endpoint raiz GET / com informações da plataforma.",
            "GET /api/v1/health (liveness).",
            "GET /api/v1/status (readiness).",
            "GET /api/v1/version.",
            "GET /api/v1/metrics.",
            "Envelope de erro padronizado para toda a API.",
        ),
    ),
    ChangelogEntry(
        version="0.1.0",
        module="Módulo 2.6 — Sistema de Logs",
        changes=("Cabeçalhos X-Request-ID e X-Response-Time-Ms em toda resposta.",),
    ),
    ChangelogEntry(
        version="0.1.0",
        module="Módulo 2.7 — Tratamento Global de Erros",
        changes=(
            "Envelope de erro ganhou campos: success, code, category, "
            "severity, correlation_id, trace_id, timestamp, details.",
            "Catálogo oficial de códigos de erro (PIA-XXXX).",
        ),
    ),
    ChangelogEntry(
        version="0.1.0",
        module="Módulo 2.8 — Segurança Base",
        changes=(
            "Cabeçalhos de segurança em toda resposta.",
            "CORS centralizado e configurável.",
            "Novos códigos de erro: PIA-1006 a PIA-1009 (payload grande, "
            "media type não suportado, rate limit, host não confiável).",
        ),
    ),
    ChangelogEntry(
        version="0.1.0",
        module="Módulo 2.9 — Documentação OpenAPI",
        changes=(
            "Todos os endpoints documentados com resumo, descrição, tags e responses.",
            "Tags organizadas em grupos (System, Health, Status, Version, "
            "Metrics + placeholders para módulos futuros).",
            "Metadados de versão embutidos no schema OpenAPI.",
        ),
    ),
)


def render_changelog_markdown() -> str:
    """Gera o conteúdo de `CHANGELOG_API.md` a partir de `API_CHANGELOG`."""
    lines = ["# Changelog da API — PIA-OS", ""]
    for entry in API_CHANGELOG:
        lines.append(f"## {entry.version} — {entry.module}")
        lines.append("")
        for change in entry.changes:
            lines.append(f"- {change}")
        lines.append("")
    return "\n".join(lines)
