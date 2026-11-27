"""
Configuração do banco de dados SQLAlchemy.

Migrações: o esquema é versionado com Alembic (pasta ``migrations/``). Ao
mudar um modelo, gere uma migração nova::

    alembic revision --autogenerate -m "descricao curta"

revise o arquivo gerado e versione-o junto com a mudança no modelo. A
aplicação aplica as migrações pendentes sozinha ao iniciar (``criar_tabelas``).
O teste ``tests/test_migracoes.py`` falha se um modelo mudar sem migração.
"""
import importlib
import logging
import os
import threading
from pathlib import Path

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./raas_caps.db")

IS_SQLITE = DATABASE_URL.startswith("sqlite")
IS_POSTGRES = DATABASE_URL.startswith("postgres")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if IS_SQLITE else {},
    pool_pre_ping=True,
    echo=False,
)

if IS_SQLITE:
    # WAL: leituras (navegacao, relatorios) nao ficam mais bloqueadas
    # esperando escritas concorrentes (ex: log de auditoria a cada request).
    # Sem isso, o modo padrao do SQLite trava o arquivo inteiro a cada commit.
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Registra o gancho que filtra as consultas por unidade. O import tem de
# acontecer aqui, e não só no main, para que o escopo valha também em scripts,
# testes e tarefas de linha de comando que usam o banco sem subir a aplicação.
from sistema import escopo as _escopo  # noqa: E402,F401  (efeito colateral: event listener)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _corrigir_tipo_atendimento_grupo():
    """Acerta o tipo dos registros de grupo gravados antes desta correção.

    Até aqui todo lançamento feito pela tela de registros era salvo como
    Individual ('01'), porque a tela não pergunta o tipo e o schema tinha esse
    valor fixo como padrão. Quem lançava um atendimento em grupo via o
    histórico marcado como Individual. A varredura é idempotente e só vai num
    sentido: procedimento de grupo — ou qualquer atendimento lançado dentro de
    um grupo — gravado como Individual passa para Grupo.
    O contrário não se mexe, para não desfazer o tipo escolhido nos eventos."""
    try:
        with engine.connect() as conn:
            resultado = conn.execute(text(
                "UPDATE registros_raas SET service_type = '02' "
                "WHERE COALESCE(service_type, '') <> '02' "
                "AND (group_id IS NOT NULL OR procedure_id IN ("
                "    SELECT id FROM procedimentos WHERE LOWER(name) LIKE '%grupo%'"
                "))"
            ))
            conn.commit()
            if resultado.rowcount:
                logger.info(
                    "Correção: %s registro(s) de grupo estavam como Individual.",
                    resultado.rowcount,
                )
    except Exception as e:
        logger.warning("Correção do tipo de atendimento não aplicada: %s", e)


def _padronizar_cids():
    """Deixa os CIDs já gravados no padrão do arquivo RAAS: maiúsculas, sem ponto.

    Antes da normalização na entrada, quem digitasse "z032" criava um segundo
    diagnóstico aos olhos dos relatórios — a lista de CIDs mais frequentes
    mostrava "Z032" e "z032" em duas linhas. O ponto trazia outro problema: o
    campo do CID no layout tem 4 posições, então "F84.0" saía cortado como
    "F84." na exportação. A varredura é idempotente e só mexe no que está fora
    do padrão."""
    colunas = ("cid_main", "cid_associated1", "cid_associated2", "cid_associated3", "cid_causes")
    try:
        with engine.connect() as conn:
            total = 0
            for coluna in colunas:
                padrao = f"UPPER(REPLACE({coluna}, '.', ''))"
                resultado = conn.execute(text(
                    f"UPDATE pacientes SET {coluna} = {padrao} "
                    f"WHERE {coluna} IS NOT NULL AND {coluna} <> {padrao}"
                ))
                total += resultado.rowcount or 0
            conn.commit()
            if total:
                logger.info("Correção: %s CID(s) passaram para o padrão (maiúsculas, sem ponto).", total)
    except Exception as e:
        logger.warning("Padronização dos CIDs não aplicada: %s", e)


def _descobrir_modelos(project_root: Path) -> list[str]:
    modules = []
    for package_dir in project_root.iterdir():
        if (
            not package_dir.is_dir()
            or package_dir.name.startswith((".", "_"))
            or not (package_dir / "__init__.py").is_file()
        ):
            continue
        for model_file in package_dir.rglob("*_model.py"):
            relative_path = model_file.relative_to(package_dir).with_suffix("")
            modules.append(".".join((package_dir.name, *relative_path.parts)))
    return sorted(modules)


def _importar_modelos(project_root: Path | None = None) -> None:
    root = project_root or Path(__file__).resolve().parent
    for module_name in _descobrir_modelos(root):
        importlib.import_module(module_name)


RAIZ_DO_PROJETO = Path(__file__).resolve().parent

# Chave da trava do PostgreSQL que serializa as migrações (número arbitrário,
# só precisa ser o mesmo em todos os processos da aplicação).
_TRAVA_MIGRACAO = 727_2026
_TRAVA_MIGRACAO_THREADS = threading.Lock()


def configuracao_alembic():
    """Config do Alembic apontando para a pasta de migrações do projeto,
    independente do diretório de onde a aplicação foi iniciada."""
    from alembic.config import Config

    cfg = Config(str(RAIZ_DO_PROJETO / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ_DO_PROJETO / "migrations"))
    return cfg


def migrar_esquema(alvo=None) -> None:
    """Aplica as migrações pendentes do Alembic (``upgrade head``).

    Roda numa transação só: se uma migração falhar, nada fica pela metade
    (o PostgreSQL desfaz DDL em transação). No PostgreSQL a trava consultiva
    garante que só um processo migra por vez — o gunicorn sobe vários workers
    e todos passam por aqui ao iniciar; os outros esperam e encontram o banco
    já atualizado.

    Dentro de um mesmo processo, a trava de thread faz o mesmo papel: o
    Alembic guarda o ambiente da migração num objeto global (``alembic.context``)
    e não pode rodar em duas threads ao mesmo tempo.
    """
    from alembic import command

    cfg = configuracao_alembic()
    alvo = alvo if alvo is not None else engine  # um Engine (o padrão ou o de um teste)
    with _TRAVA_MIGRACAO_THREADS, alvo.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _TRAVA_MIGRACAO})
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def criar_tabelas():
    """Deixa o banco no esquema atual e aplica as correções de dados."""
    # Importar todos os modelos para registrar no Base.metadata
    _importar_modelos()

    migrar_esquema()
    _corrigir_tipo_atendimento_grupo()
    _padronizar_cids()
