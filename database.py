"""
Configuração do banco de dados SQLAlchemy.

Migrações automáticas: ao adicionar uma nova coluna a um modelo, basta
acrescentar uma tupla (tabela, coluna, tipo_sql) na lista _MIGRATIONS abaixo.
Na próxima inicialização a coluna é criada via ALTER TABLE se ainda não
existir — idempotente, funciona em SQLite e PostgreSQL.
"""
import importlib
import logging
import os
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


# ── Lista de migrações (tabela, coluna, tipo_sql) ──
# Para adicionar uma nova coluna a uma tabela existente, basta incluir
# uma nova tupla aqui. A coluna será criada automaticamente no próximo boot.
_MIGRATIONS = [
    ("pacientes", "carate", "VARCHAR(2)"),
    ("pacientes", "street_code", "VARCHAR(10)"),
    ("pacientes", "mot_saida", "VARCHAR(2)"),
    ("profissionais", "birth_date", "VARCHAR(10)"),
    ("usuarios", "help_enabled", "BOOLEAN DEFAULT TRUE"),
    # LGPD / segurança
    ("usuarios", "must_change_password", "BOOLEAN DEFAULT FALSE"),
    ("usuarios", "senha_alterada_em", "TIMESTAMP"),
    ("usuarios", "failed_logins", "INTEGER DEFAULT 0"),
    ("usuarios", "locked_until", "TIMESTAMP"),
    ("usuarios", "termo_versao", "VARCHAR(20)"),
    ("usuarios", "termo_aceito_em", "TIMESTAMP"),
    ("pacientes", "base_legal", "VARCHAR(40)"),
    ("pacientes", "anonimizado", "BOOLEAN DEFAULT FALSE"),
    ("pacientes", "anonimizado_em", "TIMESTAMP"),
    # Acompanhamento no CAPS
    ("pacientes", "reference_technicians", "VARCHAR(200)"),
    ("pacientes", "psychiatrist", "VARCHAR(100)"),
    ("pacientes", "patient_status", "VARCHAR(20)"),
    ("pacientes", "referred_by", "VARCHAR(100)"),
    ("pacientes", "referred_to", "VARCHAR(100)"),
    ("pacientes", "referring_technician", "VARCHAR(100)"),
    ("pacientes", "discharge_technician", "VARCHAR(100)"),
    # Grupo de atendimento em que o registro foi lançado (digitação em lote).
    # Substituiu o antigo session_number (sessão de 1 a 5), que foi revogado;
    # a coluna antiga pode continuar no banco, sem uso.
    ("registros_raas", "group_id", "VARCHAR(36)"),
    ("grupos", "created_seq", "INTEGER DEFAULT 0"),
    # CID Secundário 3 (layout RAAS, posições 271-274 do Registro 15)
    ("pacientes", "cid_associated3", "VARCHAR(10)"),
    # ── Servidor multiunidade (7 modalidades de CAPS) ──
    # Cada tabela de dado assistencial passa a dizer de que unidade a linha é.
    # A coluna aceita nulo porque um banco que vem da versão de um só CAPS é
    # migrado sem recriar as tabelas; `python -m unidade.migracao` atribui as
    # linhas antigas à unidade escolhida.
    ("pacientes", "unidade_id", "VARCHAR(36)"),
    ("registros_raas", "unidade_id", "VARCHAR(36)"),
    ("profissionais", "unidade_id", "VARCHAR(36)"),
    ("grupos", "unidade_id", "VARCHAR(36)"),
    ("eventos", "unidade_id", "VARCHAR(36)"),
    ("evento_registros", "unidade_id", "VARCHAR(36)"),
    ("evento_pacientes", "unidade_id", "VARCHAR(36)"),
    ("lgpd_solicitacoes", "unidade_id", "VARCHAR(36)"),
    ("lgpd_incidentes", "unidade_id", "VARCHAR(36)"),
    ("logs_sistema", "unidade_id", "VARCHAR(36)"),
    # Lotação do usuário (não é escopo: ver usuario_model).
    ("usuarios", "unidade_id", "VARCHAR(36)"),
]


def _run_migrations():
    """Adiciona colunas novas em tabelas existentes (idempotente)."""
    if not _MIGRATIONS:
        return
    with engine.connect() as conn:
        for table, column, col_type in _MIGRATIONS:
            try:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                ))
                conn.commit()
                logger.info("Migração: adicionada coluna %s.%s", table, column)
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                msg = str(e).lower()
                if "duplicate column" in msg or "already exists" in msg:
                    pass  # Coluna já existe — esperado
                else:
                    logger.warning("Migração: aviso em %s.%s: %s", table, column, e)



# ── Índices adicionais (tabela, nome, coluna) ──
# CREATE INDEX IF NOT EXISTS já é idempotente por si só (não precisa de try/except).
_INDICES = [
    ("registros_raas", "ix_registros_raas_service_date", "service_date"),
    ("registros_raas", "ix_registros_raas_group_id", "group_id"),
    # O filtro por unidade entra em todo SELECT das tabelas com escopo: sem
    # índice, cada consulta varreria a tabela inteira. Os compostos atendem as
    # duas consultas mais pesadas (registros da competência e lista de pacientes).
    ("pacientes", "ix_pacientes_unidade", "unidade_id"),
    ("registros_raas", "ix_registros_unidade", "unidade_id"),
    ("registros_raas", "ix_registros_unidade_mes", "unidade_id, service_month"),
    ("profissionais", "ix_profissionais_unidade", "unidade_id"),
    ("grupos", "ix_grupos_unidade", "unidade_id"),
    ("eventos", "ix_eventos_unidade", "unidade_id"),
    ("logs_sistema", "ix_logs_unidade", "unidade_id"),
    ("pacientes", "ix_pacientes_unidade_nome", "unidade_id, name"),
]


def _criar_indices():
    with engine.connect() as conn:
        for table, index_name, column in _INDICES:
            conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})"
            ))
        conn.commit()


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


def criar_tabelas():
    """Cria todas as tabelas e roda migrações automáticas."""
    # Importar todos os modelos para registrar no Base.metadata
    _importar_modelos()

    Base.metadata.create_all(bind=engine)
    _run_migrations()
    _criar_indices()
    _corrigir_tipo_atendimento_grupo()
    _padronizar_cids()
