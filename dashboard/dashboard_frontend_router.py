"""
Rota da página inicial (dashboard).
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from dashboard.dashboard_service import DashboardService
from database import get_db
from sistema.templates import templates
from usuario.usuario_service import UsuarioService

router = APIRouter(tags=["Frontend - Dashboard"])


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """Página principal - redireciona para login ou mostra o dashboard."""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=302)

    contexto = DashboardService.montar_contexto(db)
    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        **contexto,
        "active_page": "dashboard",
    })
