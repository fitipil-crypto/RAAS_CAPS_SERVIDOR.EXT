"""
Rotas frontend para configurações.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from usuario.usuario_service import UsuarioService
from config.config_service import ConfigService
from sistema.templates import templates

router = APIRouter(tags=["Frontend - Configurações"])


@router.get("/configuracoes", response_class=HTMLResponse)
def page_configuracoes(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)


    config = ConfigService.get_config_estabelecimento(db)

    return templates.TemplateResponse(request, "configuracoes.html", {
        "user": user,
        "config": config,
        "active_page": "configuracoes",
    })
