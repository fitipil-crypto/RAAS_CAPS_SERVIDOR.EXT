"""
Schemas Pydantic para eventos.
"""
from pydantic import ConfigDict, BaseModel, Field
from typing import Optional, List
from datetime import datetime


class EventoBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Nome do evento")
    event_date: str = Field(..., description="Data do evento YYYY-MM-DD")
    notes: Optional[str] = None


class EventoCriar(EventoBase):
    pass


class EventoAtualizar(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    event_date: Optional[str] = None
    notes: Optional[str] = None


class EventoResposta(EventoBase):
    id: str
    service_month: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class EventoPacientesAdicionar(BaseModel):
    patient_ids: List[str] = Field(..., min_length=1)


class ProcedimentoEvento(BaseModel):
    procedure_id: str
    quantity: int = Field(default=1, ge=1)


class EventoLancamento(BaseModel):
    """Lançamento em lote: cada procedimento é cruzado com cada profissional,
    para todos os pacientes da lista do evento."""
    procedures: List[ProcedimentoEvento] = Field(..., min_length=1, max_length=5)
    professional_ids: List[str] = Field(..., min_length=1, max_length=10)
    local_realizacao: str = Field(default="C")
    service_type: str = Field(default="02")  # 02 = Grupo
    srv: str = Field(default="115")
    cls: str = Field(default="002")
