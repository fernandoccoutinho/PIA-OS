#!/usr/bin/env bash
# Script de verificação de qualidade — portátil, não depende de nenhum
# sistema de CI específico (GitHub Actions, GitLab CI, CircleCI, Jenkins
# ou execução manual local funcionam igual). Espelha `make check`, como
# um artefato independente de `make` estar disponível no runner.
#
# Uso:
#   bash scripts/run_ci_checks.sh
#
# Sai com código diferente de zero se qualquer etapa falhar — apropriado
# para gate de CI.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Lint (ruff)"
ruff check .

echo "==> Format check (black)"
black --check .

echo "==> Testes + cobertura (pytest)"
pytest

echo "==> Tudo passou."
