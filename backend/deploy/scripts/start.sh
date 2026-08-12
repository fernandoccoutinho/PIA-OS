#!/usr/bin/env bash
# start.sh — inicia o ambiente escolhido via Docker Compose.
#
# Uso:
#   bash deploy/scripts/start.sh [dev|test|prod|base] [-- <args extras do compose>]
#
# Padrão: dev. Exemplos:
#   bash deploy/scripts/start.sh dev
#   bash deploy/scripts/start.sh prod
#   bash deploy/scripts/start.sh base -- --profile with-proxy

set -euo pipefail
cd "$(dirname "$0")/../.."  # raiz de backend/

ENVIRONMENT="${1:-dev}"
shift || true

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

if [ ! -f .env ]; then
  echo "Aviso: .env não encontrado na raiz de backend/. Copiando deploy/env/.env.example para .env..."
  cp deploy/env/.env.example .env
fi

echo "==> Subindo ambiente '$ENVIRONMENT' ($COMPOSE_FILE)"
docker compose -f "$COMPOSE_FILE" up -d "$@"
echo "==> Ambiente '$ENVIRONMENT' no ar. Ver logs com: docker compose -f $COMPOSE_FILE logs -f"
