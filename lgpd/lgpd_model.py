"""
Modelos LGPD: solicitações de titulares (art. 18) e incidentes de segurança (art. 48).
"""
import uuid as uuid_lib
from sqlalchemy import Column, String, DateTime, Text, Boolean
from sqlalchemy.sql import func
from database import Base
from sistema.escopo import EscopoUnidade


class SolicitacaoTitular(EscopoUnidade, Base):
    __tablename__ = "lgpd_solicitacoes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    paciente_id = Column(String(36), nullable=True, index=True)
    titular_nome = Column(String(200), nullable=False)  # guardado à parte: sobrevive à anonimização
    tipo = Column(String(30), nullable=False)
    descricao = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="aberta", index=True)  # aberta, atendida, negada
    solicitada_em = Column(DateTime(timezone=True), server_default=func.now())
    prazo_em = Column(DateTime(timezone=True), nullable=False)
    resolvida_em = Column(DateTime(timezone=True), nullable=True)
    resolvida_por = Column(String(100), nullable=True)
    resposta = Column(Text, nullable=True)
    registrada_por = Column(String(100), nullable=True)


class IncidenteSeguranca(EscopoUnidade, Base):
    __tablename__ = "lgpd_incidentes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    ocorrido_em = Column(String(10), nullable=False)  # YYYY-MM-DD
    descricao = Column(Text, nullable=False)
    dados_afetados = Column(Text, nullable=True)
    titulares_afetados = Column(String(50), nullable=True)
    risco = Column(String(10), nullable=False, default="baixo")  # baixo, medio, alto
    medidas = Column(Text, nullable=True)
    comunicado_anpd = Column(Boolean, default=False)
    comunicado_titulares = Column(Boolean, default=False)
    registrado_por = Column(String(100), nullable=True)
    registrado_em = Column(DateTime(timezone=True), server_default=func.now())
