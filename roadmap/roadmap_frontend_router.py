"""
Rotas frontend para o roadmap.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from usuario.usuario_service import UsuarioService
from roadmap.roadmap_service import RoadmapService
from sistema.templates import templates

router = APIRouter(tags=["Frontend - Roadmap"])


@router.get("/roadmap", response_class=HTMLResponse)
def page_roadmap(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    items = RoadmapService.listar_todos(db)
    return templates.TemplateResponse(request, "roadmap.html", {
        "user": user,
        "items": items,
        "active_page": "roadmap",
    })
