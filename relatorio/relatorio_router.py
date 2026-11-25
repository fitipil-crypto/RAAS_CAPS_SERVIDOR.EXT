"""
Rotas da API para relatórios.
"""
import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from config.config_service import ConfigService
from relatorio.relatorio_service import RelatorioService
from relatorio.impressao_service import ImpressaoService, preparar
from relatorio.relatorios_operacionais_service import (
    RELATORIOS_OPERACIONAIS, RelatoriosOperacionaisService,
)
from sistema.auth import require_auth, require_role

router = APIRouter(prefix="/api/relatorios", tags=["Relatórios"])


@router.get("/dashboard")
def dashboard_stats(request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    return RelatorioService.get_dashboard_stats(db)


@router.get("/completo")
def relatorio_completo(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin", "gestor", "coordenador")
    return RelatorioService.get_relatorio_completo(db)


@router.get("/comparativo-mensal")
def comparativo_mensal(request: Request, n: int = 12, db: Session = Depends(get_db)):
    require_role(request, db, "admin", "gestor", "coordenador")
    return RelatorioService.get_comparativo_mensal(db, n_months=n)


@router.get("/indicadores-caps")
def indicadores_caps(request: Request, month: str = None, db: Session = Depends(get_db)):
    require_role(request, db, "admin", "gestor", "coordenador")
    if month and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(status_code=400, detail="Mês inválido. Use o formato AAAA-MM.")
    return RelatorioService.get_indicadores_caps(db, month=month)


_FORMATOS_IMPRESSAO = {
    "csv": ("text/csv; charset=utf-8", "csv"),
    "txt": ("text/plain; charset=utf-8", "txt"),
    "excel": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "pdf": ("application/pdf", "pdf"),
}


@router.get("/impressao/exportar")
def exportar_impressao(request: Request, formato: str, db: Session = Depends(get_db)):
    usuario = require_role(request, db, "admin", "gestor", "coordenador")
    if formato not in _FORMATOS_IMPRESSAO:
        raise HTTPException(status_code=400, detail="Formato inválido. Use pdf, csv ou txt.")
    r = preparar(db, request.query_params, request.session)
    if formato in ("csv", "txt"):
        conteudo = ImpressaoService.gerar_csv(r["blocos"])
    elif formato == "excel":
        conteudo = ImpressaoService.gerar_excel(r["blocos"], r["titulo"], r["subtitulo"])
    else:
        cidade = ConfigService.obter_valor(db, "default_city", "") or ""
        estado = ConfigService.obter_valor(db, "default_state", "") or ""
        localidade = "/".join(parte for parte in (cidade, estado) if parte) or "Município não informado"
        metadados = {
            "organizacao": ConfigService.obter_valor(db, "organ_name", "RAAS-CAPS"),
            "sigla": ConfigService.obter_valor(db, "organ_code", ""),
            "municipio": localidade,
            "cnes": ConfigService.obter_valor(db, "cnes_code", "Não informado"),
            "impresso_por": usuario.name or usuario.username,
            "usuario": usuario.username,
            "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }
        conteudo = ImpressaoService.gerar_pdf(r["blocos"], r["titulo"], r["subtitulo"], metadados)
    media_type, extensao = _FORMATOS_IMPRESSAO[formato]
    nome = f"{r['tipo']}_{date.today().isoformat()}.{extensao}"
    disposicao = "inline" if formato == "pdf" else "attachment"
    return Response(content=conteudo, media_type=media_type,
                    headers={"Content-Disposition": f'{disposicao}; filename="{nome}"'})


@router.get("/operacional/exportar")
def exportar_relatorio_operacional(
    request: Request, relatorio: str, formato: str = "pdf", db: Session = Depends(get_db)
):
    usuario = require_role(request, db, "admin", "gestor", "coordenador")
    if relatorio not in RELATORIOS_OPERACIONAIS:
        raise HTTPException(status_code=400, detail="Relatório operacional inválido.")
    if formato not in _FORMATOS_IMPRESSAO:
        raise HTTPException(status_code=400, detail="Formato inválido. Use pdf, csv ou txt.")

    r = RelatoriosOperacionaisService.construir(db, relatorio, request.query_params)
    if formato in ("csv", "txt"):
        conteudo = ImpressaoService.gerar_csv(r["blocos"])
    elif formato == "excel":
        conteudo = ImpressaoService.gerar_excel(r["blocos"], r["titulo"], "")
    else:
        cidade = ConfigService.obter_valor(db, "default_city", "") or ""
        estado = ConfigService.obter_valor(db, "default_state", "") or ""
        localidade = "/".join(parte for parte in (cidade, estado) if parte) or "Município não informado"
        metadados = {
            "organizacao": ConfigService.obter_valor(db, "organ_name", "RAAS-CAPS"),
            "sigla": ConfigService.obter_valor(db, "organ_code", ""),
            "municipio": localidade,
            "cnes": ConfigService.obter_valor(db, "cnes_code", "Não informado"),
            "impresso_por": usuario.name or usuario.username,
            "usuario": usuario.username,
            "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }
        conteudo = ImpressaoService.gerar_pdf(r["blocos"], r["titulo"], "", metadados)

    media_type, extensao = _FORMATOS_IMPRESSAO[formato]
    nome = f"{relatorio}_{date.today().isoformat()}.{extensao}"
    disposicao = "inline" if formato == "pdf" else "attachment"
    return Response(content=conteudo, media_type=media_type,
                    headers={"Content-Disposition": f'{disposicao}; filename="{nome}"'})
