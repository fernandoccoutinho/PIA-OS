#!/usr/bin/env bash
# stop.sh — para o ambiente escolhido via Docker Compose.
#
# Uso:
#   bash deploy/scripts/stop.sh [dev|test|prod|base] [--volumes]
#
# `--volumes` também remove os volumes nomeados (dados do banco) — use
# com cuidado, é destrutivo e não tem confirmação interativa.

set -euo pipefail
cd "$(dirname "$0")/../.."

ENVIRONMENT="${1:-dev}"
REMOVE_VOLUMES="${2:-}"

case "$ENVIRONMENT" in
  dev)   COMPOSE_FILE="deploy/compose/docker-compose.dev.yml" ;;
  test)  COMPOSE_FILE="deploy/compose/docker-compose.test.yml" ;;
  prod)  COMPOSE_FILE="deploy/compose/docker-compose.prod.yml" ;;
  base)  COMPOSE_FILE="deploy/compose/docker-compose.yml" ;;
  *)
    echo "Ambiente desconhecido: '$ENVIRONMENT'. Use dev, test, prod ou base." >&2
    exit 1
    ;;
esac

if [ "$REMOVE_VOLUMES" = "--volumes" ]; then
  echo "==> Parando '$ENVIRONMENT' e REMOVENDO volumes (dados do banco serão perdidos)"
  docker compose -f "$COMPOSE_FILE" down --volumes
else
  echo "==> Parando '$ENVIRONMENT' (volumes preservados)"
  docker compose -f "$COMPOSE_FILE" down
fi
