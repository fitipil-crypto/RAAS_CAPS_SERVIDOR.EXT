"""
Rotas frontend para importação RAAS.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from usuario.usuario_service import UsuarioService
from sistema.templates import templates

router = APIRouter(tags=["Frontend - Importação"])


@router.get("/importar", response_class=HTMLResponse)
def page_importar(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse(url="/", status_code=302)


    return templates.TemplateResponse(request, "importar.html", {
        "user": user,
        "active_page": "importar",
    })
