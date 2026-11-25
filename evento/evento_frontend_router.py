"""
Rotas frontend para eventos da unidade.
"""
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, date

from database import get_db
from usuario.usuario_service import UsuarioService
from evento.evento_service import EventoService
from paciente.paciente_service import PacienteService
from profissional.profissional_service import ProfissionalService
from procedimento.procedimento_service import ProcedimentoService
from sistema.reference_data import SRV_OPTS, CLS_OPTS
from sistema.templates import templates

router = APIRouter(tags=["Frontend - Eventos"])

DIAS_SEMANA = (
    "segunda-feira", "terça-feira", "quarta-feira",
    "quinta-feira", "sexta-feira", "sábado", "domingo",
)


def _rotulo_data(iso: str) -> dict:
    """Data do evento em pt-BR, com o dia da semana.

    A ficha mostra a data por extenso; o YYYY-MM-DD continua no data-attribute
    do card, que é o que o JavaScript usa para abrir os modais.
    """
    try:
        dia = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return {"br": iso or "—", "semana": ""}
    return {"br": dia.strftime("%d/%m/%Y"), "semana": DIAS_SEMANA[dia.weekday()]}



@router.get("/eventos", response_class=HTMLResponse)
def page_eventos(request: Request, month: str = Query(None), db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    # Lançamento múltiplo é de administrador e coordenador.
    if user.role not in ("admin", "coordenador"):
        return RedirectResponse(url="/", status_code=302)


    if not month:
        month = datetime.now().strftime("%Y-%m")

    pacientes = {p.id: p for p in PacienteService.listar_todos(db)}
    eventos = []
    # O nº do evento segue a ordem das datas na competência, como nos grupos.
    da_competencia = EventoService.listar_por_mes(db, month)
    numeros = EventoService.numerar(da_competencia)
    for evento in da_competencia:
        participantes = [
            pacientes[pid] for pid in EventoService.listar_patient_ids(db, evento.id)
            if pid in pacientes
        ]
        participantes.sort(key=lambda p: (p.name or "").upper())
        eventos.append({
            "evento": evento,
            "numero": numeros.get(evento.id, 0),
            "pacientes": participantes,
            "data": _rotulo_data(evento.event_date),
            "registros": EventoService.contar_registros(db, evento.id),
            "resumo": EventoService.resumo_lancamento(db, evento.id),
        })

    active_procedures = []
    for p in ProcedimentoService.listar_todos(db):
        if p.active:
            p.label = f"{p.code} — {p.name}"
            active_procedures.append(p)
    active_procedures.sort(key=lambda p: p.label)

    active_professionals = [p for p in ProfissionalService.listar_todos(db) if p.active]
    active_professionals.sort(key=lambda p: (p.name or "").upper())

    return templates.TemplateResponse(request, "eventos.html", {
        "user": user,
        "eventos": eventos,
        "total_participantes": sum(len(e["pacientes"]) for e in eventos),
        "pacientes": pacientes,
        "active_procedimentos": active_procedures,
        "active_profissionais": active_professionals,
        "sel_month": month,
        "srv_opts": SRV_OPTS,
        "cls_opts": CLS_OPTS,
        "active_page": "eventos",
    })
