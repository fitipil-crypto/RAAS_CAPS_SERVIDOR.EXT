"""
Modelo de dados dos grupos de atendimento.

Um grupo é uma sessão coletiva realizada na competência: tem descrição,
data, horário e quantidade de pessoas. Os atendimentos lançados nele são
Registros RAAS normais, apontando para o grupo por ``group_id``.

O número do grupo (Grupo nº 1, nº 2, ...) não é gravado: ele é calculado
pela ordem de data e horário dentro da competência (e, no empate, pela
ordem de criação), de modo que um grupo lançado depois, mas com data
anterior, entre na posição certa sem precisar renumerar os outros.
"""
import uuid as uuid_lib
from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.sql import func
from database import Base
from sistema.escopo import EscopoUnidade


class Grupo(EscopoUnidade, Base):
    __tablename__ = "grupos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    service_month = Column(String(7), nullable=False, index=True)  # competência YYYY-MM
    description = Column(String(30), nullable=False)  # até 30 caracteres
    group_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    group_time = Column(String(5), nullable=False)  # HH:MM
    people_count = Column(Integer, nullable=False, default=1)
    # Desempate da numeração entre grupos com a mesma data e horário: dois
    # grupos criados no mesmo segundo empatariam em created_at (o CURRENT_TIMESTAMP
    # do SQLite só tem segundos) e trocariam de número a cada consulta.
    created_seq = Column(Integer, nullable=False, default=0, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Grupo(desc='{self.description}', data='{self.group_date} {self.group_time}')>"
