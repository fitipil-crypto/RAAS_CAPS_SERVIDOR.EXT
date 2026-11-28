# Histórico de mudanças

Todas as mudanças relevantes do RAAS-CAPS ficam registradas aqui. O formato
segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as
versões seguem o [Versionamento Semântico](https://semver.org/lang/pt-BR/):
`MAIOR.MENOR.CORREÇÃO`.

Como usar: cada PR acrescenta uma linha em **Não lançado**. Ao publicar uma
versão, renomeie essa seção para o número e a data, e marque o commit com
`git tag -a vX.Y.Z -m "vX.Y.Z"`.

## [Não lançado]

### Adicionado
- Ao fazer login, o usuário entra direto na unidade em que está lotado. Antes,
  admin e gestor sempre começavam em "Todas as unidades", mesmo com lotação.
- Migrações versionadas do banco com **Alembic** (`migrations/`). As migrações
  pendentes são aplicadas na inicialização. No PostgreSQL, uma trava impede
  que os workers do gunicorn migrem ao mesmo tempo.
- Testes das regras de lançamento (`tests/test_registro_validacao.py`), da
  retenção de competências (`tests/test_retencao.py`), dos utilitários de CSV
  (`tests/test_csv_import_export.py`) e das migrações (`tests/test_migracoes.py`).
  Este último falha se um modelo mudar sem migração.
- CI: a suíte roda também no **PostgreSQL**, com cobertura mínima obrigatória.
- `docs/REQUISITOS.md`: requisitos funcionais, regras de negócio e requisitos
  não funcionais, cada um ligado ao código e ao teste.
- `ruff.toml`: lint ampliado para pyflakes completo e bugbear.

### Alterado
- Os índices de consulta por unidade passaram da lista `_INDICES` do
  `database.py` para os próprios modelos (`__table_args__`).

### Corrigido
- A inicialização do banco agora é serializada entre threads. Antes,
  `test_salvamentos_simultaneos_nao_duplicam` (8 clientes subindo a aplicação
  ao mesmo tempo) podia travar a suíte inteira no Windows.

### Removido
- Lista `_MIGRATIONS` (`ALTER TABLE ADD COLUMN` na inicialização). Um banco
  antigo de qualquer versão é completado pela migração de base `0001_base`.
- Variáveis e import sem uso (`exportacao_service`, `aniversariantes_service`).

## [1.0.0] — edição servidor

### Adicionado
- Servidor multiunidade com as 7 modalidades de CAPS, isolamento por unidade,
  PostgreSQL, Docker, nginx com HTTPS e backup por `pg_dump`.
