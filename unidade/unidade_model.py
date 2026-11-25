"""
Modelo da unidade (um CAPS) e seus dados de estabelecimento.

Esta tabela é o registro das unidades e, por isso, *não* herda
``EscopoUnidade``: é ela que define o escopo, então filtrá-la por unidade
impediria qualquer um de trocar de unidade ou de listar as existentes.

Os campos de estabelecimento (CNES, UF, órgão, CNPJ, versão do layout) ficam
aqui e não mais em ``configuracoes``, porque no servidor multiunidade cada CAPS
exporta o seu próprio arquivo RAAS com o seu próprio CNES. A tabela
``configuracoes`` continua existindo para o que é do sistema inteiro, e
``ConfigService.get_config_estabelecimento`` sobrepõe os valores da unidade
ativa aos daquela tabela — assim exportação, relatórios e auditoria passaram a
usar o CNES certo sem precisar de alteração.
"""
import uuid as uuid_lib

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from database import Base

# Chaves de `configuracoes` que a unidade passa a responder (ver ConfigService).
CAMPOS_ESTABELECIMENTO = (
    "uf_code",
    "cnes_code",
    "organ_name",
    "organ_code",
    "cnpj",
    "destination_organ",
    "destination_indicator",
    "versao",
    "bdversao",
)


class Unidade(Base):
    __tablename__ = "unidades"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))

    # Identificação
    nome = Column(String(200), nullable=False)                 # organ_name
    sigla = Column(String(20), nullable=True)                  # organ_code
    modalidade = Column(String(20), nullable=False, index=True)  # unidade.modalidades.CODIGOS
    cnes = Column(String(7), nullable=False, index=True)
    cnpj = Column(String(20), nullable=True)

    # Território
    uf_code = Column(String(2), nullable=True)
    municipio_codigo = Column(String(10), nullable=True)
    municipio_nome = Column(String(120), nullable=True)
    populacao = Column(Integer, nullable=True)  # habitantes, para o aviso de porte

    # Arquivo RAAS
    destination_organ = Column(String(60), nullable=True)
    destination_indicator = Column(String(1), nullable=True, default="M")
    versao = Column(String(10), nullable=True, default="02.31")
    bdversao = Column(String(10), nullable=True)

    # Operação
    leitos_acolhimento = Column(Integer, nullable=True, default=0)
    observacoes = Column(Text, nullable=True)
    ativa = Column(Boolean, nullable=False, default=True)

    criada_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizada_em = Column(DateTime(timezone=True), onupdate=func.now())

    def config_estabelecimento(self) -> dict:
        """Os campos de estabelecimento desta unidade, nas chaves do ConfigService."""
        valores = {
            "uf_code": self.uf_code,
            "cnes_code": self.cnes,
            "organ_name": self.nome,
            "organ_code": self.sigla,
            "cnpj": self.cnpj,
            "destination_organ": self.destination_organ,
            "destination_indicator": self.destination_indicator,
            "versao": self.versao,
            "bdversao": self.bdversao,
        }
        # Campo vazio na unidade não deve apagar o valor geral: quem decide é
        # quem tem valor preenchido.
        return {c: v for c, v in valores.items() if v not in (None, "")}

    def __repr__(self):
        return f"<Unidade(nome='{self.nome}', modalidade='{self.modalidade}', cnes='{self.cnes}')>"
