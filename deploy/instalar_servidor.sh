#!/usr/bin/env bash
# Preparação de um servidor Ubuntu/Debian novo para o RAAS-CAPS.
# Rode como root (ou com sudo) em um servidor recém-criado:
#
#   sudo bash deploy/instalar_servidor.sh
#
# O que faz: atualiza o sistema, instala o Docker, cria um usuário sem
# privilégios para a aplicação, liga o firewall deixando só SSH/HTTP/HTTPS e
# configura as atualizações de segurança automáticas.
set -euo pipefail

USUARIO_APP="${USUARIO_APP:-raas}"
PORTA_SSH="${PORTA_SSH:-22}"

if [[ $EUID -ne 0 ]]; then
    echo "Rode como root:  sudo bash $0" >&2
    exit 1
fi

echo "==> Atualizando o sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

echo "==> Instalando pacotes básicos"
apt-get install -y -qq ca-certificates curl gnupg ufw unattended-upgrades postgresql-client

echo "==> Instalando o Docker (repositório oficial)"
if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${CODENAME} stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
    echo "    Docker já instalado."
fi
systemctl enable --now docker

echo "==> Usuário da aplicação: ${USUARIO_APP}"
# A aplicação não roda como root. Um comprometimento da aplicação fica limitado
# a este usuário em vez de entregar o servidor.
if ! id -u "${USUARIO_APP}" >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" "${USUARIO_APP}"
fi
usermod -aG docker "${USUARIO_APP}"

echo "==> Firewall (UFW): liberando apenas SSH, HTTP e HTTPS"
# O PostgreSQL fica só na rede interna do Docker: a porta 5432 não é liberada.
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow "${PORTA_SSH}"/tcp comment 'SSH'
ufw allow 80/tcp  comment 'HTTP (redireciona para HTTPS e renova certificado)'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
ufw status verbose

echo "==> Atualizações de segurança automáticas"
dpkg-reconfigure -f noninteractive unattended-upgrades

cat <<FIM

==========================================================================
Servidor preparado.

Próximos passos (como ${USUARIO_APP}, não como root):

  su - ${USUARIO_APP}
  # envie o código para ~/raas-caps  (git clone, scp ou rsync)
  cd ~/raas-caps
  cp .env.prod.example .env
  nano .env                      # DOMINIO, POSTGRES_PASSWORD, SECRET_KEY

  # senhas fortes:
  openssl rand -base64 32        # POSTGRES_PASSWORD
  openssl rand -base64 48        # SECRET_KEY

  # 1) certificado HTTPS (o DNS do domínio já deve apontar para este servidor)
  bash deploy/emitir_certificado.sh

  # 2) subir o sistema
  docker compose -f docker-compose.prod.yml up -d

  # 3) backup diário do banco
  bash deploy/instalar_cron_backup.sh

Depois acesse https://SEU_DOMINIO e entre com admin / a senha do .env.
==========================================================================
FIM
