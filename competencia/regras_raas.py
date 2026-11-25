"""Regras de validação do RAAS (Psicossocial) em funções puras.

Nada aqui acessa banco de dados: cada função recebe valores simples e devolve
um booleano ou o valor normalizado, o que as torna fáceis de testar. Os limites
de tamanho vêm do layout posicional que ``exportacao_service`` grava (Registro
15 = paciente, Registro 16 = procedimento/profissional).
"""
import re
from datetime import date, datetime

from sistema.reference_data import only_digits

# ─── Domínios do layout ──────────────────────────────────────────────
SEXOS_VALIDOS = {"M", "F"}
RACAS_VALIDAS = {"01", "02", "03", "04", "05", "99"}
RACA_INDIGENA = "05"
LOCAIS_VALIDOS = {"C", "T"}
SIM_NAO = {"S", "N"}

# Tamanhos dos campos de texto no Registro 15 (posições 49-78, 89-118, 119-148).
TAM_NOME = 30
TAM_MAE = 30
TAM_ENDERECO = 30

# Quantidade: 6 posições no Registro 16 (campo 86-91).
QTD_MAXIMA_LAYOUT = 999_999
# Acima disso a quantidade de um único lançamento é incomum e merece conferência.
QTD_ATENCAO = 30

# Procedimentos de atenção psicossocial ficam no grupo 03.01.08 da SIGTAP.
PREFIXO_PSICOSSOCIAL = "030108"
# Atendimento domiciliar (03.01.08.024-0): deve ser realizado no território.
PROCEDIMENTO_DOMICILIAR = "0301080240"

_RE_CID = re.compile(r"^[A-Z]\d{2,3}$")
_RE_COMPETENCIA = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def competencia_valida(valor: str | None) -> bool:
    return bool(valor and _RE_COMPETENCIA.fullmatch(valor))


def parse_data(valor) -> date | None:
    """Converte YYYY-MM-DD em ``date``; devolve None se vazio ou inválido."""
    if not valor:
        return None
    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def cns_valido(cns: str | None) -> bool:
    """Valida o Cartão Nacional de Saúde (15 dígitos) pelo dígito verificador.

    Definitivo (iniciado em 1 ou 2): módulo 11 sobre os 11 primeiros dígitos
    (PIS/PASEP), formando DV e sufixo "000" ou "001". Provisório (7, 8 ou 9):
    soma ponderada de 15 a 1 divisível por 11.
    """
    numero = only_digits(cns)
    if len(numero) != 15:
        return False
    if numero[0] in "12":
        soma = sum(int(numero[i]) * (15 - i) for i in range(11))
        resto = soma % 11
        dv = 11 - resto if resto else 0
        if dv == 10:
            soma += 2
            dv = 11 - soma % 11
            esperado = f"{numero[:11]}001{dv}"
        else:
            esperado = f"{numero[:11]}000{dv}"
        return numero == esperado
    if numero[0] in "789":
        return sum(int(numero[i]) * (15 - i) for i in range(15)) % 11 == 0
    return False


def cpf_valido(cpf: str | None) -> bool:
    numero = only_digits(cpf)
    if len(numero) != 11 or numero == numero[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(numero[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(numero[tamanho]):
            return False
    return True


def cid_valido(cid: str | None) -> bool:
    """CID-10 sem ponto, como vai no arquivo (ex.: F840). Aceita com ponto."""
    return bool(_RE_CID.fullmatch((cid or "").replace(".", "").strip().upper()))


def procedimento_valido(codigo: str | None) -> bool:
    """Código SIGTAP do procedimento: exatamente 10 dígitos."""
    return len(only_digits(codigo)) == 10


def procedimento_psicossocial(codigo: str | None) -> bool:
    return only_digits(codigo).startswith(PREFIXO_PSICOSSOCIAL)


def cbo_valido(cbo: str | None) -> bool:
    return len(only_digits(cbo)) == 6


def cep_valido(cep: str | None) -> bool:
    return len(only_digits(cep)) == 8


def municipio_valido(codigo: str | None) -> bool:
    """Código IBGE do município com 6 dígitos (sem DV) ou 7 (com DV)."""
    return len(only_digits(codigo)) in (6, 7)


def cnes_valido(cnes: str | None) -> bool:
    return len(only_digits(cnes)) == 7


def cnpj_normalizado(cnpj: str | None) -> str:
    """Remove máscara e passa para maiúsculas, mantendo letras (CNPJ alfanumérico)."""
    return re.sub(r"[^0-9A-Za-z]", "", cnpj or "").upper()


def cnpj_alfanumerico(cnpj: str | None) -> bool:
    return any(c.isalpha() for c in cnpj_normalizado(cnpj))


def cnpj_valido(cnpj: str | None) -> bool:
    """Valida CNPJ numérico ou alfanumérico (12 caracteres-base + 2 dígitos).

    Cada caractere vale ``ord(c) - 48`` (0-9 → 0-9, A-Z → 17-42); os pesos e o
    módulo 11 são os mesmos do CNPJ numérico.
    """
    valor = cnpj_normalizado(cnpj)
    if len(valor) != 14 or not valor[12:].isdigit() or valor == valor[0] * 14:
        return False
    numeros = [ord(c) - 48 for c in valor]
    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        resto = sum(numeros[i] * pesos[i] for i in range(tamanho)) % 11
        if (0 if resto < 2 else 11 - resto) != numeros[tamanho]:
            return False
    return True


def idade_em(nascimento: date | None, referencia: date) -> int | None:
    if not nascimento:
        return None
    return referencia.year - nascimento.year - ((referencia.month, referencia.day) < (nascimento.month, nascimento.day))
