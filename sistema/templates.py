"""
Instância única do Jinja2Templates, compartilhada por todos os routers de frontend.

O seletor de unidade da barra superior aparece em toda página, mas cada router
monta o seu próprio contexto. Em vez de acrescentar as mesmas três variáveis em
cada um dos routers de frontend — e ter de lembrar disso em todo router novo —
elas entram por um *context processor*, que o Starlette chama a cada
renderização recebendo a requisição.
"""
import logging

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

logger = logging.getLogger(__name__)


def contexto_unidades(request: Request) -> dict:
    """Unidade ativa e unidades disponíveis, para o seletor em `base.html`.

    Falha fechada e silenciosa: se o banco estiver indisponível ou a sessão não
    existir, o seletor simplesmente não aparece — uma página não deve deixar de
    carregar por causa dele.
    """
    vazio = {"unidades_disponiveis": [], "unidade_ativa": None, "pode_ver_todas": False}
    try:
        user_id = request.session.get("user_id")
    except (AssertionError, KeyError, AttributeError):
        return vazio
    if not user_id:
        return vazio

    from database import SessionLocal
    from unidade import modalidades
    from unidade.unidade_service import UnidadeService
    from usuario.usuario_service import UsuarioService

    db = SessionLocal()
    try:
        usuario = UsuarioService.obter_por_id(db, user_id)
        if usuario is None:
            return vazio
        unidades = UnidadeService.unidades_do_usuario(db, usuario)
        pode_ver_todas = UnidadeService.pode_ver_todas(usuario)
        # Uma unidade só e sem visão geral: não há o que escolher.
        if len(unidades) <= 1 and not pode_ver_todas:
            return vazio
        return {
            "unidades_disponiveis": [
                {
                    "id": u.id,
                    "nome": u.nome,
                    "modalidade": u.modalidade,
                    "modalidade_nome": modalidades.nome(u.modalidade),
                }
                for u in unidades
            ],
            "unidade_ativa": getattr(request.state, "unidade_id", None),
            "pode_ver_todas": pode_ver_todas,
        }
    except Exception as erro:
        logger.warning("Seletor de unidade indisponível: %s", erro)
        return vazio
    finally:
        db.close()


templates = Jinja2Templates(directory="templates", context_processors=[contexto_unidades])
