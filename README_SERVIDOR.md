# RAAS-CAPS — Edição Servidor (7 modalidades de CAPS)

Cópia do RAAS-CAPS preparada para rodar em um servidor externo, atendendo
várias unidades de CAPS no mesmo sistema, com os dados de cada uma isolados.

As 7 modalidades atendidas: **CAPS I, CAPS II, CAPS III, CAPS i, CAPS AD,
CAPS AD III e CAPS AD IV**.

> **Antes de instalar:** esta pasta não contém nenhum banco de dados, chave ou
> dado de paciente. O banco começa vazio e a senha inicial do admin vem do
> arquivo `.env` que você vai criar.

---

## 1. O que mudou em relação à versão local

| | Versão local (um CAPS) | Edição servidor |
|---|---|---|
| Banco | SQLite em arquivo | PostgreSQL |
| Acesso | rede local / túnel ngrok | domínio próprio com HTTPS |
| Servidor | `uvicorn` em um processo | `gunicorn` com 3 workers + nginx |
| Unidades | uma, nas Configurações | várias, cada uma com CNES e modalidade |
| Perfis | admin, coordenador, operador | + **gestor** (acompanha vários CAPS) |
| Backup | pasta de rede do Windows | `pg_dump` diário por cron |

Nenhuma tela foi perdida: pacientes, registros RAAS, grupos, eventos,
competência, relatórios, exportação, LGPD e logs continuam iguais — agora
filtrados pela unidade selecionada.

### Como o isolamento funciona

Cada tabela de dado assistencial ganhou a coluna `unidade_id`, e **todo**
`SELECT`, `UPDATE` e `DELETE` do sistema passa por um filtro automático pela
unidade ativa (`sistema/escopo.py`). Isso é diferente de filtrar unidade a
unidade em cada consulta: aqui não existe filtro para alguém esquecer de
aplicar — uma consulta nova nasce filtrada.

O que fica **compartilhado** entre as unidades, de propósito:

- o catálogo de **procedimentos** (é a tabela SIGTAP, igual para todos);
- os **usuários** (o login acontece antes de haver unidade ativa);
- as **configurações** do sistema que não são do estabelecimento.

O que é **por unidade**: pacientes, profissionais, registros RAAS, grupos,
eventos, solicitações e incidentes de LGPD, logs de auditoria, e os dados de
estabelecimento (CNES, nome do órgão, CNPJ, UF, versão do layout) — então
**cada CAPS exporta o seu arquivo RAAS com o seu próprio CNES**.

---

## 2. Instalação em um servidor novo (Docker — recomendado)

Serve para qualquer VPS Ubuntu 22.04+ ou Debian 12+ (Hetzner, DigitalOcean,
AWS Lightsail, Magalu Cloud, servidor da própria prefeitura). Mínimo
confortável: **2 vCPU, 4 GB de RAM, 40 GB de disco**.

### 2.1. Preparar o servidor

```bash
# conectado por SSH como root
sudo bash deploy/instalar_servidor.sh
```

O script atualiza o sistema, instala o Docker, cria o usuário `raas` sem
privilégios, liga o firewall (só SSH, 80 e 443) e ativa as atualizações de
segurança automáticas.

### 2.2. Enviar o código e configurar

```bash
su - raas
# envie esta pasta para ~/raas-caps (git clone, scp ou rsync)
cd ~/raas-caps

cp .env.prod.example .env
openssl rand -base64 32    # cole em POSTGRES_PASSWORD
openssl rand -base64 48    # cole em SECRET_KEY
nano .env                  # preencha DOMINIO também
```

### 2.3. Certificado HTTPS

O DNS do domínio precisa **já estar apontando** para o IP do servidor.

```bash
bash deploy/emitir_certificado.sh
```

### 2.4. Subir o sistema

```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f web   # acompanhar o boot
```

Acesse `https://SEU_DOMINIO` e entre com **admin** e a senha que você pôs em
`ADMIN_INITIAL_PASSWORD`. A troca de senha é obrigatória no primeiro acesso.

### 2.5. Backup diário

```bash
bash deploy/instalar_cron_backup.sh
```

Gera um `pg_dump` comprimido por dia em `./backups`, guardando 30 dias.

> **Teste a restauração.** Um backup que nunca foi restaurado não é um backup —
> o script `deploy/backup_postgres.sh` termina mostrando o comando para testar
> em um banco separado.

---

## 3. Cadastrar as unidades

No menu **Sistema › Unidades (CAPS)**, como admin:

1. **＋ Nova Unidade** para cada CAPS.
2. Preencha nome, **modalidade**, **CNES** (7 dígitos), município e UF.
3. Em CAPS III, AD, AD III e AD IV, informe os **leitos de acolhimento
   noturno**.
4. A população do município é opcional e serve só para o aviso de porte.

Ao escolher a modalidade, o formulário mostra o que ela prevê (porte,
funcionamento, leitos, fundamento legal).

### Usuários e perfis

Em **Sistema › Controle de Acesso**:

| Perfil | Alcance | Para quem |
|---|---|---|
| **admin** | todas as unidades, administra o sistema | TI / responsável técnico |
| **gestor** | todas as unidades, leitura e análises | coordenação da rede, gestão municipal |
| **coordenador** | uma unidade | coordenação do CAPS |
| **operador** | uma unidade | equipe que digita os atendimentos |

Coordenador e operador **só veem a unidade onde estão lotados** — e não
conseguem sair dela nem forçando a sessão. Com um único CAPS cadastrado a
lotação é preenchida sozinha.

Admin e gestor trocam de unidade pelo seletor na barra superior, que tem também
a visão **"Todas as unidades"** (soma de todos os CAPS, usada para comparar a
rede, restaurar backup e conferir dados sem unidade).

---

## 4. Trazer os dados que já existem

Se você já usa o RAAS-CAPS em um computador com SQLite:

```bash
# no servidor, com o raas_caps.db copiado por scp
bash deploy/importar_banco_local.sh /caminho/para/raas_caps.db
```

O script converte o banco usando o próprio código do sistema e explica os
passos finais pela interface. Depois:

1. Em **Unidades (CAPS)**, confira a unidade criada na migração — em especial a
   **modalidade**, que começa como CAPS I.
2. Se a tela avisar que há **"dados sem unidade"**, atribua-os:

```bash
docker compose -f docker-compose.prod.yml exec web python -m unidade.migracao --listar
docker compose -f docker-compose.prod.yml exec web python -m unidade.migracao --unidade <id>
```

A rotina é idempotente e só mexe em linhas sem unidade — repetir não faz mal e
dados de outra unidade nunca são tocados.

3. **Apague** o `backup_do_banco_local.json` do servidor (`shred -u`): ele tem
   dados de pacientes.

---

## 5. Operação do dia a dia

```bash
cd ~/raas-caps
C="docker compose -f docker-compose.prod.yml"

$C ps                     # o que está no ar
$C logs -f web            # log da aplicação
$C restart web            # reiniciar só a aplicação
$C down                   # parar tudo (os dados ficam no volume)

# atualizar para uma versão nova do código (faça um backup antes)
bash deploy/backup_postgres.sh && git pull && $C build web && $C up -d web
$C exec web alembic current               # confere a versão do esquema

bash deploy/backup_postgres.sh            # backup manual
curl https://SEU_DOMINIO/saude            # checagem de saúde
```

**Migrações do banco:** ao subir uma versão nova, a aplicação aplica sozinha
as migrações pendentes (Alembic, pasta `migrations/`) antes de atender. Os 3
workers não migram ao mesmo tempo: uma trava no PostgreSQL deixa um migrar e
os outros esperarem. Se uma migração falhar, ela é desfeita inteira e o
container não sobe; o erro aparece em `$C logs web`. Um banco criado antes do
Alembic é completado automaticamente na primeira subida.

O endpoint `/saude` faz um `SELECT 1` no banco, então responde **503** quando o
PostgreSQL está fora do ar — é o que o Docker e o monitoramento devem observar,
em vez de só checar se o processo está de pé.

### Sem Docker

Há um serviço do systemd pronto em `deploy/raas-caps.service`, com as
instruções no cabeçalho do arquivo. Use-o quando o servidor já tem PostgreSQL
ou a equipe prefere não usar Docker.

---

## 6. LGPD e segurança

O que esta edição já traz:

- **HTTPS obrigatório** (Let's Encrypt, renovação automática, HTTP redireciona);
- TLS 1.2+ apenas, HSTS, e CSP/`X-Frame-Options`/`no-store` pela aplicação;
- cookie de sessão `Secure` + `HttpOnly`, expiração por inatividade (30 min) e
  duração máxima (12 h), configuráveis no `.env`;
- proteção CSRF por checagem de `Origin`/`Referer` nas escritas;
- bloqueio da conta após 5 tentativas de senha erradas;
- **log de auditoria** de quem acessou o quê, agora também por unidade;
- banco e aplicação **sem porta exposta** à internet (só o nginx publica porta);
- container como usuário sem privilégios, firewall fechado, systemd endurecido;
- telas de LGPD: solicitações de titular, incidentes, anonimização, retenção.

O que **depende de você**:

- **Senhas** fortes no `.env` e nenhuma delas versionada no git;
- **backup fora do servidor** — copie `./backups` para outro lugar por SSH; um
  backup só no mesmo servidor não protege contra perda do servidor;
- considere **cifrar os dumps** em repouso (eles têm dados de saúde
  identificáveis);
- **registro das operações de tratamento** e nomeação do **encarregado (DPO)**
  nas Configurações › LGPD;
- contrato com o provedor na condição de **operador** de dados (LGPD, art. 39),
  preferindo servidores no Brasil;
- revisar os **perfis de acesso** periodicamente: quem saiu da equipe deve ser
  desativado.

> Esta edição reduz o risco técnico; ela não substitui as medidas
> administrativas que a LGPD exige da instituição.

---

## 7. As 7 modalidades: parâmetros usados

| Modalidade | Porte populacional | Público | Funcionamento | Acolhimento noturno |
|---|---|---|---|---|
| CAPS I | acima de 20.000 hab. | todas as faixas etárias, TM e AD | dias úteis | — |
| CAPS II | acima de 70.000 hab. | TM graves; AD conforme a rede local | dias úteis | — |
| CAPS III | acima de 200.000 hab. | TM graves e persistentes | 24 h, todos os dias | até 5 leitos; 7 dias corridos ou 10 intercalados em 30 |
| CAPS i | acima de 150.000 hab. | crianças e adolescentes | dias úteis | — |
| CAPS AD | acima de 70.000 hab. | AD, adultos e infantojuvenil (ECA) | dias úteis | até 5 leitos em feriados e fins de semana |
| CAPS AD III | acima de 200.000 hab. | AD com cuidados clínicos contínuos | 24 h, todos os dias | 8 a 12 leitos; até 14 dias em 30 |
| CAPS AD IV | acima de 500.000 hab. e capitais | AD, quadros graves e urgências | 24 h, todos os dias | 10 a 20 leitos de observação |

**Fontes:** Portaria GM/MS nº 3.088/2011, art. 7º, § 4º (porte e público);
Portaria GM/MS nº 336/2002 (acolhimento noturno, leitos e permanência);
Portaria GM/MS nº 3.588/2017 (CAPS AD IV). Normas consolidadas na Portaria de
Consolidação nº 3/2017, Anexo V.

### Por que são avisos e não travas

1. **A norma divergiu de si mesma.** A Portaria 3.088/2011 teve republicações
   com números diferentes — circulam cópias com "acima de quinze mil
   habitantes" para o CAPS I e "cento e cinquenta mil" para o CAPS AD III, onde
   a republicação usada aqui diz vinte mil e duzentos mil. Travar o sistema em
   um dos valores criaria erro onde a própria norma é ambígua.
2. **Habilitação é ato da gestão.** Existe CAPS habilitado fora do porte
   previsto, por decisão da CIB ou cobertura regional. O sistema que recusasse
   o cadastro estaria errado, não o serviço.
3. **Faixa etária é decisão clínica.** Um adolescente que completa 18 anos em
   acompanhamento no CAPS i não deve ter o atendimento bloqueado por um
   software.

Então o sistema **avisa** — na tela de Unidades e na auditoria de competência
(achados `M00` a `M04`) — e deixa a decisão com a equipe. Nenhum desses avisos
impede a exportação do arquivo RAAS, porque o DATASUS não recusa o arquivo por
causa deles.

Os parâmetros ficam em `unidade/modalidades.py`, um arquivo só, com o
fundamento legal de cada número ao lado. É ali que se mexe se a norma mudar.

> Uma observação que pode surgir: a modalidade **não** vai codificada no arquivo
> RAAS. O que identifica o estabelecimento no arquivo é o **CNES**; os campos
> de serviço/classificação (115/002) aparecem igualmente em CAPS I, II e III.
> Por isso a modalidade aqui serve às regras assistenciais e aos relatórios, e
> continua sendo possível ajustar serviço e classificação por unidade.

---

## 8. Estrutura do que foi acrescentado

```
unidade/                        # o módulo novo
├── modalidades.py              # as 7 modalidades e seus parâmetros
├── unidade_model.py            # tabela `unidades`
├── unidade_schema.py           # validação (modalidade, CNES de 7 dígitos)
├── unidade_service.py          # regras e resolução da unidade ativa
├── unidade_router.py           # API /api/unidades
├── unidade_frontend_router.py  # tela /unidades
├── unidade_middleware.py       # define a unidade ativa da requisição
└── migracao.py                 # atribui unidade aos dados antigos

sistema/escopo.py               # o filtro automático por unidade
templates/unidades.html         # tela de unidades
static/js/unidades.js
tests/test_unidades.py          # 45 testes de isolamento e modalidades

deploy/
├── instalar_servidor.sh        # prepara o servidor (Docker, firewall, usuário)
├── emitir_certificado.sh       # primeiro certificado HTTPS
├── nginx.conf.template         # proxy reverso com TLS
├── backup_postgres.sh          # pg_dump com rotação
├── instalar_cron_backup.sh     # agenda o backup diário
├── importar_banco_local.sh     # traz o SQLite da versão local
└── raas-caps.service           # systemd, para quem não usa Docker

Dockerfile                      # imagem de produção (gunicorn, usuário raas)
docker-compose.prod.yml         # PostgreSQL + app + nginx + certbot
.env.prod.example               # modelo de configuração
```

---

## 9. Testes

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

A suíte roda em SQLite temporário. Para rodá-la no PostgreSQL, como a CI
faz, aponte `TEST_DATABASE_URL` para um banco **de teste** (o nome precisa
conter `test`, porque a suíte apaga todas as tabelas dele):

```bash
TEST_DATABASE_URL=postgresql+psycopg://raas:senha@localhost/raas_test python -m pytest -q
```

Ela cobre, além de tudo o que já havia:

- o isolamento entre unidades em leitura, contagem agregada, `UPDATE` e
  `DELETE` em massa;
- que trocar o id na URL não abre a ficha de paciente de outro CAPS;
- que um operador não alcança outra unidade nem forçando a sessão;
- que cada unidade exporta com o seu CNES;
- que a restauração de backup exige a visão "Todas as unidades";
- os avisos de faixa etária, leitos e porte das 7 modalidades.

---

## 10. Limitações conhecidas

Para não haver surpresa depois:

- **Backup automático em pasta de rede do Windows** (tela Backup › Backup
  automático) é da versão local e fica **desligado** no servidor — o backup
  aqui é o `pg_dump` por cron. Para religá-lo, `BACKUP_AUTO_LOCAL=true`.
- A tela **Backup › Baixar/Restaurar** (JSON) continua funcionando: o download
  respeita a unidade selecionada, e a restauração exige a visão "Todas as
  unidades" porque mexe no banco inteiro.
- **`sistema/manutencao.py`** (VACUUM e snapshot do arquivo) só funciona com
  SQLite; no PostgreSQL ela avisa e não faz nada. O lugar dessas tarefas no
  servidor é o `autovacuum` do PostgreSQL e o `backup_postgres.sh`.
- Os **scripts `.bat`** de Windows foram mantidos na pasta para quem ainda roda
  a versão local, mas não têm uso no servidor Linux.
- A trava de concorrência dos registros (`registro_validacao.TRAVA_GRAVACAO`) é
  por processo. Com os 3 workers do gunicorn, dois lançamentos idênticos e
  simultâneos em workers diferentes poderiam escapar da checagem de duplicidade.
  É uma janela estreita (mesmo paciente, profissional, procedimento, data e
  grupo, no mesmo instante) e a duplicidade aparece na auditoria de competência
  antes da exportação. A solução definitiva é um índice único no banco; se
  preferir eliminar a janela agora, rode com `--workers 1` no Dockerfile.
- A migração do SQLite para PostgreSQL passa pelo backup JSON do próprio
  sistema, que cobre pacientes, profissionais, procedimentos, registros e
  configurações. **Grupos, eventos e o histórico de logs não vão nesse
  arquivo** — se precisar deles no servidor, exporte os relatórios antes de
  migrar ou mantenha o banco antigo arquivado para consulta.
