"""
Testes dos arquivos Docker Compose (Módulo 2.11).

Validam estrutura e conteúdo via parsing YAML — sem Docker disponível
neste ambiente, não é possível rodar `docker compose config`/`up` de
verdade (mesma limitação já documentada para os Dockerfiles).
"""

from pathlib import Path

import pytest
import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_DIR = BACKEND_ROOT / "deploy" / "compose"


def _load(filename: str) -> dict:
    with (COMPOSE_DIR / filename).open() as f:
        return yaml.safe_load(f)


@pytest.mark.parametrize(
    "filename",
    [
        "docker-compose.yml",
        "docker-compose.dev.yml",
        "docker-compose.test.yml",
        "docker-compose.prod.yml",
    ],
)
def test_compose_file_is_valid_yaml_with_services(filename):
    data = _load(filename)
    assert "services" in data
    assert "api" in data["services"]
    assert "db" in data["services"]


def test_base_compose_has_api_depending_on_healthy_db():
    data = _load("docker-compose.yml")
    depends_on = data["services"]["api"]["depends_on"]
    assert depends_on["db"]["condition"] == "service_healthy"


def test_base_compose_redis_and_nginx_are_profile_gated():
    data = _load("docker-compose.yml")
    assert data["services"]["redis"]["profiles"] == ["with-redis"]
    assert data["services"]["nginx"]["profiles"] == ["with-proxy"]


def test_dev_compose_mounts_source_for_hot_reload():
    data = _load("docker-compose.dev.yml")
    volumes = data["services"]["api"]["volumes"]
    assert any("/srv/app" in v for v in volumes)


def test_dev_compose_uses_dev_dockerfile():
    data = _load("docker-compose.dev.yml")
    assert data["services"]["api"]["build"]["dockerfile"] == "deploy/docker/Dockerfile.dev"


def test_test_compose_uses_tmpfs_for_disposable_database():
    data = _load("docker-compose.test.yml")
    assert "tmpfs" in data["services"]["db"]


def test_test_compose_runs_pytest_as_the_api_command():
    data = _load("docker-compose.test.yml")
    assert data["services"]["api"]["command"] == ["pytest"]


def test_prod_compose_uses_prod_dockerfile():
    data = _load("docker-compose.prod.yml")
    assert data["services"]["api"]["build"]["dockerfile"] == "deploy/docker/Dockerfile.prod"


def test_prod_compose_does_not_expose_api_or_db_ports_directly():
    """Em produção, só o nginx publica porta ao host — api/db ficam
    acessíveis apenas dentro da rede interna do compose."""
    data = _load("docker-compose.prod.yml")
    assert "ports" not in data["services"]["api"]
    assert "ports" not in data["services"]["db"]
    assert "ports" in data["services"]["nginx"]


def test_prod_compose_defines_resource_limits():
    data = _load("docker-compose.prod.yml")
    limits = data["services"]["api"]["deploy"]["resources"]["limits"]
    assert "cpus" in limits
    assert "memory" in limits


def test_prod_compose_db_password_has_no_insecure_default():
    """`${DB_PASSWORD:?...}` falha explicitamente se a variável não
    estiver definida — nunca cai silenciosamente num default fraco."""
    data = _load("docker-compose.prod.yml")
    password_expr = data["services"]["db"]["environment"]["POSTGRES_PASSWORD"]
    assert ":?" in password_expr
    assert ":-" not in password_expr  # não é um default silencioso


def test_all_compose_files_use_named_volumes_for_db_data_or_tmpfs():
    for filename in ("docker-compose.yml", "docker-compose.dev.yml", "docker-compose.prod.yml"):
        data = _load(filename)
        db_service = data["services"]["db"]
        assert "volumes" in db_service, f"{filename}: db sem volume persistente"
