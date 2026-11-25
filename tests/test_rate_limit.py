"""
Testes do middleware de rate limiting.
"""
from sistema.rate_limit_middleware import RateLimitMiddleware


def test_login_rate_limit(client):
    """5 tentativas de login erradas devem bloquear a 6ª."""
    for i in range(5):
        resp = client.post("/login", data={"username": "admin", "password": "wrong"})
        assert resp.status_code == 200

    resp = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert resp.status_code == 429
    assert "Muitas tentativas" in resp.text


def test_login_certo_nao_gasta_o_limite(client):
    """Vários profissionais entrando pelo mesmo computador não são barrados:
    só os logins errados contam para o limite do IP."""
    for i in range(8):
        resp = client.post("/login", data={"username": "admin", "password": "admin"}, follow_redirects=False)
        assert resp.status_code == 302, f"login {i + 1} recusado"


def test_api_rate_limit_por_usuario_logado(auth_client):
    """Logado, o limite é por usuário (API_USER_LIMIT) e não pelo IP."""
    limite = RateLimitMiddleware.API_USER_LIMIT
    for i in range(limite):
        resp = auth_client.get("/api/pacientes/")
        assert resp.status_code == 200, f"requisição {i + 1} bloqueada"

    resp = auth_client.get("/api/pacientes/")
    assert resp.status_code == 429


def test_api_rate_limit_sem_login_por_ip(client):
    """Sem login, o limite continua sendo por IP (API_LIMIT)."""
    for i in range(RateLimitMiddleware.API_LIMIT):
        assert client.get("/api/pacientes/").status_code != 429
    assert client.get("/api/pacientes/").status_code == 429


def test_rate_limit_nao_afeta_get_login(client):
    """GET /login não deve ser rate limited (apenas POST)."""
    for i in range(10):
        resp = client.get("/login")
        assert resp.status_code == 200
