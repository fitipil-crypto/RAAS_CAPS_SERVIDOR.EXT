"""Tela Competência: auditoria RAAS, comparativo entre meses e previsão."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from competencia.competencia_service import ABAS, CompetenciaService
from database import get_db
from usuario.usuario_service import UsuarioService
from sistema.templates import templates

router = APIRouter(tags=["Frontend - Competência"])


@router.get("/competencia", response_class=HTMLResponse)
def page_competencia(request: Request, aba: str = "auditoria", month: str | None = None,
                     mes_b: str | None = None, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role == "operador":
        return RedirectResponse(url="/", status_code=302)
    if aba not in ABAS:
        aba = "auditoria"

    r = CompetenciaService.construir(db, aba, month, mes_b)
    return templates.TemplateResponse(request, "competencia.html", {
        "user": user,
        "r": r,
        "abas": ABAS,
        "mes_b": r["dados"]["mes_a"] if aba == "comparar" else "",
        "active_page": "competencia",
    })
