"""
Segurança da aplicação (LGPD, art. 46): chave de sessão, política de senha,
cabeçalhos HTTP, proteção contra CSRF e controle de sessão/primeiro acesso.

Variáveis de ambiente:
  SECRET_KEY              chave das sessões (se ausente ou igual ao valor de
                          exemplo, uma chave aleatória é gerada em secret.key)
  COOKIE_SECURE           "true" quando o acesso é por HTTPS (recomendado)
  SESSAO_INATIVIDADE_MIN  minutos sem atividade até encerrar a sessão (30)
  SESSAO_MAX_HORAS        duração máxima do cookie de sessão (12)
  TRUST_PROXY             "true" para confiar em X-Forwarded-* (ngrok, nginx...)
  ORIGENS_PERMITIDAS      hosts extras aceitos em Origin/Referer, separados por vírgula
"""
import logging
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse

from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

logger = logging.getLogger(__name__)

SECRET_KEY_EXEMPLO = "raas-caps-secret-key-change-in-production"
_RAIZ = Path(__file__).resolve().parent.parent

SENHA_MIN = 6
MSG_SENHA = f"A senha deve ter ao menos {SENHA_MIN} caracteres, com letras e números."


def _env_bool(nome: str, padrao: bool = False) -> bool:
    return os.getenv(nome, str(padrao)).strip().lower() in ("1", "true", "yes", "sim")


def confiar_proxy() -> bool:
    return _env_bool("TRUST_PROXY")


def cookie_seguro() -> bool:
    return _env_bool("COOKIE_SECURE")


def inatividade_segundos() -> int:
    return int(os.getenv("SESSAO_INATIVIDADE_MIN", "30")) * 60


def sessao_max_segundos() -> int:
    return int(float(os.getenv("SESSAO_MAX_HORAS", "12")) * 3600)


def primeiro_acesso_ativo() -> bool:
    """Só desligado pela suíte de testes (RAAS_DESATIVAR_PRIMEIRO_ACESSO=1)."""
    return not _env_bool("RAAS_DESATIVAR_PRIMEIRO_ACESSO")


def obter_secret_key() -> str:
    """Chave de sessão: do ambiente ou, se ausente/de exemplo, gerada e guardada em secret.key."""
    chave = os.getenv("SECRET_KEY", "").strip()
    if chave and chave != SECRET_KEY_EXEMPLO:
        return chave
    arquivo = _RAIZ / "secret.key"
    try:
        if arquivo.is_file():
            salva = arquivo.read_text().strip()
            if salva:
                return salva
        nova = secrets.token_urlsafe(48)
        arquivo.write_text(nova)
        try:
            os.chmod(arquivo, 0o600)
        except OSError:
            pass
        return nova
    except OSError:
        # Sem permissão de escrita: chave efêmera (sessões caem a cada reinício).
        return secrets.token_urlsafe(48)


# ── Política de senha ──

def validar_senha(senha: str) -> str:
    if len(senha) < SENHA_MIN or not re.search(r"[A-Za-z]", senha) or not re.search(r"\d", senha):
        raise ValueError(MSG_SENHA)
    return senha


# ── Cabeçalhos HTTP e proteção CSRF ──

_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'; "
    "form-action 'self'; base-uri 'self'; object-src 'none'"
)
_METODOS_ESCRITA = {"POST", "PUT", "PATCH", "DELETE"}
logger = logging.getLogger(__name__)


def _host_origem(valor: str) -> str:
    try:
        return urlparse(valor).netloc.lower()
    except ValueError:
        return ""


def _host_para_log(valor: str | None) -> str:
    if not valor:
        return "-"
    autoridade = valor.split(",", 1)[0].strip()
    try:
        parsed = urlparse(autoridade if "://" in autoridade else f"//{autoridade}")
        host = parsed.hostname
        porta = parsed.port
    except ValueError:
        return "-"
    if not host or len(host) > 253 or any(ord(caractere) < 33 or ord(caractere) == 127 for caractere in host):
        return "-"
    host = host.lower()
    if porta is None:
        return host
    return f"[{host}]:{porta}" if ":" in host else f"{host}:{porta}"


def _hosts_aceitos(request: Request) -> set[str]:
    hosts = {request.headers.get("host", "").lower()}
    if confiar_proxy():
        fwd = request.headers.get("x-forwarded-host", "")
        if fwd:
            hosts.add(fwd.split(",")[0].strip().lower())
    extras = os.getenv("ORIGENS_PERMITIDAS", "")
    hosts.update(h.strip().lower() for h in extras.split(",") if h.strip())
    hosts.discard("")
    return hosts


_LOOPBACK = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"}


def _nome_host(netloc: str) -> str:
    """Hostname sem a porta (mantém colchetes de IPv6)."""
    if netloc.startswith("["):
        return netloc.split("]")[0] + "]"
    return netloc.rsplit(":", 1)[0]


def _origem_aceita(origem: str, hosts: set[str]) -> bool:
    if origem in hosts:
        return True
    # Página servida pela própria máquina do usuário: o encaminhamento de porta
    # (VS Code/Codespaces, túnel SSH) reescreve o Host para localhost ou para o
    # domínio *.app.github.dev, mas um site externo nunca tem origem loopback.
    return _nome_host(origem) in _LOOPBACK


class SegurancaMiddleware:
    """Cabeçalhos de segurança, no-store em conteúdo dinâmico e checagem de Origin (CSRF).

    ASGI puro (e não BaseHTTPMiddleware) de propósito: o LogMiddleware grava a
    auditoria em response.background, que se perderia se outro middleware
    baseado em call_next envolvesse a resposta dele."""

    def __init__(self, app, templates):
        self.app = app
        self.templates = templates

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path
        https = request.url.scheme == "https" or (
            confiar_proxy() and request.headers.get("x-forwarded-proto", "").lower() == "https"
        )

        async def send_com_cabecalhos(message):
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                h["X-Content-Type-Options"] = "nosniff"
                h["X-Frame-Options"] = "DENY"
                # "no-referrer" faria o navegador enviar "Origin: null" em POST do próprio site
                # e a checagem CSRF recusaria o login; same-origin não vaza nada para fora.
                h["Referrer-Policy"] = "same-origin"
                h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                h["Content-Security-Policy"] = _CSP
                if not path.startswith("/static"):
                    # Dados pessoais não devem ficar em cache do navegador/proxy.
                    h["Cache-Control"] = "no-store"
                    h["Pragma"] = "no-cache"
                if https:
                    h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            await send(message)

        if request.method in _METODOS_ESCRITA:
            origem = request.headers.get("origin") or request.headers.get("referer")
            hosts_aceitos = _hosts_aceitos(request)
            if origem and not _origem_aceita(_host_origem(origem), hosts_aceitos):
                logger.warning(
                    "[CSRF] Origem recusada: metodo=%s caminho=%s origin_host=%s request_host=%s forwarded_host=%s trust_proxy=%s",
                    request.method,
                    request.url.path,
                    _host_para_log(origem),
                    _host_para_log(request.headers.get("host")),
                    _host_para_log(request.headers.get("x-forwarded-host")) if confiar_proxy() else "-",
                    confiar_proxy(),
                )
                if "text/html" in request.headers.get("accept", "").lower():
                    resposta = self.templates.TemplateResponse(request, "erro_csrf.html", status_code=403)
                else:
                    resposta = JSONResponse(
                        status_code=403,
                        content={"detail": "Requisição de origem não permitida"},
                    )
                await resposta(scope, receive, send_com_cabecalhos)
                return

        await self.app(scope, receive, send_com_cabecalhos)


# ── Controle de sessão, usuário ativo e primeiro acesso ──

_ISENTOS_PREFIXOS = ("/static", "/privacidade", "/primeiro-acesso", "/api/lgpd/primeiro-acesso")
_ISENTOS = {"/login", "/logout", "/favicon.ico", "/health"}


class AcessoMiddleware(BaseHTTPMiddleware):
    """Para sessões autenticadas: expira por inatividade, derruba usuários
    desativados/removidos e exige troca de senha + aceite do termo.

    Deve ser adicionado ANTES do SessionMiddleware (fica por dentro dele)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in _ISENTOS or path.startswith(_ISENTOS_PREFIXOS):
            return await call_next(request)

        sessao = request.session
        user_id = sessao.get("user_id")
        if not user_id:
            return await call_next(request)

        agora = time.time()
        ultima = sessao.get("ultima_atividade")
        if ultima is not None and agora - float(ultima) > inatividade_segundos():
            sessao.clear()
            return await call_next(request)

        from database import SessionLocal
        from usuario.usuario_service import UsuarioService
        from lgpd.lgpd_service import LgpdService

        db = SessionLocal()
        try:
            user = UsuarioService.obter_por_id(db, user_id)
            if not user or not user.active:
                sessao.clear()
                return await call_next(request)
            pendente = primeiro_acesso_ativo() and LgpdService.primeiro_acesso_pendente(user)
        finally:
            db.close()

        sessao["ultima_atividade"] = agora

        if pendente:
            if path.startswith("/api"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Primeiro acesso pendente: troque a senha e aceite o termo de uso",
                             "codigo": "PRIMEIRO_ACESSO"},
                )
            return RedirectResponse(url="/primeiro-acesso", status_code=302)
        return await call_next(request)
