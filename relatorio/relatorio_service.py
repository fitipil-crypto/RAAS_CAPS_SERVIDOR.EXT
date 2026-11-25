"""
Serviço para relatórios e estatísticas.
"""
from collections import Counter
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from grupo.grupo_service import GrupoService
from registro.registro_service import RegistroService
from paciente.paciente_service import PacienteService
from profissional.profissional_service import ProfissionalService
from procedimento.procedimento_service import ProcedimentoService, get_sigtap_name
from sistema.reference_data import atendimento_e_grupo


class RelatorioService:

    @staticmethod
    def get_dashboard_stats(db: Session) -> dict:
        return {
            "total_pacientes": len(PacienteService.listar_todos(db)),
            "total_profissionais": len(ProfissionalService.listar_todos(db, ativos_only=True)),
            "total_procedimentos": len(ProcedimentoService.listar_todos(db, ativos_only=True)),
            "total_registros": len(RegistroService.listar_todos(db)),
        }

    @staticmethod
    def _calc_age(birth_date: str) -> int | None:
        if not birth_date:
            return None
        try:
            bd = datetime.strptime(birth_date, "%Y-%m-%d")
            today = datetime.now()
            age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            return age if age >= 0 else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _e_grupo(registro, proc) -> bool:
        # Mesma regra usada ao gravar o tipo do registro (sistema.reference_data):
        # lançado num grupo ou procedimento de grupo.
        return atendimento_e_grupo(registro.group_id, proc.name if proc else "")

    @staticmethod
    def _age_group(age: int | None) -> str:
        if age is None:
            return "Não informado"
        if age < 18:
            return "0-17 anos"
        if age < 30:
            return "18-29 anos"
        if age < 45:
            return "30-44 anos"
        if age < 60:
            return "45-59 anos"
        return "60+ anos"

    @staticmethod
    def get_relatorio_completo(db: Session, month: str = None) -> dict:
        registros = RegistroService.listar_todos(db)
        pacientes = {p.id: p for p in PacienteService.listar_todos(db)}
        profissionais = {p.id: p for p in ProfissionalService.listar_todos(db)}
        procedimentos = {p.id: p for p in ProcedimentoService.listar_todos(db)}

        # Filtrar por mês se informado
        if month:
            registros = [r for r in registros if r.service_month == month]

        # Stats básicas
        total_atendimentos = sum(r.quantity or 1 for r in registros)
        pacientes_ativos_ids = {r.patient_id for r in registros}
        pacientes_ativos = len(pacientes_ativos_ids)

        # Novos pacientes (criados no período do filtro ou nos últimos 30 dias)
        if month:
            new_patients = sum(
                1 for p in pacientes.values()
                if p.created_at and p.created_at.strftime("%Y-%m") == month
            )
        else:
            cutoff = datetime.now() - timedelta(days=30)
            new_patients = sum(
                1 for p in pacientes.values()
                if p.created_at and p.created_at >= cutoff
            )

        # Top 10 profissionais
        by_prof = Counter()
        for r in registros:
            if r.professional_id:
                prof = profissionais.get(r.professional_id)
                if prof:
                    by_prof[prof.name] += r.quantity or 1
        top_profs = by_prof.most_common(10)

        # Top 10 procedimentos
        by_proc = Counter()
        for r in registros:
            proc = procedimentos.get(r.procedure_id)
            if proc:
                # Prioriza o nome editado no cadastro; usa o SIGTAP apenas como fallback.
                name = proc.name or get_sigtap_name(proc.code) or proc.code
                by_proc[name] += r.quantity or 1
        top_procs = by_proc.most_common(10)

        # Atendimentos por mês (últimos 6) — ancorado no mês do filtro quando
        # informado, para que o mês escolhido sempre apareça no gráfico.
        if month:
            anchor_year, anchor_month = (int(x) for x in month.split("-"))
        else:
            now = datetime.now()
            anchor_year, anchor_month = now.year, now.month
        months = []
        for i in range(5, -1, -1):
            year = anchor_year
            mo = anchor_month - i
            while mo <= 0:
                mo += 12
                year -= 1
            months.append(f"{year:04d}-{mo:02d}")

        all_registros = RegistroService.listar_todos(db)
        month_counts = Counter()
        for r in all_registros:
            month_counts[r.service_month] += r.quantity or 1

        monthly = []
        for m in months:
            monthly.append({"month": m, "count": month_counts.get(m, 0)})

        # Demografia: gênero
        gender_counts = Counter()
        for pid in pacientes_ativos_ids:
            p = pacientes.get(pid)
            if p:
                g = p.gender or "Não informado"
                gender_counts["Masculino" if g == "M" else "Feminino" if g == "F" else "Não informado"] += 1

        # Demografia: faixas etárias
        age_groups = Counter()
        for pid in pacientes_ativos_ids:
            p = pacientes.get(pid)
            if p:
                age = RelatorioService._calc_age(p.birth_date)
                age_groups[RelatorioService._age_group(age)] += 1

        # Distribuição de CID principal
        cid_counts = Counter()
        for pid in pacientes_ativos_ids:
            p = pacientes.get(pid)
            if p and p.cid_main:
                cid_counts[p.cid_main] += 1
        top_cids = cid_counts.most_common(10)

        # Distribuição por tipo de atendimento (Individual x Grupo): conta como
        # grupo o atendimento lançado dentro de um grupo e todo procedimento com
        # "grupo" no nome.
        service_type_counts = Counter({"Individual": 0, "Grupo": 0})
        for r in registros:
            proc = procedimentos.get(r.procedure_id)
            label = "Grupo" if RelatorioService._e_grupo(r, proc) else "Individual"
            service_type_counts[label] += r.quantity or 1

        # Individual x Grupo por profissional cadastrado. As sessões são os
        # grupos de atendimento da competência em que o profissional lançou
        # pelo menos um atendimento — cada grupo conta uma sessão.
        sessoes_por_prof = GrupoService.sessoes_por_profissional(db, month)
        prof_service_stats = {p.id: {"name": p.name, "individual": 0, "grupo": 0} for p in profissionais.values()}
        for r in registros:
            if not r.professional_id or r.professional_id not in prof_service_stats:
                continue
            proc = procedimentos.get(r.procedure_id)
            key = "grupo" if RelatorioService._e_grupo(r, proc) else "individual"
            prof_service_stats[r.professional_id][key] += r.quantity or 1
        prof_service_list = sorted(
            (
                {
                    **stats,
                    "total": stats["individual"] + stats["grupo"],
                    "total_sessoes": sessoes_por_prof.get(prof_id, 0),
                }
                for prof_id, stats in prof_service_stats.items()
            ),
            key=lambda row: row["total"],
            reverse=True,
        )

        # Distribuição por local de realização
        local_counts = Counter()
        local_labels = {"C": "CAPS", "T": "Território"}
        for r in registros:
            label = local_labels.get(r.local_realizacao or "C", r.local_realizacao or "C")
            local_counts[label] += r.quantity or 1

        # Atendimentos por dia da semana
        weekday_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        weekday_counts = [0] * 7
        for r in registros:
            try:
                d = datetime.strptime(r.service_date, "%Y-%m-%d")
                weekday_counts[d.weekday()] += r.quantity or 1
            except (ValueError, TypeError):
                pass
        weekday_data = [{"day": weekday_labels[i], "count": weekday_counts[i]} for i in range(7)]

        # Média de atendimentos por paciente
        avg_per_patient = round(total_atendimentos / pacientes_ativos, 1) if pacientes_ativos > 0 else 0

        return {
            "stats": RelatorioService.get_dashboard_stats(db),
            "total_atendimentos": total_atendimentos,
            "pacientes_ativos": pacientes_ativos,
            "novos_pacientes": new_patients,
            "avg_per_patient": avg_per_patient,
            "top_profissionais": top_profs,
            "top_procedimentos": top_procs,
            "monthly": monthly,
            "gender_distribution": dict(gender_counts),
            "age_groups": dict(age_groups),
            "top_cids": top_cids,
            "service_type_distribution": dict(service_type_counts),
            "prof_service_stats": prof_service_list,
            "local_distribution": dict(local_counts),
            "weekday_distribution": weekday_data,
            "filter_month": month,
        }

    @staticmethod
    def get_indicadores_caps(db: Session, month: str = None) -> dict:
        """Dados do dashboard de indicadores CAPS para o mês informado
        (padrão: mês atual): produção mensal, perfil dos usuários,
        procedimentos mais realizados e indicadores de cuidado."""
        month = month or datetime.now().strftime("%Y-%m")
        base = RelatorioService.get_relatorio_completo(db, month=month)
        pacientes = {p.id: p for p in PacienteService.listar_todos(db)}

        registros = RegistroService.listar_todos(db, month=month)
        ativos_ids = {r.patient_id for r in registros}
        ativos = [pacientes[i] for i in ativos_ids if i in pacientes]
        n_ativos = len(ativos)

        total = base["total_atendimentos"]
        local = base["local_distribution"]
        tipo = base["service_type_distribution"]

        def pct(parte, todo):
            return round(parte / todo * 100, 1) if todo else 0

        # Usuários em tratamento sem atendimento no mês (possível busca ativa)
        sem_atendimento = [
            p for p in pacientes.values()
            if not p.conclusion_date and p.id not in ativos_ids
        ]

        indicadores = {
            "pct_territorio": pct(local.get("Território", 0), total),
            "pct_grupo": pct(tipo.get("Grupo", 0), total),
            "media_por_usuario": base["avg_per_patient"],
            "admissoes_mes": sum(
                1 for p in pacientes.values()
                if p.admission_date and p.admission_date.startswith(month)
            ),
            "desligamentos_mes": sum(
                1 for p in pacientes.values()
                if p.conclusion_date and p.conclusion_date.startswith(month)
            ),
            "situacao_rua": sum(1 for p in ativos if p.street_situation == "S"),
            "uso_alcool": sum(1 for p in ativos if p.alcohol_user),
            "uso_crack": sum(1 for p in ativos if p.crack_user),
            "uso_outras_drogas": sum(1 for p in ativos if p.other_drugs_user),
            "sem_atendimento_no_mes": len(sem_atendimento),
            "pct_sem_atendimento": pct(
                len(sem_atendimento), len(sem_atendimento) + n_ativos
            ),
        }

        return {
            "month": month,
            "total_atendimentos": total,
            "usuarios_atendidos": n_ativos,
            "producao_mensal": RelatorioService.get_comparativo_mensal(
                db, n_months=12, end_month=month
            ),
            "genero": base["gender_distribution"],
            "faixa_etaria": base["age_groups"],
            "top_cids": base["top_cids"],
            "top_procedimentos": base["top_procedimentos"],
            "local": local,
            "tipo_atendimento": tipo,
            "indicadores": indicadores,
            # Seções que vieram da antiga tela Relatórios
            "novos_pacientes": base["novos_pacientes"],
            "stats": base["stats"],
            "top_profissionais": base["top_profissionais"],
            "prof_service_stats": [p for p in base["prof_service_stats"] if p["total"]],
            "dia_semana": [(w["day"], w["count"]) for w in base["weekday_distribution"]],
        }

    @staticmethod
    def get_comparativo_mensal(db: Session, n_months: int = 12, end_month: str = None) -> list:
        """Comparativo mês a mês dos últimos n_months com métricas detalhadas.

        A janela termina no mês informado em ``end_month`` (mês do filtro da
        página), ou no mês atual quando não informado — garante que o mês
        escolhido no filtro sempre apareça no comparativo.

        Retorna lista de dicts (ordem cronológica crescente) com:
          month, label, atendimentos, pacientes_ativos, novos_pacientes,
          procedimentos_distintos, profissionais_ativos, media_por_paciente,
          var_atendimentos (% vs mês anterior), var_pacientes (% vs mês anterior).
        """
        all_registros = RegistroService.listar_todos(db)
        pacientes = {p.id: p for p in PacienteService.listar_todos(db)}

        if end_month:
            anchor_year, anchor_month = (int(x) for x in end_month.split("-"))
        else:
            now = datetime.now()
            anchor_year, anchor_month = now.year, now.month
        months_list = []
        for i in range(n_months - 1, -1, -1):
            year = anchor_year
            mo = anchor_month - i
            while mo <= 0:
                mo += 12
                year -= 1
            mk = f"{year:04d}-{mo:02d}"
            months_list.append(mk)

        regs_by_month = {}
        for r in all_registros:
            regs_by_month.setdefault(r.service_month, []).append(r)

        first_seen = {}
        for p in pacientes.values():
            if p.created_at:
                mk = p.created_at.strftime("%Y-%m")
                first_seen.setdefault(mk, 0)
                first_seen[mk] += 1

        # Primeiro calcula dados de todos os meses do intervalo
        all_rows = []
        for mk in months_list:
            regs = regs_by_month.get(mk, [])
            atendimentos = sum(r.quantity or 1 for r in regs)
            pat_ids = {r.patient_id for r in regs}
            pacientes_ativos = len(pat_ids)
            novos = first_seen.get(mk, 0)
            proc_ids = {r.procedure_id for r in regs}
            prof_ids = {r.professional_id for r in regs if r.professional_id}
            media = round(atendimentos / pacientes_ativos, 1) if pacientes_ativos > 0 else 0

            label_parts = mk.split("-")
            month_names = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                           "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
            label = f"{month_names[int(label_parts[1]) - 1]}/{label_parts[0][2:]}"

            all_rows.append({
                "month": mk,
                "label": label,
                "atendimentos": atendimentos,
                "pacientes_ativos": pacientes_ativos,
                "novos_pacientes": novos,
                "procedimentos_distintos": len(proc_ids),
                "profissionais_ativos": len(prof_ids),
                "media_por_paciente": media,
            })

        # Sempre mostra todos os meses da janela (mesmo sem dados) — omitir
        # meses vazios quebrava a comparação mês a mês (variação calculada
        # entre meses não adjacentes) e podia esconder o mês do filtro.
        result = []
        prev_atend = None
        prev_pac = None
        for row in all_rows:
            var_atend = None
            if prev_atend is not None and prev_atend > 0:
                var_atend = round((row["atendimentos"] - prev_atend) / prev_atend * 100, 1)
            var_pac = None
            if prev_pac is not None and prev_pac > 0:
                var_pac = round((row["pacientes_ativos"] - prev_pac) / prev_pac * 100, 1)

            result.append({
                "month": row["month"],
                "label": row["label"],
                "atendimentos": row["atendimentos"],
                "pacientes_ativos": row["pacientes_ativos"],
                "novos_pacientes": row["novos_pacientes"],
                "procedimentos_distintos": row["procedimentos_distintos"],
                "profissionais_ativos": row["profissionais_ativos"],
                "media_por_paciente": row["media_por_paciente"],
                "var_atendimentos": var_atend,
                "var_pacientes": var_pac,
            })

            prev_atend = row["atendimentos"]
            prev_pac = row["pacientes_ativos"]

        return result
