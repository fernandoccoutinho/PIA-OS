#!/usr/bin/env bash
# wait_for_db.sh — aguarda o PostgreSQL aceitar conexões antes de seguir.
#
# Uso:
#   bash deploy/scripts/wait_for_db.sh [host] [porta] [timeout_segundos]
#
# Útil em pipelines de CI ou scripts de deploy que rodam fora do Compose
# (o Compose já tem `depends_on: condition: service_healthy`, que cobre
# o caso comum — este script é para quando não há Compose orquestrando,
# ex.: um passo de deploy que roda migrações direto contra um banco
# gerenciado na nuvem).

set -euo pipefail

HOST="${1:-localhost}"
PORT="${2:-5432}"
TIMEOUT="${3:-60}"

echo "Aguardando PostgreSQL em ${HOST}:${PORT} (timeout ${TIMEOUT}s)..."

elapsed=0
while ! (echo > "/dev/tcp/${HOST}/${PORT}") 2>/dev/null; do
  if [ "$elapsed" -ge "$TIMEOUT" ]; then
    echo "FALHA: banco não respondeu em ${TIMEOUT}s." >&2
    exit 1
  fi
  sleep 1
  elapsed=$((elapsed + 1))
done

echo "OK: PostgreSQL em ${HOST}:${PORT} está aceitando conexões (${elapsed}s)."
