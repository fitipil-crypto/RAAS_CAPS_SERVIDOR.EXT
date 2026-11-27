# Tasks — RAAS-CAPS

**Criado em:** 2026-02-04  
**Atualizado em:** 2026-11-27

## Pendentes

Por prioridade. Ao concluir uma tarefa, mova-a para "Concluídas" e registre a
mudança no `CHANGELOG.md`.

- [ ] Transformar o job "Testes (PostgreSQL)" da CI em obrigatório (tirar o
      `continue-on-error`) depois que ele passar pela primeira vez
- [ ] Trava de duplicidade de registros no banco (índice único ou trava
      consultiva): a `TRAVA_GRAVACAO` atual vale por processo e a produção roda
      3 workers (README_SERVIDOR.md, seção 10)
- [ ] Guardar datas como `DATE` em vez de `String(10)` (`service_date`,
      `birth_date`, `admission_date`...), com migração dos dados
- [ ] Remover os índices duplicados por unidade (`ix_<tabela>_unidade` repete
      `ix_<tabela>_unidade_id`), com migração
- [ ] Ligar as regras B904 e B905 do ruff, que estão no `ignore` do `ruff.toml`
- [ ] Subir a cobertura mínima da CI aos poucos (`--cov-fail-under`)
- [ ] Testes do JavaScript do front e um teste ponta a ponta no navegador
- [ ] Dividir `relatorio/impressao_service.py` (cerca de 800 linhas)
- [ ] `RetentionService.purge_old_competencias` carrega todos os registros na
      memória: trocar por um `DELETE ... WHERE` no banco

## Concluídas

### 2026-11 — práticas de engenharia
- [x] Migrações versionadas com Alembic (`migrations/`)
- [x] Testes das regras de lançamento, da retenção, do CSV e das migrações
- [x] Suíte também no PostgreSQL na CI, com cobertura mínima
- [x] `docs/REQUISITOS.md` e `CHANGELOG.md`
- [x] Lint ampliado (`ruff.toml`)

### Itens antigos já entregues
- [x] Testes automatizados (`tests/`)
- [x] Página de exclusão de dados em lote (`templates/excluir.html`)
- [x] Validações de CNS/CPF pelo algoritmo oficial (`competencia/regras_raas.py`)
- [x] Detalhe do paciente (`templates/paciente_detalhe.html`)
- [x] Migração para PostgreSQL (edição servidor)
- [x] Deploy em produção (`deploy/`, `docker-compose.prod.yml`)

### 2026-02 — versão inicial

- [x] Analisar estrutura do arquivo JSX e identificar todos os componentes
- [x] Criar estrutura de diretórios e arquivos base (database.py, main.py, requirements.txt, .env)
- [x] Criar módulo usuario (model, schema, service, router, frontend_router, auth)
- [x] Criar módulo paciente (model, schema, service, router, frontend_router)
- [x] Criar módulo profissional (model, schema, service, router, frontend_router)
- [x] Criar módulo procedimento (model, schema, service, router, frontend_router)
- [x] Criar módulo registro (model, schema, service, router, frontend_router)
- [x] Criar módulo config (model, schema, service, router, frontend_router)
- [x] Criar módulo importacao (service, router, frontend_router)
- [x] Criar módulo exportacao (service, router, frontend_router)
- [x] Criar módulo relatorio (service, router, frontend_router)
- [x] Criar módulo backup (service, router, frontend_router)
- [x] Criar templates Jinja2 (base, login, dashboard, pacientes, profissionais, procedimentos, registros, exportacao, relatorios, configuracoes, importar, backup, acesso)
- [x] Criar arquivos estáticos (CSS, JS)
- [x] Criar README.md e implementation_plans/
