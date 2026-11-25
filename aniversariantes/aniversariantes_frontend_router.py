"""
Rotas frontend para a página de aniversariantes.
"""
from datetime import date

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from usuario.usuario_service import UsuarioService
from aniversariantes.aniversariantes_service import AniversariantesService, MESES, TIPOS
from sistema.templates import templates

router = APIRouter(tags=["Frontend - Aniversariantes"])


@router.get("/aniversariantes", response_class=HTMLResponse)
def page_aniversariantes(
    request: Request,
    mes: int = Query(None),
    tipo: str = Query("todos"),
    inativos: bool = Query(False),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)


    hoje = date.today()
    if not mes or not 1 <= mes <= 12:
        mes = hoje.month
    if tipo not in TIPOS:
        tipo = "todos"

    resumo = AniversariantesService.resumo(db, mes, tipo, inativos, hoje)

    # Agrupa o mês por dia para a linha do tempo.
    dias: dict[int, list[dict]] = {}
    for item in resumo["mes"]:
        dias.setdefault(item["dia"], []).append(item)

    mes_anterior = 12 if mes == 1 else mes - 1
    mes_seguinte = 1 if mes == 12 else mes + 1

    return templates.TemplateResponse(request, "aniversariantes.html", {
        "user": user,
        "hoje": hoje,
        "mes": mes,
        "mes_nome": MESES[mes - 1],
        "mes_anterior": mes_anterior,
        "mes_seguinte": mes_seguinte,
        "meses": MESES,
        "tipo": tipo,
        "inativos": inativos,
        "resumo": resumo,
        "dias": sorted(dias.items()),
        "max_mes": max(resumo["por_mes"] + [1]),
        "active_page": "aniversariantes",
    })
