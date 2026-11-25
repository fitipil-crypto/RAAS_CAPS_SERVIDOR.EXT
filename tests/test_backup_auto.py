"""
Testes do backup automático em pasta da rede local.
"""
import zipfile
from datetime import datetime

from backup import backup_auto_service as auto


def _config(auth_client, destino, **extra):
    dados = {"ativo": True, "destino": str(destino), "dias": [0, 2, 4], "horarios": ["12:00", "18:30"], "manter": 3}
    dados.update(extra)
    return auth_client.put("/api/backup/auto", json=dados)


def test_salvar_e_ler_configuracao(auth_client, tmp_path):
    resp = _config(auth_client, tmp_path)
    assert resp.status_code == 200, resp.text
    c = auth_client.get("/api/backup/auto").json()
    assert c["ativo"] is True and c["destino"] == str(tmp_path)
    assert c["dias"] == [0, 2, 4] and c["horarios"] == ["12:00", "18:30"] and c["manter"] == 3
    assert c["proximo"]


def test_configuracao_invalida(auth_client, tmp_path):
    assert _config(auth_client, tmp_path, horarios=["25:00"]).status_code == 400
    assert _config(auth_client, tmp_path, dias=[7]).status_code == 400
    assert _config(auth_client, tmp_path, dias=[]).status_code == 400
    assert _config(auth_client, "", ativo=True).status_code == 400
    assert _config(auth_client, tmp_path, horarios=[f"0{i}:00" for i in range(7)]).status_code == 400
    # Desligado, pode salvar sem destino.
    assert _config(auth_client, "", ativo=False, dias=[], horarios=[]).status_code == 200


def test_executar_grava_zip_completo_e_remove_antigos(auth_client, tmp_path):
    for i in range(4):  # backups antigos além do limite (manter=3)
        (tmp_path / f"{auto.PREFIXO_ARQUIVO}2020010{i}_120000.zip").write_bytes(b"x")
    _config(auth_client, tmp_path)

    resp = auth_client.post("/api/backup/auto/executar")
    assert resp.status_code == 200, resp.text
    arquivos = sorted(tmp_path.glob(f"{auto.PREFIXO_ARQUIVO}*.zip"))
    assert len(arquivos) == 3
    novo = arquivos[-1]
    with zipfile.ZipFile(novo) as z:
        nomes = z.namelist()
    assert "backup.json" in nomes and "LEIA-ME.txt" in nomes
    assert any(n.endswith(".db") for n in nomes)  # cópia completa do banco SQLite
    c = auth_client.get("/api/backup/auto").json()
    assert c["ultimo_ok"] is True and novo.name in c["ultima_msg"]


def test_destino_inacessivel_registra_falha(auth_client, tmp_path):
    _config(auth_client, tmp_path / "nao_existe")
    resp = auth_client.post("/api/backup/auto/executar")
    assert resp.status_code == 400
    assert auth_client.get("/api/backup/auto").json()["ultimo_ok"] is False
    assert auth_client.post("/api/backup/auto/testar", json={"destino": str(tmp_path / "nao_existe")}).status_code == 400
    assert auth_client.post("/api/backup/auto/testar", json={"destino": str(tmp_path)}).status_code == 200


def test_agenda_dispara_uma_vez_por_horario():
    v = dict(auto.PADRAO, backup_auto_ativo="true", backup_auto_destino="X",
             backup_auto_dias="0", backup_auto_horarios="12:00")
    segunda = datetime(2026, 11, 16, 12, 3)  # segunda-feira
    assert auto._slot_devido(v, segunda) == "2026-11-16 12:00"
    assert auto._slot_devido(dict(v, backup_auto_ultimo_slot="2026-11-16 12:00"), segunda) is None
    assert auto._slot_devido(v, datetime(2026, 11, 16, 11, 59)) is None   # antes do horário
    assert auto._slot_devido(v, datetime(2026, 11, 16, 12, 15)) is None   # passou da tolerância
    assert auto._slot_devido(v, datetime(2026, 11, 17, 12, 3)) is None    # terça não está marcada
    assert auto._slot_devido(dict(v, backup_auto_ativo="false"), segunda) is None


def test_proximo_horario():
    v = dict(auto.PADRAO, backup_auto_ativo="true", backup_auto_dias="0,4", backup_auto_horarios="08:00,18:00")
    assert auto.proximo_horario(v, datetime(2026, 11, 16, 9, 0)) == "16/11/2026 18:00"   # segunda
    assert auto.proximo_horario(v, datetime(2026, 11, 16, 19, 0)) == "20/11/2026 08:00"  # vai para sexta


def test_nome_de_computador_invalido_e_recusado(auth_client):
    resp = auth_client.get("/api/backup/auto/rede/pastas", params={"host": "pc & del *"})
    assert resp.status_code == 400


def test_somente_admin(auth_client, client):
    auth_client.post("/api/usuarios/", json={
        "username": "op_backup", "name": "Op", "role": "operador", "password": "senha123", "active": True})
    client.post("/login", data={"username": "op_backup", "password": "senha123"})
    assert client.get("/api/backup/auto").status_code == 403
    assert client.post("/api/backup/auto/executar").status_code == 403


def test_varredura_acha_quem_atende_na_porta_de_compartilhamento(monkeypatch):
    """A busca na rede acha o computador pela porta aberta (445/139), sem
    depender do `net view` nem do ping."""
    import socket

    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(8)
    porta = servidor.getsockname()[1]
    try:
        monkeypatch.setattr(auto, "_PORTAS_COMPARTILHAMENTO", (porta,))
        monkeypatch.setattr(auto, "_enderecos_locais", lambda: ["127.0.0.2"])
        achados = auto._varrer_rede()
    finally:
        servidor.close()

    assert "127.0.0.1" in [ip for ip, _ in achados]
    # Quem não atende na porta fica de fora.
    assert "127.0.0.3" not in [ip for ip, _ in achados]


def test_varredura_ignora_a_propria_maquina_e_o_loopback(monkeypatch):
    monkeypatch.setattr(auto, "_enderecos_locais", lambda: ["192.168.0.7"])
    alvos = auto._alvos_da_rede()
    assert "192.168.0.7" not in alvos          # a própria máquina não é alvo
    assert alvos[0] == "192.168.0.1" and alvos[-1] == "192.168.0.254"
    assert len(alvos) == 253


def test_porta_fechada_nao_conta_como_computador():
    servidor = __import__("socket").socket()
    servidor.bind(("127.0.0.1", 0))
    porta = servidor.getsockname()[1]
    servidor.close()  # ninguém mais escuta nessa porta
    assert auto._porta_aberta("127.0.0.1", porta) is False


def _resposta_nbstat(nomes):
    """Resposta NBSTAT sintética: (nome, sufixo, de_grupo) por registro."""
    pergunta = auto._pacote_nbstat()
    cabecalho = b"\x00\x00\x85\x00\x00\x00\x00\x01\x00\x00\x00\x00"
    nome_codificado = pergunta[12:46]          # nome + tipo/classe da pergunta
    registros = b"".join(
        nome.ljust(15).encode("ascii") + bytes([sufixo])
        + (0x8000 if grupo else 0x0400).to_bytes(2, "big")
        for nome, sufixo, grupo in nomes
    )
    corpo = bytes([len(nomes)]) + registros
    resposta_rr = nome_codificado + b"\x00\x21\x00\x01\x00\x00\x00\x00" + len(corpo).to_bytes(2, "big")
    return cabecalho + pergunta[12:50] + resposta_rr + corpo


def test_le_o_nome_do_computador_na_resposta_netbios():
    """Rede de trabalho do Windows não tem DNS: o nome vem do próprio micro."""
    resposta = _resposta_nbstat([
        ("WORKGROUP", 0x00, True),    # nome de grupo: não é o do computador
        ("SAUDE-95896", 0x00, False),  # este é o nome da máquina
        ("SAUDE-95896", 0x20, False),  # mesmo nome, serviço de arquivos
    ])
    assert auto._ler_nome_netbios(resposta) == "SAUDE-95896"


def test_resposta_netbios_truncada_nao_quebra():
    assert auto._ler_nome_netbios(b"") == ""
    assert auto._ler_nome_netbios(_resposta_nbstat([("PC", 0x00, False)])[:60]) == ""


def test_netbios_sem_resposta_devolve_vazio():
    # 192.0.2.x é faixa reservada para documentação: ninguém responde.
    assert auto._nome_netbios("192.0.2.1", timeout=0.2) == ""
