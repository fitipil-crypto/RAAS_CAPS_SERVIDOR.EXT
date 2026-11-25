"""
Rotas frontend para usuários (Controle de Acesso).
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from database import get_db
from usuario.usuario_service import UsuarioService
from sistema.templates import templates

router = APIRouter(tags=["Frontend - Usuários"])


def _get_current_user(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return UsuarioService.obter_por_id(db, user_id)


@router.get("/acesso", response_class=HTMLResponse)
def page_acesso(request: Request, db: Session = Depends(get_db)):
    user = _get_current_user(request, db)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=302)


    # Apenas admin enxerga todos os usuários; os demais veem só o próprio
    users = UsuarioService.listar_todos(db) if user.role == "admin" else [user]
    # Nome da unidade de cada usuário na listagem. Vem de todas as unidades
    # (inclusive inativas) para que um usuário lotado em unidade desativada não
    # apareça como "Todas as unidades", que é o oposto do que acontece.
    from unidade.unidade_service import UnidadeService

    nomes_unidades = {u.id: u.nome for u in UnidadeService.listar(db)}
    return templates.TemplateResponse(request, "acesso.html", {
        "user": user,
        "users": users,
        "nomes_unidades": nomes_unidades,
        "active_page": "acesso",
    })
