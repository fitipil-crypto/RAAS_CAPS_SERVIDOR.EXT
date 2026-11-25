"""
Rotas frontend LGPD: política de privacidade (pública), primeiro acesso e painel de conformidade.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from lgpd.lgpd_schema import TIPOS_SOLICITACAO
from lgpd.lgpd_service import LgpdService, TERMO_VERSAO
from paciente.paciente_schema import BASES_LEGAIS
from sistema import seguranca
from usuario.usuario_service import UsuarioService
from sistema.templates import templates

router = APIRouter(tags=["Frontend - LGPD"])


def _usuario_atual(request: Request, db: Session):
    user_id = request.session.get("user_id")
    return UsuarioService.obter_por_id(db, user_id) if user_id else None


@router.get("/privacidade", response_class=HTMLResponse)
def page_privacidade(request: Request, db: Session = Depends(get_db)):
    """Aviso de privacidade — público, acessível também sem login."""
    return templates.TemplateResponse(request, "privacidade.html", {
        "user": _usuario_atual(request, db),
        "lgpd": LgpdService.obter_config(db),
        "bases_legais": BASES_LEGAIS,
        "termo_versao": TERMO_VERSAO,
    })


@router.get("/primeiro-acesso", response_class=HTMLResponse)
def page_primeiro_acesso(request: Request, db: Session = Depends(get_db)):
    user = _usuario_atual(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not LgpdService.primeiro_acesso_pendente(user):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "primeiro_acesso.html", {
        "user": None,  # layout sem menu lateral
        "usuario": user,
        "lgpd": LgpdService.obter_config(db),
        "termo_versao": TERMO_VERSAO,
        "troca_obrigatoria": bool(user.must_change_password),
        "senha_regra": seguranca.MSG_SENHA,
    })


@router.get("/lgpd", response_class=HTMLResponse)
def page_lgpd(request: Request, db: Session = Depends(get_db)):
    user = _usuario_atual(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role not in ("admin", "coordenador"):
        return RedirectResponse(url="/", status_code=302)

    https = request.url.scheme == "https" or (
        seguranca.confiar_proxy() and request.headers.get("x-forwarded-proto", "").lower() == "https"
    )
    config = LgpdService.obter_config(db)
    sem_termo = LgpdService.contar_usuarios_sem_termo(db)
    verificacoes = [
        ("Conexão HTTPS", https, "Em rede, acesse sempre por HTTPS (veja docs/LGPD.md)."),
        ("Cookie de sessão seguro (COOKIE_SECURE)", seguranca.cookie_seguro(), "Defina COOKIE_SECURE=true ao usar HTTPS."),
        ("Encarregado (DPO) informado", bool(config["encarregado_nome"] and config["encarregado_email"]), "Preencha o encarregado abaixo (art. 41)."),
        ("Todos os usuários aceitaram o termo vigente", sem_termo == 0, f"{sem_termo} usuário(s) ainda não aceitaram."),
    ]
    return templates.TemplateResponse(request, "lgpd.html", {
        "user": user,
        "lgpd": config,
        "tipos": TIPOS_SOLICITACAO,
        "verificacoes": verificacoes,
        "active_page": "lgpd",
    })
