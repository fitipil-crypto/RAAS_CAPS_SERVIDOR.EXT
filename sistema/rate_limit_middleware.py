"""
Middleware de rate limiting para proteção contra brute force.

Estratégia: sliding window em memória.
- Login: 5 tentativas ERRADAS por 60 segundos (IP). Login certo não conta, para
  que vários profissionais entrem pelo mesmo computador; a conta ainda é
  bloqueada após 5 erros seguidos (UsuarioService).
- API de quem está logado: 300 requisições por 60 segundos (usuário).
- API sem login: 60 requisições por 60 segundos (IP).
"""
import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from sistema.seguranca import confiar_proxy

_login_hits: dict[str, list[float]] = defaultdict(list)
_api_hits: dict[str, list[float]] = defaultdict(list)


def reset_rate_limits():
    """Limpa contadores de rate limiting (para testes)."""
    _login_hits.clear()
    _api_hits.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    LOGIN_LIMIT = 5
    LOGIN_WINDOW = 60
    API_LIMIT = 60
    API_USER_LIMIT = 300
    API_WINDOW = 60

    def __init__(self, app):
        super().__init__(app)

    def _client_ip(self, request: Request) -> str:
        # X-Forwarded-For só vale atrás de um proxy confiável (TRUST_PROXY=true);
        # caso contrário qualquer cliente poderia forjá-lo e fugir do limite.
        forwarded = request.headers.get("x-forwarded-for", "") if confiar_proxy() else ""
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _check(self, store: dict, key: str, limit: int, window: int, registrar: bool = True) -> tuple[bool, int]:
        now = time.time()
        hits = store[key]
        cutoff = now - window
        while hits and hits[0] < cutoff:
            hits.pop(0)
        if len(hits) >= limit:
            retry = int(window - (now - hits[0]))
            return False, max(retry, 1)
        if registrar:
            hits.append(now)
        return True, 0

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        ip = self._client_ip(request)

        if path == "/login" and method == "POST":
            allowed, retry = self._check(_login_hits, ip, self.LOGIN_LIMIT, self.LOGIN_WINDOW, registrar=False)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Muitas tentativas. Tente novamente em {retry}s."},
                    headers={"Retry-After": str(retry)},
                )
            response = await call_next(request)
            if response.status_code != 302:  # 302 = login certo (redireciona para o início)
                _login_hits[ip].append(time.time())
            return response

        if path.startswith("/api"):
            # Logado: limite por usuário (vários profissionais podem dividir o
            # mesmo computador/IP). Requer o SessionMiddleware por fora deste.
            user_id = request.scope.get("session", {}).get("user_id")
            if user_id:
                allowed, retry = self._check(_api_hits, f"user:{user_id}", self.API_USER_LIMIT, self.API_WINDOW)
            else:
                allowed, retry = self._check(_api_hits, ip, self.API_LIMIT, self.API_WINDOW)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Limite de requisições excedido. Tente em {retry}s."},
                    headers={"Retry-After": str(retry)},
                )

        return await call_next(request)
