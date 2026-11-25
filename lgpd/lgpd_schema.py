"""
Schemas Pydantic do módulo LGPD.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sistema.seguranca import validar_senha

TIPOS_SOLICITACAO = {
    "confirmacao": "Confirmação de tratamento",
    "acesso": "Acesso aos dados",
    "correcao": "Correção de dados",
    "anonimizacao": "Anonimização, bloqueio ou eliminação",
    "portabilidade": "Portabilidade",
    "compartilhamento": "Informação sobre compartilhamento",
    "revogacao": "Revogação de consentimento",
    "oposicao": "Oposição ao tratamento",
}


class PrimeiroAcesso(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str
    aceite: bool = Field(..., description="Aceite do termo de uso e confidencialidade")

    @field_validator("new_password")
    @classmethod
    def _senha_forte(cls, v):
        return validar_senha(v)


class SolicitacaoCriar(BaseModel):
    paciente_id: Optional[str] = None
    titular_nome: str = Field(..., min_length=1, max_length=200)
    tipo: str
    descricao: Optional[str] = None

    @field_validator("tipo")
    @classmethod
    def _tipo_valido(cls, v):
        if v not in TIPOS_SOLICITACAO:
            raise ValueError("Tipo de solicitação inválido")
        return v


class SolicitacaoResolver(BaseModel):
    status: str
    resposta: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _status_valido(cls, v):
        if v not in ("atendida", "negada"):
            raise ValueError("Status deve ser 'atendida' ou 'negada'")
        return v


class SolicitacaoResposta(BaseModel):
    id: str
    paciente_id: Optional[str] = None
    titular_nome: str
    tipo: str
    descricao: Optional[str] = None
    status: str
    solicitada_em: Optional[datetime] = None
    prazo_em: datetime
    resolvida_em: Optional[datetime] = None
    resolvida_por: Optional[str] = None
    resposta: Optional[str] = None
    atrasada: bool = False

    model_config = ConfigDict(from_attributes=True)


class IncidenteCriar(BaseModel):
    ocorrido_em: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    descricao: str = Field(..., min_length=3)
    dados_afetados: Optional[str] = None
    titulares_afetados: Optional[str] = None
    risco: str = "baixo"
    medidas: Optional[str] = None
    comunicado_anpd: bool = False
    comunicado_titulares: bool = False

    @field_validator("risco")
    @classmethod
    def _risco_valido(cls, v):
        if v not in ("baixo", "medio", "alto"):
            raise ValueError("Risco deve ser baixo, medio ou alto")
        return v


class IncidenteResposta(IncidenteCriar):
    id: str
    registrado_por: Optional[str] = None
    registrado_em: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ConfigLgpd(BaseModel):
    controlador_nome: Optional[str] = None
    controlador_cnpj: Optional[str] = None
    encarregado_nome: Optional[str] = None
    encarregado_email: Optional[str] = None
    encarregado_telefone: Optional[str] = None


class AnonimizarRequest(BaseModel):
    confirm: str
    solicitacao_id: Optional[str] = None
