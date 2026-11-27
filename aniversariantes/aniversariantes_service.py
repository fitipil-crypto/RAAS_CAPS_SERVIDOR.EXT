"""
Serviço de aniversariantes da instituição (pacientes e profissionais).
"""
from datetime import date, datetime

from sqlalchemy.orm import Session

from paciente.paciente_model import Paciente
from profissional.profissional_model import Profissional

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]
DIAS_SEMANA = [
    "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
    "Sexta-feira", "Sábado", "Domingo",
]

TIPOS = ("todos", "paciente", "profissional")


def _parse_data(valor: str | None) -> date | None:
    if not valor:
        return None
    try:
        return datetime.strptime(valor[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _aniversario_no_ano(nascimento: date, ano: int) -> date:
    """Data do aniversário no ano; quem nasceu em 29/02 comemora em 28/02 nos anos não bissextos."""
    try:
        return nascimento.replace(year=ano)
    except ValueError:
        return date(ano, 2, 28)


def _paciente_ativo(p: Paciente) -> bool:
    return not (p.mot_saida or p.conclusion_date)


class AniversariantesService:

    @staticmethod
    def _pessoas(db: Session, tipo: str, incluir_inativos: bool) -> list[dict]:
        pessoas = []
        if tipo in ("todos", "paciente"):
            for p in db.query(Paciente).all():
                nasc = _parse_data(p.birth_date)
                if not nasc or (not incluir_inativos and not _paciente_ativo(p)):
                    continue
                pessoas.append({
                    "id": p.id, "tipo": "paciente", "nome": p.name, "nascimento": nasc,
                    "detalhe": f"Prontuário {p.prontuario}" if p.prontuario else "Paciente",
                    "telefone": p.cell_phone or p.phone or "",
                    "ativo": _paciente_ativo(p),
                    "link": f"/pacientes/{p.id}",
                })
        if tipo in ("todos", "profissional"):
            for p in db.query(Profissional).all():
                nasc = _parse_data(p.birth_date)
                if not nasc or (not incluir_inativos and not p.active):
                    continue
                pessoas.append({
                    "id": p.id, "tipo": "profissional", "nome": p.name, "nascimento": nasc,
                    "detalhe": p.specialty or p.team or "Profissional",
                    "telefone": "", "ativo": bool(p.active), "link": "/profissionais",
                })
        return pessoas

    @staticmethod
    def _enriquecer(pessoa: dict, hoje: date, ano: int | None = None) -> dict:
        """Calcula a próxima (ou a do ano pedido) data de aniversário, idade e distância em dias."""
        nasc = pessoa["nascimento"]
        if ano is None:
            aniv = _aniversario_no_ano(nasc, hoje.year)
            if aniv < hoje:
                aniv = _aniversario_no_ano(nasc, hoje.year + 1)
        else:
            aniv = _aniversario_no_ano(nasc, ano)
        dias = (aniv - hoje).days
        return {
            **pessoa,
            "nascimento": nasc.isoformat(),
            "nascimento_br": nasc.strftime("%d/%m/%Y"),
            "aniversario": aniv.isoformat(),
            "dia": aniv.day,
            "mes": aniv.month,
            "dia_semana": DIAS_SEMANA[aniv.weekday()],
            "idade": aniv.year - nasc.year,
            "dias_restantes": dias,
            "hoje": dias == 0,
            "iniciais": "".join(w[0] for w in (pessoa["nome"] or "?").split()[:2]).upper(),
        }

    @staticmethod
    def do_mes(db: Session, mes: int, tipo: str = "todos", incluir_inativos: bool = False,
               hoje: date | None = None) -> list[dict]:
        hoje = hoje or date.today()
        tipo = tipo if tipo in TIPOS else "todos"
        itens = [
            AniversariantesService._enriquecer(p, hoje, hoje.year)
            for p in AniversariantesService._pessoas(db, tipo, incluir_inativos)
            if _aniversario_no_ano(p["nascimento"], hoje.year).month == mes
        ]
        itens.sort(key=lambda i: (i["dia"], (i["nome"] or "").upper()))
        return itens

    @staticmethod
    def proximos(db: Session, dias: int = 7, tipo: str = "todos", incluir_inativos: bool = False,
                 hoje: date | None = None) -> list[dict]:
        """Aniversariantes de hoje até daqui a `dias` dias (atravessa virada de mês e de ano)."""
        hoje = hoje or date.today()
        itens = [
            AniversariantesService._enriquecer(p, hoje)
            for p in AniversariantesService._pessoas(db, tipo if tipo in TIPOS else "todos", incluir_inativos)
        ]
        itens = [i for i in itens if i["dias_restantes"] <= dias]
        itens.sort(key=lambda i: (i["dias_restantes"], (i["nome"] or "").upper()))
        return itens

    @staticmethod
    def resumo(db: Session, mes: int, tipo: str = "todos", incluir_inativos: bool = False,
               hoje: date | None = None) -> dict:
        hoje = hoje or date.today()
        mes_itens = AniversariantesService.do_mes(db, mes, tipo, incluir_inativos, hoje)
        prox = AniversariantesService.proximos(db, 7, tipo, incluir_inativos, hoje)
        # Meses com aniversariantes (para o gráfico anual) respeitando os mesmos filtros.
        por_mes = [0] * 12
        for p in AniversariantesService._pessoas(db, tipo if tipo in TIPOS else "todos", incluir_inativos):
            por_mes[_aniversario_no_ano(p["nascimento"], hoje.year).month - 1] += 1
        return {
            "hoje": [i for i in prox if i["hoje"]],
            "proximos": [i for i in prox if not i["hoje"]],
            "mes": mes_itens,
            "por_mes": por_mes,
            "total_mes": len(mes_itens),
            "pacientes_mes": sum(1 for i in mes_itens if i["tipo"] == "paciente"),
            "profissionais_mes": sum(1 for i in mes_itens if i["tipo"] == "profissional"),
        }

    @staticmethod
    def de_hoje(db: Session, hoje: date | None = None) -> list[dict]:
        return AniversariantesService.proximos(db, 0, hoje=hoje)
