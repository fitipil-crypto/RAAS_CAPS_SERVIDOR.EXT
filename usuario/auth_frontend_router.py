"""
Rotas de login e logout.
"""
import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from sistema.log_service import LogService
from sistema.templates import templates
from usuario.usuario_service import UsuarioService

router = APIRouter(tags=["Frontend - Autenticação"])


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


# Rota síncrona de propósito: a conferência da senha (bcrypt) leva ~0,5 s e,
# numa rota async, pararia o servidor inteiro durante cada login. Assim ela
# roda no pool de threads e os demais usuários seguem sendo atendidos.
@router.post("/login")
def login_submit(request: Request, username: str = Form(""), password: str = Form(""),
                 db: Session = Depends(get_db)):

    alvo = UsuarioService.obter_por_username(db, username)
    bloqueado = bool(alvo and UsuarioService.esta_bloqueado(alvo))
    user = UsuarioService.autenticar(db, username, password)
    if not user:
        LogService.registrar(
            db, action="LOGIN", username=username[:100], method="POST", path="/login", status_code=401,
            details="Conta bloqueada por tentativas excessivas" if bloqueado else "Credenciais inválidas",
        )
        # Mensagem única: não revela se o usuário existe nem se está bloqueado.
        return templates.TemplateResponse(request, "login.html", {
            "error": "Usuário ou senha inválidos, ou conta temporariamente bloqueada"
        })

    request.session.clear()  # nova sessão a cada login (evita fixação de sessão)
    request.session["user_id"] = user.id
    request.session["ultima_atividade"] = time.time()
    UsuarioService.atualizar_ultimo_login(db, user.id)
    LogService.registrar(db, action="LOGIN", user_id=user.id, username=user.username, method="POST", path="/login", status_code=200, details="Login bem-sucedido")
    return RedirectResponse(url="/", status_code=302)


@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    username = None
    if user_id:
        user = UsuarioService.obter_por_id(db, user_id)
        if user:
            username = user.username
    LogService.registrar(db, action="LOGOUT", user_id=user_id, username=username, method="GET", path="/logout", status_code=200, details="Logout")
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
