"""
Schemas Pydantic para validação de usuários.
"""
from pydantic import ConfigDict, BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

from sistema.seguranca import validar_senha

# Perfis aceitos. ``gestor`` é da edição servidor: acompanha mais de uma unidade
# (lê relatórios e auditoria de qualquer CAPS, alterna entre unidades) sem os
# poderes de administração do sistema. Até aqui o perfil era texto livre, e um
# erro de digitação criava um usuário sem acesso a nada.
PERFIS = ("admin", "gestor", "coordenador", "operador")


def _validar_perfil(valor: str) -> str:
    valor = (valor or "").strip().lower()
    if valor not in PERFIS:
        raise ValueError(f"Perfil inválido. Use um de: {', '.join(PERFIS)}")
    return valor


class UsuarioBase(BaseModel):
    username: str = Field(..., min_length=1, max_length=100, description="Login do usuário")
    name: str = Field(..., min_length=1, max_length=200, description="Nome completo")
    role: str = Field(default="operador", description="Perfil: admin, gestor, coordenador ou operador")
    active: bool = Field(default=True, description="Usuário ativo")
    help_enabled: bool = Field(default=True, description="Ajuda (ícones i e tutoriais) liberada")
    unidade_id: Optional[str] = Field(
        default=None,
        description="Unidade (CAPS) do usuário. Vazio só para admin/gestor, que veem todas.",
    )

    @field_validator("help_enabled", mode="before")
    @classmethod
    def _help_nulo_e_ativo(cls, v):
        return True if v is None else v

    @field_validator("role")
    @classmethod
    def _perfil_conhecido(cls, v):
        return _validar_perfil(v)


class UsuarioCriar(UsuarioBase):
    password: str = Field(..., description="Senha (mínimo 6 caracteres, com letras e números)")

    _senha_forte = field_validator("password")(lambda cls, v: validar_senha(v))


class UsuarioAtualizar(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    help_enabled: Optional[bool] = None
    unidade_id: Optional[str] = None

    @field_validator("role")
    @classmethod
    def _perfil_conhecido(cls, v):
        return _validar_perfil(v) if v not in (None, "") else v


class AjudaEmLote(BaseModel):
    enabled: bool


class SenhaAtualizar(BaseModel):
    current_password: Optional[str] = Field(None, description="Senha atual (obrigatório para próprio usuário)")
    new_password: str = Field(..., description="Nova senha (mínimo 6 caracteres, com letras e números)")
    confirm_password: str = Field(..., description="Confirmação da nova senha")

    _senha_forte = field_validator("new_password")(lambda cls, v: validar_senha(v))


class UsuarioResposta(UsuarioBase):
    id: str
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
