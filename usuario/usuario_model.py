"""
Modelo de dados para usuários do sistema.
"""
import uuid as uuid_lib
from sqlalchemy import Column, String, Boolean, DateTime, Integer
from sqlalchemy.sql import func
from database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    username = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="operador")
    """admin, gestor, coordenador, operador.

    ``gestor`` existe por causa do servidor multiunidade: é quem acompanha
    mais de um CAPS (coordenação da rede, apoio à gestão municipal) e pode
    alternar entre unidades ou usar a visão "Todas as unidades", sem ter os
    poderes de administração do sistema que o ``admin`` tem.
    """
    password_hash = Column(String(255), nullable=False)
    active = Column(Boolean, default=True)
    help_enabled = Column(Boolean, default=True, nullable=True)  # ícones "i" e tutoriais
    last_login = Column(DateTime(timezone=True), nullable=True)
    # Lotação: a unidade (CAPS) deste usuário. Vazio só faz sentido para
    # admin/gestor, que circulam por todas. Esta tabela de propósito NÃO usa
    # o mixin EscopoUnidade: o login acontece antes de haver unidade ativa,
    # e filtrar os usuários pelo escopo impediria qualquer um de entrar.
    unidade_id = Column(String(36), nullable=True, index=True)
    # Segurança / LGPD
    must_change_password = Column(Boolean, default=False, nullable=True)
    senha_alterada_em = Column(DateTime(timezone=True), nullable=True)
    failed_logins = Column(Integer, default=0, nullable=True)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    termo_versao = Column(String(20), nullable=True)  # versão do termo de uso/confidencialidade aceito
    termo_aceito_em = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    @property
    def ajuda_ativa(self) -> bool:
        """Ajuda (ícones "i" e tutoriais) liberada; o admin sempre a tem."""
        return self.role == "admin" or self.help_enabled is not False

    def __repr__(self):
        return f"<Usuario(username='{self.username}', role='{self.role}')>"
