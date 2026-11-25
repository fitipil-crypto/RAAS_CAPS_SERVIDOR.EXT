"""
Schemas (Pydantic) da unidade.
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator

from unidade import modalidades


def _so_digitos(valor: str | None) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


def _validar_modalidade(valor: str) -> str:
    """Aceita só um dos 7 códigos de modalidade."""
    valor = (valor or "").strip()
    if not modalidades.valida(valor):
        raise ValueError(f"Modalidade inválida. Use uma de: {', '.join(modalidades.CODIGOS)}")
    return valor


def _validar_cnes(valor: str) -> str:
    numero = _so_digitos(valor)
    if len(numero) != 7:
        raise ValueError("O CNES precisa ter 7 dígitos.")
    return numero


class UnidadeBase(BaseModel):
    nome: str = Field(min_length=2, max_length=200)
    sigla: str | None = Field(default=None, max_length=20)
    modalidade: str
    cnes: str
    cnpj: str | None = Field(default=None, max_length=20)
    uf_code: str | None = Field(default=None, max_length=2)
    municipio_codigo: str | None = Field(default=None, max_length=10)
    municipio_nome: str | None = Field(default=None, max_length=120)
    populacao: int | None = Field(default=None, ge=0)
    destination_organ: str | None = Field(default=None, max_length=60)
    destination_indicator: str | None = Field(default="M", max_length=1)
    versao: str | None = Field(default="02.31", max_length=10)
    bdversao: str | None = Field(default=None, max_length=10)
    leitos_acolhimento: int | None = Field(default=0, ge=0, le=999)
    observacoes: str | None = None
    ativa: bool = True

    @field_validator("modalidade")
    @classmethod
    def _modalidade_conhecida(cls, valor: str) -> str:
        return _validar_modalidade(valor)

    @field_validator("cnes")
    @classmethod
    def _cnes_sete_digitos(cls, valor: str) -> str:
        return _validar_cnes(valor)

    @field_validator("destination_indicator")
    @classmethod
    def _indicador(cls, valor: str | None) -> str | None:
        if valor in (None, ""):
            return "M"
        valor = valor.strip().upper()
        if valor not in ("E", "M"):
            raise ValueError("Indicador de destino: E (Estadual) ou M (Municipal).")
        return valor


class UnidadeCriar(UnidadeBase):
    pass


class UnidadeAtualizar(BaseModel):
    """Atualização parcial: só o que vier é alterado."""

    nome: str | None = Field(default=None, min_length=2, max_length=200)
    sigla: str | None = Field(default=None, max_length=20)
    modalidade: str | None = None
    cnes: str | None = None
    cnpj: str | None = Field(default=None, max_length=20)
    uf_code: str | None = Field(default=None, max_length=2)
    municipio_codigo: str | None = Field(default=None, max_length=10)
    municipio_nome: str | None = Field(default=None, max_length=120)
    populacao: int | None = Field(default=None, ge=0)
    destination_organ: str | None = Field(default=None, max_length=60)
    destination_indicator: str | None = Field(default=None, max_length=1)
    versao: str | None = Field(default=None, max_length=10)
    bdversao: str | None = Field(default=None, max_length=10)
    leitos_acolhimento: int | None = Field(default=None, ge=0, le=999)
    observacoes: str | None = None
    ativa: bool | None = None

    @field_validator("modalidade")
    @classmethod
    def _modalidade_conhecida(cls, valor: str | None) -> str | None:
        return _validar_modalidade(valor) if valor not in (None, "") else valor

    @field_validator("cnes")
    @classmethod
    def _cnes_sete_digitos(cls, valor: str | None) -> str | None:
        return _validar_cnes(valor) if valor not in (None, "") else valor


class UnidadeResposta(UnidadeBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    modalidade_nome: str = ""
    avisos: list[str] = []


class ModalidadeResposta(BaseModel):
    codigo: str
    nome: str
    descricao: str
    populacao_minima: int | None
    faixa_etaria: str
    funcionamento: str
    acolhimento_noturno: bool
    leitos: str
    permanencia_dias_corridos: int | None
    permanencia_dias_intercalados: int | None
    permanencia_janela_dias: int | None
    alcool_e_drogas: bool
    fundamento: str
    observacoes: list[str]
