"""
Rotas da API para usuários.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from sistema.auth import require_auth, require_role
from usuario.usuario_schema import (
    UsuarioResposta, UsuarioCriar, UsuarioAtualizar, SenhaAtualizar, AjudaEmLote
)
from usuario.usuario_service import UsuarioService

router = APIRouter(prefix="/api/usuarios", tags=["Usuários"])


def _resolver_unidade(db: Session, perfil: str | None, unidade_id: str | None) -> str | None:
    """Decide em que unidade o usuário fica lotado; devolve o valor a gravar.

    coordenador e operador só enxergam a unidade da sua lotação: sem ela, o
    usuário entraria no sistema e não veria paciente nenhum — um "não funciona"
    difícil de diagnosticar. Mas também não faz sentido obrigar a escolher onde
    não há escolha: com uma única unidade cadastrada — o caso de quem só tem um
    CAPS — a lotação é preenchida sozinha. A pergunta só aparece quando existe
    mais de uma unidade, que é quando ela realmente importa.

    admin e gestor circulam por todas, então para eles a lotação é opcional e
    fica como vier.
    """
    from unidade.unidade_service import PERFIS_MULTIUNIDADE, UnidadeService

    if unidade_id and not UnidadeService.obter_por_id(db, unidade_id):
        raise HTTPException(status_code=400, detail="Unidade não encontrada.")
    if perfil in PERFIS_MULTIUNIDADE:
        return unidade_id or None
    if unidade_id:
        return unidade_id

    ativas = UnidadeService.listar(db, apenas_ativas=True)
    if not ativas:
        return None  # primeira instalação: ainda não há unidade para lotar
    if len(ativas) == 1:
        return ativas[0].id
    raise HTTPException(
        status_code=400,
        detail=(
            "Escolha a unidade (CAPS) deste usuário. Só os perfis admin e gestor "
            "atendem todas as unidades."
        ),
    )


@router.get("/", response_model=List[UsuarioResposta])
def listar_usuarios(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    return UsuarioService.listar_todos(db)


@router.post("/ajuda")
def definir_ajuda_em_lote(data: AjudaEmLote, request: Request, db: Session = Depends(get_db)):
    """Admin: liga/desliga a ajuda (ícones "i" e tutoriais) de todos os demais usuários."""
    require_role(request, db, "admin")
    alterados = UsuarioService.definir_ajuda_em_lote(db, data.enabled)
    return {"alterados": alterados, "enabled": data.enabled}


@router.get("/{user_id}", response_model=UsuarioResposta)
def obter_usuario(user_id: str, request: Request, db: Session = Depends(get_db)):
    current_user_id = require_auth(request)
    if current_user_id != user_id:
        require_role(request, db, "admin")
    user = UsuarioService.obter_por_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user


@router.post("/", response_model=UsuarioResposta)
def criar_usuario(data: UsuarioCriar, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    data = data.model_copy(update={"unidade_id": _resolver_unidade(db, data.role, data.unidade_id)})
    try:
        return UsuarioService.criar(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{user_id}", response_model=UsuarioResposta)
def atualizar_usuario(user_id: str, data: UsuarioAtualizar, request: Request, db: Session = Depends(get_db)):
    current_user_id = require_auth(request)
    current_user = UsuarioService.obter_por_id(db, current_user_id)
    if current_user_id != user_id and (not current_user or current_user.role != "admin"):
        raise HTTPException(status_code=403, detail="Acesso negado")
    if not current_user or current_user.role != "admin":
        # Usuário comum só pode alterar o próprio nome, nunca o próprio perfil/status
        # nem a unidade em que está lotado.
        data = UsuarioAtualizar(name=data.name)
    else:
        atual = UsuarioService.obter_por_id(db, user_id)
        perfil = data.role if data.role is not None else (atual.role if atual else None)
        unidade = data.unidade_id if data.unidade_id is not None else (atual.unidade_id if atual else None)
        data = data.model_copy(update={"unidade_id": _resolver_unidade(db, perfil, unidade)})
    user = UsuarioService.atualizar(db, user_id, data)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user


@router.post("/{user_id}/senha")
def alterar_senha(user_id: str, data: SenhaAtualizar, request: Request, db: Session = Depends(get_db)):
    current_user_id = require_auth(request)
    current_user = UsuarioService.obter_por_id(db, current_user_id)
    if current_user_id != user_id and (not current_user or current_user.role != "admin"):
        raise HTTPException(status_code=403, detail="Acesso negado")
    if current_user_id == user_id and not data.current_password:
        raise HTTPException(status_code=400, detail="Senha atual é obrigatória")
    try:
        success = UsuarioService.alterar_senha(db, user_id, data, redefinida_por_admin=current_user_id != user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        return {"mensagem": "Senha alterada com sucesso"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{user_id}")
def deletar_usuario(user_id: str, request: Request, db: Session = Depends(get_db)):
    current_user_id = require_auth(request)
    if current_user_id == user_id:
        raise HTTPException(status_code=400, detail="Não é possível excluir o próprio usuário")
    require_role(request, db, "admin")
    success = UsuarioService.deletar(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return {"mensagem": "Usuário excluído com sucesso"}
