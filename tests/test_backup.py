"""
Testes do backup: as barras de progresso do front dependem dos cabeçalhos
Content-Length (percentual do download) e Content-Disposition (nome do arquivo).
"""


def test_download_backup_traz_cabecalhos_de_progresso(auth_client):
    resp = auth_client.get("/api/backup/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert int(resp.headers["content-length"]) == len(resp.content)
    assert "filename=backup_raas_caps_" in resp.headers["content-disposition"]


def test_restaurar_backup_com_arquivo_invalido_retorna_detalhe(auth_client):
    resp = auth_client.post(
        "/api/backup/restaurar",
        files={"file": ("ruim.json", b"nao eh json", "application/json")},
    )
    assert resp.status_code == 400
    assert isinstance(resp.json()["detail"], str)


def test_ciclo_backup_restauracao(auth_client):
    pac = auth_client.post("/api/pacientes/", json={
        "name": "PACIENTE BACKUP", "cns": "700000000000009",
        "birth_date": "1985-05-05", "gender": "F",
    })
    assert pac.status_code == 200, pac.text

    conteudo = auth_client.get("/api/backup/download").content
    resp = auth_client.post(
        "/api/backup/restaurar",
        files={"file": ("backup.json", conteudo, "application/json")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True
    nomes = [p["name"] for p in auth_client.get("/api/pacientes/").json()]
    assert "PACIENTE BACKUP" in nomes


def _criar_paciente(auth_client, nome="PACIENTE ORIGINAL", cns="700000000000009"):
    resp = auth_client.post("/api/pacientes/", json={
        "name": nome, "cns": cns, "birth_date": "1985-05-05", "gender": "F",
    })
    assert resp.status_code == 200, resp.text


def _nomes(auth_client):
    return [p["name"] for p in auth_client.get("/api/pacientes/").json()]


def test_restaurar_backup_com_item_invalido_nao_apaga_nada(auth_client):
    import json
    _criar_paciente(auth_client)
    backup = json.loads(auth_client.get("/api/backup/download").content)
    backup["records"] = [{"service_month": "2026-01"}]  # faltam campos obrigatórios

    resp = auth_client.post(
        "/api/backup/restaurar",
        files={"file": ("ruim.json", json.dumps(backup).encode(), "application/json")},
    )
    assert resp.status_code == 400
    assert "records[1]" in resp.json()["detail"]
    assert "PACIENTE ORIGINAL" in _nomes(auth_client)


def test_restaurar_json_que_nao_e_backup_nao_apaga_nada(auth_client):
    _criar_paciente(auth_client)
    resp = auth_client.post(
        "/api/backup/restaurar",
        files={"file": ("vazio.json", b"{}", "application/json")},
    )
    assert resp.status_code == 400
    assert "PACIENTE ORIGINAL" in _nomes(auth_client)


def test_falha_no_meio_da_restauracao_faz_rollback(auth_client, monkeypatch):
    import json
    from config.config_service import ConfigService
    _criar_paciente(auth_client)
    backup = json.loads(auth_client.get("/api/backup/download").content)

    def falha(*args, **kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(ConfigService, "atualizar_varios", falha)
    try:
        resp = auth_client.post(
            "/api/backup/restaurar",
            files={"file": ("b.json", json.dumps(backup, default=str).encode(), "application/json")},
        )
        assert resp.status_code >= 500
    except RuntimeError:
        pass  # TestClient pode repropagar a exceção do servidor
    monkeypatch.undo()
    assert "PACIENTE ORIGINAL" in _nomes(auth_client)


def test_restaurar_backup_antigo_com_dados_fora_do_padrao_atual(auth_client):
    """Backup gerado antes das regras de formato (ex.: CEP com 7 dígitos) deve
    continuar restaurável: a restauração não recusa dados que já estiveram no
    sistema."""
    import json
    data = {
        "version": "4.27",
        "patients": [{
            "name": "PACIENTE LEGADO", "cns": "702404066969027",
            "birth_date": "2009-01-24", "gender": "M",
            "cep": "1906372",  # 7 dígitos: inválido no cadastro atual
        }],
        "professionals": [], "procedures": [], "records": [],
    }
    resp = auth_client.post(
        "/api/backup/restaurar",
        files={"file": ("backup.json", json.dumps(data).encode(), "application/json")},
    )
    assert resp.status_code == 200, resp.text
    pacientes = auth_client.get("/api/pacientes/").json()
    assert any(p["name"] == "PACIENTE LEGADO" and p["cep"] == "1906372" for p in pacientes)
