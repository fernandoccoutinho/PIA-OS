#!/usr/bin/env bash
# backup.sh — dump do PostgreSQL, versionado por timestamp.
#
# Uso:
#   bash deploy/scripts/backup.sh [dev|test|prod|base]
#
# Gera deploy/backups/<ambiente>/pia_os_<ambiente>_<timestamp>.sql.gz —
# nunca sobrescreve um backup anterior (cada execução cria um arquivo
# novo). Sem armazenamento externo (S3, GCS, etc.) nesta etapa — os
# arquivos ficam no host, em deploy/backups/ (fora do controle de
# versão — ver .gitignore).

set -euo pipefail
cd "$(dirname "$0")/../.."

ENVIRONMENT="${1:-dev}"

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
BACKUP_DIR="deploy/backups/${ENVIRONMENT}"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BACKUP_FILE="${BACKUP_DIR}/pia_os_${ENVIRONMENT}_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "==> Gerando backup de '$CONTAINER' (banco '$DB_NAME') em $BACKUP_FILE"
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists \
  | gzip > "$BACKUP_FILE"

echo "==> Backup concluído: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
echo "==> Backups existentes para '$ENVIRONMENT':"
ls -lh "$BACKUP_DIR"
