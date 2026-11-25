"""
Rotas frontend para a tela de tutoriais.
"""
import re

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from markupsafe import Markup, escape
from sqlalchemy.orm import Session

from database import get_db
from usuario.usuario_service import UsuarioService
from ajuda.ajuda_conteudo import SECOES, FLUXO, PERFIS
from sistema.templates import templates

router = APIRouter(tags=["Frontend - Ajuda"])


def _fmt(texto: str) -> Markup:
    """Escapa o texto e aplica **negrito**, `código` e [[Tecla]]."""
    html = str(escape(texto))
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
    html = re.sub(r"\[\[(.+?)\]\]", r"<kbd>\1</kbd>", html)
    return Markup(html)


@router.get("/tutoriais", response_class=HTMLResponse)
def page_tutoriais(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    # O administrador pode desligar a ajuda de um usuário.
    if not user.ajuda_ativa:
        return RedirectResponse(url="/", status_code=302)


    secoes = []
    for s in SECOES:
        secoes.append({
            **s,
            "resumo": _fmt(s["resumo"]),
            "passos": [_fmt(p) for p in s["passos"]],
            "dica": _fmt(s["dica"]) if s.get("dica") else None,
            "acessivel": user.role in s["perfis"],
            "perfis_rotulos": [PERFIS[p] for p in s["perfis"]],
        })

    return templates.TemplateResponse(request, "tutoriais.html", {
        "user": user,
        "secoes": secoes,
        "fluxo": FLUXO,
        "active_page": "tutoriais",
    })
