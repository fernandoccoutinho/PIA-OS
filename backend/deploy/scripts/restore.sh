#!/usr/bin/env bash
# restore.sh — restaura o banco a partir de um arquivo de backup.
#
# Uso:
#   bash deploy/scripts/restore.sh [dev|test|prod|base] <caminho-do-backup.sql.gz>
#
# DESTRUTIVO: sobrescreve o conteúdo atual do banco do ambiente
# escolhido. Pede confirmação interativa antes de prosseguir (exceto se
# a variável CONFIRM=yes já estiver definida, para uso não-interativo
# em automação — use com cuidado redobrado nesse caso).

set -euo pipefail
cd "$(dirname "$0")/../.."

ENVIRONMENT="${1:-}"
BACKUP_FILE="${2:-}"

if [ -z "$ENVIRONMENT" ] || [ -z "$BACKUP_FILE" ]; then
  echo "Uso: bash deploy/scripts/restore.sh [dev|test|prod|base] <caminho-do-backup.sql.gz>" >&2
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Arquivo de backup não encontrado: $BACKUP_FILE" >&2
  exit 1
fi

case "$ENVIRONMENT" in
  dev)   CONTAINER="pia_os_db_dev" ;;
  test)  CONTAINER="pia_os_db_test" ;;
  prod)  CONTAINER="pia_os_db_prod" ;;
  base)  CONTAINER="pia_os_db" ;;
  *)
    echo "Ambiente desconhecido: '$ENVIRONMENT'. Use dev, test, prod ou base." >&2
    exit 1
    ;;
esac

DB_USER="${DB_USER:-pia_user}"
DB_NAME="${DB_NAME:-pia_os}"

echo "ATENÇÃO: isso vai sobrescrever o banco '$DB_NAME' no ambiente '$ENVIRONMENT' (container '$CONTAINER')."
echo "Origem: $BACKUP_FILE"

if [ "${CONFIRM:-}" != "yes" ]; then
  read -r -p "Confirma a restauração? Digite 'sim' para continuar: " answer
  if [ "$answer" != "sim" ]; then
    echo "Cancelado."
    exit 1
  fi
fi

echo "==> Restaurando..."
gunzip -c "$BACKUP_FILE" | docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"
echo "==> Restauração concluída."
