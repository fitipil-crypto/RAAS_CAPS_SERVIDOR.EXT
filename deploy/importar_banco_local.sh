#!/usr/bin/env bash
# Traz o banco SQLite da versão local para o PostgreSQL do servidor.
#
#   bash deploy/importar_banco_local.sh /caminho/para/raas_caps.db
#
# O caminho é o arquivo raas_caps.db copiado do computador onde o sistema rodava
# (traga-o por scp, nunca por e-mail ou pendrive sem cifra: são dados de saúde).
#
# Como funciona: sobe a aplicação apontada para o arquivo SQLite, gera o backup
# JSON que o próprio sistema já sabe ler, e a restauração é feita pela interface.
# Assim a conversão usa o código do sistema — os mesmos validadores — em vez de
# uma tradução de tipos feita à mão entre dois bancos diferentes.
set -euo pipefail

cd "$(dirname "$0")/.."

ORIGEM="${1:-}"
if [[ -z "${ORIGEM}" || ! -f "${ORIGEM}" ]]; then
    echo "Uso: bash deploy/importar_banco_local.sh /caminho/para/raas_caps.db" >&2
    exit 1
fi

COMPOSE="docker compose -f docker-compose.prod.yml"
TEMP="$(mktemp -d)"
trap 'rm -rf "${TEMP}"' EXIT

cp "${ORIGEM}" "${TEMP}/raas_caps.db"

echo "==> Lendo o banco local e gerando o JSON de backup"
# Um container de uso único, com o SQLite montado: só converte.
${COMPOSE} run --rm --no-deps \
    -v "${TEMP}:/tmp/origem" \
    -e DATABASE_URL="sqlite:////tmp/origem/raas_caps.db" \
    -e SECRET_KEY="conversao-temporaria-nao-usada-em-sessao" \
    web python -c "
import json
from database import criar_tabelas, SessionLocal
from backup.backup_service import BackupService

criar_tabelas()
db = SessionLocal()
dados = BackupService.criar_backup(db)
with open('/tmp/origem/backup.json', 'w', encoding='utf-8') as f:
    json.dump(dados, f, ensure_ascii=False, default=str)
print('pacientes:', len(dados.get('patients', [])))
print('profissionais:', len(dados.get('professionals', [])))
print('procedimentos:', len(dados.get('procedures', [])))
print('registros:', len(dados.get('records', [])))
"

cp "${TEMP}/backup.json" ./backup_do_banco_local.json
chmod 600 ./backup_do_banco_local.json

cat <<FIM

Arquivo salvo como: ./backup_do_banco_local.json   (contém dados de pacientes)

Agora termine pela interface, que é onde a restauração é validada:

  1. Acesse https://SEU_DOMINIO e entre como admin.
  2. Na barra superior, selecione "Todas as unidades"
     (a restauração afeta o banco inteiro e exige essa visão).
  3. Vá em Backup > Restaurar e envie backup_do_banco_local.json.
  4. Vá em Unidades (CAPS) e confira a unidade criada na migração —
     principalmente a MODALIDADE, que começa como CAPS I.
  5. Se a tela de Unidades avisar que há "dados sem unidade", rode:

       ${COMPOSE} exec web python -m unidade.migracao --listar
       ${COMPOSE} exec web python -m unidade.migracao --unidade <id>

  6. APAGUE o backup_do_banco_local.json do servidor depois:
       shred -u backup_do_banco_local.json
FIM
