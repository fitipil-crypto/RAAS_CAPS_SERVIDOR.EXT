"""
Rotas da API de aniversariantes.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from aniversariantes.aniversariantes_service import AniversariantesService
from sistema.auth import require_auth

router = APIRouter(prefix="/api/aniversariantes", tags=["Aniversariantes"])



@router.get("/")
def listar_aniversariantes(
    request: Request,
    mes: int = Query(None, ge=1, le=12),
    tipo: str = Query("todos"),
    incluir_inativos: bool = Query(False),
    db: Session = Depends(get_db),
):
    require_auth(request)
    mes = mes or date.today().month
    return AniversariantesService.resumo(db, mes, tipo, incluir_inativos)


@router.get("/hoje")
def aniversariantes_hoje(request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    return AniversariantesService.de_hoje(db)
