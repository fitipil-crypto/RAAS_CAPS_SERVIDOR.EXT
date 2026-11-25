#!/usr/bin/env bash
# Backup do banco PostgreSQL do RAAS-CAPS.
#
#   bash deploy/backup_postgres.sh
#
# Grava um dump comprimido em ./backups e apaga os mais antigos que
# BACKUP_MANTER_DIAS (padrão 30). Pensado para rodar por cron — veja
# deploy/instalar_cron_backup.sh.
#
# Por que `pg_dump` e não copiar o arquivo do banco: copiar o diretório de dados
# com o PostgreSQL rodando produz um backup corrompido. O pg_dump lê dentro de
# uma transação e gera um arquivo consistente com o servidor no ar.
#
# Atenção (LGPD, art. 46): o dump tem dados de saúde identificáveis. Guarde-o em
# local com acesso restrito e, ao copiá-lo para fora do servidor, use canal
# cifrado (scp/rsync por SSH). Considere cifrar o arquivo em repouso.
set -euo pipefail

cd "$(dirname "$0")/.."

[[ -f .env ]] || { echo "Arquivo .env não encontrado." >&2; exit 1; }
set -a
# shellcheck disable=SC1091
source .env
set +a

BANCO="${POSTGRES_DB:-raas_caps}"
USUARIO="${POSTGRES_USER:-raas}"
MANTER_DIAS="${BACKUP_MANTER_DIAS:-30}"
COMPOSE="docker compose -f docker-compose.prod.yml"
PASTA="./backups"
ARQUIVO="raas_caps_$(date +%Y%m%d_%H%M%S).sql.gz"

mkdir -p "${PASTA}"
chmod 700 "${PASTA}"

echo "==> Backup de ${BANCO}"
# Escreve em .parcial e renomeia ao fim: um backup interrompido não fica no
# diretório parecendo íntegro.
if ! ${COMPOSE} exec -T db pg_dump -U "${USUARIO}" -d "${BANCO}" --clean --if-exists \
        | gzip -9 > "${PASTA}/${ARQUIVO}.parcial"; then
    echo "FALHA no pg_dump. Backup não gerado." >&2
    rm -f "${PASTA}/${ARQUIVO}.parcial"
    exit 1
fi

# Um dump vazio ou truncado indica falha silenciosa; 1 KB é menos que o
# cabeçalho de qualquer dump real.
TAMANHO=$(stat -c%s "${PASTA}/${ARQUIVO}.parcial")
if [[ "${TAMANHO}" -lt 1024 ]]; then
    echo "FALHA: o dump saiu com apenas ${TAMANHO} bytes." >&2
    rm -f "${PASTA}/${ARQUIVO}.parcial"
    exit 1
fi

mv "${PASTA}/${ARQUIVO}.parcial" "${PASTA}/${ARQUIVO}"
chmod 600 "${PASTA}/${ARQUIVO}"
echo "    ${PASTA}/${ARQUIVO} ($(numfmt --to=iec "${TAMANHO}" 2>/dev/null || echo "${TAMANHO} B"))"

echo "==> Removendo backups com mais de ${MANTER_DIAS} dia(s)"
find "${PASTA}" -name 'raas_caps_*.sql.gz' -type f -mtime "+${MANTER_DIAS}" -print -delete

echo "==> Backups atuais"
ls -lh "${PASTA}" | tail -n +2 | tail -5

cat <<FIM

Lembre-se: um backup que nunca foi restaurado não é um backup.
Para testar a restauração em um banco separado:

  ${COMPOSE} exec -T db psql -U ${USUARIO} -d postgres -c 'CREATE DATABASE teste_restauracao'
  gunzip -c ${PASTA}/${ARQUIVO} | ${COMPOSE} exec -T db psql -U ${USUARIO} -d teste_restauracao
  # depois de conferir:
  ${COMPOSE} exec -T db psql -U ${USUARIO} -d postgres -c 'DROP DATABASE teste_restauracao'
FIM
