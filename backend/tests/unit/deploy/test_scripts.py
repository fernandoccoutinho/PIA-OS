"""
Testes dos scripts operacionais (Módulo 2.11).

Valida sintaxe (`bash -n`) e permissão de execução — sem Docker
disponível, não é possível executá-los de ponta a ponta de verdade
(precisam de containers reais rodando).
"""

import os
import subprocess
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = BACKEND_ROOT / "deploy" / "scripts"

ALL_SCRIPTS = [
    "start.sh",
    "stop.sh",
    "healthcheck.sh",
    "wait_for_db.sh",
    "backup.sh",
    "restore.sh",
]


@pytest.mark.parametrize("script_name", ALL_SCRIPTS)
def test_script_exists_and_is_executable(script_name):
    path = SCRIPTS_DIR / script_name
    assert path.exists(), f"{script_name} não existe"
    assert os.access(path, os.X_OK), f"{script_name} não é executável (chmod +x)"


@pytest.mark.parametrize("script_name", ALL_SCRIPTS)
def test_script_has_valid_bash_syntax(script_name):
    path = SCRIPTS_DIR / script_name
    result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, f"{script_name}: {result.stderr}"


@pytest.mark.parametrize("script_name", ["start.sh", "stop.sh", "backup.sh", "restore.sh"])
def test_script_handles_all_four_environments(script_name):
    content = (SCRIPTS_DIR / script_name).read_text()
    for env_name in ("dev", "test", "prod", "base"):
        assert env_name in content, f"{script_name} não trata o ambiente '{env_name}'"


def test_restore_script_requires_confirmation_by_default():
    content = (SCRIPTS_DIR / "restore.sh").read_text()
    assert "CONFIRM" in content
    assert "read -r -p" in content


def test_backup_script_uses_timestamped_filenames():
    content = (SCRIPTS_DIR / "backup.sh").read_text()
    assert "TIMESTAMP" in content
    assert "date -u" in content


def test_healthcheck_script_targets_the_official_endpoint():
    content = (SCRIPTS_DIR / "healthcheck.sh").read_text()
    assert "/api/v1/health" in content
