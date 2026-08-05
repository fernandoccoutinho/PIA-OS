"""
Testes de sanidade dos Dockerfiles (Módulo 2.11).

Sem Docker disponível neste ambiente de sandbox/CI — não é possível
rodar `docker build` de verdade aqui. Estes testes validam o que dá
para validar sem um daemon Docker: presença dos arquivos, estrutura
mínima esperada (FROM, WORKDIR, CMD/ENTRYPOINT, HEALTHCHECK onde
esperado, usuário não-root em produção). Ver docs/DOCKER.md sobre essa
limitação, documentada desde o Módulo 2.1.
"""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
DOCKER_DIR = BACKEND_ROOT / "deploy" / "docker"


def _find_upwards(filename_parts: tuple[str, ...]) -> Path:
    """Resolve um caminho que pode estar na raiz do repositório de
    trabalho OU dentro de `src/` (empacotamento do Módulo 2.13, onde
    `requirements/`/`.dockerignore` viram parte de `src/` — o contexto
    de build do Docker é sempre o pai imediato de `app/`, qualquer que
    seja a raiz). Evita hardcodar um único layout."""
    candidate = BACKEND_ROOT.joinpath(*filename_parts)
    if candidate.exists():
        return candidate
    return BACKEND_ROOT / "src" / Path(*filename_parts)


def _read(filename: str) -> str:
    return (DOCKER_DIR / filename).read_text()


def test_all_three_dockerfiles_exist():
    assert (DOCKER_DIR / "Dockerfile").exists()
    assert (DOCKER_DIR / "Dockerfile.dev").exists()
    assert (DOCKER_DIR / "Dockerfile.prod").exists()


def test_dockerignore_exists_at_build_context_root():
    # O funcional é backend/.dockerignore (ou src/.dockerignore, no
    # empacotamento do Módulo 2.13), não deploy/docker/.dockerignore —
    # ver a nota no próprio arquivo.
    assert _find_upwards((".dockerignore",)).exists()
    assert (DOCKER_DIR / ".dockerignore").exists()


def test_default_dockerfile_has_healthcheck_and_non_root_user():
    content = _read("Dockerfile")
    assert "FROM python:3.12-slim" in content
    assert "HEALTHCHECK" in content
    assert "/api/v1/health" in content
    assert "USER piaos" in content


def test_dev_dockerfile_uses_dev_requirements_and_reload():
    content = _read("Dockerfile.dev")
    assert "requirements/dev.txt" in content
    assert "--reload" in content


def test_prod_dockerfile_is_multistage_with_non_root_user_and_gunicorn():
    content = _read("Dockerfile.prod")
    assert content.count("FROM python:3.12-slim") == 2  # builder + runtime
    assert "AS builder" in content
    assert "USER piaos" in content
    assert "gunicorn" in content
    assert "HEALTHCHECK" in content


def test_prod_dockerfile_does_not_install_dev_requirements():
    content = _read("Dockerfile.prod")
    assert "requirements/dev.txt" not in content


def test_prod_requirements_file_extends_base():
    content = _find_upwards(("requirements", "prod.txt")).read_text()
    assert "-r base.txt" in content
    assert "gunicorn" in content
