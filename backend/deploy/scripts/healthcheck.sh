#!/usr/bin/env bash
# healthcheck.sh — verifica o endpoint oficial de liveness (GET /health).
#
# Uso:
#   bash deploy/scripts/healthcheck.sh [host] [porta]
#
# Padrão: localhost:8000. Sai com 0 se saudável, 1 caso contrário — apto
# para uso em CI, cron, ou como checagem externa ao container (o
# Dockerfile já define seu próprio HEALTHCHECK via curl direto; este
# script serve para checagem de fora, ex.: de uma máquina de
# monitoramento ou de um passo de deploy que aguarda o serviço subir).

set -euo pipefail

HOST="${1:-localhost}"
PORT="${2:-8000}"
URL="http://${HOST}:${PORT}/api/v1/health"

response=$(curl -fsS -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null || echo "000")

if [ "$response" = "200" ]; then
  echo "OK: $URL respondeu 200"
  exit 0
else
  echo "FALHA: $URL respondeu '$response' (esperado 200)" >&2
  exit 1
fi
