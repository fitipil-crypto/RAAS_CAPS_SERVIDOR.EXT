"""
RAAS-CAPS - Sistema de Gestão de Atendimentos Psicossociais
Aplicação FastAPI modular baseada na arquitetura do projeto Fluxi.
"""
import importlib
import logging
import os
import sys

# Rodado direto por um Python sem as dependências (ex.: o /usr/bin/python3 do
# Codespace, quando é o interpretador selecionado no VS Code): reexecuta com o
# Python do projeto em vez de falhar no import.
if __name__ == "__main__":
    try:
        import fastapi  # noqa: F401
    except ModuleNotFoundError:
        _raiz = os.path.dirname(os.path.abspath(__file__))
        for _python in (
            os.path.join(_raiz, ".venv", "bin", "python"),
            os.path.join(_raiz, ".venv", "Scripts", "python.exe"),
            "/usr/local/python/current/bin/python3",
        ):
            if os.path.exists(_python) and os.path.realpath(_python) != os.path.realpath(sys.executable):
                os.execv(_python, [_python, os.path.abspath(__file__), *sys.argv[1:]])
        raise

# Carrega o .env (SECRET_KEY, COOKIE_SECURE, TRUST_PROXY...) sem sobrescrever o ambiente real.
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from database import criar_tabelas, engine, SessionLocal
from logging_config import configurar_logging
from usuario.usuario_service import UsuarioService
from config.config_service import ConfigService
from sistema.log_middleware import LogMiddleware
from sistema.rate_limit_middleware import RateLimitMiddleware
from sistema import seguranca
from sistema.seguranca import SegurancaMiddleware, AcessoMiddleware
from sistema.templates import templates
from roadmap.roadmap_service import RoadmapService
from unidade.unidade_middleware import UnidadeMiddleware
from unidade.unidade_service import UnidadeService

logger = configurar_logging(debug=os.getenv("DEBUG", "false").lower() == "true")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando RAAS-CAPS...")
    criar_tabelas()
    db = SessionLocal()
    try:
        UsuarioService.inicializar_admin_padrao(db)
        UsuarioService.exigir_troca_de_senha_padrao(db)
        ConfigService.inicializar_config_padrao(db)
        RoadmapService.inicializar_seeds(db)
        # Servidor multiunidade: um banco que vem da versão de um só CAPS
        # ganha aqui a sua primeira unidade, a partir das Configurações do
        # estabelecimento. Sem isso os dados existentes ficariam sem unidade.
        UnidadeService.inicializar_unidade_padrao(db)
        logger.info("RAAS-CAPS iniciado com sucesso.")
    finally:
        db.close()
    # Backup automático: na versão local, uma thread grava em pasta compartilhada
    # do Windows. No servidor isso não se aplica — o backup é do PostgreSQL, por
    # cron (deploy/backup_postgres.sh). BACKUP_AUTO_LOCAL=true religa o agendador
    # para quem rodar esta cópia em rede local com SQLite.
    if os.getenv("BACKUP_AUTO_LOCAL", "false").lower() == "true":
        from backup.backup_auto_service import iniciar_agendador
        iniciar_agendador()
    else:
        logger.info("Agendador de backup em rede local desligado (use deploy/backup_postgres.sh).")
    yield


app = FastAPI(
    title="RAAS-CAPS Servidor",
    version="5.0-servidor",
    description=(
        "Sistema de Gestão de Atendimentos Psicossociais — edição servidor, "
        "multiunidade (7 modalidades de CAPS)"
    ),
    lifespan=lifespan,
)

# Ordem: o último adicionado é o mais externo. O AcessoMiddleware e o
# RateLimitMiddleware precisam ficar por dentro do SessionMiddleware (usam a sessão).
app.add_middleware(AcessoMiddleware)
app.add_middleware(RateLimitMiddleware)
# Define a unidade (CAPS) ativa da requisição e, com ela, o escopo dos dados.
# Precisa ficar por dentro do SessionMiddleware (lê a unidade escolhida na
# sessão) e por fora dos dois de cima, para que qualquer consulta que eles
# façam já esteja filtrada pela unidade.
app.add_middleware(UnidadeMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=seguranca.obter_secret_key(),
    session_cookie="raas_caps_session",
    max_age=seguranca.sessao_max_segundos(),
    same_site="lax",
    https_only=seguranca.cookie_seguro(),
)

os.makedirs("static", exist_ok=True)
os.makedirs("uploads", exist_ok=True)
os.makedirs("exports", exist_ok=True)

class _StaticSemCache(StaticFiles):
    """Sempre revalida (ETag -> 304), então não precisa de ?v= nos assets."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


class _SemAccessLogEstatico(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/static/" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(_SemAccessLogEstatico())

app.mount("/static", _StaticSemCache(directory="static"), name="static")
app.add_middleware(LogMiddleware)
app.add_middleware(SegurancaMiddleware, templates=templates)  # mais externo: cabeçalhos, no-store e checagem de Origin (CSRF)


# ── Registro dos routers ──
# Cada domínio expõe `router` (API) e/ou `*_frontend_router.router` (páginas HTML).
_MODULOS_ROUTERS = [
    "usuario.usuario_router",
    "unidade.unidade_router",
    "paciente.paciente_router",
    "profissional.profissional_router",
    "procedimento.procedimento_router",
    "registro.registro_router",
    "grupo.grupo_router",
    "evento.evento_router",
    "config.config_router",
    "importacao.importacao_router",
    "exportacao.exportacao_router",
    "relatorio.relatorio_router",
    "competencia.competencia_router",
    "backup.backup_router",
    "roadmap.roadmap_router",
    "sistema.log_router",
    "sistema.excluir_router",
    "aniversariantes.aniversariantes_router",
    "lgpd.lgpd_router",
    # Frontend
    "usuario.auth_frontend_router",
    "dashboard.dashboard_frontend_router",
    "usuario.usuario_frontend_router",
    "unidade.unidade_frontend_router",
    "paciente.paciente_frontend_router",
    "profissional.profissional_frontend_router",
    "procedimento.procedimento_frontend_router",
    "registro.registro_frontend_router",
    "grupo.grupo_frontend_router",
    "evento.evento_frontend_router",
    "config.config_frontend_router",
    "importacao.importacao_frontend_router",
    "exportacao.exportacao_frontend_router",
    "relatorio.relatorio_frontend_router",
    "competencia.competencia_frontend_router",
    "backup.backup_frontend_router",
    "roadmap.roadmap_frontend_router",
    "sistema.log_frontend_router",
    "sistema.excluir_frontend_router",
    "ajuda.ajuda_frontend_router",
    "aniversariantes.aniversariantes_frontend_router",
    "lgpd.lgpd_frontend_router",
]

for _modulo in _MODULOS_ROUTERS:
    app.include_router(importlib.import_module(_modulo).router)


@app.get("/saude", include_in_schema=False)
@app.get("/health", include_in_schema=False)
def saude():
    """Checagem de saúde para o proxy, o Docker e o monitoramento.

    Confere o banco de verdade (um SELECT 1), e não só se o processo está de pé:
    com o PostgreSQL fora do ar o processo continua respondendo, e um balanceador
    mandaria tráfego para uma instância que não consegue atender ninguém.
    Devolve 503 nesse caso, para o proxy tirá-la da rotação.
    """
    from fastapi.responses import JSONResponse
    from sqlalchemy import text as _text

    try:
        with engine.connect() as conexao:
            conexao.execute(_text("SELECT 1"))
    except Exception as erro:
        logger.error("Checagem de saúde falhou: %s", erro)
        return JSONResponse({"status": "indisponivel", "banco": "erro"}, status_code=503)
    return {"status": "ok", "banco": "ok", "versao": app.version}


def _porta_livre(host: str, inicial: int, tentativas: int = 10) -> int:
    """Retorna a primeira porta livre a partir de `inicial` (8000 -> 8001 -> ...)."""
    import socket
    for porta in range(inicial, inicial + tentativas):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, porta))
                return porta
            except OSError:
                print(f"Porta {porta} em uso, tentando {porta + 1}...")
    raise RuntimeError(f"Nenhuma porta livre entre {inicial} e {inicial + tentativas - 1}")


if __name__ == "__main__":
    import uvicorn
    _host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(
        "main:app",
        host=_host,
        port=_porta_livre(_host, int(os.getenv("PORT", "8000"))),
        reload=os.getenv("DEBUG", "false").lower() == "true"
    )
