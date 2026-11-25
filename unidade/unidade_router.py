"""
Rotas da API para unidades (CAPS) e para a escolha da unidade ativa.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from sistema.auth import require_auth, require_role
from unidade import modalidades
from unidade.unidade_schema import (
    ModalidadeResposta,
    UnidadeAtualizar,
    UnidadeCriar,
    UnidadeResposta,
)
from unidade.unidade_service import UnidadeInvalida, UnidadeService

router = APIRouter(prefix="/api/unidades", tags=["Unidades"])


@router.get("/modalidades", response_model=list[ModalidadeResposta])
def listar_modalidades(request: Request):
    """As 7 modalidades de CAPS com seus parâmetros de referência."""
    require_auth(request)
    return [modalidades.resumo(m.codigo) for m in modalidades.listar()]


@router.get("/", response_model=list[UnidadeResposta])
def listar_unidades(request: Request, apenas_ativas: bool = False, db: Session = Depends(get_db)):
    """Unidades que o usuário logado pode acessar."""
    user_id = require_auth(request)
    from usuario.usuario_service import UsuarioService

    usuario = UsuarioService.obter_por_id(db, user_id)
    unidades = UnidadeService.unidades_do_usuario(db, usuario)
    if not apenas_ativas and UnidadeService.pode_ver_todas(usuario):
        unidades = UnidadeService.listar(db)
    return [UnidadeService.para_resposta(u) for u in unidades]


@router.get("/ativa")
def obter_unidade_ativa(request: Request, db: Session = Depends(get_db)):
    """Qual unidade está valendo nesta sessão (None = todas as unidades)."""
    require_auth(request)
    unidade = UnidadeService.obter_por_id(db, request.session.get("unidade_id"))
    if not unidade:
        return {"unidade_id": None, "nome": "Todas as unidades", "modalidade": None}
    return {
        "unidade_id": unidade.id,
        "nome": unidade.nome,
        "modalidade": unidade.modalidade,
        "modalidade_nome": modalidades.nome(unidade.modalidade),
    }


@router.post("/ativa/{unidade_id}")
def trocar_unidade_ativa(unidade_id: str, request: Request, db: Session = Depends(get_db)):
    """Troca a unidade da sessão.

    ``unidade_id`` igual a ``todas`` volta para a visão geral, permitida só a
    admin e gestor. A permissão é reconferida aqui e, a cada requisição, no
    middleware: a sessão guarda a escolha, não a autorização.
    """
    user_id = require_auth(request)
    from usuario.usuario_service import UsuarioService

    usuario = UsuarioService.obter_por_id(db, user_id)

    if unidade_id == "todas":
        if not UnidadeService.pode_ver_todas(usuario):
            raise HTTPException(403, "Seu perfil atende uma unidade por vez.")
        request.session.pop("unidade_id", None)
        return {"unidade_id": None, "nome": "Todas as unidades"}

    permitidas = {u.id for u in UnidadeService.unidades_do_usuario(db, usuario)}
    if unidade_id not in permitidas:
        raise HTTPException(403, "Você não tem acesso a esta unidade.")
    request.session["unidade_id"] = unidade_id
    unidade = UnidadeService.obter_por_id(db, unidade_id)
    return {"unidade_id": unidade.id, "nome": unidade.nome, "modalidade": unidade.modalidade}


@router.get("/{unidade_id}", response_model=UnidadeResposta)
def obter_unidade(unidade_id: str, request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    unidade = UnidadeService.obter_por_id(db, unidade_id)
    if not unidade:
        raise HTTPException(404, "Unidade não encontrada")
    return UnidadeService.para_resposta(unidade)


@router.post("/", response_model=UnidadeResposta)
def criar_unidade(dados: UnidadeCriar, request: Request, db: Session = Depends(get_db)):
    """Cadastra uma unidade. Só o admin: criar unidade abre um novo escopo de dados."""
    require_role(request, db, "admin")
    try:
        unidade = UnidadeService.criar(db, dados)
    except UnidadeInvalida as erro:
        raise HTTPException(400, str(erro)) from erro
    return UnidadeService.para_resposta(unidade)


@router.put("/{unidade_id}", response_model=UnidadeResposta)
def atualizar_unidade(
    unidade_id: str, dados: UnidadeAtualizar, request: Request, db: Session = Depends(get_db)
):
    require_role(request, db, "admin")
    try:
        unidade = UnidadeService.atualizar(db, unidade_id, dados)
    except UnidadeInvalida as erro:
        raise HTTPException(400, str(erro)) from erro
    if not unidade:
        raise HTTPException(404, "Unidade não encontrada")
    return UnidadeService.para_resposta(unidade)


@router.delete("/{unidade_id}")
def desativar_unidade(unidade_id: str, request: Request, db: Session = Depends(get_db)):
    """Desativa a unidade (o histórico é preservado — ver UnidadeService.desativar)."""
    require_role(request, db, "admin")
    if not UnidadeService.desativar(db, unidade_id):
        raise HTTPException(404, "Unidade não encontrada")
    return {"mensagem": "Unidade desativada. O histórico dela foi preservado."}
