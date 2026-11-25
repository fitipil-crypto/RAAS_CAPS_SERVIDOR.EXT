"""
Schemas Pydantic para grupos de atendimento.
"""
import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_DESCRICAO = 30
MAX_PESSOAS = 30


def _validar_data(valor: str) -> str:
    try:
        datetime.strptime(valor, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError("Data do grupo inválida (use AAAA-MM-DD)")
    return valor


def _validar_hora(valor: str) -> str:
    """Aceita HH:MM (24 h). '8:00' vira '08:00'."""
    if not re.fullmatch(r"\d{1,2}:\d{2}", valor or ""):
        raise ValueError("Horário do grupo inválido (use HH:MM)")
    hora, minuto = (int(p) for p in valor.split(":"))
    if hora > 23 or minuto > 59:
        raise ValueError("Horário do grupo inválido (use HH:MM)")
    return f"{hora:02d}:{minuto:02d}"


class GrupoBase(BaseModel):
    description: str = Field(..., min_length=1, max_length=MAX_DESCRICAO, description="Descrição do grupo")
    group_date: str = Field(..., description="Data do grupo AAAA-MM-DD")
    group_time: str = Field(..., description="Horário do grupo HH:MM")
    people_count: int = Field(default=1, ge=1, le=MAX_PESSOAS, description="Quantidade de pessoas")

    @field_validator("description")
    @classmethod
    def _descricao_sem_espacos_nas_pontas(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Informe a descrição do grupo")
        return v

    _data = field_validator("group_date")(_validar_data)
    _hora = field_validator("group_time")(_validar_hora)


class GrupoCriar(GrupoBase):
    pass


class GrupoAtualizar(BaseModel):
    description: Optional[str] = Field(default=None, min_length=1, max_length=MAX_DESCRICAO)
    group_date: Optional[str] = None
    group_time: Optional[str] = None
    people_count: Optional[int] = Field(default=None, ge=1, le=MAX_PESSOAS)

    @field_validator("group_date")
    @classmethod
    def _data(cls, v):
        return None if v is None else _validar_data(v)

    @field_validator("group_time")
    @classmethod
    def _hora(cls, v):
        return None if v is None else _validar_hora(v)


class GrupoResposta(GrupoBase):
    id: str
    service_month: str
    numero: int = Field(default=0, description="Posição do grupo na competência (por data e horário)")
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RegistroDoGrupo(BaseModel):
    """Um atendimento lançado no grupo, já com os nomes para exibição."""
    id: str
    patient_id: str
    patient_name: str
    patient_prontuario: Optional[str] = None
    procedure_id: str
    procedure_code: Optional[str] = None
    procedure_name: str
    professional_id: Optional[str] = None
    professional_name: str
    quantity: int = 1


class PacienteDoGrupo(BaseModel):
    patient_id: str
    patient_name: str
    patient_prontuario: Optional[str] = None
    registros: List[RegistroDoGrupo] = []


class GrupoDetalhe(GrupoResposta):
    pacientes: List[PacienteDoGrupo] = []
    total_registros: int = 0
