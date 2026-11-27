"""
Configuração do pytest para RAAS-CAPS.

Usa banco SQLite em arquivo temporário para isolamento. Com TEST_DATABASE_URL
definida (a CI usa para rodar a suíte também no PostgreSQL, o banco de
produção), usa esse banco — que é APAGADO no início e no fim da sessão.
"""
import os
import tempfile

_test_db = os.path.join(tempfile.gettempdir(), "test_raas_caps.db")
if os.path.exists(_test_db):
    os.remove(_test_db)

_url_externa = os.getenv("TEST_DATABASE_URL")
if _url_externa and "test" not in _url_externa.rsplit("/", 1)[-1]:
    # Trava de segurança: a suíte apaga todas as tabelas do banco de teste.
    raise RuntimeError("TEST_DATABASE_URL precisa apontar para um banco com 'test' no nome.")

os.environ["DATABASE_URL"] = _url_externa or f"sqlite:///{_test_db}"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DEBUG"] = "true"
# A suíte loga com admin/admin direto; os testes de LGPD religam o primeiro acesso.
os.environ["RAAS_DESATIVAR_PRIMEIRO_ACESSO"] = "1"
os.environ["COOKIE_SECURE"] = "false"
os.environ["TRUST_PROXY"] = "false"

import pytest
from fastapi.testclient import TestClient

from sqlalchemy import text

from database import Base, engine, SessionLocal, criar_tabelas
from main import app


def _apagar_esquema():
    """Remove as tabelas dos modelos e o controle de versão do Alembic: sem
    apagar alembic_version, a próxima sessão acharia o banco já migrado."""
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Migra o banco de teste (as mesmas migrações da produção) uma vez por sessão."""
    if _url_externa:
        _apagar_esquema()  # sobra de uma sessão interrompida
    criar_tabelas()
    yield
    _apagar_esquema()
    engine.dispose()
    if os.path.exists(_test_db):
        os.remove(_test_db)


@pytest.fixture(scope="function", autouse=True)
def clean_db():
    """Limpa dados e rate limits entre testes."""
    from sistema.rate_limit_middleware import reset_rate_limits
    reset_rate_limits()
    yield
    reset_rate_limits()
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()


@pytest.fixture(scope="function")
def db_session():
    """Sessão de banco para uso direto em testes."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client():
    """Cliente de teste sem autenticação."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def auth_client(db_session):
    """Cliente autenticado como admin."""
    from usuario.usuario_service import UsuarioService

    UsuarioService.inicializar_admin_padrao(db_session)

    with TestClient(app) as c:
        c.post("/login", data={"username": "admin", "password": "admin"})
        yield c
