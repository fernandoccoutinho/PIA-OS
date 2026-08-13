"""
Testes dos arquivos de ambiente (Módulo 2.11).

Garantem que nenhum overlay contém segredo real (só placeholders
óbvios) e que cada overlay define o que se espera dele.
"""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
ENV_DIR = BACKEND_ROOT / "deploy" / "env"

# Valores que, se aparecessem literalmente como SECRET_KEY/DB_PASSWORD,
# indicariam um segredo real esquecido no arquivo versionado.
_PLACEHOLDER_MARKERS = ("troque-por", "test-secret-key-not-for-production", "change-me")


def _read(filename: str) -> str:
    return (ENV_DIR / filename).read_text()


def test_all_env_files_exist():
    for filename in (".env.example", ".env.development", ".env.test", ".env.production"):
        assert (ENV_DIR / filename).exists(), f"{filename} ausente"


def test_env_example_points_to_the_master_file_not_duplicating_it():
    content = _read(".env.example")
    assert "backend/.env.example" in content
    # Não deve conter uma variável de configuração real — é só um ponteiro.
    assert "DATABASE_URL=" not in content
    assert "SECRET_KEY=" not in content


def test_development_overlay_has_debug_enabled():
    content = _read(".env.development")
    assert "ENVIRONMENT=development" in content
    assert "DEBUG=true" in content


def test_test_overlay_disables_debug():
    content = _read(".env.test")
    assert "ENVIRONMENT=testing" in content
    assert "DEBUG=false" in content


def test_production_overlay_disables_debug_and_wildcard_hosts():
    content = _read(".env.production")
    assert "ENVIRONMENT=production" in content
    assert "DEBUG=false" in content
    assert "TRUSTED_HOSTS=*" not in content
    assert "CORS_ALLOWED_ORIGINS=*" not in content


def test_no_env_overlay_contains_a_real_looking_secret():
    """Todo valor de SECRET_KEY/DB_PASSWORD nos overlays deve ser um
    placeholder reconhecível — nunca algo que pareça um segredo real."""
    for filename in (".env.development", ".env.test", ".env.production"):
        content = _read(filename)
        for line in content.splitlines():
            if line.startswith("SECRET_KEY=") or line.startswith("DB_PASSWORD="):
                value = line.split("=", 1)[1]
                assert any(
                    marker in value for marker in _PLACEHOLDER_MARKERS
                ), f"{filename}: '{line}' não parece um placeholder reconhecível"


def test_production_overlay_documents_secret_key_generation():
    content = _read(".env.production")
    assert "secrets.token_urlsafe" in content
