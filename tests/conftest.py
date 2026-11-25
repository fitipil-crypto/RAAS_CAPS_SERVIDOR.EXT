"""
Configuração do pytest para RAAS-CAPS.

Usa banco SQLite em arquivo temporário para isolamento.
"""
import os
import tempfile

_test_db = os.path.join(tempfile.gettempdir(), "test_raas_caps.db")
if os.path.exists(_test_db):
    os.remove(_test_db)

os.environ["DATABASE_URL"] = f"sqlite:///{_test_db}"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DEBUG"] = "true"
# A suíte loga com admin/admin direto; os testes de LGPD religam o primeiro acesso.
os.environ["RAAS_DESATIVAR_PRIMEIRO_ACESSO"] = "1"
os.environ["COOKIE_SECURE"] = "false"
os.environ["TRUST_PROXY"] = "false"

import pytest
from fastapi.testclient import TestClient

from database import Base, engine, SessionLocal, criar_tabelas
from main import app


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Cria tabelas uma vez por sessão de teste."""
    criar_tabelas()
    yield
    Base.metadata.drop_all(bind=engine)
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
