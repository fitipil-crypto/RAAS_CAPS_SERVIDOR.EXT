"""Comparativo entre duas competências."""
from collections import Counter

from sqlalchemy.orm import Session

from paciente.paciente_model import Paciente
from procedimento.procedimento_model import Procedimento
from profissional.profissional_model import Profissional
from procedimento.procedimento_service import get_sigtap_name
from registro.registro_model import Registro

# Variação (em pontos percentuais) a partir da qual a linha ganha destaque.
LIMITE_DESTAQUE = 20.0


def variacao_percentual(atual: float, anterior: float) -> float | None:
    """Variação % de ``atual`` sobre ``anterior``; None quando não há base."""
    if not anterior:
        return None
    return round((atual - anterior) / anterior * 100, 1)


def metricas(registros: list[Registro], pacientes_novos: int = 0, grupo_ids: frozenset = frozenset()) -> dict:
    """Totais de uma competência. ``grupo_ids`` são os procedimentos de grupo;
    todo atendimento lançado dentro de um grupo também conta como grupo."""
    atendimentos = sum(r.quantity or 1 for r in registros)
    pacientes = {r.patient_id for r in registros}
    grupo = sum(r.quantity or 1 for r in registros if r.group_id or r.procedure_id in grupo_ids)
    territorio = sum(r.quantity or 1 for r in registros if (r.local_realizacao or "C") == "T")
    return {
        "atendimentos": atendimentos,
        "lancamentos": len(registros),
        "pacientes": len(pacientes),
        "pacientes_novos": pacientes_novos,
        "profissionais": len({r.professional_id for r in registros if r.professional_id}),
        "procedimentos": len({r.procedure_id for r in registros}),
        "individual": atendimentos - grupo,
        "grupo": grupo,
        "caps": atendimentos - territorio,
        "territorio": territorio,
        "media_por_paciente": round(atendimentos / len(pacientes), 1) if pacientes else 0,
    }


def linha_comparacao(rotulo: str, valor_a: float, valor_b: float) -> dict:
    """Linha com o valor nas duas competências, a diferença e o percentual."""
    pct = variacao_percentual(valor_b, valor_a)
    return {
        "rotulo": rotulo,
        "a": valor_a,
        "b": valor_b,
        "diferenca": round(valor_b - valor_a, 1),
        "pct": pct,
        "destaque": pct is not None and abs(pct) >= LIMITE_DESTAQUE,
    }


def comparar_contagens(contagem_a: Counter, contagem_b: Counter) -> list[dict]:
    """Compara duas contagens por chave, da maior variação absoluta para a menor."""
    chaves = set(contagem_a) | set(contagem_b)
    linhas = [linha_comparacao(c, contagem_a.get(c, 0), contagem_b.get(c, 0)) for c in chaves]
    return sorted(linhas, key=lambda l: (-abs(l["diferenca"]), l["rotulo"]))


ROTULOS_METRICAS = [
    ("atendimentos", "Atendimentos (quantidade)"),
    ("lancamentos", "Lançamentos"),
    ("pacientes", "Pacientes atendidos"),
    ("pacientes_novos", "Pacientes novos (cadastro)"),
    ("profissionais", "Profissionais com produção"),
    ("procedimentos", "Procedimentos distintos"),
    ("individual", "Individual"),
    ("grupo", "Grupo"),
    ("caps", "Realizados no CAPS"),
    ("territorio", "Realizados no território"),
    ("media_por_paciente", "Média de atendimentos por paciente"),
]


class ComparativoService:

    @staticmethod
    def comparar(db: Session, mes_a: str, mes_b: str) -> dict:
        """Compara ``mes_a`` (base) com ``mes_b``. A diferença é sempre B − A."""
        regs = {m: db.query(Registro).filter(Registro.service_month == m).all() for m in (mes_a, mes_b)}
        profissionais = {p.id: p.name for p in db.query(Profissional).all()}
        procedimentos = {p.id: p for p in db.query(Procedimento).all()}
        grupo_ids = frozenset(
            i for i, p in procedimentos.items() if p.name and "grupo" in p.name.lower()
        )
        novos = {m: 0 for m in (mes_a, mes_b)}
        for p in db.query(Paciente).all():
            if p.created_at and p.created_at.strftime("%Y-%m") in novos:
                novos[p.created_at.strftime("%Y-%m")] += 1

        met = {m: metricas(regs[m], novos[m], grupo_ids) for m in (mes_a, mes_b)}
        linhas = [linha_comparacao(rotulo, met[mes_a][chave], met[mes_b][chave]) for chave, rotulo in ROTULOS_METRICAS]

        def contar(mes, chave_fn):
            c = Counter()
            for r in regs[mes]:
                c[chave_fn(r)] += r.quantity or 1
            return c

        def nome_prof(r):
            return profissionais.get(r.professional_id, "Não informado")

        def nome_proc(r):
            p = procedimentos.get(r.procedure_id)
            return (get_sigtap_name(p.code) or p.name) if p else "Não informado"

        return {
            "mes_a": mes_a,
            "mes_b": mes_b,
            "linhas": linhas,
            "por_profissional": comparar_contagens(contar(mes_a, nome_prof), contar(mes_b, nome_prof)),
            "por_procedimento": comparar_contagens(contar(mes_a, nome_proc), contar(mes_b, nome_proc)),
            "metricas": met,
        }
