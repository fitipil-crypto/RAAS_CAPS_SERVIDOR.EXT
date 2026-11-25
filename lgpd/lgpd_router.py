"""
Rotas da API LGPD.
"""
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from lgpd.lgpd_schema import (
    PrimeiroAcesso, SolicitacaoCriar, SolicitacaoResolver, SolicitacaoResposta,
    IncidenteCriar, IncidenteResposta, ConfigLgpd, AnonimizarRequest,
)
from lgpd.lgpd_service import LgpdService, TERMO_VERSAO
from paciente.paciente_service import PacienteService
from sistema.auth import require_auth, require_role
from sistema.log_service import LogService
from usuario.usuario_service import UsuarioService

router = APIRouter(prefix="/api/lgpd", tags=["LGPD"])

PERFIS_GESTAO = ("admin", "coordenador")


def _solicitacao_resposta(sol) -> SolicitacaoResposta:
    resp = SolicitacaoResposta.model_validate(sol)
    resp.atrasada = LgpdService.atrasada(sol)
    return resp


@router.post("/primeiro-acesso")
def primeiro_acesso(data: PrimeiroAcesso, request: Request, db: Session = Depends(get_db)):
    """Troca a senha inicial/temporária e registra o aceite do termo de uso."""
    user_id = require_auth(request)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    try:
        LgpdService.concluir_primeiro_acesso(db, user, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    LogService.registrar(
        db, action="TERMO", user_id=user.id, username=user.username, resource_type="usuario",
        resource_id=user.id, method="POST", path="/api/lgpd/primeiro-acesso", status_code=200,
        details=f"Aceite do termo de uso v{TERMO_VERSAO} e troca de senha",
    )
    return {"mensagem": "Acesso liberado"}


# ── Controlador / encarregado ──

@router.get("/config")
def obter_config(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_GESTAO)
    return LgpdService.obter_config(db)


@router.put("/config")
def salvar_config(data: ConfigLgpd, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    return LgpdService.salvar_config(db, data)


# ── Solicitações de titulares ──

@router.get("/solicitacoes", response_model=List[SolicitacaoResposta])
def listar_solicitacoes(request: Request, status: Optional[str] = None, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_GESTAO)
    return [_solicitacao_resposta(s) for s in LgpdService.listar_solicitacoes(db, status)]


@router.post("/solicitacoes", response_model=SolicitacaoResposta)
def criar_solicitacao(data: SolicitacaoCriar, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, *PERFIS_GESTAO)
    if data.paciente_id and not PacienteService.obter_por_id(db, data.paciente_id):
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    return _solicitacao_resposta(LgpdService.criar_solicitacao(db, data, user.username))


@router.put("/solicitacoes/{sol_id}", response_model=SolicitacaoResposta)
def resolver_solicitacao(sol_id: str, data: SolicitacaoResolver, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, *PERFIS_GESTAO)
    sol = LgpdService.resolver_solicitacao(db, sol_id, data, user.username)
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    return _solicitacao_resposta(sol)


# ── Dados do titular ──

@router.get("/titulares/{paciente_id}/exportar")
def exportar_titular(paciente_id: str, request: Request, db: Session = Depends(get_db)):
    """Cópia dos dados do titular em JSON (acesso e portabilidade). Auditada como EXPORT."""
    require_role(request, db, *PERFIS_GESTAO)
    paciente = PacienteService.obter_por_id(db, paciente_id)
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    conteudo = json.dumps(LgpdService.exportar_titular(db, paciente), ensure_ascii=False, indent=2, default=str)
    return Response(
        content=conteudo,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=titular_{paciente.id[:8]}_{datetime.now():%Y%m%d}.json"},
    )


@router.post("/titulares/{paciente_id}/anonimizar")
def anonimizar_titular(paciente_id: str, data: AnonimizarRequest, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, "admin")
    if data.confirm != "ANONIMIZAR":
        raise HTTPException(status_code=400, detail="Confirmação inválida. Digite ANONIMIZAR.")
    paciente = PacienteService.obter_por_id(db, paciente_id)
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    if paciente.anonimizado:
        raise HTTPException(status_code=400, detail="Paciente já anonimizado")
    LgpdService.anonimizar_paciente(db, paciente)
    if data.solicitacao_id:
        LgpdService.resolver_solicitacao(
            db, data.solicitacao_id,
            SolicitacaoResolver(status="atendida", resposta="Dados anonimizados"), user.username,
        )
    LogService.registrar(
        db, action="ANONIMIZAR", user_id=user.id, username=user.username, resource_type="paciente",
        resource_id=paciente_id, method="POST", path=f"/api/lgpd/titulares/{paciente_id}/anonimizar",
        status_code=200, details="Paciente anonimizado (LGPD art. 18, IV)",
    )
    return {"mensagem": "Paciente anonimizado"}


# ── Incidentes de segurança ──

@router.get("/incidentes", response_model=List[IncidenteResposta])
def listar_incidentes(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, *PERFIS_GESTAO)
    return LgpdService.listar_incidentes(db)


@router.post("/incidentes", response_model=IncidenteResposta)
def criar_incidente(data: IncidenteCriar, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, "admin")
    return LgpdService.criar_incidente(db, data, user.username)
