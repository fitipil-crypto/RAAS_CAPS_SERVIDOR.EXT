"""
Rotas frontend para relatórios.
"""
import re
from urllib.parse import urlencode
from datetime import date

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.datastructures import QueryParams

from database import get_db
from usuario.usuario_service import UsuarioService
from relatorio.relatorio_service import RelatorioService
from relatorio.impressao_service import (
    ABAS_OPERACIONAIS, CAMPOS, CAMPOS_PADRAO, GRUPOS_CAMPOS, SECOES, ImpressaoService, preparar,
)
from relatorio.relatorios_operacionais_service import (
    RELATORIOS_OPERACIONAIS, RelatoriosOperacionaisService,
)
from sistema.templates import templates

router = APIRouter(tags=["Frontend - Relatórios"])


@router.get("/relatorios/pacientes", response_class=HTMLResponse)
def page_relatorio_pacientes(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role == "operador":
        return RedirectResponse(url="/", status_code=302)

    # A tela começa sempre com o modelo padrão, sem reaproveitar a seleção
    # de colunas da tela antiga de impressão.
    itens = list(request.query_params.multi_items())
    if not request.query_params.get("campos_enviados"):
        itens.extend([("tipo", "pacientes"), ("campos_enviados", "1")])
        itens.extend(("campo", campo) for campo in CAMPOS_PADRAO)
    params = QueryParams(itens)

    return templates.TemplateResponse(request, "relatorio_pacientes.html", {
        "user": user,
        "r": preparar(db, params, dict(request.session)),
        "opcoes": ImpressaoService.opcoes_filtro(db),
        "active_page": "relatorio_pacientes",
    })


@router.get("/relatorios/operacionais/{relatorio}", response_class=HTMLResponse)
def page_relatorio_operacional(request: Request, relatorio: str, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role == "operador":
        return RedirectResponse(url="/", status_code=302)
    if relatorio not in RELATORIOS_OPERACIONAIS:
        return RedirectResponse(url="/indicadores", status_code=302)
    if relatorio in ABAS_OPERACIONAIS:
        # Estes relatórios agora são abas de Relatórios Impressão.
        consulta = urlencode([("tipo", relatorio)] + [
            (k, v) for k, v in request.query_params.multi_items() if k not in ("tipo", "relatorio")
        ])
        return RedirectResponse(url=f"/relatorios-impressao?{consulta}", status_code=302)

    dados = RelatoriosOperacionaisService.construir(db, relatorio, request.query_params)
    return templates.TemplateResponse(request, "relatorio_operacional.html", {
        "user": user,
        "r": dados,
        "active_page": f"relatorio_{relatorio}",
    })


@router.get("/relatorios")
def page_relatorios(month: str = None):
    """A antiga tela Relatórios foi incorporada aos Indicadores CAPS."""
    if month and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        return RedirectResponse(url=f"/indicadores?month={month}", status_code=302)
    return RedirectResponse(url="/indicadores", status_code=302)


@router.get("/indicadores", response_class=HTMLResponse)
def page_indicadores(request: Request, db: Session = Depends(get_db), month: str = None):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role == "operador":
        return RedirectResponse(url="/", status_code=302)
    if month and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        month = None


    return templates.TemplateResponse(request, "indicadores.html", {
        "user": user,
        "d": RelatorioService.get_indicadores_caps(db, month=month),
        "active_page": "indicadores",
    })


@router.get("/relatorios-impressao", response_class=HTMLResponse)
def page_relatorios_impressao(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role == "operador":
        return RedirectResponse(url="/", status_code=302)


    return templates.TemplateResponse(request, "relatorios_impressao.html", {
        "user": user,
        "r": preparar(db, request.query_params, request.session),
        "opcoes": ImpressaoService.opcoes_filtro(db),
        "campos": CAMPOS,
        "grupos_campos": GRUPOS_CAMPOS,
        "campos_padrao": CAMPOS_PADRAO,
        "secoes": SECOES,
        "abas_operacionais": ABAS_OPERACIONAIS,
        "emissao": date.today().strftime("%d/%m/%Y"),
        "active_page": "relatorios_impressao",
    })
