"""
As 7 modalidades de CAPS e seus parâmetros assistenciais.

Fonte dos parâmetros
--------------------
Portaria GM/MS nº 3.088/2011, art. 7º, § 4º (texto republicado), que organiza os
CAPS em modalidades e fixa o porte populacional de cada uma; Portaria GM/MS
nº 336/2002, que trata do acolhimento noturno (até 5 leitos para repouso ou
observação, permanência limitada a 7 dias corridos ou 10 dias intercalados em
30 dias); e Portaria GM/MS nº 3.588/2017, que criou o CAPS AD IV. As normas
estão hoje consolidadas na Portaria de Consolidação nº 3/2017, Anexo V.

Por que esses números são *referência* e não regra rígida
---------------------------------------------------------
Duas razões práticas:

1. O texto da 3.088/2011 teve republicações com números divergentes — há cópias
   em circulação com "acima de quinze mil habitantes" para o CAPS I e "cento e
   cinquenta mil" para o CAPS AD III, onde a republicação usada aqui diz vinte
   mil e duzentos mil. Travar o sistema em um dos valores criaria um erro onde
   a própria norma é ambígua.
2. Habilitação é ato da gestão: existe CAPS habilitado em município fora do
   porte previsto, por decisão da CIB ou por cobertura regional. O sistema que
   recusasse o cadastro estaria errado, não o serviço.

Por isso cada parâmetro vira **aviso** (``avisos_da_unidade``), nunca bloqueio,
e os campos que afetam a operação do dia a dia — leitos de acolhimento noturno
e faixa etária — são sobrescritíveis na própria unidade.

Os códigos (``CAPS_I``, ``CAPS_AD_III``...) são os valores gravados no banco:
não os renomeie sem migrar a coluna ``modalidade`` da tabela ``unidades``.
"""
from dataclasses import dataclass, field

# Idade que separa criança/adolescente de adulto (ECA, art. 2º: adolescente até
# 18 anos incompletos). Usada como faixa padrão do CAPS i.
IDADE_MAIOR_IDADE = 18


@dataclass(frozen=True)
class Modalidade:
    """Parâmetros de uma modalidade de CAPS."""

    codigo: str
    nome: str
    descricao: str
    populacao_minima: int | None          # habitantes do município/região
    idade_minima: int | None              # faixa etária atendida (None = sem piso)
    idade_maxima: int | None              # None = sem teto
    funcionamento_24h: bool
    acolhimento_noturno: bool
    leitos_minimos: int | None
    leitos_maximos: int | None
    permanencia_dias_corridos: int | None       # dias seguidos no acolhimento
    permanencia_dias_intercalados: int | None   # dias alternados na janela
    permanencia_janela_dias: int | None         # janela de apuração (30 dias)
    alcool_e_drogas: bool                 # público de álcool e outras drogas
    fundamento: str
    observacoes: tuple[str, ...] = field(default=())

    @property
    def infantojuvenil(self) -> bool:
        return self.idade_maxima is not None

    def faixa_etaria_texto(self) -> str:
        if self.idade_maxima is None and self.idade_minima is None:
            return "Todas as faixas etárias"
        if self.idade_maxima is not None:
            return f"Até {self.idade_maxima} anos (crianças e adolescentes)"
        return f"A partir de {self.idade_minima} anos"

    def leitos_texto(self) -> str:
        if not self.acolhimento_noturno:
            return "Sem acolhimento noturno"
        if self.leitos_minimos and self.leitos_maximos:
            return f"{self.leitos_minimos} a {self.leitos_maximos} leitos"
        if self.leitos_maximos:
            return f"Até {self.leitos_maximos} leitos"
        return "Acolhimento noturno"


MODALIDADES: dict[str, Modalidade] = {
    "CAPS_I": Modalidade(
        codigo="CAPS_I",
        nome="CAPS I",
        descricao=(
            "Atende pessoas com transtornos mentais graves e persistentes e também com "
            "necessidades decorrentes do uso de crack, álcool e outras drogas, de todas as "
            "faixas etárias."
        ),
        populacao_minima=20_000,
        idade_minima=None,
        idade_maxima=None,
        funcionamento_24h=False,
        acolhimento_noturno=False,
        leitos_minimos=None,
        leitos_maximos=None,
        permanencia_dias_corridos=None,
        permanencia_dias_intercalados=None,
        permanencia_janela_dias=None,
        alcool_e_drogas=True,
        fundamento="Portaria GM/MS 3.088/2011, art. 7º, § 4º, I",
    ),
    "CAPS_II": Modalidade(
        codigo="CAPS_II",
        nome="CAPS II",
        descricao=(
            "Atende pessoas com transtornos mentais graves e persistentes, podendo também "
            "atender pessoas com necessidades decorrentes do uso de crack, álcool e outras "
            "drogas, conforme a organização da rede de saúde local."
        ),
        populacao_minima=70_000,
        idade_minima=None,
        idade_maxima=None,
        funcionamento_24h=False,
        acolhimento_noturno=False,
        leitos_minimos=None,
        leitos_maximos=None,
        permanencia_dias_corridos=None,
        permanencia_dias_intercalados=None,
        permanencia_janela_dias=None,
        alcool_e_drogas=True,
        fundamento="Portaria GM/MS 3.088/2011, art. 7º, § 4º, II",
        observacoes=(
            "O atendimento de álcool e outras drogas depende da organização da rede local.",
        ),
    ),
    "CAPS_III": Modalidade(
        codigo="CAPS_III",
        nome="CAPS III",
        descricao=(
            "Atende pessoas com transtornos mentais graves e persistentes. Atenção contínua, "
            "24 horas, incluindo feriados e fins de semana, com retaguarda clínica e "
            "acolhimento noturno a outros serviços de saúde mental, inclusive CAPS AD."
        ),
        populacao_minima=200_000,
        idade_minima=None,
        idade_maxima=None,
        funcionamento_24h=True,
        acolhimento_noturno=True,
        leitos_minimos=None,
        leitos_maximos=5,
        permanencia_dias_corridos=7,
        permanencia_dias_intercalados=10,
        permanencia_janela_dias=30,
        alcool_e_drogas=False,
        fundamento=(
            "Portaria GM/MS 3.088/2011, art. 7º, § 4º, III; leitos e permanência: "
            "Portaria GM/MS 336/2002"
        ),
    ),
    "CAPS_i": Modalidade(
        codigo="CAPS_i",
        nome="CAPS i",
        descricao=(
            "Atende crianças e adolescentes com transtornos mentais graves e persistentes e os "
            "que fazem uso de crack, álcool e outras drogas. Serviço aberto e de caráter "
            "comunitário."
        ),
        populacao_minima=150_000,
        idade_minima=None,
        idade_maxima=IDADE_MAIOR_IDADE - 1,
        funcionamento_24h=False,
        acolhimento_noturno=False,
        leitos_minimos=None,
        leitos_maximos=None,
        permanencia_dias_corridos=None,
        permanencia_dias_intercalados=None,
        permanencia_janela_dias=None,
        alcool_e_drogas=True,
        fundamento="Portaria GM/MS 3.088/2011, art. 7º, § 4º, VI",
        observacoes=(
            "A continuidade do cuidado de quem completa 18 anos em acompanhamento é decisão "
            "clínica: o sistema avisa, não impede o lançamento.",
        ),
    ),
    "CAPS_AD": Modalidade(
        codigo="CAPS_AD",
        nome="CAPS AD",
        descricao=(
            "Atende adultos ou crianças e adolescentes, considerando as normativas do Estatuto "
            "da Criança e do Adolescente, com necessidades decorrentes do uso de crack, álcool "
            "e outras drogas. Serviço aberto e de caráter comunitário."
        ),
        populacao_minima=70_000,
        idade_minima=None,
        idade_maxima=None,
        funcionamento_24h=False,
        acolhimento_noturno=True,
        leitos_minimos=None,
        leitos_maximos=5,
        permanencia_dias_corridos=7,
        permanencia_dias_intercalados=10,
        permanencia_janela_dias=30,
        alcool_e_drogas=True,
        fundamento=(
            "Portaria GM/MS 3.088/2011, art. 7º, § 4º, IV; acolhimento noturno em feriados e "
            "fins de semana: Portaria GM/MS 336/2002"
        ),
    ),
    "CAPS_AD_III": Modalidade(
        codigo="CAPS_AD_III",
        nome="CAPS AD III",
        descricao=(
            "Atende adultos ou crianças e adolescentes, considerando as normativas do Estatuto "
            "da Criança e do Adolescente, com necessidades de cuidados clínicos contínuos. "
            "Funcionamento 24 horas, incluindo feriados e fins de semana."
        ),
        populacao_minima=200_000,
        idade_minima=None,
        idade_maxima=None,
        funcionamento_24h=True,
        acolhimento_noturno=True,
        leitos_minimos=8,
        leitos_maximos=12,
        permanencia_dias_corridos=14,
        permanencia_dias_intercalados=None,
        permanencia_janela_dias=30,
        alcool_e_drogas=True,
        fundamento=(
            "Portaria GM/MS 3.088/2011, art. 7º, § 4º, V (máximo de 12 leitos para observação "
            "e monitoramento); faixa de 8 a 12 leitos e permanência de 14 dias em 30: "
            "redefinição posterior do CAPS AD III"
        ),
    ),
    "CAPS_AD_IV": Modalidade(
        codigo="CAPS_AD_IV",
        nome="CAPS AD IV",
        descricao=(
            "Atende pessoas com quadros graves decorrentes do uso de crack, álcool e outras "
            "drogas, inclusive em situações de urgência. Funcionamento 24 horas, todos os dias, "
            "com leitos de observação."
        ),
        populacao_minima=500_000,
        idade_minima=None,
        idade_maxima=None,
        funcionamento_24h=True,
        acolhimento_noturno=True,
        leitos_minimos=10,
        leitos_maximos=20,
        permanencia_dias_corridos=None,
        permanencia_dias_intercalados=None,
        permanencia_janela_dias=None,
        alcool_e_drogas=True,
        fundamento="Portaria GM/MS 3.588/2017 (municípios acima de 500 mil habitantes e capitais)",
        observacoes=(
            "Previsto para municípios acima de 500 mil habitantes e capitais; confira a "
            "habilitação da unidade antes de usar os parâmetros de leitos.",
        ),
    ),
}

# Ordem de exibição nas telas (a mesma dos incisos da portaria, com o AD IV ao fim).
ORDEM = ("CAPS_I", "CAPS_II", "CAPS_III", "CAPS_i", "CAPS_AD", "CAPS_AD_III", "CAPS_AD_IV")

CODIGOS = ORDEM


def listar() -> list[Modalidade]:
    """As 7 modalidades na ordem de exibição."""
    return [MODALIDADES[c] for c in ORDEM]


def obter(codigo: str | None) -> Modalidade | None:
    return MODALIDADES.get((codigo or "").strip()) if codigo else None


def valida(codigo: str | None) -> bool:
    return (codigo or "").strip() in MODALIDADES


def nome(codigo: str | None) -> str:
    modalidade = obter(codigo)
    return modalidade.nome if modalidade else (codigo or "—")


# ── Avisos (nunca bloqueiam) ────────────────────────────────────────────────

def aviso_faixa_etaria(codigo: str | None, idade: int | None) -> str | None:
    """Avisa quando a idade do paciente foge da faixa da modalidade.

    Só o CAPS i tem teto de idade; as demais atendem todas as faixas. Devolve
    None quando está tudo certo ou quando falta a data de nascimento.
    """
    modalidade = obter(codigo)
    if modalidade is None or idade is None:
        return None
    if modalidade.idade_maxima is not None and idade > modalidade.idade_maxima:
        return (
            f"Paciente com {idade} anos em {modalidade.nome}, que atende até "
            f"{modalidade.idade_maxima} anos (crianças e adolescentes)."
        )
    if modalidade.idade_minima is not None and idade < modalidade.idade_minima:
        return (
            f"Paciente com {idade} anos em {modalidade.nome}, que atende a partir de "
            f"{modalidade.idade_minima} anos."
        )
    return None


def aviso_leitos(codigo: str | None, leitos: int | None) -> str | None:
    """Confere a quantidade de leitos de acolhimento noturno informada."""
    modalidade = obter(codigo)
    if modalidade is None or leitos is None:
        return None
    if leitos < 0:
        return "A quantidade de leitos não pode ser negativa."
    if not modalidade.acolhimento_noturno and leitos > 0:
        return (
            f"{modalidade.nome} não tem acolhimento noturno previsto, mas foram informados "
            f"{leitos} leito(s)."
        )
    if modalidade.leitos_maximos is not None and leitos > modalidade.leitos_maximos:
        return (
            f"{modalidade.nome} prevê no máximo {modalidade.leitos_maximos} leito(s) de "
            f"acolhimento noturno; foram informados {leitos}."
        )
    if modalidade.leitos_minimos is not None and 0 < leitos < modalidade.leitos_minimos:
        return (
            f"{modalidade.nome} prevê no mínimo {modalidade.leitos_minimos} leito(s) de "
            f"acolhimento noturno; foram informados {leitos}."
        )
    return None


def aviso_porte(codigo: str | None, populacao: int | None) -> str | None:
    """Compara a população do município com o porte previsto para a modalidade."""
    modalidade = obter(codigo)
    if modalidade is None or not populacao or modalidade.populacao_minima is None:
        return None
    if populacao < modalidade.populacao_minima:
        return (
            f"{modalidade.nome} é indicado para municípios ou regiões com população acima de "
            f"{modalidade.populacao_minima:,} habitantes".replace(",", ".")
            + f"; a população informada é de {populacao:,}".replace(",", ".")
            + ". A habilitação pode ser regional ou decisão da gestão — confira antes de alterar."
        )
    return None


def avisos_da_unidade(
    codigo: str | None,
    *,
    populacao: int | None = None,
    leitos: int | None = None,
) -> list[str]:
    """Todos os avisos aplicáveis ao cadastro de uma unidade."""
    return [
        aviso
        for aviso in (aviso_porte(codigo, populacao), aviso_leitos(codigo, leitos))
        if aviso
    ]


def resumo(codigo: str | None) -> dict:
    """Dados da modalidade prontos para a tela ou para a API."""
    modalidade = obter(codigo)
    if modalidade is None:
        return {}
    return {
        "codigo": modalidade.codigo,
        "nome": modalidade.nome,
        "descricao": modalidade.descricao,
        "populacao_minima": modalidade.populacao_minima,
        "faixa_etaria": modalidade.faixa_etaria_texto(),
        "funcionamento": "24 horas, todos os dias" if modalidade.funcionamento_24h else "Dias úteis",
        "acolhimento_noturno": modalidade.acolhimento_noturno,
        "leitos": modalidade.leitos_texto(),
        "permanencia_dias_corridos": modalidade.permanencia_dias_corridos,
        "permanencia_dias_intercalados": modalidade.permanencia_dias_intercalados,
        "permanencia_janela_dias": modalidade.permanencia_janela_dias,
        "alcool_e_drogas": modalidade.alcool_e_drogas,
        "fundamento": modalidade.fundamento,
        "observacoes": list(modalidade.observacoes),
    }
