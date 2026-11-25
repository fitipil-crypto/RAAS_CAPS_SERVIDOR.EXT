"""
Testes de LGPD e segurança: primeiro acesso, política de senha, bloqueio,
sessão, cabeçalhos, CSRF, trilha de auditoria, direitos do titular e incidentes.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from sistema import seguranca
from sistema.log_model import LogSistema
from usuario.usuario_schema import UsuarioCriar
from usuario.usuario_service import UsuarioService, MAX_FALHAS_LOGIN


def _utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def primeiro_acesso_ligado(monkeypatch):
    monkeypatch.delenv("RAAS_DESATIVAR_PRIMEIRO_ACESSO", raising=False)


def _criar_usuario(db, username, role="operador", senha="senha12345"):
    u = UsuarioService.criar(db, UsuarioCriar(username=username, name=username.upper(), role=role, password=senha))
    u.must_change_password = False
    u.termo_versao = __import__("lgpd.lgpd_service", fromlist=["TERMO_VERSAO"]).TERMO_VERSAO
    db.commit()
    return u


def _logar(username, senha="senha12345"):
    c = TestClient(app)
    c.__enter__()
    c.post("/login", data={"username": username, "password": senha})
    return c


def _logs(db, action, resource_type=None):
    db.expire_all()
    q = db.query(LogSistema).filter(LogSistema.action == action)
    if resource_type:
        q = q.filter(LogSistema.resource_type == resource_type)
    return q.all()


@pytest.fixture
def paciente_com_atendimento(auth_client):
    pac = auth_client.post("/api/pacientes/", json={
        "name": "MARIA TITULAR", "cpf": "52998224725", "cns": "700000000000099",
        "birth_date": "1985-06-15", "gender": "F", "mother_name": "ANA", "phone": "11999998888",
        "email": "maria@example.com", "address": "RUA A", "city": "SAO PAULO", "state": "SP",
        "municipality_code": "355030", "cid_main": "F200",
    }).json()
    prof = auth_client.post("/api/profissionais/", json={"name": "PROF", "cns": "700000000000001", "cbo": "225125"}).json()
    proc = auth_client.post("/api/procedimentos/", json={"code": "0301080020", "name": "ATENDIMENTO INDIVIDUAL"}).json()
    hoje = datetime.now()
    reg = auth_client.post("/api/registros/", json={
        "patient_id": pac["id"], "professional_id": prof["id"], "procedure_id": proc["id"],
        "service_month": hoje.strftime("%Y-%m"), "service_date": hoje.strftime("%Y-%m-%d"),
        "notes": "Maria relatou conflito familiar",
    })
    assert reg.status_code == 200, reg.text
    return pac


# ── Primeiro acesso: troca de senha + termo ──

def test_primeiro_acesso_bloqueia_ate_trocar_senha_e_aceitar_termo(client, db_session, auth_client, primeiro_acesso_ligado):
    # auth_client logou como admin/admin (must_change_password) com o gate desligado;
    # agora, com o gate ligado, o admin padrão é barrado.
    admin = UsuarioService.obter_por_username(db_session, "admin")
    assert admin.must_change_password is True

    resp = auth_client.get("/pacientes", follow_redirects=False)
    assert resp.status_code == 302 and resp.headers["location"] == "/primeiro-acesso"
    api = auth_client.get("/api/pacientes/")
    assert api.status_code == 403 and api.json()["codigo"] == "PRIMEIRO_ACESSO"
    assert auth_client.get("/primeiro-acesso").status_code == 200

    # senha fraca é recusada
    fraca = auth_client.post("/api/lgpd/primeiro-acesso", json={
        "current_password": "admin", "new_password": "abc", "confirm_password": "abc", "aceite": True})
    assert fraca.status_code == 422
    # sem aceite do termo
    sem_aceite = auth_client.post("/api/lgpd/primeiro-acesso", json={
        "current_password": "admin", "new_password": "NovaSenha123", "confirm_password": "NovaSenha123", "aceite": False})
    assert sem_aceite.status_code == 400
    # senha atual errada
    errada = auth_client.post("/api/lgpd/primeiro-acesso", json={
        "current_password": "xxx", "new_password": "NovaSenha123", "confirm_password": "NovaSenha123", "aceite": True})
    assert errada.status_code == 400

    ok = auth_client.post("/api/lgpd/primeiro-acesso", json={
        "current_password": "admin", "new_password": "NovaSenha123", "confirm_password": "NovaSenha123", "aceite": True})
    assert ok.status_code == 200
    db_session.expire_all()
    admin = UsuarioService.obter_por_username(db_session, "admin")
    assert admin.must_change_password is False
    assert admin.termo_versao and admin.termo_aceito_em
    assert auth_client.get("/api/pacientes/").status_code == 200
    assert _logs(db_session, "TERMO")

    # a nova senha vale e a antiga não
    assert UsuarioService.autenticar(db_session, "admin", "NovaSenha123")
    assert UsuarioService.autenticar(db_session, "admin", "admin") is None


def test_usuario_novo_criado_pelo_admin_precisa_trocar_senha(db_session):
    u = UsuarioService.criar(db_session, UsuarioCriar(username="novo", name="Novo", password="provisoria1"))
    assert u.must_change_password is True


def test_senha_do_admin_padrao_antigo_e_marcada_para_troca(db_session):
    UsuarioService.inicializar_admin_padrao(db_session)
    admin = UsuarioService.obter_por_username(db_session, "admin")
    admin.must_change_password = False
    db_session.commit()
    assert UsuarioService.exigir_troca_de_senha_padrao(db_session) == 1
    db_session.refresh(admin)
    assert admin.must_change_password is True


# ── Política de senha ──

@pytest.mark.parametrize("senha", ["curt1", "somenteletras", "123456789"])
def test_politica_de_senha_recusa_senhas_fracas(auth_client, senha):
    resp = auth_client.post("/api/usuarios/", json={
        "username": "fraco", "name": "Fraco", "role": "operador", "password": senha})
    assert resp.status_code == 422


# ── Bloqueio por tentativas ──

def test_conta_bloqueia_apos_tentativas_erradas(db_session):
    _criar_usuario(db_session, "alvo")
    for _ in range(MAX_FALHAS_LOGIN):
        assert UsuarioService.autenticar(db_session, "alvo", "errada123") is None
    user = UsuarioService.obter_por_username(db_session, "alvo")
    assert UsuarioService.esta_bloqueado(user)
    # mesmo com a senha certa, continua bloqueada
    assert UsuarioService.autenticar(db_session, "alvo", "senha12345") is None
    # expirado o bloqueio, volta a logar e zera o contador
    user.locked_until = _utc() - timedelta(minutes=1)
    db_session.commit()
    assert UsuarioService.autenticar(db_session, "alvo", "senha12345")
    db_session.refresh(user)
    assert not user.failed_logins and user.locked_until is None


def test_login_nao_revela_se_conta_esta_bloqueada(client, db_session):
    _criar_usuario(db_session, "alvo")
    for _ in range(MAX_FALHAS_LOGIN):
        UsuarioService.autenticar(db_session, "alvo", "errada123")
    bloqueada = client.post("/login", data={"username": "alvo", "password": "senha12345"})
    inexistente = client.post("/login", data={"username": "fantasma", "password": "senha12345"})
    assert bloqueada.status_code == 200 and "bloqueada" in bloqueada.text
    assert "bloqueada" in inexistente.text  # mesma mensagem para ambos
    assert "logout" not in bloqueada.text.lower()


# ── Sessão ──

def test_sessao_expira_por_inatividade(db_session, monkeypatch):
    _criar_usuario(db_session, "ocioso")
    c = _logar("ocioso")
    assert c.get("/api/pacientes/").status_code == 200
    monkeypatch.setenv("SESSAO_INATIVIDADE_MIN", "0")
    assert c.get("/api/pacientes/").status_code == 401


def test_usuario_desativado_perde_a_sessao_na_hora(db_session, auth_client):
    _criar_usuario(db_session, "demitido")
    c = _logar("demitido")
    assert c.get("/api/pacientes/").status_code == 200
    uid = UsuarioService.obter_por_username(db_session, "demitido").id
    assert auth_client.put(f"/api/usuarios/{uid}", json={"active": False}).status_code == 200
    assert c.get("/api/pacientes/").status_code == 401


def test_login_gera_nova_sessao(client, db_session):
    _criar_usuario(db_session, "sessao")
    client.get("/login")
    client.post("/login", data={"username": "sessao", "password": "senha12345"})
    assert client.get("/api/pacientes/").status_code == 200


# ── Cabeçalhos e CSRF ──

def test_cabecalhos_de_seguranca(auth_client):
    resp = auth_client.get("/api/pacientes/")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]
    assert resp.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in resp.headers


def test_hsts_atras_de_proxy_https(auth_client, monkeypatch):
    monkeypatch.setenv("TRUST_PROXY", "true")
    resp = auth_client.get("/api/pacientes/", headers={"x-forwarded-proto": "https"})
    assert "strict-transport-security" in resp.headers


def test_estaticos_podem_ser_cacheados(client):
    resp = client.get("/static/css/style.css")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") != "no-store"


def test_csrf_recusa_origem_diferente(auth_client):
    resp = auth_client.post("/api/pacientes/", json={"name": "X"}, headers={"origin": "https://evil.example"})
    assert resp.status_code == 403


def test_csrf_aceita_mesma_origem_e_origem_permitida(auth_client, monkeypatch):
    ok = auth_client.post("/api/pacientes/", json={"name": "X"}, headers={"origin": "http://testserver"})
    assert ok.status_code == 200
    monkeypatch.setenv("ORIGENS_PERMITIDAS", "meu.dominio.com.br")
    ok2 = auth_client.post("/api/pacientes/", json={"name": "Y"}, headers={"origin": "https://meu.dominio.com.br"})
    assert ok2.status_code == 200


def test_login_tambem_checa_origem(client, caplog):
    with caplog.at_level("WARNING", logger=seguranca.__name__):
        resp = client.post("/login", data={"username": "a", "password": "b"}, headers={"origin": "https://evil.example"})

    assert resp.status_code == 403
    assert "origin_host=evil.example" in caplog.text
    assert "request_host=testserver" in caplog.text


def test_login_aceita_host_publico_explicitamente_permitido(client, monkeypatch):
    monkeypatch.setenv("ORIGENS_PERMITIDAS", "caps.example.com")

    resp = client.post(
        "/login",
        data={"username": "usuario-publico", "password": "senha-errada"},
        headers={"origin": "https://caps.example.com"},
    )

    assert resp.status_code == 200


def test_log_de_referer_recusado_nao_expoe_caminho_ou_query(client, caplog):
    with caplog.at_level("WARNING", logger=seguranca.__name__):
        resp = client.post(
            "/login",
            data={"username": "a", "password": "b"},
            headers={"referer": "https://evil.example/login?token=segredo"},
        )

    assert resp.status_code == 403
    assert "origin_host=evil.example" in caplog.text
    assert "token=segredo" not in caplog.text


def test_x_forwarded_for_so_vale_com_trust_proxy(client, monkeypatch):
    # Sem TRUST_PROXY, trocar o cabeçalho não escapa do limite de tentativas
    for i in range(5):
        client.post("/login", data={"username": "x", "password": "y"}, headers={"x-forwarded-for": f"10.0.0.{i}"})
    resp = client.post("/login", data={"username": "x", "password": "y"}, headers={"x-forwarded-for": "10.9.9.9"})
    assert resp.status_code == 429


def test_secret_key_gerada_quando_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(seguranca, "_RAIZ", tmp_path)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    k1 = seguranca.obter_secret_key()
    assert len(k1) >= 40 and k1 != seguranca.SECRET_KEY_EXEMPLO
    assert (tmp_path / "secret.key").read_text() == k1
    assert seguranca.obter_secret_key() == k1  # estável entre reinícios
    monkeypatch.setenv("SECRET_KEY", seguranca.SECRET_KEY_EXEMPLO)  # valor de exemplo é ignorado
    assert seguranca.obter_secret_key() == k1
    monkeypatch.setenv("SECRET_KEY", "minha-chave")
    assert seguranca.obter_secret_key() == "minha-chave"


# ── Política de privacidade ──

def test_politica_de_privacidade_e_publica(client, auth_client):
    auth_client.put("/api/lgpd/config", json={
        "controlador_nome": "CAPS TESTE", "encarregado_nome": "Dra. DPO", "encarregado_email": "dpo@caps.gov.br"})
    resp = client.get("/privacidade")
    assert resp.status_code == 200
    assert "CAPS TESTE" in resp.text and "dpo@caps.gov.br" in resp.text
    assert "Art. 18" in resp.text or "art. 18" in resp.text


def test_config_lgpd_so_admin_altera(db_session):
    _criar_usuario(db_session, "coord", role="coordenador")
    c = _logar("coord")
    assert c.get("/api/lgpd/config").status_code == 200
    assert c.put("/api/lgpd/config", json={"encarregado_nome": "X"}).status_code == 403


# ── Auditoria ──

def test_abrir_ficha_do_paciente_e_auditado(auth_client, db_session, paciente_com_atendimento):
    pid = paciente_com_atendimento["id"]
    assert auth_client.get(f"/pacientes/{pid}").status_code == 200
    auth_client.get(f"/api/pacientes/{pid}")
    views = [l for l in _logs(db_session, "VIEW", "paciente") if l.resource_id == pid]
    assert len(views) >= 2
    assert all(l.username == "admin" for l in views)


def test_exportacoes_sao_auditadas_como_export(auth_client, db_session, paciente_com_atendimento):
    pid = paciente_com_atendimento["id"]
    assert auth_client.get(f"/api/lgpd/titulares/{pid}/exportar").status_code == 200
    assert auth_client.get("/api/backup/download").status_code == 200
    assert auth_client.get("/api/pacientes/exportar/csv").status_code == 200
    paths = {l.path for l in _logs(db_session, "EXPORT")}
    assert f"/api/lgpd/titulares/{pid}/exportar" in paths
    assert "/api/backup/download" in paths and "/api/pacientes/exportar/csv" in paths
    titular = [l for l in _logs(db_session, "EXPORT") if l.path.endswith("/exportar")][0]
    assert titular.resource_type == "paciente" and titular.resource_id == pid


def test_logs_recentes_nao_podem_ser_apagados(auth_client, db_session):
    auth_client.get("/api/pacientes/")
    antes = db_session.query(LogSistema).count()
    resp = auth_client.delete("/api/logs/limpar?dias=0")
    assert resp.status_code == 200 and resp.json()["removidos"] == 0
    assert db_session.query(LogSistema).count() >= antes


# ── Direitos do titular ──

def test_exportar_dados_do_titular(auth_client, paciente_com_atendimento):
    pid = paciente_com_atendimento["id"]
    resp = auth_client.get(f"/api/lgpd/titulares/{pid}/exportar")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    corpo = resp.json()
    assert corpo["titular"]["name"] == "MARIA TITULAR" and corpo["titular"]["cpf"] == "52998224725"
    assert len(corpo["atendimentos"]) == 1
    assert corpo["atendimentos"][0]["procedimento_codigo"] == "0301080020"


def test_exportar_titular_inexistente_404(auth_client):
    assert auth_client.get("/api/lgpd/titulares/nao-existe/exportar").status_code == 404


def test_operador_nao_exporta_nem_anonimiza(db_session, paciente_com_atendimento):
    _criar_usuario(db_session, "op")
    c = _logar("op")
    pid = paciente_com_atendimento["id"]
    assert c.get(f"/api/lgpd/titulares/{pid}/exportar").status_code == 403
    assert c.post(f"/api/lgpd/titulares/{pid}/anonimizar", json={"confirm": "ANONIMIZAR"}).status_code == 403
    assert c.get("/api/lgpd/solicitacoes").status_code == 403
    assert c.get("/api/lgpd/incidentes").status_code == 403
    assert c.get("/lgpd", follow_redirects=False).status_code == 302


def test_coordenador_exporta_mas_nao_anonimiza(db_session, paciente_com_atendimento):
    _criar_usuario(db_session, "coord", role="coordenador")
    c = _logar("coord")
    pid = paciente_com_atendimento["id"]
    assert c.get(f"/api/lgpd/titulares/{pid}/exportar").status_code == 200
    assert c.post(f"/api/lgpd/titulares/{pid}/anonimizar", json={"confirm": "ANONIMIZAR"}).status_code == 403
    assert c.get("/lgpd").status_code == 200


def test_anonimizar_paciente(auth_client, db_session, paciente_com_atendimento):
    pid = paciente_com_atendimento["id"]
    assert auth_client.post(f"/api/lgpd/titulares/{pid}/anonimizar", json={"confirm": "sim"}).status_code == 400

    resp = auth_client.post(f"/api/lgpd/titulares/{pid}/anonimizar", json={"confirm": "ANONIMIZAR"})
    assert resp.status_code == 200
    p = auth_client.get(f"/api/pacientes/{pid}").json()
    assert p["name"].startswith("PACIENTE ANONIMIZADO")
    for campo in ("cpf", "cns", "mother_name", "phone", "email", "address"):
        assert p[campo] is None, campo
    assert p["birth_date"] == "1985-01-01"       # só o ano
    assert p["cid_main"] == "F200" and p["municipality_code"] == "355030"  # mantém dado estatístico
    assert p["anonimizado"] is True and p["anonimizado_em"]
    # dados identificáveis também saem do atendimento e a busca não acha mais o titular
    regs = auth_client.get("/api/registros/").json()
    assert all(not r.get("notes") for r in regs)
    assert auth_client.get("/api/pacientes/?search=MARIA").json() == []
    assert auth_client.post(f"/api/lgpd/titulares/{pid}/anonimizar", json={"confirm": "ANONIMIZAR"}).status_code == 400
    assert [l for l in _logs(db_session, "ANONIMIZAR") if l.resource_id == pid]


def test_anonimizar_resolve_solicitacao_vinculada(auth_client, paciente_com_atendimento):
    pid = paciente_com_atendimento["id"]
    sol = auth_client.post("/api/lgpd/solicitacoes", json={
        "paciente_id": pid, "titular_nome": "MARIA TITULAR", "tipo": "anonimizacao"}).json()
    auth_client.post(f"/api/lgpd/titulares/{pid}/anonimizar", json={"confirm": "ANONIMIZAR", "solicitacao_id": sol["id"]})
    lista = auth_client.get("/api/lgpd/solicitacoes").json()
    assert lista[0]["status"] == "atendida" and lista[0]["resolvida_por"] == "admin"
    assert lista[0]["titular_nome"] == "MARIA TITULAR"  # nome do solicitante preservado


def test_base_legal_do_paciente(auth_client):
    p = auth_client.post("/api/pacientes/", json={"name": "A"}).json()
    assert p["base_legal"] == "tutela_saude"
    ok = auth_client.put(f"/api/pacientes/{p['id']}", json={"base_legal": "consentimento"})
    assert ok.json()["base_legal"] == "consentimento"
    assert auth_client.put(f"/api/pacientes/{p['id']}", json={"base_legal": "inventada"}).status_code == 422


# ── Solicitações e incidentes ──

def test_solicitacao_tem_prazo_de_15_dias_e_pode_ser_resolvida(auth_client):
    resp = auth_client.post("/api/lgpd/solicitacoes", json={
        "titular_nome": "JOAO", "tipo": "acesso", "descricao": "quer cópia"})
    assert resp.status_code == 200
    sol = resp.json()
    prazo = datetime.fromisoformat(sol["prazo_em"])
    assert 14 <= (prazo - _utc()).days <= 15
    assert sol["status"] == "aberta" and sol["atrasada"] is False

    fim = auth_client.put(f"/api/lgpd/solicitacoes/{sol['id']}", json={"status": "atendida", "resposta": "enviado"})
    assert fim.json()["status"] == "atendida" and fim.json()["resolvida_em"]
    assert auth_client.put(f"/api/lgpd/solicitacoes/{sol['id']}", json={"status": "qualquer"}).status_code == 422
    assert auth_client.put("/api/lgpd/solicitacoes/nao-existe", json={"status": "negada"}).status_code == 404
    assert auth_client.post("/api/lgpd/solicitacoes", json={"titular_nome": "X", "tipo": "invalido"}).status_code == 422
    assert auth_client.post("/api/lgpd/solicitacoes", json={
        "titular_nome": "X", "tipo": "acesso", "paciente_id": "nao-existe"}).status_code == 404


def test_solicitacao_vencida_aparece_como_atrasada(auth_client, db_session):
    sol = auth_client.post("/api/lgpd/solicitacoes", json={"titular_nome": "ANA", "tipo": "correcao"}).json()
    from lgpd.lgpd_model import SolicitacaoTitular
    db_session.query(SolicitacaoTitular).filter_by(id=sol["id"]).update({"prazo_em": _utc() - timedelta(days=1)})
    db_session.commit()
    atual = auth_client.get("/api/lgpd/solicitacoes?status=aberta").json()[0]
    assert atual["atrasada"] is True


def test_registro_de_incidente(auth_client):
    resp = auth_client.post("/api/lgpd/incidentes", json={
        "ocorrido_em": "2026-10-01", "descricao": "Notebook perdido", "risco": "alto",
        "dados_afetados": "cadastro de pacientes", "titulares_afetados": "120",
        "medidas": "Senhas trocadas", "comunicado_anpd": True})
    assert resp.status_code == 200
    lista = auth_client.get("/api/lgpd/incidentes").json()
    assert lista[0]["descricao"] == "Notebook perdido" and lista[0]["registrado_por"] == "admin"
    assert auth_client.post("/api/lgpd/incidentes", json={
        "ocorrido_em": "01/10/2026", "descricao": "x"}).status_code == 422
    assert auth_client.post("/api/lgpd/incidentes", json={
        "ocorrido_em": "2026-10-01", "descricao": "x", "risco": "enorme"}).status_code == 422


def test_pagina_lgpd_para_admin(auth_client):
    resp = auth_client.get("/lgpd")
    assert resp.status_code == 200
    assert "Painel de conformidade" in resp.text and "Encarregado" in resp.text


def test_referrer_policy_permite_origin_em_post_do_proprio_site(client):
    # "no-referrer" faz o navegador mandar "Origin: null" no POST do login e a checagem CSRF recusa.
    resp = client.get("/login")
    assert resp.headers["referrer-policy"] == "same-origin"


def test_origin_null_continua_recusado(client):
    resp = client.post("/login", data={"username": "a", "password": "b"}, headers={"origin": "null"})
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Requisição de origem não permitida"}


def test_origin_null_mostra_pagina_html_para_navegador(client):
    resp = client.post(
        "/login",
        data={"username": "a", "password": "b"},
        headers={"origin": "null", "accept": "text/html"},
    )

    assert resp.status_code == 403
    assert resp.headers["content-type"].startswith("text/html")
    assert "Este envio foi bloqueado por segurança" in resp.text
    assert 'href="/login"' in resp.text
    assert resp.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in resp.headers["content-security-policy"]


def test_csrf_para_cliente_json_mantem_resposta_json(client):
    resp = client.post(
        "/login",
        data={"username": "a", "password": "b"},
        headers={"origin": "null", "accept": "application/json"},
    )

    assert resp.status_code == 403
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"detail": "Requisição de origem não permitida"}


def test_login_aceita_origem_na_porta_8001(client):
    resp = client.post(
        "/login",
        data={"username": "a", "password": "b"},
        headers={"origin": "http://localhost:8001", "host": "localhost:8001"},
    )
    assert resp.status_code == 200
