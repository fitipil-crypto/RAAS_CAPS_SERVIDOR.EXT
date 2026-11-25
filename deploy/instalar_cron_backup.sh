#!/usr/bin/env bash
# Instala no cron do usuário atual o backup diário do banco.
#
#   bash deploy/instalar_cron_backup.sh
#
# Roda todos os dias às 23h10 e guarda a saída em logs/backup.log.
set -euo pipefail

PROJETO="$(cd "$(dirname "$0")/.." && pwd)"
HORA="${HORA_BACKUP:-10 23}"   # minuto hora
LINHA="${HORA} * * * cd ${PROJETO} && bash deploy/backup_postgres.sh >> ${PROJETO}/logs/backup.log 2>&1"

mkdir -p "${PROJETO}/logs"

# Remove uma entrada anterior do mesmo script antes de inserir, para não
# acumular duplicatas a cada execução.
ATUAL="$(crontab -l 2>/dev/null | grep -v 'deploy/backup_postgres.sh' || true)"
printf '%s\n%s\n' "${ATUAL}" "${LINHA}" | grep -v '^$' | crontab -

echo "Agendado:"
crontab -l | grep backup_postgres
echo
echo "Para conferir o log depois:  tail -f ${PROJETO}/logs/backup.log"
echo "Para desinstalar:            crontab -e  (apague a linha)"
