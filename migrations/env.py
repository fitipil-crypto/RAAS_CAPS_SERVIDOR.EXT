"""
Ambiente do Alembic para o RAAS-CAPS.

Funciona de dois jeitos:

* pela linha de comando (``alembic upgrade head``): abre a conexão com o
  ``engine`` do ``database.py``, que lê DATABASE_URL;
* chamado pela aplicação (``database.migrar_esquema``): reaproveita a conexão
  recebida em ``config.attributes["connection"]``, que já está dentro da
  transação (e, no PostgreSQL, da trava) aberta por quem chamou.
"""
from logging.config import fileConfig

from alembic import context

from database import Base, _importar_modelos, engine

config = context.config
conexao_recebida = config.attributes.get("connection")

# Só configura o logging pela linha de comando: dentro da aplicação isso
# substituiria a configuração de log que o main.py já montou.
if conexao_recebida is None and config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Todos os modelos precisam estar importados para o autogenerate enxergá-los.
_importar_modelos()
target_metadata = Base.metadata


def _configurar(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Gera o SQL sem conectar (``alembic upgrade head --sql``)."""
    _configurar(
        url=str(engine.url),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=engine.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def _rodar(conexao) -> None:
    # O SQLite não altera nem remove coluna com ALTER TABLE: o modo "batch"
    # recria a tabela por baixo dos panos quando a migração precisa disso.
    _configurar(connection=conexao, render_as_batch=conexao.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if conexao_recebida is not None:
        _rodar(conexao_recebida)
        return
    with engine.connect() as conexao:
        _rodar(conexao)
        conexao.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
