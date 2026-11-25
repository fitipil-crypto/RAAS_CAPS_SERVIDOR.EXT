"""
Relatórios Impressão.

Dois tipos de relatório, ambos com impressão e exportação CSV, Excel e PDF:
  • Pacientes: lista no formato da planilha do CAPS, com os campos escolhidos
    pelo usuário (catálogo CAMPOS) e filtros detalhados.
  • Indicadores: as seções do item Relatórios (resumo, atendimentos por mês,
    tops, distribuições...) em forma de tabela.

Os dois tipos viram uma lista de "blocos" (título + colunas + linhas) e um
único conjunto de geradores transforma os blocos em CSV, Excel ou PDF.
"""
import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from paciente.paciente_model import Paciente
from paciente.paciente_schema import SITUACOES_PACIENTE
from registro.registro_model import Registro

# Paleta da planilha: cabeçalho verde-oliva, linhas alternadas amarelo-claro, barra
# "Emitido em" marrom-claro com texto preto em negrito,
# CID de TEA (F84) em azul e uma cor por psiquiatra.
COR_CABECALHO = "C4D79B"
COR_ZEBRA = "FFF9E0"
COR_EMISSAO = "C4A077"
COR_BORDA = "7F7F7F"
COR_TEA = "0099CC"
CORES_MEDICO = ["C00000", "000000", "1F4E79", "7030A0", "375623", "974706"]

ETNIAS = {"01": "BRANCA", "02": "PRETA", "03": "PARDA", "04": "AMARELA", "05": "INDÍGENA"}
SEXOS = {"M": "Masculino", "F": "Feminino"}
ORIGENS = {
    "01": "Demanda espontânea", "02": "Atenção básica", "03": "Serviço de urgência",
    "04": "Outro CAPS", "05": "Hospital dia", "06": "Hospital psiquiátrico",
}
DESTINOS = {
    "00": "Permanência", "01": "Outro CAPS", "02": "Atenção básica", "03": "Alta", "04": "Óbito",
}
SIMNAO = {"S": "Sim", "N": "Não"}


@dataclass
class Coluna:
    chave: str
    titulo: str
    largura: int
    grupo: str = ""
    centro: bool = False
    rotulo: str = ""  # nome na lista de campos, quando o cabeçalho da coluna é abreviado


# Catálogo de campos do relatório de pacientes, na ordem em que aparecem.
CAMPOS = [
    Coluna("nome", "Paciente", 34, "Identificação"),
    Coluna("cns", "CNS", 15, "Identificação"),
    Coluna("cpf", "CPF", 13, "Identificação"),
    Coluna("prontuario", "Pront", 7, "Identificação", True),
    Coluna("matricula", "Data Admiss", 10, "Clínico/Social", True, rotulo="Data de admissão"),
    Coluna("conclusao", "Conclusão", 10, "Clínico/Social", True),
    Coluna("cid1", "CID Princ.", 8, "Clínico/Social", True),
    Coluna("cid2", "CID Sec. 1", 8, "Clínico/Social", True),
    Coluna("cid3", "CID Sec. 2", 8, "Clínico/Social", True),
    Coluna("cid5", "CID Sec. 3", 8, "Clínico/Social", True),
    Coluna("cid4", "CID Causas", 8, "Clínico/Social", True),
    Coluna("nascimento", "Data Nasc", 10, "Identificação", True),
    Coluna("idade", "Idade", 9, "Identificação", True),
    Coluna("sexo", "Sexo", 9, "Identificação", True),
    Coluna("etnia", "Etnia", 9, "Identificação", True),
    Coluna("mae", "Nome da Mãe", 26, "Identificação"),
    Coluna("responsavel", "Responsável", 22, "Identificação"),
    Coluna("telefone", "Telefone", 13, "Identificação"),
    Coluna("celular", "Celular", 13, "Identificação"),
    Coluna("email", "E-mail", 22, "Identificação"),
    Coluna("endereco", "Endereço", 30, "Endereço"),
    Coluna("bairro", "Bairro", 21, "Endereço"),
    Coluna("cidade", "Cidade", 16, "Endereço"),
    Coluna("uf", "UF", 4, "Endereço", True),
    Coluna("cep", "CEP", 10, "Endereço", True),
    Coluna("origem", "Origem", 16, "Clínico/Social"),
    Coluna("destino", "Destino", 14, "Clínico/Social"),
    Coluna("drogas", "Álcool/Drogas", 16, "Clínico/Social"),
    Coluna("rua", "Sit. Rua", 7, "Clínico/Social", True),
    Coluna("esf", "Cob. ESF", 7, "Clínico/Social", True),
    Coluna("cnes_usf", "CNES USF", 9, "Clínico/Social", True),
    Coluna("qtd_atend", "Atendimentos", 9, "Atendimentos", True),
    Coluna("ult_atend", "Último Atend.", 10, "Atendimentos", True),
    # Acompanhamento: sempre em sequência e no fim do relatório (mesma ordem da aba).
    Coluna("trs", "TRS", 16, "Acompanhamento"),
    Coluna("medico", "Drª", 14, "Acompanhamento"),
    Coluna("situacao", "Situação", 12, "Acompanhamento"),
    Coluna("encaminhado", "Encam. por", 16, "Acompanhamento"),
    Coluna("encaminhado_para", "Encam. p/ trat. em", 18, "Acompanhamento"),
    Coluna("tecnico_encaminhou", "Téc. que encam.", 16, "Acompanhamento"),
    Coluna("tecnico_alta", "Téc. que deu alta", 16, "Acompanhamento"),
]
CAMPOS_POR_CHAVE = {c.chave: c for c in CAMPOS}
COLUNA_N = Coluna("n", "Nº", 4, centro=True)

# Modelo padrão: as colunas da planilha do CAPS.
CAMPOS_PADRAO = [
    "nome", "cns", "cpf", "prontuario", "matricula", "cid1", "cid2", "cid3", "cid4",
    "nascimento", "idade", "etnia", "bairro", "trs", "medico", "situacao", "encaminhado",
]
GRUPOS_CAMPOS = ["Identificação", "Endereço", "Clínico/Social", "Atendimentos", "Acompanhamento"]

ORDENACOES = {
    "nome": "Nome",
    "bairro": "Bairro",
    "idade": "Idade",
    "matricula": "Data de admissão (mais recente)",
    "medico": "Psiquiatra",
    "prontuario": "Prontuário",
}

FILTROS_TEXTO = ("busca", "medico", "tecnico", "situacao", "sexo", "etnia", "bairro", "cid",
                 "idade_min", "idade_max", "admissao_de", "admissao_ate", "ordenar")

# Seções do item Relatórios que podem ir para a impressão.
SECOES = {
    "resumo": "Resumo",
    "cuidado": "Indicadores de Cuidado",
    "mensal": "Atendimentos por Mês (últimos 6)",
    "comparativo": "Comparativo Mês a Mês (12 meses)",
    "profissionais": "Top 10 Profissionais",
    "procedimentos": "Top 10 Procedimentos",
    "cids": "Top 10 CIDs Principais",
    "genero": "Distribuição por Gênero",
    "faixas": "Faixas Etárias",
    "tipos": "Tipos de Atendimento",
    "prof_tipo": "Individual x Grupo por Profissional",
    "local": "Local de Realização",
    "semana": "Atendimentos por Dia da Semana",
}
ORDEM_FAIXAS = ["0-17 anos", "18-29 anos", "30-44 anos", "45-59 anos", "60+ anos", "Não informado"]
MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


@dataclass
class Bloco:
    """Uma tabela do relatório. Cada célula é um valor simples ou um dict
    {"v": valor, "cor": "RRGGBB", "b": negrito, "barra": 0-100}."""
    titulo: str
    colunas: list[Coluna]
    linhas: list[list] = field(default_factory=list)
    vazio: str = "Nenhum dado disponível."
    rotulo_contagem: str = "registro(s)"


def valor(celula):
    return celula["v"] if isinstance(celula, dict) else celula


def _data_br(texto: str | None) -> str:
    if not texto:
        return ""
    try:
        return datetime.strptime(texto[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return texto


def _meses_de_vida(nascimento: str | None, hoje: date) -> int | None:
    if not nascimento:
        return None
    try:
        nasc = datetime.strptime(nascimento[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    meses = (hoje.year - nasc.year) * 12 + (hoje.month - nasc.month)
    if hoje.day < nasc.day:
        meses -= 1
    return meses if meses >= 0 else None


def idade_anos_meses(nascimento: str | None, hoje: date | None = None) -> str:
    """Idade no formato da planilha: '11 a 2 m'."""
    meses = _meses_de_vida(nascimento, hoje or date.today())
    return "" if meses is None else f"{meses // 12} a {meses % 12} m"


def eh_tea(cid: str) -> bool:
    return (cid or "").upper().replace(".", "").startswith("F84")


def _inteiro(texto) -> int | None:
    try:
        return int(texto)
    except (TypeError, ValueError):
        return None


def titulo_impressao(db: Session, sufixo: str = "Pacientes") -> str:
    from config.config_service import ConfigService
    sigla = ConfigService.obter_valor(db, "organ_code", "") or ConfigService.obter_valor(db, "organ_name", "")
    return f"{sigla} — {sufixo}" if sigla else sufixo


def ler_filtros(params) -> dict:
    return {k: (params.get(k) or "").strip() for k in FILTROS_TEXTO}


def ler_campos(params, salvos: list[str] | None = None) -> list[str]:
    """Campos pedidos na URL (?campo=a&campo=b), senão os salvos, senão o padrão.
    O nome do paciente sempre aparece."""
    if params.get("campos_enviados"):
        pedidos = params.getlist("campo")
    else:
        pedidos = salvos or CAMPOS_PADRAO
    escolhidos = [c.chave for c in CAMPOS if c.chave in set(pedidos)]
    return escolhidos if "nome" in escolhidos else ["nome"] + escolhidos


def ler_secoes(params, salvas: list[str] | None = None) -> list[str]:
    if params.get("secoes_enviadas"):
        pedidas = params.getlist("secao")
    else:
        pedidas = salvas or list(SECOES)
    return [s for s in SECOES if s in set(pedidas)]


class ImpressaoService:

    # ── Relatório de pacientes ──────────────────────────────────────────────

    @staticmethod
    def opcoes_filtro(db: Session) -> dict:
        def distintos(coluna):
            return sorted({(v or "").strip() for (v,) in db.query(coluna).distinct().all() if (v or "").strip()})

        return {
            "medicos": distintos(Paciente.psychiatrist),
            "bairros": distintos(Paciente.neighborhood),
            "situacoes": SITUACOES_PACIENTE,
            "sexos": SEXOS,
            "etnias": ETNIAS,
            "ordenacoes": ORDENACOES,
        }

    @staticmethod
    def linhas(db: Session, filtros: dict | None = None, campos: list[str] | None = None) -> list[dict]:
        f = {k: "" for k in FILTROS_TEXTO}
        f.update(filtros or {})
        campos = campos or CAMPOS_PADRAO

        query = db.query(Paciente).filter(Paciente.anonimizado.isnot(True))
        if f["medico"]:
            query = query.filter(Paciente.psychiatrist == f["medico"])
        if f["tecnico"]:
            query = query.filter(Paciente.reference_technicians.ilike(f"%{f['tecnico']}%"))
        if f["situacao"] == "sem":
            query = query.filter((Paciente.patient_status.is_(None)) | (Paciente.patient_status == ""))
        elif f["situacao"]:
            query = query.filter(Paciente.patient_status == f["situacao"])
        if f["sexo"]:
            query = query.filter(Paciente.gender == f["sexo"])
        if f["etnia"]:
            query = query.filter(Paciente.race == f["etnia"])
        if f["bairro"]:
            query = query.filter(Paciente.neighborhood.ilike(f"%{f['bairro']}%"))
        if f["cid"]:
            prefixo = f"{f['cid'].upper()}%"
            query = query.filter(Paciente.cid_main.ilike(prefixo) | Paciente.cid_associated1.ilike(prefixo)
                                 | Paciente.cid_associated2.ilike(prefixo) | Paciente.cid_associated3.ilike(prefixo)
                                 | Paciente.cid_causes.ilike(prefixo))
        if f["admissao_de"]:
            query = query.filter(Paciente.admission_date >= f["admissao_de"])
        if f["admissao_ate"]:
            query = query.filter(Paciente.admission_date <= f["admissao_ate"])
        if f["busca"]:
            q = f"%{f['busca']}%"
            query = query.filter(Paciente.name.ilike(q) | Paciente.cns.ilike(q)
                                 | Paciente.prontuario.ilike(q) | Paciente.cpf.ilike(q))
        pacientes = query.order_by(Paciente.name.asc()).all()

        hoje = date.today()
        idade_min, idade_max = _inteiro(f["idade_min"]), _inteiro(f["idade_max"])
        if idade_min is not None or idade_max is not None:
            def na_faixa(p):
                meses = _meses_de_vida(p.birth_date, hoje)
                if meses is None:
                    return False
                anos = meses // 12
                return (idade_min is None or anos >= idade_min) and (idade_max is None or anos <= idade_max)
            pacientes = [p for p in pacientes if na_faixa(p)]

        atend = {}
        if pacientes and {"qtd_atend", "ult_atend"} & set(campos):
            consulta = (
                db.query(Registro.patient_id, func.sum(Registro.quantity), func.max(Registro.service_date))
                .filter(Registro.patient_id.in_([p.id for p in pacientes]))
                .group_by(Registro.patient_id)
            )
            atend = {pid: (total or 0, ultimo) for pid, total, ultimo in consulta.all()}

        cor_medico = {m: CORES_MEDICO[i % len(CORES_MEDICO)]
                      for i, m in enumerate(ImpressaoService.opcoes_filtro(db)["medicos"])}

        linhas = []
        for p in pacientes:
            medico = (p.psychiatrist or "").strip()
            drogas = [nome for nome, marcado in (("Álcool", p.alcohol_user), ("Crack", p.crack_user),
                                                  ("Outras", p.other_drugs_user)) if marcado]
            endereco = " ".join(x for x in (p.street_type, p.address) if x)
            if p.street_number:
                endereco += f", {p.street_number}"
            if p.address_complement:
                endereco += f" - {p.address_complement}"
            total, ultimo = atend.get(p.id, (0, None))
            linhas.append({
                "nome": p.name or "",
                "medico": medico,
                "cor_medico": cor_medico.get(medico, "000000"),
                "cns": p.cns or "",
                "cpf": p.cpf or "",
                "prontuario": p.prontuario or "",
                "matricula": _data_br(p.admission_date),
                "conclusao": _data_br(p.conclusion_date),
                "trs": p.reference_technicians or "",
                "cid1": p.cid_main or "",
                "cid2": p.cid_associated1 or "",
                "cid3": p.cid_associated2 or "",
                "cid4": p.cid_causes or "",
                "cid5": p.cid_associated3 or "",
                "nascimento": _data_br(p.birth_date),
                "idade": idade_anos_meses(p.birth_date, hoje),
                "sexo": SEXOS.get(p.gender or "", ""),
                "encaminhado": p.referred_by or "",
                "encaminhado_para": p.referred_to or "",
                "tecnico_encaminhou": p.referring_technician or "",
                "tecnico_alta": p.discharge_technician or "",
                "etnia": ETNIAS.get(p.race or "", ""),
                "mae": p.mother_name or "",
                "responsavel": p.guardian_name or "",
                "telefone": p.phone or "",
                "celular": p.cell_phone or "",
                "email": p.email or "",
                "endereco": endereco,
                "bairro": p.neighborhood or "",
                "cidade": p.city or "",
                "uf": p.state or "",
                "cep": p.cep or "",
                "origem": ORIGENS.get(p.user_origin or "", ""),
                "destino": DESTINOS.get(p.user_destination or "", ""),
                "drogas": ", ".join(drogas),
                "rua": SIMNAO.get(p.street_situation or "", ""),
                "esf": SIMNAO.get(p.esf_coverage or "", ""),
                "cnes_usf": p.cnes_usf or "",
                "situacao": SITUACOES_PACIENTE.get(p.patient_status or "", ""),
                "qtd_atend": total,
                "ult_atend": _data_br(ultimo),
                # Chaves auxiliares de ordenação
                "_meses": _meses_de_vida(p.birth_date, hoje),
                "_admissao": p.admission_date or "",
            })

        ordem = f["ordenar"]
        if ordem == "bairro":
            linhas.sort(key=lambda l: (l["bairro"].upper() or "~", l["nome"].upper()))
        elif ordem == "idade":
            linhas.sort(key=lambda l: (l["_meses"] is None, l["_meses"] or 0, l["nome"].upper()))
        elif ordem == "matricula":
            linhas.sort(key=lambda l: l["_admissao"], reverse=True)
        elif ordem == "medico":
            linhas.sort(key=lambda l: (l["medico"].upper() or "~", l["nome"].upper()))
        elif ordem == "prontuario":
            linhas.sort(key=lambda l: (_inteiro(l["prontuario"]) is None, _inteiro(l["prontuario"]) or 0))
        for i, linha in enumerate(linhas, start=1):
            linha["n"] = i
        return linhas

    @staticmethod
    def bloco_pacientes(linhas: list[dict], campos: list[str], titulo: str) -> Bloco:
        colunas = [COLUNA_N] + [CAMPOS_POR_CHAVE[c] for c in campos]
        bloco = Bloco(titulo, colunas, vazio="Nenhum paciente encontrado com esses filtros.", rotulo_contagem="paciente(s)")
        for l in linhas:
            linha = []
            for col in colunas:
                v = l[col.chave]
                if col.chave == "medico":
                    linha.append({"v": v, "cor": l["cor_medico"]})
                elif col.chave.startswith("cid") and eh_tea(v):
                    linha.append({"v": v, "cor": COR_TEA})
                elif col.chave == "idade":
                    linha.append({"v": v, "b": True})
                else:
                    linha.append(v)
            bloco.linhas.append(linha)
        return bloco

    # ── Relatório de indicadores (item Relatórios) ──────────────────────────

    @staticmethod
    def blocos_indicadores(db: Session, month: str | None, secoes: list[str]) -> list[Bloco]:
        from relatorio.relatorio_service import RelatorioService

        d = RelatorioService.get_relatorio_completo(db, month=month)
        total = d["total_atendimentos"] or 0
        ativos = d["pacientes_ativos"] or 0

        def pct(parte, todo):
            p = round(parte / todo * 100, 1) if todo else 0
            return {"v": f"{p:.1f}%".replace(".", ","), "barra": p}

        def mes(chave):
            ano, m = chave.split("-")
            return f"{MESES[int(m) - 1]}/{ano[2:]}"

        def decimal(v):
            return str(v).replace(".", ",")

        def var(v):
            if v is None:
                return "—"
            return {"v": f"{'+' if v > 0 else ''}{v:.1f}%".replace(".", ","),
                    "cor": "375623" if v > 0 else ("C00000" if v < 0 else "000000")}

        C = Coluna
        tabelas = {}  # seção → (linhas, colunas)
        if "resumo" in secoes:
            s = d["stats"]
            tabelas["resumo"] = [
                ["Atendimentos" + (" no período" if month else ""), total],
                ["Pacientes ativos", ativos],
                ["Novos pacientes", d["novos_pacientes"]],
                ["Média atendimentos/paciente", decimal(d["avg_per_patient"])],
                ["Total de pacientes cadastrados", s["total_pacientes"]],
                ["Profissionais ativos", s["total_profissionais"]],
                ["Procedimentos ativos", s["total_procedimentos"]],
                ["Total de registros", s["total_registros"]],
            ], [C("i", "Indicador", 40), C("v", "Valor", 14, centro=True)]
        titulos = dict(SECOES)
        if "cuidado" in secoes:
            # São indicadores do mês: sem competência escolhida, usa o mês atual.
            caps = RelatorioService.get_indicadores_caps(db, month=month)
            ind = caps["indicadores"]
            if not month:
                titulos["cuidado"] += f" ({mes(caps['month'])})"
            tabelas["cuidado"] = [
                ["Usuários atendidos", caps["usuarios_atendidos"]],
                ["Atendimentos por usuário", decimal(ind["media_por_usuario"])],
                ["Atividades no território", decimal(f"{ind['pct_territorio']}%")],
                ["Atendimentos em grupo", decimal(f"{ind['pct_grupo']}%")],
                ["Admissões no mês", ind["admissoes_mes"]],
                ["Desligamentos no mês", ind["desligamentos_mes"]],
                ["Em situação de rua", ind["situacao_rua"]],
                ["Uso de álcool", ind["uso_alcool"]],
                ["Uso de crack", ind["uso_crack"]],
                ["Uso de outras drogas", ind["uso_outras_drogas"]],
                ["Sem atendimento no mês (busca ativa)",
                 f"{ind['sem_atendimento_no_mes']} ({decimal(ind['pct_sem_atendimento'])}%)"],
            ], [C("i", "Indicador", 40), C("v", "Valor", 14, centro=True)]
        if "mensal" in secoes:
            maior = max((m["count"] for m in d["monthly"]), default=0)
            tabelas["mensal"] = [
                [mes(m["month"]), m["count"], pct(m["count"], maior)] for m in d["monthly"]
            ], [C("m", "Mês", 14), C("a", "Atendimentos", 14, centro=True), C("p", "% do maior mês", 26)]
        if "comparativo" in secoes:
            comp = RelatorioService.get_comparativo_mensal(db, n_months=12, end_month=month)
            tabelas["comparativo"] = [
                [r["label"], r["atendimentos"], var(r["var_atendimentos"]), r["pacientes_ativos"],
                 var(r["var_pacientes"]), r["novos_pacientes"], r["procedimentos_distintos"],
                 r["profissionais_ativos"], decimal(r["media_por_paciente"])]
                for r in reversed(comp)
            ], [C("m", "Mês", 10), C("a", "Atendimentos", 12, centro=True), C("va", "Var.", 9, centro=True),
                C("p", "Pac. ativos", 11, centro=True), C("vp", "Var.", 9, centro=True),
                C("n", "Novos pac.", 10, centro=True), C("pr", "Proced.", 9, centro=True),
                C("pf", "Profis.", 9, centro=True), C("md", "Média/pac.", 10, centro=True)]

        def ranking(secao, itens, rotulo, unidade, base):
            tabelas[secao] = [[i, nome, qtd, pct(qtd, base)] for i, (nome, qtd) in enumerate(itens, start=1)], \
                [C("i", "#", 4, centro=True), C("n", rotulo, 44), C("q", unidade, 13, centro=True), C("p", "%", 24)]

        def distribuicao(secao, itens, rotulo, unidade):
            base = sum(q for _, q in itens)
            tabelas[secao] = [[nome, qtd, pct(qtd, base)] for nome, qtd in itens], \
                [C("n", rotulo, 26), C("q", unidade, 13, centro=True), C("p", "%", 28)]

        if "profissionais" in secoes:
            ranking("profissionais", d["top_profissionais"], "Profissional", "Atendimentos", total)
        if "procedimentos" in secoes:
            ranking("procedimentos", d["top_procedimentos"], "Procedimento", "Atendimentos", total)
        if "cids" in secoes:
            ranking("cids", d["top_cids"], "CID", "Pacientes", ativos)
        if "genero" in secoes:
            distribuicao("genero", list(d["gender_distribution"].items()), "Gênero", "Pacientes")
        if "faixas" in secoes:
            faixas = d["age_groups"]
            distribuicao("faixas", [(f, faixas[f]) for f in ORDEM_FAIXAS if faixas.get(f)], "Faixa etária", "Pacientes")
        if "tipos" in secoes:
            distribuicao("tipos", list(d["service_type_distribution"].items()), "Tipo", "Atendimentos")
        if "prof_tipo" in secoes:
            tabelas["prof_tipo"] = [
                [p["name"], p["individual"], p["grupo"], p["total_sessoes"], {"v": p["total"], "b": True}]
                for p in d["prof_service_stats"] if p["total"]
            ], [C("n", "Profissional", 40), C("i", "Individual", 12, centro=True), C("g", "Grupo", 12, centro=True),
                C("ts", "Sessões", 12, centro=True), C("t", "Total", 12, centro=True)]
        if "local" in secoes:
            distribuicao("local", list(d["local_distribution"].items()), "Local", "Atendimentos")
        if "semana" in secoes:
            distribuicao("semana", [(w["day"], w["count"]) for w in d["weekday_distribution"]], "Dia", "Atendimentos")

        return [Bloco(titulos[s], tabelas[s][1], tabelas[s][0]) for s in secoes if s in tabelas]

    # ── Geradores de arquivo (servem aos dois tipos de relatório) ───────────

    @staticmethod
    def gerar_csv(blocos: list[Bloco]) -> bytes:
        saida = io.StringIO()
        saida.write("﻿")
        escritor = csv.writer(saida, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        varios = len(blocos) > 1
        for i, bloco in enumerate(blocos):
            if varios:
                if i:
                    escritor.writerow([])
                escritor.writerow([bloco.titulo])
            escritor.writerow([c.titulo for c in bloco.colunas])
            for linha in bloco.linhas:
                escritor.writerow([valor(c) for c in linha])
        return saida.getvalue().encode("utf-8")

    @staticmethod
    def gerar_excel(blocos: list[Bloco], titulo: str, subtitulo: str = "") -> bytes:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        wb.remove(wb.active)
        lado = Side(style="thin", color=COR_BORDA)
        borda = Border(left=lado, right=lado, top=lado, bottom=lado)
        centro = Alignment(horizontal="center", vertical="center")
        fundo_cab = PatternFill("solid", fgColor=COR_CABECALHO)
        fundo_res = PatternFill("solid", fgColor=COR_EMISSAO)
        emissao = f"Emitido em {date.today().strftime('%d/%m/%Y')}{subtitulo}"
        usados = set()

        for bloco in blocos:
            nome = "".join(ch for ch in bloco.titulo if ch not in "[]:*?/\\")[:31] or "Relatório"
            while nome in usados:
                nome = f"{nome[:27]} {len(usados)}"
            usados.add(nome)
            ws = wb.create_sheet(nome)
            n = len(bloco.colunas)

            ws.cell(row=1, column=1, value=titulo if len(blocos) == 1 else f"{titulo} — {bloco.titulo}")
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n)
            ws["A1"].font = Font(bold=True, size=14)
            ws["A1"].alignment = centro
            ws["A1"].fill = fundo_cab

            for col, c in enumerate(bloco.colunas, start=1):
                cel = ws.cell(row=2, column=col, value=c.titulo)
                cel.font = Font(bold=True)
                cel.fill = fundo_cab
                cel.alignment = centro
                cel.border = borda

            ws.cell(row=3, column=1, value=f"{emissao} — {len(bloco.linhas)} linha(s)")
            ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=n)
            for col in range(1, n + 1):
                cel = ws.cell(row=3, column=col)
                cel.fill = fundo_res
                cel.font = Font(bold=True, size=9)
                cel.border = borda

            for r, linha in enumerate(bloco.linhas, start=4):
                for col, (c, celula) in enumerate(zip(bloco.colunas, linha), start=1):
                    cel = ws.cell(row=r, column=col, value=valor(celula))
                    cel.border = borda
                    if isinstance(celula, dict) and (celula.get("cor") or celula.get("b")):
                        cel.font = Font(color=celula.get("cor") or "000000", bold=bool(celula.get("b")))
                    if c.centro:
                        cel.alignment = centro

            for col, c in enumerate(bloco.colunas, start=1):
                ws.column_dimensions[get_column_letter(col)].width = c.largura + 2
            ws.freeze_panes = "C4" if n > 3 else "A4"
            if bloco.linhas:
                ws.auto_filter.ref = f"A2:{get_column_letter(n)}{3 + len(bloco.linhas)}"
            ws.page_setup.orientation = "landscape"
            ws.page_setup.fitToWidth = 1
            ws.page_setup.fitToHeight = 0
            ws.sheet_properties.pageSetUpPr.fitToPage = True
            ws.print_title_rows = "2:2"

        if not wb.sheetnames:
            wb.create_sheet("Relatório")
        saida = io.BytesIO()
        wb.save(saida)
        return saida.getvalue()

    @staticmethod
    def gerar_pdf(blocos: list[Bloco], titulo: str, subtitulo: str = "", metadados: dict | None = None) -> bytes:
        from fpdf import FPDF

        # As fontes embutidas do PDF só cobrem latin-1: troca o que não couber.
        def txt(texto) -> str:
            texto = str(texto).replace("—", "-").replace("–", "-").replace("…", "...")
            return texto.encode("latin-1", "replace").decode("latin-1")

        def rgb(hexcor: str) -> tuple[int, int, int]:
            return tuple(int(hexcor[i:i + 2], 16) for i in (0, 2, 4))

        metadados = metadados or {}
        organizacao = metadados.get("organizacao") or "RAAS-CAPS"
        sigla = metadados.get("sigla") or ""
        municipio = metadados.get("municipio") or "Município não informado"
        cnes = metadados.get("cnes") or "Não informado"
        impresso_por = metadados.get("impresso_por") or "Usuário do sistema"
        usuario = metadados.get("usuario") or ""
        gerado_em = metadados.get("gerado_em") or datetime.now().strftime("%d/%m/%Y %H:%M")

        MM_POR_UNIDADE = 2.3
        maior = max((sum(c.largura for c in b.colunas) for b in blocos), default=0)
        largura_natural = maior * MM_POR_UNIDADE
        formato_pagina = "A3" if largura_natural > 280 else "A4"
        orientacao = "L" if largura_natural > 194 else "P"
        pdf = FPDF(orientation=orientacao, unit="mm", format=formato_pagina)
        pdf.set_auto_page_break(auto=True, margin=17)
        TOPO_CORPO = 18
        pdf.set_margins(10, TOPO_CORPO, 10)
        largura_lateral = pdf.epw * 0.3
        pdf.set_title(txt(titulo))
        pdf.set_author(txt(impresso_por))
        altura = 5

        def rodape():
            pdf.set_draw_color(*rgb("CBD5E1"))
            pdf.line(10, pdf.h - 14, pdf.w - 10, pdf.h - 14)
            pdf.set_y(-11)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*rgb("475569"))
            esquerda = f"Impresso por: {impresso_por}"
            if usuario:
                esquerda += f" ({usuario})"
            esquerda += f" - {gerado_em}"
            pdf.cell(pdf.epw * 0.78, 4, txt(esquerda))
            pdf.cell(pdf.epw * 0.22, 4, txt(f"Página {pdf.page_no()}"), align="R")

        pdf.footer = rodape

        def cabecalho():
            # Identificação da unidade reaplicada em cada página, nas laterais
            # do título (que a primeira página imprime no centro desta faixa).
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*rgb("153E75"))
            pdf.set_xy(10, 5)
            pdf.cell(largura_lateral, 4.5, caber(organizacao, largura_lateral))
            pdf.set_xy(pdf.w - 10 - largura_lateral, 5)
            pdf.cell(largura_lateral, 4.5, caber(sigla, largura_lateral), align="R")

            pdf.set_font("Helvetica", "", 7.5)
            pdf.set_text_color(*rgb("475569"))
            pdf.set_xy(10, 10.5)
            pdf.cell(largura_lateral, 4, caber(f"Município: {municipio}", largura_lateral))
            pdf.set_xy(pdf.w - 10 - largura_lateral, 10.5)
            pdf.cell(largura_lateral, 4, caber(f"CNES: {cnes}", largura_lateral), align="R")

            pdf.set_draw_color(*rgb("CBD5E1"))
            pdf.line(10, 16, pdf.w - 10, 16)
            pdf.set_y(TOPO_CORPO)

        pdf.header = cabecalho

        def caber(texto, largura: float) -> str:
            texto = txt(texto)
            if pdf.get_string_width(texto) <= largura - 1.5:
                return texto
            while texto and pdf.get_string_width(texto + "...") > largura - 1.5:
                texto = texto[:-1]
            return texto + "..."

        def cabecalho_tabela(bloco, larguras):
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(0, 0, 0)
            pdf.set_fill_color(*rgb(COR_CABECALHO))
            pdf.set_draw_color(*rgb(COR_BORDA))
            for c, w in zip(bloco.colunas, larguras):
                pdf.cell(w, altura + 1, caber(c.titulo, w), border=1, align="C", fill=True)
            pdf.ln()

        pdf.add_page()
        pdf.set_text_color(*rgb("153E75"))
        # Reduz a fonte de títulos longos para não invadir as laterais do cabeçalho.
        tamanho = 14
        pdf.set_font("Helvetica", "B", tamanho)
        while tamanho > 8 and pdf.get_string_width(txt(titulo)) > pdf.epw - 2 * largura_lateral - 4:
            tamanho -= 0.5
            pdf.set_font("Helvetica", "B", tamanho)
        pdf.set_y(5)
        pdf.cell(0, 6, txt(titulo), align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*rgb("475569"))
        linha_contexto = f"Emitido em {gerado_em}"
        if subtitulo:
            linha_contexto += f" — {subtitulo}"
        pdf.cell(0, 4.5, txt(linha_contexto), align="C")
        pdf.set_y(TOPO_CORPO)

        for bloco in blocos:
            natural = sum(c.largura for c in bloco.colunas) * MM_POR_UNIDADE
            # Usa até 112% da largura natural nos relatórios mais estreitos,
            # aproveitando melhor a página sem comprometer relatórios largos.
            fator = min(1.12, pdf.epw / natural) if natural else 1
            larguras = [c.largura * MM_POR_UNIDADE * fator for c in bloco.colunas]
            largura_tabela = sum(larguras)
            x_tabela = pdf.l_margin + max(0, (pdf.epw - largura_tabela) / 2)

            # Título, cabeçalho e ao menos 3 linhas ficam juntos na mesma página.
            if pdf.will_page_break(6 + (altura + 1) + altura * min(3, max(len(bloco.linhas), 1))):
                pdf.add_page()
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(*rgb("153E75"))
            pdf.set_fill_color(*rgb("EAF2F8"))
            rotulo = bloco.titulo if len(blocos) > 1 else f"{len(bloco.linhas)} {bloco.rotulo_contagem}"
            pdf.cell(0, 6, txt(rotulo), fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
            pdf.set_x(x_tabela)
            cabecalho_tabela(bloco, larguras)

            if not bloco.linhas:
                pdf.set_font("Helvetica", "I", 7)
                pdf.set_x(x_tabela)
                pdf.cell(largura_tabela, altura, txt(bloco.vazio), border=1, align="C")
                pdf.ln()
            for i, linha in enumerate(bloco.linhas):
                if pdf.will_page_break(altura):
                    pdf.add_page()
                    pdf.set_x(x_tabela)
                    cabecalho_tabela(bloco, larguras)
                else:
                    pdf.set_x(x_tabela)
                for c, w, celula in zip(bloco.colunas, larguras, linha):
                    extra = celula if isinstance(celula, dict) else {}
                    pdf.set_font("Helvetica", "B" if extra.get("b") else "", 7.2)
                    pdf.set_text_color(*rgb(extra.get("cor") or "000000"))
                    pdf.set_fill_color(*rgb(COR_ZEBRA))
                    zebra = i % 2 == 1
                    if "barra" in extra:
                        # Célula de percentual: barra proporcional ao lado do número.
                        x, y = pdf.get_x(), pdf.get_y()
                        pdf.cell(w, altura, "", border=1, fill=zebra)
                        largura_barra = max(0, (w - 14) * min(extra["barra"], 100) / 100)
                        if largura_barra:
                            pdf.set_fill_color(*rgb(COR_CABECALHO))
                            pdf.rect(x + 0.8, y + 1, largura_barra, altura - 2, style="F")
                        pdf.set_xy(x + w - 13, y)
                        pdf.cell(12.5, altura, txt(extra["v"]), align="R")
                        pdf.set_xy(x + w, y)
                    else:
                        pdf.cell(w, altura, caber(valor(celula), w), border=1,
                                 align="C" if c.centro else "L", fill=zebra)
                pdf.ln()
            pdf.ln(4)
        return bytes(pdf.output())


# Relatórios operacionais que viraram abas de Relatórios Impressão (chave → rótulo da aba).
ABAS_OPERACIONAIS = {
    "atendimentos": "📝 Atendimentos realizados",
    "producao": "👨‍⚕️ Produção profissional",
    "busca-ativa": "🔎 Busca ativa",
    "incompletos": "🧾 Cadastros incompletos",
}


def preparar(db: Session, params, sessao: dict) -> dict:
    """Lê tipo, filtros, campos e seções da URL (lembrando a última escolha
    de campos e seções na sessão) e monta os blocos do relatório."""
    import re
    from urllib.parse import urlencode

    tipo = params.get("tipo") or "pacientes"
    if tipo in ABAS_OPERACIONAIS:
        from relatorio.relatorios_operacionais_service import RelatoriosOperacionaisService

        r = RelatoriosOperacionaisService.construir(db, tipo, params)
        filtros = {k: v for k, v in r["filtros"].items() if k != "dias_num"}
        r.update({
            "tipo": tipo,
            "titulo": titulo_impressao(db, r["titulo"]),
            "subtitulo": "",
            "qs": urlencode([("tipo", tipo)] + [(k, v) for k, v in filtros.items() if v]),
        })
        return r
    if tipo != "indicadores":
        tipo = "pacientes"
    if tipo == "pacientes":
        filtros = ler_filtros(params)
        campos = ler_campos(params, sessao.get("rimp_campos"))
        sessao["rimp_campos"] = campos
        titulo = titulo_impressao(db)
        linhas = ImpressaoService.linhas(db, filtros, campos)
        blocos = [ImpressaoService.bloco_pacientes(linhas, campos, titulo)]
        consulta = [("tipo", tipo)] + [(k, v) for k, v in filtros.items() if v] \
            + [("campos_enviados", "1")] + [("campo", c) for c in campos]
        return {"tipo": tipo, "filtros": filtros, "campos": campos, "linhas": linhas, "blocos": blocos,
                "titulo": titulo, "subtitulo": "", "qs": urlencode(consulta)}

    mes = params.get("mes") or ""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mes):
        mes = ""
    secoes = ler_secoes(params, sessao.get("rimp_secoes"))
    sessao["rimp_secoes"] = secoes
    periodo = f"{MESES[int(mes[5:]) - 1]}/{mes[:4]}" if mes else "todo o período"
    titulo = titulo_impressao(db, "Indicadores")
    consulta = [("tipo", tipo), ("mes", mes), ("secoes_enviadas", "1")] + [("secao", s) for s in secoes]
    return {"tipo": tipo, "mes": mes, "secoes": secoes, "periodo": periodo,
            "blocos": ImpressaoService.blocos_indicadores(db, mes or None, secoes),
            "titulo": titulo, "subtitulo": f" — Competência: {periodo}", "qs": urlencode(consulta)}
