"""Previsão de fechamento da competência.

Método (simples e explicável, sem modelo estatístico):
  • ritmo atual  = atendimentos lançados ÷ dias úteis decorridos;
  • projeção     = lançados + ritmo × dias úteis restantes;
  • referência   = média e desvio-padrão do ritmo por dia útil nos meses
                   fechados anteriores (até ``JANELA`` meses com produção).
A faixa esperada é (média ± desvio) × dias úteis do mês. Com menos de
``MINIMO_HISTORICO`` meses de histórico, a faixa não é exibida.
"""
from collections import Counter
from datetime import date
from statistics import mean, pstdev

from sqlalchemy.orm import Session

from competencia.periodos import dias_uteis, mes_de, meses_anteriores
from profissional.profissional_model import Profissional
from registro.registro_model import Registro

JANELA = 6
MINIMO_HISTORICO = 3
# Projeção abaixo desta fração da média histórica é sinalizada.
LIMIAR_ABAIXO = 0.8


def projetar_total(atual: int, dias_decorridos: int, dias_totais: int) -> float | None:
    """Projeta o fechamento pelo ritmo por dia útil; None sem dias decorridos."""
    if dias_decorridos <= 0:
        return None
    return atual + atual / dias_decorridos * max(dias_totais - dias_decorridos, 0)


def faixa_historica(ritmos: list[float], dias_totais: int) -> tuple[float, float, float] | None:
    """(mínimo, média, máximo) esperados para o mês; None com histórico curto."""
    if len(ritmos) < MINIMO_HISTORICO:
        return None
    media, desvio = mean(ritmos), pstdev(ritmos)
    return (max(media - desvio, 0) * dias_totais, media * dias_totais, (media + desvio) * dias_totais)


def situacao(projecao: float | None, media_historica: float | None) -> str:
    if projecao is None or not media_historica:
        return "Sem base"
    if projecao < media_historica * LIMIAR_ABAIXO:
        return "Abaixo do ritmo"
    return "Dentro do esperado"


class PrevisaoService:

    @staticmethod
    def prever(db: Session, month: str, hoje: date | None = None) -> dict:
        """Previsão da competência ``month``.

        Mês corrente → projeta o fechamento; mês passado → mostra o realizado
        contra o histórico; mês futuro → não há o que prever.
        """
        hoje = hoje or date.today()
        mes_hoje = mes_de(hoje)
        if month > mes_hoje:
            return {"competencia": month, "estado": "futuro"}

        registros = db.query(Registro).filter(Registro.service_month == month).all()
        historico = meses_anteriores(month, JANELA)
        por_mes = {m: Counter() for m in historico}
        for r in db.query(Registro).filter(Registro.service_month.in_(historico)).all():
            por_mes[r.service_month][r.professional_id or ""] += r.quantity or 1
        meses_com_dados = [m for m in historico if sum(por_mes[m].values())]

        totais_historicos = [sum(por_mes[m].values()) for m in meses_com_dados]
        ritmos = [sum(por_mes[m].values()) / dias_uteis(m) for m in meses_com_dados]
        total_dias = dias_uteis(month)
        faixa = faixa_historica(ritmos, total_dias)
        media_total = mean(totais_historicos) if totais_historicos else None

        atual = sum(r.quantity or 1 for r in registros)
        corrente = month == mes_hoje
        if corrente:
            dias_com_lancamento = {r.service_date for r in registros}
            ate = hoje if hoje.isoformat() in dias_com_lancamento else date.fromordinal(hoje.toordinal() - 1)
            decorridos = dias_uteis(month, ate) if mes_de(ate) == month else 0
            projecao = projetar_total(atual, decorridos, total_dias)
        else:
            decorridos, projecao = total_dias, float(atual)

        profissionais = {p.id: p.name for p in db.query(Profissional).all()}
        atuais_prof = Counter()
        for r in registros:
            atuais_prof[r.professional_id or ""] += r.quantity or 1
        linhas_prof = []
        for pid in set(atuais_prof) | {p for m in meses_com_dados for p in por_mes[m]}:
            historico_prof = [por_mes[m].get(pid, 0) for m in meses_com_dados]
            media_prof = mean(historico_prof) if historico_prof else None
            proj_prof = projetar_total(atuais_prof.get(pid, 0), decorridos, total_dias) if corrente else float(atuais_prof.get(pid, 0))
            linhas_prof.append({
                "profissional": profissionais.get(pid, "Não informado"),
                "atual": atuais_prof.get(pid, 0),
                "projecao": round(proj_prof) if proj_prof is not None else None,
                "media": round(media_prof) if media_prof is not None else None,
                "situacao": situacao(proj_prof, media_prof) if len(meses_com_dados) >= MINIMO_HISTORICO else "Histórico insuficiente",
            })
        linhas_prof.sort(key=lambda l: (-(l["projecao"] or 0), l["profissional"]))

        return {
            "competencia": month,
            "estado": "corrente" if corrente else "fechado",
            "atual": atual,
            "dias_decorridos": decorridos,
            "dias_totais": total_dias,
            "ritmo": round(atual / decorridos, 1) if decorridos else None,
            "projecao": round(projecao) if projecao is not None else None,
            "faixa": tuple(round(v) for v in faixa) if faixa else None,
            "media_historica": round(media_total) if media_total is not None else None,
            "meses_historico": len(meses_com_dados),
            "situacao": situacao(projecao, media_total) if len(meses_com_dados) >= MINIMO_HISTORICO else "Histórico insuficiente",
            "profissionais": linhas_prof,
        }
