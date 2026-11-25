"""
Rotas frontend para registros RAAS.
"""
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
from collections import defaultdict

from database import get_db
from grupo.grupo_service import GrupoService
from evento.evento_service import EventoService
from usuario.usuario_service import UsuarioService
from registro.registro_service import RegistroService
from paciente.paciente_service import PacienteService
from profissional.profissional_service import ProfissionalService
from procedimento.procedimento_service import ProcedimentoService
from sistema.reference_data import SRV_OPTS, CLS_OPTS, SERVICE_TYPE_MAP, DEFAULT_TEAM_CODE, DEFAULT_TEAM_NAME
from registro.registro_validacao import max_profissionais_lote
from sistema.templates import templates

router = APIRouter(tags=["Frontend - Registros"])

# ── Cor de fundo das linhas da lista de atendimentos ──
# Dentro de um mesmo dia, 2+ lançamentos seguidos do mesmo profissional formam um
# bloco e pintam a linha (amarelo/azul); a mesma regra vale para o procedimento
# (rosa/vermelho). O profissional tem prioridade quando a linha cai nos dois, e o
# que sobra do bloco de procedimento só é pintado se ficarem 2+ linhas seguidas
# sem cor — lançamento sozinho nunca fica colorido. A alternância corre pela lista
# inteira, sem reiniciar a cada data, para o último bloco de um dia e o primeiro
# do dia seguinte nunca saírem na mesma cor.
CORES_PROFISSIONAL = ("reg-bloco-amarelo", "reg-bloco-azul")
CORES_PROCEDIMENTO = ("reg-proc-rosa", "reg-proc-vermelho")


def _valor(registro, campo):
    """Lê o campo de um registro do banco ou de um dicionário (tela Grupos)."""
    if isinstance(registro, dict):
        return registro.get(campo)
    return getattr(registro, campo, None)


def _trechos_seguidos(registros, campo):
    """Trechos de registros vizinhos com a mesma data e o mesmo valor em `campo`,
    como (valor, posições), na ordem em que aparecem na lista."""
    trechos = []
    for i, r in enumerate(registros):
        chave = (_valor(r, "service_date"), _valor(r, campo))
        if trechos and trechos[-1][0] == chave:
            trechos[-1][1].append(i)
        else:
            trechos.append((chave, [i]))
    return [(chave[1], posicoes) for chave, posicoes in trechos]


def _pedacos_sem_cor(posicoes, cores):
    """Quebra as posições do trecho nos pedaços seguidos que continuam sem cor."""
    pedacos, atual = [], []
    for i in posicoes:
        if cores[i]:
            if atual:
                pedacos.append(atual)
                atual = []
        else:
            atual.append(i)
    if atual:
        pedacos.append(atual)
    return pedacos


def cores_das_linhas(registros):
    """Classe CSS de fundo de cada registro, na ordem em que aparece na lista."""
    cores = [""] * len(registros)

    n = 0
    for profissional, posicoes in _trechos_seguidos(registros, "professional_id"):
        if not profissional or len(posicoes) < 2:
            continue
        for i in posicoes:
            cores[i] = CORES_PROFISSIONAL[n % 2]
        n += 1

    n = 0
    for procedimento, posicoes in _trechos_seguidos(registros, "procedure_id"):
        if not procedimento or len(posicoes) < 2:
            continue
        for pedaco in _pedacos_sem_cor(posicoes, cores):
            if len(pedaco) < 2:
                continue
            for i in pedaco:
                cores[i] = CORES_PROCEDIMENTO[n % 2]
            n += 1

    return cores



@router.get("/registros", response_class=HTMLResponse)
def page_registros(request: Request, month: str = Query(None), db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)


    if not month:
        month = datetime.now().strftime("%Y-%m")

    registros = RegistroService.listar_por_mes(db, month)
    pacientes = {p.id: p for p in PacienteService.listar_todos(db)}
    profissionais = {p.id: p for p in ProfissionalService.listar_todos(db)}
    procedimentos = {p.id: p for p in ProcedimentoService.listar_todos(db)}

    # Grupos da competência: o número vem da ordem de data e horário.
    grupos = {g.id: g for g in GrupoService.listar_por_mes(db, month)}
    numeros = GrupoService.numerar(list(grupos.values()))

    # Eventos da competência: o vínculo com o registro está em evento_registros.
    eventos = {e.id: e for e in EventoService.listar_por_mes(db, month)}
    numeros_evento = EventoService.numerar(list(eventos.values()))
    evento_do_registro = EventoService.eventos_por_registro(db, list(eventos))

    # Enrich records with display names
    for r in registros:
        proc = procedimentos.get(r.procedure_id)
        r.procedure_name = proc.name if proc else "—"
        r.professional_name = profissionais.get(r.professional_id).name if profissionais.get(r.professional_id) else "—"
        r.service_type_label = SERVICE_TYPE_MAP.get(r.service_type, "—")
        grupo = grupos.get(r.group_id)
        r.grupo_label = f"Grupo nº {numeros.get(grupo.id)}" if grupo else ""
        r.grupo_titulo = (
            f"{grupo.description} — {grupo.group_date[8:10]}/{grupo.group_date[5:7]}/{grupo.group_date[:4]}"
            f" às {grupo.group_time}" if grupo else ""
        )
        evento = eventos.get(evento_do_registro.get(r.id))
        r.evento_label = f"Evento nº {numeros_evento.get(evento.id)}" if evento else ""
        r.evento_titulo = (
            f"{evento.name} — {evento.event_date[8:10]}/{evento.event_date[5:7]}/{evento.event_date[:4]}"
            if evento else ""
        )

    # Group by patient
    grouped = defaultdict(list)
    for r in registros:
        grouped[r.patient_id].append(r)
    groups = []
    for pid, recs in grouped.items():
        pat = pacientes.get(pid)
        for r, cor in zip(recs, cores_das_linhas(recs)):
            r.cor_linha = cor
        groups.append({"patient": pat, "records": recs})
    groups.sort(key=lambda g: (g["patient"].name if g["patient"] else "").upper())

    # Active professionals and procedures for the form
    active_professionals = [p for p in profissionais.values() if p.active]
    active_procedures = []
    for p in procedimentos.values():
        if p.active:
            p.label = f"{p.code} — {p.name}"
            active_procedures.append(p)

    return templates.TemplateResponse(request, "registros.html", {
        "user": user,
        "registros": registros,
        "groups": groups,
        "pacientes": pacientes,
        "profissionais": profissionais,
        "procedimentos": procedimentos,
        "active_profissionais": active_professionals,
        "active_procedimentos": active_procedures,
        "sel_month": month,
        "srv_opts": SRV_OPTS,
        "cls_opts": CLS_OPTS,
        "service_type_map": SERVICE_TYPE_MAP,
        "default_team_code": DEFAULT_TEAM_CODE,
        "default_team_name": DEFAULT_TEAM_NAME,
        "lote_max_profs": max_profissionais_lote(user.role),
        "active_page": "registros",
    })
