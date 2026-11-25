"""
Rota frontend da tela de Grupos de atendimento.

Mostra, na competência escolhida, cada grupo lançado com a sua descrição,
data e horário e, dentro dele, os pacientes com os procedimentos e quem os
realizou — a mesma relação da caixa de grupos da digitação em lote.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from grupo.grupo_service import GrupoService
from registro.registro_frontend_router import cores_das_linhas
from sistema.templates import templates
from usuario.usuario_service import UsuarioService

router = APIRouter(tags=["Frontend - Grupos"])


@router.get("/grupos", response_class=HTMLResponse)
def page_grupos(request: Request, month: str = Query(None), db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not month:
        month = datetime.now().strftime("%Y-%m")

    grupos = GrupoService.detalhar(db, GrupoService.listar_por_mes(db, month))

    # Cada grupo em que o profissional lançou conta uma sessão dele no mês.
    sessoes = GrupoService.sessoes_por_profissional(db, month)
    profissionais = {}
    for grupo in grupos:
        for paciente in grupo["pacientes"]:
            # Mesmo padrão de cores da lista de Registros RAAS: 2+ atendimentos
            # seguidos do mesmo profissional (amarelo/azul) ou do mesmo
            # procedimento (rosa/vermelho) formam um bloco colorido.
            for registro, cor in zip(paciente["registros"], cores_das_linhas(paciente["registros"])):
                registro["cor_linha"] = cor
            for registro in paciente["registros"]:
                nome = registro["professional_name"]
                if registro["professional_id"]:
                    profissionais[nome] = sessoes.get(registro["professional_id"], 0)

    return templates.TemplateResponse(request, "grupos.html", {
        "user": user,
        "grupos": grupos,
        "sel_month": month,
        "total_pacientes": sum(len(g["pacientes"]) for g in grupos),
        "total_registros": sum(g["total_registros"] for g in grupos),
        "sessoes_por_profissional": sorted(profissionais.items()),
        "active_page": "grupos",
    })
