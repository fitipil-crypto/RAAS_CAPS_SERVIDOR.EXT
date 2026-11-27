# Requisitos e regras de negócio — RAAS-CAPS

Este documento descreve **o que o sistema deve fazer** e **quais regras ele
aplica**. Cada regra aponta para o código que a implementa e para o teste que a
garante. Ao mudar uma regra, atualize as três coisas juntas: este documento, o
código e o teste.

Identificadores: `RF` = requisito funcional, `RN` = regra de negócio,
`RNF` = requisito não funcional.

---

## 1. Objetivo e usuários

O RAAS-CAPS registra os atendimentos dos Centros de Atenção Psicossocial e gera
o arquivo **RAAS (Registro das Ações Ambulatoriais de Saúde — Psicossocial)**
no layout posicional do DATASUS, para o faturamento no SIA/SUS. A edição
servidor atende várias unidades (as 7 modalidades de CAPS) num mesmo banco.

| Perfil | O que pode fazer |
|---|---|
| `admin` | Tudo, inclusive usuários, unidades, backup e configurações do sistema. |
| `gestor` | Acompanha mais de um CAPS: alterna entre unidades ou usa "Todas as unidades". Não administra o sistema. |
| `coordenador` | Gestão da própria unidade. |
| `operador` | Digitação e consulta na própria unidade. |

Autorização por perfil: `sistema/auth.py` (`require_role`). Testes:
`tests/test_auth.py`, `tests/test_usuarios.py`.

---

## 2. Requisitos funcionais

| ID | Requisito | Onde |
|---|---|---|
| RF01 | Cadastrar, editar, buscar e desativar pacientes (identificação, endereço, dados clínicos e sociais). | `paciente/` |
| RF02 | Cadastrar profissionais (CNS, CBO, equipe) e procedimentos SIGTAP. | `profissional/`, `procedimento/` |
| RF03 | Lançar atendimentos por competência mensal, um a um ou em lote. | `registro/` |
| RF04 | Lançar atendimentos em grupo e em eventos coletivos. | `grupo/`, `evento/` |
| RF05 | Auditar a competência antes de exportar, listando erros e avisos. | `competencia/auditoria_service.py` |
| RF06 | Gerar o arquivo RAAS (registros 01, 15 e 16) e exportar CSV/planilhas. | `exportacao/` |
| RF07 | Importar arquivos RAAS e CSV de cadastros, com pré-visualização. | `importacao/`, `sistema/csv_import_export.py` |
| RF08 | Emitir relatórios operacionais, indicadores e versões para impressão. | `relatorio/`, `dashboard/` |
| RF09 | Isolar os dados de cada unidade (CAPS) no mesmo banco. | `sistema/escopo.py`, `unidade/` |
| RF10 | Fazer backup e restauração dos dados. | `backup/`, `deploy/backup_postgres.sh` |
| RF11 | Atender os direitos do titular e registrar incidentes (LGPD). | `lgpd/`, `docs/LGPD.md` |
| RF12 | Registrar em log de auditoria quem acessou, alterou ou exportou o quê. | `sistema/log_middleware.py` |

---

## 3. Regras de negócio

### 3.1 Lançamento de atendimentos (`registro/registro_validacao.py`)

Testes: `tests/test_registro_validacao.py`, `tests/test_registros.py`.

| ID | Regra |
|---|---|
| RN01 | A data do atendimento tem de estar dentro da competência escolhida (`2026-08-31` só entra em `2026-08`). |
| RN02 | A data do atendimento não pode ser anterior à data de admissão do paciente. |
| RN03 | O mesmo atendimento (data, paciente, profissional, procedimento e grupo) não pode ser lançado duas vezes, nem no banco nem dentro do mesmo lote. |
| RN04 | O mesmo paciente pode estar em grupos diferentes no mesmo dia, mas não duas vezes no mesmo grupo. |
| RN05 | O atendimento lançado num grupo tem de ser no dia do grupo. |
| RN06 | Um profissional não pode estar em dois grupos com a mesma data e o mesmo horário. |
| RN07 | Um grupo não pode ter mais pacientes distintos do que a quantidade de pessoas informada ao criá-lo. |
| RN08 | O procedimento 03.01.08.021-6 (atendimento em grupo) só pode ser lançado pela tela de grupos. |
| RN09 | No lançamento em lote: no máximo 5 profissionais por vez (10 para `admin`). |

### 3.2 Validação dos dados do RAAS (`competencia/regras_raas.py`)

Funções puras, testadas em `tests/test_competencia.py`. A auditoria da
competência (`competencia/auditoria_service.py`) aplica estas regras e
classifica cada achado como **bloqueio** (impede a exportação) ou **alerta**
(pede conferência).

| ID | Regra |
|---|---|
| RN10 | CNS com 15 dígitos e dígito verificador válido (definitivo, que começa com 1 ou 2, e provisório, que começa com 7, 8 ou 9). |
| RN11 | CPF com dígitos verificadores válidos. CNPJ numérico ou alfanumérico válido. |
| RN12 | CID-10 gravado em maiúsculas e sem ponto (ex.: `F840`), porque o campo do layout tem 4 posições. |
| RN13 | Código de procedimento SIGTAP com 10 dígitos. Os de atenção psicossocial começam com `030108`. |
| RN14 | O atendimento domiciliar (03.01.08.024-0) lançado como realizado no CAPS (local `C`) gera alerta: ele é feito no território (`T`). |
| RN15 | CBO com 6 dígitos, CEP com 8, CNES com 7, município IBGE com 6 ou 7. |
| RN16 | Sexo `M`/`F`; raça/cor no domínio do layout. Paciente indígena (`05`) sem etnia é bloqueio. |
| RN17 | Nome, nome da mãe e endereço são cortados em 30 posições no arquivo. A quantidade vai até 999.999, e acima de 30 num lançamento gera aviso. |

### 3.3 Modalidades de CAPS (`unidade/modalidades.py`)

| ID | Regra |
|---|---|
| RN18 | Toda unidade tem uma das 7 modalidades: CAPS I, II, III, i, AD, AD III e AD IV. |
| RN19 | Faixa etária, leitos e porte populacional fora do esperado para a modalidade geram **aviso**, não bloqueio (ver README_SERVIDOR.md, seção 7). |

Testes: `tests/test_unidades.py`.

### 3.4 Retenção de dados (`sistema/retention_service.py`)

| ID | Regra |
|---|---|
| RN20 | A purga mantém a competência atual e as 3 anteriores e só roda quando chamada explicitamente, nunca de forma automática. |
| RN21 | Registros sem competência não são apagados. Com uma unidade ativa, só os registros dela são apagados. |

Testes: `tests/test_retencao.py`.

---

## 4. Requisitos não funcionais

| ID | Requisito | Onde |
|---|---|---|
| RNF01 | **Isolamento entre unidades:** todo SELECT, UPDATE e DELETE do ORM em tabelas assistenciais é filtrado pela unidade ativa, sem depender de cada consulta lembrar do filtro. | `sistema/escopo.py`, `tests/test_unidades.py` |
| RNF02 | **Senhas:** bcrypt; mínimo de 6 caracteres, com letra e número; troca obrigatória da senha padrão. | `sistema/seguranca.py`, `usuario/` |
| RNF03 | **Bloqueio de conta:** 15 minutos depois de 5 falhas de login seguidas. | `usuario/usuario_service.py` |
| RNF04 | **Proteção da aplicação:** CSRF, limite de requisições, cabeçalhos de segurança e cookies seguros atrás de HTTPS. | `sistema/seguranca.py`, `sistema/rate_limit_middleware.py` |
| RNF05 | **LGPD:** termo de confidencialidade, aviso de privacidade, prazo de 15 dias para responder ao titular, anonimização. | `lgpd/`, `docs/LGPD.md` |
| RNF06 | **Banco:** PostgreSQL em produção e SQLite na versão local. O esquema é versionado com Alembic e as migrações são aplicadas na inicialização. | `database.py`, `migrations/` |
| RNF07 | **Disponibilidade:** `/saude` verifica o banco e o container é reiniciado se o banco não responder. | `Dockerfile` |
| RNF08 | **Qualidade:** toda mudança passa pela CI (lint, testes em SQLite e PostgreSQL, cobertura mínima, auditoria de dependências e build do Docker). | `.github/workflows/ci.yml` |

---

## 5. Limitações conhecidas

Ver README_SERVIDOR.md, seção 10. A principal: a trava contra lançamento
duplicado (RN03) vale por processo, e a produção roda 3 workers.
