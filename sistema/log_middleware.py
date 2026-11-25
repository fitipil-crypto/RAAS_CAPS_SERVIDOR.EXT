"""
Middleware para log automático de todas as requisições.
NÃO registra endereços IP.
"""
import re
import time
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from database import SessionLocal
from sistema.log_service import LogService

# Ações automáticas por método HTTP
_METHOD_ACTIONS = {
    "POST": "CREATE",
    "PUT": "UPDATE",
    "PATCH": "UPDATE",
    "DELETE": "DELETE",
    "GET": "VIEW",
}

# Mapeia paths para resource_type
_PATH_RESOURCES = [
    ("/api/pacientes", "paciente"),
    ("/api/profissionais", "profissional"),
    ("/api/procedimentos", "procedimento"),
    ("/api/registros", "registro"),
    ("/api/usuarios", "usuario"),
    ("/api/configuracoes", "config"),
    ("/api/importacao", "importacao"),
    ("/api/exportacao", "exportacao"),
    ("/api/backup", "backup"),
    ("/api/relatorios", "relatorio"),
    ("/api/roadmap", "roadmap"),
    ("/api/lgpd", "lgpd"),
]

# Rotas que entregam dados pessoais em lote ou de um titular: auditadas como EXPORT.
_EXPORT_PATHS = ("/api/exportacao/raas", "/api/backup/download", "/api/pacientes/exportar",
                 "/api/relatorios/impressao/exportar")
_TITULAR_RE = re.compile(r"^/api/lgpd/titulares/([^/]+)/")
# Página de detalhe do paciente (HTML): abrir a ficha é um acesso a dado sensível.
_FICHA_RE = re.compile(r"^/pacientes/([^/]+)$")


def _get_resource_type(path: str) -> str | None:
    for prefix, rtype in _PATH_RESOURCES:
        if path.startswith(prefix):
            return rtype
    return None


class LogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)

        method = request.method
        path = request.url.path

        # Ignora arquivos estáticos e health checks
        if path.startswith("/static") or path in ("/favicon.ico", "/health"):
            return response

        # Ignora GET em páginas HTML (frontend) — muito ruidoso
        # Loga apenas API calls e métodos modificadores
        is_api = path.startswith("/api")
        is_modifier = method in ("POST", "PUT", "PATCH", "DELETE")
        is_auth = path in ("/login", "/logout")
        ficha = _FICHA_RE.match(path) if method == "GET" and response.status_code == 200 else None

        if not (is_api or is_auth or ficha or (is_modifier and not path.startswith("/static"))):
            return response

        # Determinar ação
        if path == "/login" and method == "POST":
            action = "LOGIN"
        elif path == "/logout":
            action = "LOGOUT"
        elif is_api:
            action = _METHOD_ACTIONS.get(method, "VIEW")
        else:
            action = _METHOD_ACTIONS.get(method, "VIEW")
        if method == "GET" and (path.startswith(_EXPORT_PATHS) or (_TITULAR_RE.match(path) and path.endswith("/exportar"))):
            action = "EXPORT"

        resource_type = _get_resource_type(path)

        # Extrair resource_id do path se houver (ex: /api/pacientes/123)
        resource_id = None
        titular = _TITULAR_RE.match(path)
        if ficha:
            resource_type, resource_id = "paciente", ficha.group(1)
        elif titular:
            resource_type, resource_id = "paciente", titular.group(1)
        elif resource_type:
            parts = path.split("/")
            if len(parts) >= 4 and parts[-1]:
                resource_id = parts[-1]

        # Obter usuário da sessão
        try:
            user_id = request.session.get("user_id")
        except Exception:
            user_id = None

        status_code = response.status_code
        # A unidade ativa é lida agora, dentro da requisição: o log roda depois,
        # em background, quando o escopo já não existe mais (ver LogService).
        unidade_id = getattr(request.state, "unidade_id", None)

        def _registrar_log():
            # Roda em background apos a resposta ser enviada ao navegador,
            # para nao segurar a requisicao do usuario esperando o commit
            # (e a leitura de username) no banco.
            username = None
            if user_id:
                try:
                    from usuario.usuario_service import UsuarioService
                    db = SessionLocal()
                    try:
                        user = UsuarioService.obter_por_id(db, user_id)
                        if user:
                            username = user.username
                    finally:
                        db.close()
                except Exception:
                    pass

            try:
                db = SessionLocal()
                try:
                    LogService.registrar(
                        db,
                        action=action,
                        user_id=user_id,
                        username=username,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        method=method,
                        path=path,
                        status_code=status_code,
                        details=f"Duracao: {duration_ms}ms",
                        unidade_id=unidade_id,
                    )
                finally:
                    db.close()
            except Exception:
                pass  # Não falhar a requisição por erro de log

        response.background = BackgroundTask(_registrar_log)
        return response
