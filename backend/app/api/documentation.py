"""
Verificador automático de consistência da documentação da API.

Inspeciona `app.routes` (rotas reais registradas) para detectar: rotas
sem resumo, sem descrição, sem tags, ou sem nenhuma response documentada
além do sucesso padrão. Também verifica schemas públicos sem
`description` em algum campo (`app/docs/schemas.py`).

Não é um endpoint HTTP — é uma função chamável por testes ou por
`scripts/check_api_docs.py`, gerando um `ConsistencyReport`.
"""

from dataclasses import dataclass, field

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.docs.schemas import PUBLIC_SCHEMAS, fields_missing_description
from app.docs.tags import ACTIVE_TAG_NAMES


@dataclass
class ConsistencyReport:
    endpoints_without_summary: list[str] = field(default_factory=list)
    endpoints_without_description: list[str] = field(default_factory=list)
    endpoints_without_tags: list[str] = field(default_factory=list)
    endpoints_with_unknown_tags: list[str] = field(default_factory=list)
    endpoints_without_documented_responses: list[str] = field(default_factory=list)
    schemas_without_full_description: dict[str, list[str]] = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return not (
            self.endpoints_without_summary
            or self.endpoints_without_description
            or self.endpoints_without_tags
            or self.endpoints_with_unknown_tags
            or self.endpoints_without_documented_responses
            or self.schemas_without_full_description
        )

    def render(self) -> str:
        if self.is_clean:
            return "Relatório de Consistência da Documentação: nenhum problema encontrado."
        lines = ["Relatório de Consistência da Documentação:"]
        for label, items in (
            ("Endpoints sem summary", self.endpoints_without_summary),
            ("Endpoints sem description", self.endpoints_without_description),
            ("Endpoints sem tags", self.endpoints_without_tags),
            ("Endpoints com tags fora do catálogo", self.endpoints_with_unknown_tags),
            ("Endpoints sem responses documentadas", self.endpoints_without_documented_responses),
        ):
            if items:
                lines.append(f"- {label}: {items}")
        for schema_name, fields in self.schemas_without_full_description.items():
            lines.append(f"- Schema '{schema_name}' com campos sem description: {fields}")
        return "\n".join(lines)


def check_endpoint_documentation(app: FastAPI) -> ConsistencyReport:
    """Verifica cada `APIRoute` real da aplicação — não uma lista mantida
    à parte, que poderia divergir do que está de fato registrado."""
    report = ConsistencyReport()

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue  # rotas de documentação (Swagger/ReDoc) não são endpoints da API

        identifier = f"{list(route.methods or [])} {route.path}"

        if not route.summary:
            report.endpoints_without_summary.append(identifier)
        if not route.description:
            report.endpoints_without_description.append(identifier)
        if not route.tags:
            report.endpoints_without_tags.append(identifier)
        else:
            unknown = [t for t in route.tags if t not in ACTIVE_TAG_NAMES]
            if unknown:
                report.endpoints_with_unknown_tags.append(f"{identifier} ({unknown})")
        # Toda rota tem >=1 response de sucesso implícita (o response_model);
        # exigimos que pelo menos uma response de erro também esteja documentada.
        if not route.responses or len(route.responses) == 0:
            report.endpoints_without_documented_responses.append(identifier)

    for schema in PUBLIC_SCHEMAS:
        missing = fields_missing_description(schema)
        if missing:
            report.schemas_without_full_description[schema.__name__] = missing

    return report
