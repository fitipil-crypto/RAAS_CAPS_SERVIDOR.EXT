"""
Testes dos utilitários usados pelos scripts .bat (sistema/manutencao.py).
"""
import os
import sqlite3
import time
from datetime import datetime

from sistema import manutencao


def _criar_banco(caminho):
    con = sqlite3.connect(str(caminho))
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (42)")
    con.commit()
    con.close()


def test_backup_cria_snapshot_legivel(tmp_path):
    banco = tmp_path / "raas_caps.db"
    _criar_banco(banco)
    pasta = tmp_path / "bk"
    msg = manutencao.backup_diario(f"sqlite:///{banco}", pasta=str(pasta), hoje=datetime(2026, 10, 8))
    assert "backup criado" in msg
    copia = pasta / "raas_caps_20261008.db"
    assert sqlite3.connect(str(copia)).execute("SELECT x FROM t").fetchone() == (42,)
    assert not list(pasta.glob("*.tmp"))


def test_backup_so_um_por_dia(tmp_path):
    banco = tmp_path / "raas_caps.db"
    _criar_banco(banco)
    pasta = str(tmp_path / "bk")
    hoje = datetime(2026, 10, 8)
    manutencao.backup_diario(f"sqlite:///{banco}", pasta=pasta, hoje=hoje)
    assert "ja existe" in manutencao.backup_diario(f"sqlite:///{banco}", pasta=pasta, hoje=hoje)


def test_backup_remove_antigos(tmp_path):
    banco = tmp_path / "raas_caps.db"
    _criar_banco(banco)
    pasta = tmp_path / "bk"
    pasta.mkdir()
    velho = pasta / "raas_caps_20260101.db"
    velho.write_bytes(b"x")
    recente = pasta / "raas_caps_20261005.db"
    recente.write_bytes(b"x")
    hoje = datetime(2026, 10, 8)
    antigo_ts = hoje.timestamp() - 40 * 86400
    os.utime(velho, (antigo_ts, antigo_ts))
    os.utime(recente, (hoje.timestamp() - 3 * 86400,) * 2)
    msg = manutencao.backup_diario(f"sqlite:///{banco}", pasta=str(pasta), mantem_dias=14, hoje=hoje)
    assert "removido" in msg
    assert not velho.exists() and recente.exists()


def test_backup_ignora_banco_que_nao_e_sqlite_ou_nao_existe(tmp_path):
    assert "nao e SQLite" in manutencao.backup_diario("postgresql://x/y", pasta=str(tmp_path))
    assert "nao existe" in manutencao.backup_diario(f"sqlite:///{tmp_path}/nada.db", pasta=str(tmp_path))


def test_rotacionar_log(tmp_path):
    log = tmp_path / "server.log"
    log.write_bytes(b"a" * 2048)
    assert manutencao.rotacionar_log(str(log), max_mb=0.001, copias=2)
    assert not log.exists() and (tmp_path / "server.log.1").exists()
    # novo ciclo: .1 vira .2, descartando o excedente
    log.write_bytes(b"b" * 2048)
    manutencao.rotacionar_log(str(log), max_mb=0.001, copias=2)
    log.write_bytes(b"c" * 2048)
    manutencao.rotacionar_log(str(log), max_mb=0.001, copias=2)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["server.log.1", "server.log.2"]
    assert (tmp_path / "server.log.1").read_bytes().startswith(b"c")


def test_rotacionar_log_pequeno_nao_mexe(tmp_path):
    log = tmp_path / "server.log"
    log.write_text("pouco")
    assert manutencao.rotacionar_log(str(log), max_mb=10) == ""
    assert log.exists()


def test_hash_requisitos_muda_com_o_arquivo(tmp_path):
    arq = tmp_path / "requirements.txt"
    arq.write_text("fastapi==1\n")
    h1 = manutencao.hash_requisitos(str(arq))
    arq.write_text("fastapi==2\n")
    assert h1 != manutencao.hash_requisitos(str(arq)) and len(h1) == 64


def test_cli_agora_e_ajuda(capsys):
    assert manutencao.main(["agora"]) == 0
    assert abs(int(capsys.readouterr().out) - int(time.time())) < 5
    assert manutencao.main([]) == 2
