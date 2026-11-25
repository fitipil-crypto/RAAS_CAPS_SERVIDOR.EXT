"""
Rotas da API dos grupos de atendimento.

Os grupos são criados e usados dentro da digitação em lote; por isso os
mesmos perfis que lançam registros (admin e operador) podem criá-los.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from grupo.grupo_schema import GrupoAtualizar, GrupoCriar, GrupoDetalhe, GrupoResposta
from grupo.grupo_service import GrupoService
from sistema.auth import require_auth, require_role

router = APIRouter(prefix="/api/grupos", tags=["Grupos de atendimento"])

PERFIS_LANCAMENTO = ("admin", "operador")

MSG_NAO_ENCONTRADO = "Grupo não encontrado"
MSG_DUPLICADO = "Já existe um grupo com essa descrição, data e horário"
MSG_DATA_COM_REGISTROS = "O grupo já tem atendimentos lançados: exclua-os antes de mudar a data"
MSG_MENOS_PESSOAS = "O grupo já tem {atual} paciente(s): a quantidade de pessoas não pode ser menor"
MSG_COM_REGISTROS = "O grupo tem atendimentos lançados e não pode ser excluído"


def _obter_ou_404(db: Session, grupo_id: str):
    grupo = GrupoService.obter_por_id(db, grupo_id)
    if not grupo:
        raise HTTPException(status_code=404, detail=MSG_NAO_ENCONTRADO)
    return grupo


def _resposta(grupo, numero: int) -> GrupoResposta:
    return GrupoResposta(**{**GrupoResposta.model_validate(grupo).model_dump(), "numero": numero})


def _detalhar(db: Session, grupos: list) -> List[GrupoDetalhe]:
    """Converte o detalhe montado pelo serviço nos schemas da resposta."""
    return [GrupoDetalhe(**d) for d in GrupoService.detalhar(db, grupos)]


@router.get("/", response_model=List[GrupoDetalhe])
def listar_grupos(request: Request, month: str = Query(...), db: Session = Depends(get_db)):
    require_auth(request)
    return _detalhar(db, GrupoService.listar_por_mes(db, month))


@router.get("/{grupo_id}", response_model=GrupoDetalhe)
def obter_grupo(grupo_id: str, request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    return _detalhar(db, [_obter_ou_404(db, grupo_id)])[0]


@router.post("/", response_model=GrupoResposta)
def criar_grupo(data: GrupoCriar, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_LANCAMENTO)
    if GrupoService.existe_igual(db, data.description, data.group_date, data.group_time):
        raise HTTPException(status_code=400, detail=MSG_DUPLICADO)
    grupo = GrupoService.criar(db, data)
    return _resposta(grupo, GrupoService.numero_de(db, grupo))


@router.put("/{grupo_id}", response_model=GrupoResposta)
def atualizar_grupo(grupo_id: str, data: GrupoAtualizar, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_LANCAMENTO)
    atual = _obter_ou_404(db, grupo_id)
    novos = data.model_dump(exclude_unset=True, exclude_none=True)
    pacientes = GrupoService.pacientes(db, grupo_id)

    # Mudar a data deixaria os atendimentos já lançados fora do dia do grupo.
    if novos.get("group_date", atual.group_date) != atual.group_date and pacientes:
        raise HTTPException(status_code=400, detail=MSG_DATA_COM_REGISTROS)
    if novos.get("people_count", atual.people_count) < len(pacientes):
        raise HTTPException(status_code=400, detail=MSG_MENOS_PESSOAS.format(atual=len(pacientes)))
    if GrupoService.existe_igual(
        db,
        novos.get("description", atual.description),
        novos.get("group_date", atual.group_date),
        novos.get("group_time", atual.group_time),
        excluir_id=grupo_id,
    ):
        raise HTTPException(status_code=400, detail=MSG_DUPLICADO)

    grupo = GrupoService.atualizar(db, grupo_id, data)
    return _resposta(grupo, GrupoService.numero_de(db, grupo))


@router.delete("/{grupo_id}")
def deletar_grupo(grupo_id: str, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_LANCAMENTO)
    _obter_ou_404(db, grupo_id)
    if GrupoService.tem_registros(db, grupo_id):
        raise HTTPException(status_code=400, detail=MSG_COM_REGISTROS)
    GrupoService.deletar(db, grupo_id)
    return {"mensagem": "Grupo excluído com sucesso"}
