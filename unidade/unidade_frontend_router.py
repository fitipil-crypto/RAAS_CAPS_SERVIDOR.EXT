"""
Rotas frontend das unidades (CAPS).
"""
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from sistema.templates import templates
from unidade import modalidades
from unidade.unidade_service import UnidadeService
from usuario.usuario_service import UsuarioService

router = APIRouter(tags=["Frontend - Unidades"])


@router.get("/unidades", response_class=HTMLResponse)
def page_unidades(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role not in ("admin", "gestor"):
        return RedirectResponse(url="/", status_code=302)

    unidades = UnidadeService.listar(db)
    return templates.TemplateResponse(request, "unidades.html", {
        "user": user,
        "unidades": [UnidadeService.para_resposta(u) for u in unidades],
        "modalidades": [modalidades.resumo(m.codigo) for m in modalidades.listar()],
        "totais": UnidadeService.totais_por_unidade(db),
        "active_page": "unidades",
    })


@router.post("/unidades/ativa")
def trocar_unidade(
    request: Request, unidade_id: str = Form(...), db: Session = Depends(get_db)
):
    """Troca de unidade pelo seletor da barra superior (formulário, com CSRF)."""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)

    if unidade_id == "todas":
        if UnidadeService.pode_ver_todas(user):
            request.session.pop("unidade_id", None)
    else:
        permitidas = {u.id for u in UnidadeService.unidades_do_usuario(db, user)}
        if unidade_id in permitidas:
            request.session["unidade_id"] = unidade_id

    # Volta para a página de onde veio, mas só se for um caminho deste sistema:
    # repassar o Referer inteiro abriria um redirecionamento para fora.
    destino = request.headers.get("referer") or "/"
    if not destino.startswith("/"):
        caminho = urlparse(destino).path or "/"
        destino = caminho if caminho.startswith("/") else "/"
    return RedirectResponse(url=destino, status_code=303)
