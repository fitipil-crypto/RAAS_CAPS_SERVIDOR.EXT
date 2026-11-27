"""
Testes das migrações do banco (Alembic).

O mais importante é o primeiro: ele quebra a CI quando alguém muda um modelo
e esquece de gerar a migração correspondente.
"""
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

import database
from database import Base, configuracao_alembic, migrar_esquema


def _diferencas(conn):
    database._importar_modelos()
    contexto = MigrationContext.configure(conn, opts={"compare_type": True})
    return compare_metadata(contexto, Base.metadata)


def _revisao_atual(eng):
    with eng.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def _head():
    return ScriptDirectory.from_config(configuracao_alembic()).get_current_head()


@pytest.fixture
def banco_vazio(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'migracao.db'}")
    yield eng
    eng.dispose()


def test_modelos_e_migracoes_estao_em_dia():
    """O banco migrado (o da própria suíte, SQLite ou PostgreSQL) bate com os
    modelos. Se falhar: rode `alembic revision --autogenerate -m "..."`."""
    with database.engine.connect() as conn:
        diferencas = _diferencas(conn)
    assert diferencas == [], (
        "Modelo mudou sem migração. Gere uma com "
        "`alembic revision --autogenerate -m \"descricao\"`. Diferenças: "
        f"{diferencas}"
    )


def test_ha_uma_unica_head():
    """Duas heads = duas migrações criadas em paralelo a partir da mesma base."""
    assert len(ScriptDirectory.from_config(configuracao_alembic()).get_heads()) == 1


def test_banco_vazio_chega_na_head(banco_vazio):
    migrar_esquema(banco_vazio)
    assert _revisao_atual(banco_vazio) == _head()
    with banco_vazio.connect() as conn:
        assert _diferencas(conn) == []


def test_migrar_duas_vezes_nao_muda_nada(banco_vazio):
    migrar_esquema(banco_vazio)
    migrar_esquema(banco_vazio)
    assert _revisao_atual(banco_vazio) == _head()


def test_downgrade_e_upgrade_de_volta(banco_vazio):
    migrar_esquema(banco_vazio)
    cfg = configuracao_alembic()
    with banco_vazio.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "base")
    assert set(inspect(banco_vazio).get_table_names()) == {"alembic_version"}

    migrar_esquema(banco_vazio)
    with banco_vazio.connect() as conn:
        assert _diferencas(conn) == []


def test_banco_anterior_ao_alembic_e_completado(banco_vazio):
    """Banco da versão antiga (create_all + ALTER TABLE manual): sem a tabela
    alembic_version, com tabelas faltando colunas e índices. A migração de
    base completa o que falta sem perder as linhas que já existiam."""
    with banco_vazio.begin() as conn:
        conn.execute(text(
            "CREATE TABLE usuarios (id VARCHAR(36) PRIMARY KEY, username VARCHAR(50) NOT NULL, "
            "password_hash VARCHAR(255) NOT NULL, name VARCHAR(200) NOT NULL, "
            "profile VARCHAR(20) NOT NULL, active BOOLEAN)"
        ))
        conn.execute(text(
            "INSERT INTO usuarios (id, username, password_hash, name, profile, active) "
            "VALUES ('u1', 'admin', 'x', 'Administrador', 'admin', 1)"
        ))
        conn.execute(text(
            "CREATE TABLE grupos (id VARCHAR(36) PRIMARY KEY, service_month VARCHAR(7) NOT NULL, "
            "description VARCHAR(30) NOT NULL, group_date VARCHAR(10) NOT NULL, "
            "group_time VARCHAR(5) NOT NULL, people_count INTEGER NOT NULL)"
        ))
        conn.execute(text(
            "INSERT INTO grupos VALUES ('g1', '2025-01', 'OFICINA', '2025-01-10', '13:00', 5)"
        ))
        # Coluna antiga que saiu do modelo: tem de continuar lá, intocada.
        conn.execute(text("ALTER TABLE grupos ADD COLUMN coluna_antiga VARCHAR(5)"))

    migrar_esquema(banco_vazio)

    insp = inspect(banco_vazio)
    assert _revisao_atual(banco_vazio) == _head()
    assert "pacientes" in insp.get_table_names()  # tabela que faltava foi criada
    colunas_usuarios = {c["name"] for c in insp.get_columns("usuarios")}
    assert {"help_enabled", "failed_logins", "unidade_id", "locked_until"} <= colunas_usuarios
    assert "coluna_antiga" in {c["name"] for c in insp.get_columns("grupos")}
    assert "ix_grupos_unidade" in {i["name"] for i in insp.get_indexes("grupos")}

    with banco_vazio.connect() as conn:
        usuario = conn.execute(text(
            "SELECT username, help_enabled, must_change_password, failed_logins FROM usuarios"
        )).one()
        grupo = conn.execute(text("SELECT description, created_seq FROM grupos")).one()
    # Linhas antigas recebem o mesmo padrão que a lista _MIGRATIONS dava.
    assert tuple(usuario) == ("admin", 1, 0, 0)
    assert tuple(grupo) == ("OFICINA", 0)
