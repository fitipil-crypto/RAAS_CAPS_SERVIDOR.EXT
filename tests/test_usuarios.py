"""
Testes do módulo de usuários.
"""


def test_listar_usuarios(auth_client):
    """GET /api/usuarios/ deve listar usuários."""
    resp = auth_client.get("/api/usuarios/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(u["username"] == "admin" for u in data)


def test_criar_usuario(auth_client):
    """POST /api/usuarios/ deve criar um usuário."""
    resp = auth_client.post("/api/usuarios/", json={
        "username": "operador1",
        "name": "Operador Teste",
        "role": "operador",
        "password": "senha123",
        "active": True,
    })
    assert resp.status_code == 200
    assert resp.json()["username"] == "operador1"


def test_criar_usuario_duplicado(auth_client):
    """POST /api/usuarios/ com username duplicado deve retornar 400."""
    auth_client.post("/api/usuarios/", json={
        "username": "dupuser",
        "name": "User 1",
        "role": "operador",
        "password": "senha123",
        "active": True,
    })
    resp = auth_client.post("/api/usuarios/", json={
        "username": "dupuser",
        "name": "User 2",
        "role": "operador",
        "password": "senha456",
        "active": True,
    })
    assert resp.status_code == 400


def test_deletar_usuario(auth_client):
    """DELETE /api/usuarios/{id} deve excluir usuário."""
    create = auth_client.post("/api/usuarios/", json={
        "username": "tempuser",
        "name": "Temp",
        "role": "coordenador",
        "password": "temporaria123",
        "active": True,
    })
    uid = create.json()["id"]
    resp = auth_client.delete(f"/api/usuarios/{uid}")
    assert resp.status_code == 200


def test_nao_deletar_proprio_usuario(auth_client):
    """DELETE do próprio usuário deve retornar 400."""
    users = auth_client.get("/api/usuarios/").json()
    admin_id = next(u["id"] for u in users if u["username"] == "admin")
    resp = auth_client.delete(f"/api/usuarios/{admin_id}")
    assert resp.status_code == 400


def test_alterar_senha(auth_client):
    """POST /api/usuarios/{id}/senha deve alterar a senha."""
    users = auth_client.get("/api/usuarios/").json()
    admin_id = next(u["id"] for u in users if u["username"] == "admin")
    resp = auth_client.post(f"/api/usuarios/{admin_id}/senha", json={
        "current_password": "admin",
        "new_password": "novasenha123",
        "confirm_password": "novasenha123",
    })
    assert resp.status_code == 200


def test_alterar_senha_errada(auth_client):
    """POST /api/usuarios/{id}/senha com senha atual errada deve retornar 400."""
    users = auth_client.get("/api/usuarios/").json()
    admin_id = next(u["id"] for u in users if u["username"] == "admin")
    resp = auth_client.post(f"/api/usuarios/{admin_id}/senha", json={
        "current_password": "errada",
        "new_password": "novasenha123",
        "confirm_password": "novasenha123",
    })
    assert resp.status_code == 400


def test_alterar_propria_senha_sem_senha_atual(auth_client):
    """Trocar a própria senha sem informar a senha atual deve retornar 400."""
    users = auth_client.get("/api/usuarios/").json()
    admin_id = next(u["id"] for u in users if u["username"] == "admin")
    resp = auth_client.post(f"/api/usuarios/{admin_id}/senha", json={
        "new_password": "novasenha123",
        "confirm_password": "novasenha123",
    })
    assert resp.status_code == 400


def test_operador_nao_lista_usuarios(auth_client, client):
    """Usuário não-admin não pode listar usuários nem ver outro usuário."""
    auth_client.post("/api/usuarios/", json={
        "username": "op_restrito", "name": "Op", "role": "operador",
        "password": "senha123", "active": True,
    })
    admin_id = next(u["id"] for u in auth_client.get("/api/usuarios/").json() if u["username"] == "admin")
    client.post("/login", data={"username": "op_restrito", "password": "senha123"})
    assert client.get("/api/usuarios/").status_code == 403
    assert client.get(f"/api/usuarios/{admin_id}").status_code == 403


def _criar_operador(auth_client, username="op_ajuda"):
    resp = auth_client.post("/api/usuarios/", json={
        "username": username, "name": "Op Ajuda", "role": "operador",
        "password": "senha123", "active": True,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_ajuda_vem_ativa_por_padrao(auth_client):
    assert _criar_operador(auth_client)["help_enabled"] is True


def test_admin_desativa_e_reativa_ajuda_de_outro_usuario(auth_client):
    op = _criar_operador(auth_client)
    resp = auth_client.put(f"/api/usuarios/{op['id']}", json={"help_enabled": False})
    assert resp.status_code == 200
    assert resp.json()["help_enabled"] is False
    resp = auth_client.put(f"/api/usuarios/{op['id']}", json={"help_enabled": True})
    assert resp.json()["help_enabled"] is True


def test_usuario_comum_nao_liga_a_propria_ajuda(auth_client, client):
    op = _criar_operador(auth_client)
    auth_client.put(f"/api/usuarios/{op['id']}", json={"help_enabled": False})
    client.post("/login", data={"username": "op_ajuda", "password": "senha123"})
    client.put(f"/api/usuarios/{op['id']}", json={"help_enabled": True})
    assert auth_client.get(f"/api/usuarios/{op['id']}").json()["help_enabled"] is False


def test_ajuda_em_lote_atinge_so_nao_admins(auth_client):
    op = _criar_operador(auth_client)
    resp = auth_client.post("/api/usuarios/ajuda", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["alterados"] == 1
    assert auth_client.get(f"/api/usuarios/{op['id']}").json()["help_enabled"] is False
    admin = next(u for u in auth_client.get("/api/usuarios/").json() if u["username"] == "admin")
    assert admin["help_enabled"] is True


def test_ajuda_em_lote_exige_admin(auth_client, client):
    _criar_operador(auth_client)
    client.post("/login", data={"username": "op_ajuda", "password": "senha123"})
    assert client.post("/api/usuarios/ajuda", json={"enabled": False}).status_code == 403


def test_tutoriais_abre_para_quem_tem_ajuda(auth_client):
    resp = auth_client.get("/tutoriais")
    assert resp.status_code == 200
    assert "Tutoriais" in resp.text
    assert "Digitação RAAS" in resp.text


def test_tutoriais_exige_login(client):
    resp = client.get("/tutoriais", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


def test_ajuda_desativada_esconde_icones_e_tutoriais(auth_client, client):
    op = _criar_operador(auth_client, "op_sem_ajuda")
    client.post("/login", data={"username": "op_sem_ajuda", "password": "senha123"})

    # com ajuda: ícone i, menu e tutoriais
    home = client.get("/registros").text
    assert 'class="info-tip"' in home
    assert 'href="/tutoriais"' in home
    assert client.get("/tutoriais").status_code == 200

    auth_client.put(f"/api/usuarios/{op['id']}", json={"help_enabled": False})

    # sem ajuda: nada de ícone, menu nem tutoriais
    home = client.get("/registros").text
    assert 'class="info-tip"' not in home
    assert 'href="/tutoriais"' not in home
    resp = client.get("/tutoriais", follow_redirects=False)
    assert resp.status_code == 302 and resp.headers["location"] == "/"


def test_admin_sempre_tem_ajuda(auth_client):
    auth_client.post("/api/usuarios/ajuda", json={"enabled": False})
    assert 'class="info-tip"' in auth_client.get("/registros").text
    assert auth_client.get("/tutoriais").status_code == 200


def test_pagina_acesso_mostra_coluna_ajuda_para_admin(auth_client):
    _criar_operador(auth_client, "op_coluna")
    html = auth_client.get("/acesso").text
    assert "alternarAjuda" in html
    assert "ajudaEmLote" in html
