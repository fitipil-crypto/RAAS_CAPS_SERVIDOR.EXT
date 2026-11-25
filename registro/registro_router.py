"""
Rotas da API para registros RAAS.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from types import SimpleNamespace
from typing import List

from database import get_db
from registro.registro_schema import RegistroResposta, RegistroCriar, RegistroAtualizar
from registro.registro_service import RegistroService
from registro.registro_validacao import (
    MSG_PROC_GRUPO_SEM_GRUPO, MSG_PROFISSIONAIS_DEMAIS, TRAVA_GRAVACAO, RegistroInvalido,
    eh_proc_grupo, max_profissionais_lote, validar_grupo, validar_registro,
)
from sistema.auth import require_auth, require_role

router = APIRouter(prefix="/api/registros", tags=["Registros RAAS"])


@router.get("/", response_model=List[RegistroResposta])
def listar_registros(request: Request, month: str = Query(None), db: Session = Depends(get_db)):
    require_auth(request)
    return RegistroService.listar_todos(db, month)


@router.get("/{registro_id}", response_model=RegistroResposta)
def obter_registro(registro_id: str, request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    reg = RegistroService.obter_por_id(db, registro_id)
    if not reg:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    return reg


def _validar(db: Session, data, vistos: set | None = None, excluir_id: str | None = None) -> None:
    """Traduz violações de regra de negócio em HTTP 400."""
    group_id = getattr(data, "group_id", None)
    try:
        validar_grupo(
            db, group_id=group_id, professional_id=data.professional_id,
            service_date=data.service_date, patient_ids={data.patient_id},
        )
        validar_registro(
            db, service_month=data.service_month, service_date=data.service_date,
            patient_id=data.patient_id, professional_id=data.professional_id,
            procedure_id=data.procedure_id, vistos=vistos, excluir_id=excluir_id,
            group_id=group_id,
        )
    except RegistroInvalido as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/", response_model=RegistroResposta)
def criar_registro(data: RegistroCriar, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin", "operador")
    with TRAVA_GRAVACAO:
        _validar(db, data)
        return RegistroService.criar(db, data)


@router.post("/varios", response_model=List[RegistroResposta])
def criar_varios_registros(registros: List[RegistroCriar], request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin", "operador")
    vistos = set()
    with TRAVA_GRAVACAO:
        for data in registros:
            _validar(db, data, vistos)
        return RegistroService.criar_varios(db, registros)


# Digitação em lote: até 30 pacientes (o tamanho máximo de um grupo) × até 5
# procedimentos × até 10 profissionais (o limite do administrador).
MAX_REGISTROS_LOTE = 1500


class RegistroLote(BaseModel):
    registros: List[RegistroCriar] = Field(..., min_length=1, max_length=MAX_REGISTROS_LOTE)


@router.post("/lote")
def criar_registros_lote(lote: RegistroLote, request: Request, db: Session = Depends(get_db)):
    """Digitação em lote: valida cada linha e só grava se todas forem válidas.

    Em caso de erro nada é gravado e a resposta (400) lista as linhas com
    problema em ``erros`` (``linha`` é o índice, a partir de 0, em ``registros``).
    """
    usuario = require_role(request, db, "admin", "operador")
    limite = max_profissionais_lote(usuario.role)
    if len({r.professional_id for r in lote.registros}) > limite:
        raise HTTPException(status_code=400, detail=MSG_PROFISSIONAIS_DEMAIS.format(limite=limite))
    with TRAVA_GRAVACAO:
        return _gravar_lote(db, lote)


def _erros_de_grupo(db: Session, registros: List[RegistroCriar]) -> list[str]:
    """Confere as regras do grupo olhando o lote como um todo.

    A quantidade de pessoas só faz sentido com todos os pacientes do lote
    juntos (um a um, cada linha caberia) e o impedimento de horário vale por
    profissional — por isso não é uma validação de linha."""
    por_grupo: dict[str, dict] = {}
    for data in registros:
        if not data.group_id:
            continue
        bloco = por_grupo.setdefault(data.group_id, {"pacientes": set(), "profissionais": set(), "datas": set()})
        bloco["pacientes"].add(data.patient_id)
        bloco["profissionais"].add(data.professional_id)
        bloco["datas"].add(data.service_date)

    erros = []
    for group_id, bloco in por_grupo.items():
        for professional_id in bloco["profissionais"]:
            for service_date in bloco["datas"]:
                try:
                    validar_grupo(
                        db, group_id=group_id, professional_id=professional_id,
                        service_date=service_date, patient_ids=bloco["pacientes"],
                    )
                except RegistroInvalido as e:
                    erros.append(str(e))
    return erros


def _gravar_lote(db: Session, lote: RegistroLote):
    erros = []
    vistos = set()
    # Regras do grupo (horário do profissional, quantidade de pessoas) valem
    # para o lote inteiro: um erro aqui barra a gravação toda, não uma linha.
    erros_de_grupo = _erros_de_grupo(db, lote.registros)
    if erros_de_grupo:
        return JSONResponse(status_code=400, content={"detail": erros_de_grupo[0], "erros": []})
    for i, data in enumerate(lote.registros):
        # Na digitação em lote o atendimento em grupo só entra dentro de um grupo.
        if not data.group_id and eh_proc_grupo(db, data.procedure_id):
            erros.append({"linha": i, "mensagem": MSG_PROC_GRUPO_SEM_GRUPO})
            continue
        try:
            validar_registro(
                db, service_month=data.service_month, service_date=data.service_date,
                patient_id=data.patient_id, professional_id=data.professional_id,
                procedure_id=data.procedure_id, vistos=vistos,
                group_id=data.group_id,
            )
        except RegistroInvalido as e:
            erros.append({"linha": i, "mensagem": str(e)})
    if erros:
        return JSONResponse(
            status_code=400,
            content={"detail": f"{len(erros)} linha(s) com erro. Nada foi salvo.", "erros": erros},
        )
    criados = RegistroService.criar_varios(db, lote.registros)
    return {"criados": len(criados)}


@router.put("/{registro_id}", response_model=RegistroResposta)
def atualizar_registro(registro_id: str, data: RegistroAtualizar, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin", "operador")
    atual = RegistroService.obter_por_id(db, registro_id)
    if not atual:
        raise HTTPException(status_code=404, detail="Registro não encontrado")

    update_data = data.model_dump(exclude_unset=True)
    with TRAVA_GRAVACAO:
        return _validar_e_atualizar(db, registro_id, atual, data, update_data)


def _validar_e_atualizar(db: Session, registro_id: str, atual, data: RegistroAtualizar, update_data: dict):
    _validar(db, SimpleNamespace(
        service_month=update_data.get("service_month", atual.service_month),
        service_date=update_data.get("service_date", atual.service_date),
        patient_id=update_data.get("patient_id", atual.patient_id),
        professional_id=update_data.get("professional_id", atual.professional_id),
        procedure_id=update_data.get("procedure_id", atual.procedure_id),
        group_id=update_data.get("group_id", atual.group_id),
    ), excluir_id=registro_id)

    reg = RegistroService.atualizar(db, registro_id, data)
    return reg


@router.delete("/{registro_id}")
def deletar_registro(registro_id: str, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    success = RegistroService.deletar(db, registro_id)
    if not success:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    return {"mensagem": "Registro excluído com sucesso"}


@router.post("/deletar-varios")
def deletar_varios(ids: List[str], request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    count = RegistroService.deletar_varios(db, ids)
    return {"mensagem": f"{count} registro(s) excluído(s)"}
