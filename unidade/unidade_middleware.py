"""
Middleware que define a unidade ativa de cada requisição.

Fica *por dentro* do SessionMiddleware (precisa ler a sessão) e por fora dos
routers, para que o escopo já esteja valendo quando qualquer consulta rodar.

A unidade escolhida vem da sessão (``unidade_id``), nunca de cabeçalho ou de
parâmetro de URL, e é sempre reconferida contra o perfil do usuário em
``UnidadeService.resolver_unidade_ativa``: um operador não consegue ver outra
unidade mexendo no que o navegador envia.
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from database import SessionLocal
from sistema.escopo import definir_unidade_ativa, restaurar_unidade_ativa

logger = logging.getLogger(__name__)

# Caminhos que rodam antes de haver unidade (login, estáticos, saúde do serviço).
PREFIXOS_LIVRES = ("/static", "/login", "/logout", "/saude", "/health", "/primeiro-acesso")


class UnidadeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = definir_unidade_ativa(None)
        try:
            unidade_id = None
            if not request.url.path.startswith(PREFIXOS_LIVRES):
                unidade_id = self._resolver(request)
            restaurar_unidade_ativa(token)
            token = definir_unidade_ativa(unidade_id)
            request.state.unidade_id = unidade_id
            return await call_next(request)
        finally:
            restaurar_unidade_ativa(token)

    @staticmethod
    def _resolver(request: Request) -> str | None:
        """Lê sessão e banco para decidir a unidade; qualquer falha vira 'todas'."""
        try:
            sessao = request.session
        except AssertionError:
            return None  # SessionMiddleware ainda não instalado (testes isolados)
        user_id = sessao.get("user_id")
        if not user_id:
            return None

        from unidade.unidade_service import UnidadeService
        from usuario.usuario_service import UsuarioService

        db = SessionLocal()
        try:
            usuario = UsuarioService.obter_por_id(db, user_id)
            ativa = UnidadeService.resolver_unidade_ativa(db, usuario, sessao.get("unidade_id"))
            # Perfil de uma só unidade: a sessão acompanha o que valeu de fato,
            # para a tela mostrar a mesma unidade que o escopo está usando.
            if ativa and sessao.get("unidade_id") != ativa:
                sessao["unidade_id"] = ativa
            return ativa
        except Exception as erro:  # banco fora do ar, migração em curso...
            logger.warning("Não foi possível definir a unidade ativa: %s", erro)
            return None
        finally:
            db.close()
