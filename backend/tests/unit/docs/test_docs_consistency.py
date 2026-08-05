"""
Testes do verificador de consistência da documentação (Módulo 2.12).

Não depende de nada de `app/` — `scripts/check_docs_consistency.py` é
puramente sobre arquivos `.md`. Testado tanto contra o repositório real
(garante que a documentação atual está consistente) quanto com fixtures
isoladas (garante que o verificador detecta problemas de verdade, não
só "sempre passa").
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND_ROOT / "scripts"))

import check_docs_consistency as checker  # noqa: E402


def test_real_repository_documentation_is_consistent():
    report = checker.check_docs_consistency()
    assert report.is_clean, report.render()


def test_all_required_files_exist_in_the_real_repository():
    missing = checker.check_required_files()
    assert missing == [], f"Arquivos obrigatórios ausentes: {missing}"


def test_report_render_when_clean():
    report = checker.ConsistencyReport()
    assert "nenhum problema" in report.render()


def test_report_render_when_dirty():
    report = checker.ConsistencyReport(broken_links=["a.md -> b.md"])
    assert "a.md -> b.md" in report.render()
    assert report.is_clean is False


def test_check_broken_links_detects_a_real_broken_link(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("Ver [outro](nao-existe.md).")
    broken = checker.check_broken_links([doc])
    assert len(broken) == 1


def test_check_broken_links_ignores_external_and_anchor_links(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("Ver [site](https://example.com) e [secao](#titulo).")
    broken = checker.check_broken_links([doc])
    assert broken == []


def test_check_broken_links_accepts_a_valid_relative_link(tmp_path):
    target = tmp_path / "target.md"
    target.write_text("conteudo")
    doc = tmp_path / "doc.md"
    doc.write_text("Ver [alvo](target.md).")
    broken = checker.check_broken_links([doc, target])
    assert broken == []


def test_check_orphaned_docs_detects_a_document_no_one_links_to(tmp_path):
    orphan = tmp_path / "orphan.md"
    orphan.write_text("ninguem me referencia")
    orphaned = checker.check_orphaned_docs([orphan])
    assert str(orphan) in orphaned or orphan.name in "".join(orphaned)


def test_check_orphaned_docs_does_not_flag_a_referenced_document(tmp_path):
    target = tmp_path / "target.md"
    target.write_text("conteudo")
    doc = tmp_path / "doc.md"
    doc.write_text("Ver [alvo](target.md).")
    orphaned = checker.check_orphaned_docs([doc, target])
    assert not any("target.md" in item for item in orphaned)


def test_check_orphaned_docs_never_flags_entry_points(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("ninguem me referencia, mas sou um entry point")
    orphaned = checker.check_orphaned_docs([readme])
    assert orphaned == []


def test_check_orphaned_docs_never_flags_a_redirect_stub(tmp_path):
    stub = tmp_path / "OLD_DOC.md"
    stub.write_text("Este documento foi consolidado em `docs/backend/x.md`.")
    orphaned = checker.check_orphaned_docs([stub])
    assert orphaned == []


def test_diagrams_have_matching_mermaid_and_drawio_pairs():
    problems = checker.check_unreferenced_diagrams()
    assert problems == [], problems


def test_all_adrs_are_referenced_in_the_index():
    unused = checker.check_unused_adrs()
    assert unused == [], unused


def test_consistency_checker_script_exits_zero_on_clean_repo():
    import subprocess

    result = subprocess.run(
        [sys.executable, str(BACKEND_ROOT / "scripts" / "check_docs_consistency.py")],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout
