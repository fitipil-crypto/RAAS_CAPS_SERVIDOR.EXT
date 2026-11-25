"""
Modelos de dados para eventos da unidade.

Um evento (festa junina, dia das crianças etc.) agrupa muitos pacientes e
serve para lançar os mesmos procedimentos/profissionais para todos de uma
vez. Os registros gerados são Registros RAAS normais — o evento guarda
apenas a lista de participantes e a identificação da atividade.
"""
import uuid as uuid_lib
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from database import Base
from sistema.escopo import EscopoUnidade


class Evento(EscopoUnidade, Base):
    __tablename__ = "eventos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    name = Column(String(120), nullable=False)
    event_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    service_month = Column(String(7), nullable=False, index=True)  # YYYY-MM (competência)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Evento(name='{self.name}', date='{self.event_date}')>"


class EventoRegistro(EscopoUnidade, Base):
    """Liga cada Registro RAAS ao evento que o gerou.

    Tabela à parte em vez de uma coluna em registros_raas: não altera a
    tabela existente (o SQLite não ganha colunas novas pelo create_all) e
    permite apagar na exclusão do evento exatamente os registros que ele
    criou — nunca os que já existiam e foram ignorados no lançamento.
    """

    __tablename__ = "evento_registros"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    event_id = Column(String(36), nullable=False, index=True)
    registro_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<EventoRegistro(event='{self.event_id}', registro='{self.registro_id}')>"


class EventoPaciente(EscopoUnidade, Base):
    __tablename__ = "evento_pacientes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    event_id = Column(String(36), nullable=False, index=True)
    patient_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<EventoPaciente(event='{self.event_id}', patient='{self.patient_id}')>"
