#!/usr/bin/env python3
"""
Verificador de consistência da documentação (Módulo 2.12).

Roda sem depender de nada de `app/` — só varre arquivos `.md` do
repositório. Uso:

    PYTHONPATH=. python scripts/check_docs_consistency.py

Sai com código 1 se algum problema for encontrado.
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Diretórios cuja documentação markdown entra na varredura.
DOC_ROOTS = [
    BACKEND_ROOT / "docs",
    BACKEND_ROOT / "deploy",
    BACKEND_ROOT / "Developer_Build_Kit",  # Módulo 2.13
]
TOP_LEVEL_DOCS = [
    BACKEND_ROOT / "README.md",
    BACKEND_ROOT / "README_BACKEND.md",
    BACKEND_ROOT / "CONTRIBUTING.md",
    BACKEND_ROOT / "CHANGELOG_API.md",
    # Módulo 2.13 — relatórios e artefatos da baseline oficial
    BACKEND_ROOT / "CHANGELOG.md",
    BACKEND_ROOT / "BASELINE.md",
    BACKEND_ROOT / "BASELINE_FREEZE.md",
    BACKEND_ROOT / "PROJECT_METRICS.md",
    BACKEND_ROOT / "KNOWN_LIMITATIONS.md",
    BACKEND_ROOT / "TRACEABILITY_MATRIX.md",
    BACKEND_ROOT / "DEPENDENCY_MATRIX.md",
    BACKEND_ROOT / "STRUCTURE_MANIFEST.md",
    BACKEND_ROOT / "FINAL_CHECKLIST.md",
]

# Arquivos que são pontos de entrada — não contam como "órfãos" mesmo
# que nenhum outro documento os referencie (é normal um índice não ser
# referenciado por ninguém, ele é o ponto de partida da navegação).
ENTRY_POINTS = {
    "README.md",
    "README_BACKEND.md",
    "README_DEPLOY.md",
    "index.md",
    "CONTRIBUTING.md",
    "CHANGELOG_API.md",
}

# Stubs de redirecionamento — mantidos por compatibilidade com caminhos
# ainda referenciados por docstrings do código-fonte (Módulos 2.3-2.9),
# que o Módulo 2.12 explicitamente não altera. Um stub nunca é
# referenciado por outro .md de propósito (o conteúdo real já foi
# movido) — não é o tipo de "documento órfão" que este verificador
# deveria sinalizar como problema.
REDIRECT_STUB_MARKER = "foi consolidado em"

LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


@dataclass
class ConsistencyReport:
    broken_links: list[str] = field(default_factory=list)
    orphaned_docs: list[str] = field(default_factory=list)
    unreferenced_diagrams: list[str] = field(default_factory=list)
    unused_adrs: list[str] = field(default_factory=list)
    missing_required_files: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (
            self.broken_links
            or self.orphaned_docs
            or self.unreferenced_diagrams
            or self.unused_adrs
            or self.missing_required_files
        )

    def render(self) -> str:
        if self.is_clean:
            return "Relatório de Consistência da Documentação: nenhum problema encontrado."
        lines = ["Relatório de Consistência da Documentação:"]
        for label, items in (
            ("Links quebrados", self.broken_links),
            ("Documentos órfãos (nunca referenciados)", self.orphaned_docs),
            ("Diagramas não referenciados", self.unreferenced_diagrams),
            ("ADRs não referenciados no índice", self.unused_adrs),
            ("Arquivos obrigatórios ausentes", self.missing_required_files),
        ):
            if items:
                lines.append(f"- {label}:")
                lines.extend(f"    {item}" for item in items)
        return "\n".join(lines)


def _all_markdown_files() -> list[Path]:
    files: list[Path] = list(TOP_LEVEL_DOCS)
    for root in DOC_ROOTS:
        files.extend(sorted(root.rglob("*.md")))
    return [f for f in files if f.exists()]


def _extract_links(md_file: Path) -> list[str]:
    content = md_file.read_text(encoding="utf-8")
    return LINK_PATTERN.findall(content)


def _display_path(path: Path) -> str:
    """Caminho relativo a `BACKEND_ROOT` quando possível — caso contrário
    (ex.: um arquivo de teste em `tmp_path`, fora do repositório), o
    caminho absoluto. `relative_to` lança `ValueError` se `path` não for
    descendente de `BACKEND_ROOT`, o que aconteceria sempre em teste
    unitário isolado se não fosse por este fallback.
    """
    try:
        return str(path.relative_to(BACKEND_ROOT))
    except ValueError:
        return str(path)


def check_broken_links(md_files: list[Path]) -> list[str]:
    broken = []
    for md_file in md_files:
        for link in _extract_links(md_file):
            if link.startswith(("http://", "https://", "#", "mailto:")):
                continue  # externo ou âncora — fora do escopo desta checagem
            target_path = link.split("#")[0]  # remove âncora de seção, se houver
            if not target_path:
                continue
            resolved = (md_file.parent / target_path).resolve()
            if not resolved.exists():
                broken.append(f"{_display_path(md_file)} -> {link}")
    return broken


def check_orphaned_docs(md_files: list[Path]) -> list[str]:
    referenced: set[Path] = set()
    for md_file in md_files:
        for link in _extract_links(md_file):
            if link.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target_path = link.split("#")[0]
            if not target_path:
                continue
            resolved = (md_file.parent / target_path).resolve()
            if resolved.exists():
                referenced.add(resolved)

    orphaned = []
    for md_file in md_files:
        if md_file.name in ENTRY_POINTS:
            continue
        if REDIRECT_STUB_MARKER in md_file.read_text(encoding="utf-8"):
            continue
        if md_file.resolve() not in referenced:
            orphaned.append(_display_path(md_file))
    return orphaned


def check_unreferenced_diagrams() -> list[str]:
    diagrams_dir = BACKEND_ROOT / "docs" / "diagrams"
    if not diagrams_dir.exists():
        return []
    drawio_files = {f.stem for f in diagrams_dir.glob("*.drawio")}
    md_files = {f.stem for f in diagrams_dir.glob("*.md")}
    missing_md = drawio_files - md_files
    missing_drawio = md_files - drawio_files
    return [f"{name}.drawio sem versão textual (.md)" for name in sorted(missing_md)] + [
        f"{name}.md sem .drawio correspondente" for name in sorted(missing_drawio)
    ]


def check_unused_adrs() -> list[str]:
    adr_dir = BACKEND_ROOT / "docs" / "adr"
    index_path = adr_dir / "index.md"
    if not index_path.exists():
        return ["docs/adr/index.md ausente — não é possível verificar ADRs referenciados"]
    index_content = index_path.read_text(encoding="utf-8")
    unused = []
    for adr_file in sorted(adr_dir.glob("ADR-*.md")):
        if adr_file.stem not in index_content:
            unused.append(str(adr_file.relative_to(BACKEND_ROOT)))
    return unused


def check_required_files() -> list[str]:
    required = [
        "docs/architecture/overview.md",
        "docs/architecture/module_map.md",
        "docs/architecture/dependency_map.md",
        "docs/architecture/directory_structure.md",
        "docs/development/coding_standards.md",
        "docs/development/workflow.md",
        "docs/development/contributing.md",
        "docs/development/release_process.md",
        "docs/adr/index.md",
        "README_BACKEND.md",
    ]
    return [path for path in required if not (BACKEND_ROOT / path).exists()]


def check_docs_consistency() -> ConsistencyReport:
    md_files = _all_markdown_files()
    return ConsistencyReport(
        broken_links=check_broken_links(md_files),
        orphaned_docs=check_orphaned_docs(md_files),
        unreferenced_diagrams=check_unreferenced_diagrams(),
        unused_adrs=check_unused_adrs(),
        missing_required_files=check_required_files(),
    )


if __name__ == "__main__":
    report = check_docs_consistency()
    print(report.render())
    sys.exit(0 if report.is_clean else 1)
