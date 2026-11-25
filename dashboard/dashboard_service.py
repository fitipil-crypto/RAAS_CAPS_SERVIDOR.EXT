"""
Montagem dos indicadores exibidos na página inicial (dashboard).
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from aniversariantes.aniversariantes_service import AniversariantesService
from procedimento.procedimento_service import ProcedimentoService
from registro.registro_service import RegistroService

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def _variacao(atual: float, anterior: float) -> float | None:
    """Variação percentual arredondada; None quando não há base de comparação."""
    if not anterior:
        return None
    return round((atual - anterior) / anterior * 100)


class DashboardService:

    @staticmethod
    def montar_contexto(db: Session, now: datetime | None = None) -> dict:
        now = now or datetime.now()
        current_month = now.strftime("%Y-%m")
        ultimo_dia_mes_anterior = now.replace(day=1) - timedelta(days=1)
        mes_anterior = ultimo_dia_mes_anterior.strftime("%Y-%m")

        mes = RegistroService.estatisticas_mes(db, current_month)
        mes_ant = RegistroService.estatisticas_mes(db, mes_anterior)

        # Cada indicador traz o valor atual, a variação em relação ao mês anterior e o tom visual.
        indicadores = [
            {"key": "pacientes", "label": "Pacientes no mês", "icon": "👥", "tom": "primary",
             "valor": mes["pacientes"], "variacao": _variacao(mes["pacientes"], mes_ant["pacientes"])},
            {"key": "atendimentos", "label": "Atendimentos no mês", "icon": "📝", "tom": "accent",
             "valor": mes["registros"], "variacao": _variacao(mes["registros"], mes_ant["registros"])},
            {"key": "procedimentos", "label": "Procedimentos usados", "icon": "📋", "tom": "secondary",
             "valor": mes["procedimentos"], "variacao": _variacao(mes["procedimentos"], mes_ant["procedimentos"])},
            {"key": "media", "label": "Média por paciente", "icon": "📊", "tom": "warning",
             "valor": round(mes["registros"] / max(mes["pacientes"], 1), 1),
             "variacao": _variacao(
                 mes["registros"] / max(mes["pacientes"], 1),
                 mes_ant["registros"] / max(mes_ant["pacientes"], 1),
             )},
        ]

        inicio_7dias = (now - timedelta(days=6)).strftime("%Y-%m-%d")
        contagem_dias = RegistroService.contagem_por_dia(db, inicio_7dias)

        dias = []
        for i in range(6, -1, -1):
            d = now - timedelta(days=i)
            dias.append({"label": d.strftime("%d/%m"), "count": contagem_dias.get(d.strftime("%Y-%m-%d"), 0)})
        max_count = max([d["count"] for d in dias] + [1])
        for d in dias:
            d["altura"] = round(d["count"] / max_count * 100)

        top = RegistroService.top_procedimentos_mes(db, current_month, limite=5)
        max_top = max([p["total"] for p in top] + [1])
        top_procedimentos = []
        for p in top:
            proc = ProcedimentoService.obter_por_id(db, p["procedure_id"])
            top_procedimentos.append({
                "code": proc.code if proc else "—",
                "name": proc.name if proc else "Procedimento removido",
                "total": p["total"],
                "largura": round(p["total"] / max_top * 100),
            })

        return {
            "aniversariantes": AniversariantesService.proximos(db, 7, hoje=now.date()),
            "indicadores": indicadores,
            "dias": dias,
            "semana_total": sum(d["count"] for d in dias),
            "top_procedimentos": top_procedimentos,
            "competencia": f"{MESES[now.month - 1]} de {now.year}",
            "mes_anterior_nome": MESES[ultimo_dia_mes_anterior.month - 1],
        }
