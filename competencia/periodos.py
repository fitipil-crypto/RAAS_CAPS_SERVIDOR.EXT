"""Utilitários de competência (YYYY-MM) e dias úteis."""
import calendar
from datetime import date

MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def rotulo_mes(month: str) -> str:
    ano, mes = month.split("-")
    return f"{MESES_ABREV[int(mes) - 1]}/{ano}"


def mes_anterior(month: str) -> str:
    ano, mes = (int(x) for x in month.split("-"))
    return f"{ano - 1}-12" if mes == 1 else f"{ano}-{mes - 1:02d}"


def meses_anteriores(month: str, quantidade: int) -> list[str]:
    """Os ``quantidade`` meses imediatamente anteriores, do mais antigo ao mais recente."""
    meses, atual = [], month
    for _ in range(quantidade):
        atual = mes_anterior(atual)
        meses.append(atual)
    return list(reversed(meses))


def mes_de(dia: date) -> str:
    return dia.strftime("%Y-%m")


def dias_uteis(month: str, ate: date | None = None) -> int:
    """Dias úteis (segunda a sexta) do mês, opcionalmente até ``ate`` inclusive.

    Feriados não são considerados: o sistema não tem calendário de feriados.
    """
    ano, mes = (int(x) for x in month.split("-"))
    ultimo = calendar.monthrange(ano, mes)[1]
    total = 0
    for dia in range(1, ultimo + 1):
        atual = date(ano, mes, dia)
        if ate and atual > ate:
            break
        if atual.weekday() < 5:
            total += 1
    return total
