"""
Rotas da API para eventos da unidade.

Lançamento múltiplo é operação de administrador — nenhuma rota aqui é
acessível a coordenador ou operador.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from evento.evento_schema import (
    EventoResposta, EventoCriar, EventoAtualizar, EventoPacientesAdicionar, EventoLancamento,
)
from evento.evento_service import EventoService
from sistema.auth import require_role

router = APIRouter(prefix="/api/eventos", tags=["Eventos"])

# Administrador e coordenador gerenciam eventos e lançam os registros.
PERFIS_EVENTO = ("admin", "coordenador")

MSG_NAO_ENCONTRADO = "Evento não encontrado"
MSG_SO_ADMIN_APAGA = "Apagar os atendimentos do evento é exclusivo do administrador"


def _obter_ou_404(db: Session, evento_id: str):
    evento = EventoService.obter_por_id(db, evento_id)
    if not evento:
        raise HTTPException(status_code=404, detail=MSG_NAO_ENCONTRADO)
    return evento


@router.get("/", response_model=List[EventoResposta])
def listar_eventos(request: Request, month: str = Query(None), db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_EVENTO)
    return EventoService.listar_por_mes(db, month)


@router.get("/{evento_id}", response_model=EventoResposta)
def obter_evento(evento_id: str, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_EVENTO)
    return _obter_ou_404(db, evento_id)


@router.post("/", response_model=EventoResposta)
def criar_evento(data: EventoCriar, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_EVENTO)
    return EventoService.criar(db, data)


@router.put("/{evento_id}", response_model=EventoResposta)
def atualizar_evento(evento_id: str, data: EventoAtualizar, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_EVENTO)
    _obter_ou_404(db, evento_id)
    return EventoService.atualizar(db, evento_id, data)


@router.delete("/{evento_id}")
def deletar_evento(
    evento_id: str,
    request: Request,
    remover_registros: bool = Query(False, description="Apagar também os atendimentos lançados pelo evento"),
    db: Session = Depends(get_db),
):
    user = require_role(request, db, *PERFIS_EVENTO)
    if remover_registros and user.role != "admin":
        raise HTTPException(status_code=403, detail=MSG_SO_ADMIN_APAGA)
    resultado = EventoService.deletar(db, evento_id, remover_registros)
    if resultado is None:
        raise HTTPException(status_code=404, detail=MSG_NAO_ENCONTRADO)
    removidos = resultado["registros_removidos"]
    mensagem = "Evento excluído com sucesso"
    if removidos:
        mensagem += f" · {removidos} atendimento(s) apagado(s)"
    return {"mensagem": mensagem, **resultado}


@router.get("/{evento_id}/registros")
def listar_registros(evento_id: str, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_EVENTO)
    _obter_ou_404(db, evento_id)
    return {
        "registro_ids": EventoService.listar_registro_ids(db, evento_id),
        "existentes": EventoService.contar_registros(db, evento_id),
        "resumo": EventoService.resumo_lancamento(db, evento_id),
    }


@router.get("/{evento_id}/pacientes")
def listar_pacientes(evento_id: str, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_EVENTO)
    _obter_ou_404(db, evento_id)
    return {"patient_ids": EventoService.listar_patient_ids(db, evento_id)}


@router.post("/{evento_id}/pacientes")
def adicionar_pacientes(evento_id: str, data: EventoPacientesAdicionar, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_EVENTO)
    _obter_ou_404(db, evento_id)
    return EventoService.adicionar_pacientes(db, evento_id, data.patient_ids)


@router.delete("/{evento_id}/pacientes/{patient_id}")
def remover_paciente(evento_id: str, patient_id: str, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_EVENTO)
    _obter_ou_404(db, evento_id)
    if not EventoService.remover_paciente(db, evento_id, patient_id):
        raise HTTPException(status_code=404, detail="Paciente não está na lista do evento")
    return {"mensagem": "Paciente removido da lista"}


@router.post("/{evento_id}/registros")
def lancar_registros(evento_id: str, data: EventoLancamento, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_EVENTO)
    _obter_ou_404(db, evento_id)
    resultado = EventoService.lancar_registros(db, evento_id, data)
    if resultado.get("erro"):
        raise HTTPException(status_code=400, detail=resultado["erro"])
    return resultado
