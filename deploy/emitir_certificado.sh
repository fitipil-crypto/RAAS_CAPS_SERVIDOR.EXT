#!/usr/bin/env bash
# Emite o primeiro certificado HTTPS (Let's Encrypt) para o domínio do .env.
#
#   bash deploy/emitir_certificado.sh
#
# Rode ANTES do primeiro `up -d`: o nginx não sobe sem o certificado, porque a
# configuração dele referencia os arquivos .pem. A renovação depois é automática
# (serviço `certbot` do compose).
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
    echo "Arquivo .env não encontrado. Faça:  cp .env.prod.example .env && nano .env" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${DOMINIO:?Defina DOMINIO no .env}"
EMAIL="${EMAIL_CERTIFICADO:-admin@${DOMINIO}}"

echo "==> Domínio: ${DOMINIO}"
echo "==> E-mail de aviso de vencimento: ${EMAIL}"
echo
echo "Confirme que o DNS de ${DOMINIO} aponta para este servidor e que as portas"
echo "80 e 443 estão abertas. O Let's Encrypt precisa alcançar este servidor."
read -r -p "Continuar? [s/N] " resposta
[[ "${resposta}" =~ ^[sSyY]$ ]] || { echo "Cancelado."; exit 1; }

# O certbot standalone sobe um servidor próprio na porta 80. Por isso o nginx
# não pode estar no ar agora — na renovação o método é outro (webroot), que
# funciona com o nginx ligado.
echo "==> Parando o nginx, se estiver no ar"
docker compose -f docker-compose.prod.yml stop nginx 2>/dev/null || true

# Os volumes recebem o nome do projeto do compose como prefixo (o nome da pasta).
PROJETO="$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]')"

echo "==> Pedindo o certificado"
docker run --rm \
    -p 80:80 \
    -v "${PROJETO}_certbot-cert:/etc/letsencrypt" \
    -v "${PROJETO}_certbot-www:/var/www/certbot" \
    certbot/certbot certonly --standalone \
    --non-interactive --agree-tos \
    --email "${EMAIL}" \
    -d "${DOMINIO}"

echo
echo "Certificado emitido. Agora suba o sistema:"
echo "  docker compose -f docker-compose.prod.yml up -d"
echo
echo "Se o volume não foi encontrado, confira o nome com:  docker volume ls | grep certbot"
