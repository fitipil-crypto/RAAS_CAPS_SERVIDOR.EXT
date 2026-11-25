"""API da tela Competência: dados em JSON e exportação PDF/CSV/TXT."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from competencia.competencia_service import ABAS, CompetenciaService
from config.config_service import ConfigService
from database import get_db
from relatorio.impressao_service import ImpressaoService
from sistema.auth import require_role

router = APIRouter(prefix="/api/competencia", tags=["Competência"])

_FORMATOS = {
    "csv": ("text/csv; charset=utf-8", "csv"),
    "txt": ("text/plain; charset=utf-8", "txt"),
    "pdf": ("application/pdf", "pdf"),
}


def _construir(db, aba, month, mes_b):
    if aba not in ABAS:
        raise HTTPException(status_code=400, detail="Aba inválida.")
    return CompetenciaService.construir(db, aba, month, mes_b)


@router.get("/auditoria")
def auditoria(request: Request, month: str | None = None, db: Session = Depends(get_db)):
    require_role(request, db, "admin", "gestor", "coordenador")
    r = _construir(db, "auditoria", month, None)["dados"]
    return {
        "competencia": r["competencia"], "pode_exportar": r["pode_exportar"], "contagem": r["contagem"],
        "achados": [a.__dict__ for a in r["achados"]],
    }


@router.get("/comparar")
def comparar(request: Request, month: str | None = None, mes_b: str | None = None, db: Session = Depends(get_db)):
    require_role(request, db, "admin", "gestor", "coordenador")
    return _construir(db, "comparar", month, mes_b)["dados"]


@router.get("/previsao")
def previsao(request: Request, month: str | None = None, db: Session = Depends(get_db)):
    require_role(request, db, "admin", "gestor", "coordenador")
    return _construir(db, "previsao", month, None)["dados"]


@router.get("/exportar")
def exportar(request: Request, aba: str, formato: str = "pdf", month: str | None = None,
             mes_b: str | None = None, db: Session = Depends(get_db)):
    usuario = require_role(request, db, "admin", "gestor", "coordenador")
    if formato not in _FORMATOS:
        raise HTTPException(status_code=400, detail="Formato inválido. Use pdf, csv ou txt.")
    r = _construir(db, aba, month, mes_b)

    if formato == "pdf":
        cidade = ConfigService.obter_valor(db, "default_city", "") or ""
        estado = ConfigService.obter_valor(db, "default_state", "") or ""
        metadados = {
            "organizacao": ConfigService.obter_valor(db, "organ_name", "RAAS-CAPS"),
            "sigla": ConfigService.obter_valor(db, "organ_code", ""),
            "municipio": "/".join(p for p in (cidade, estado) if p) or "Município não informado",
            "cnes": ConfigService.obter_valor(db, "cnes_code", "Não informado"),
            "impresso_por": usuario.name or usuario.username,
            "usuario": usuario.username,
            "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }
        conteudo = ImpressaoService.gerar_pdf(r["blocos"], r["titulo"], f"Competência {r['competencia']}", metadados)
    else:
        conteudo = ImpressaoService.gerar_csv(r["blocos"])

    media_type, extensao = _FORMATOS[formato]
    nome = f"competencia_{aba}_{r['competencia']}_{date.today().isoformat()}.{extensao}"
    disposicao = "inline" if formato == "pdf" else "attachment"
    return Response(content=conteudo, media_type=media_type,
                    headers={"Content-Disposition": f'{disposicao}; filename="{nome}"'})
