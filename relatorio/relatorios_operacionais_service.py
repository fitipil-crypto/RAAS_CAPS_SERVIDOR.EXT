"""Relatórios operacionais do RAAS-CAPS.

Este módulo concentra os cinco relatórios de uso cotidiano da unidade. Cada
relatório devolve blocos de tabela, para que a mesma estrutura seja usada na
tela e na exportação PDF/CSV/Excel.
"""
from collections import Counter, defaultdict
from datetime import date, datetime

from sqlalchemy.orm import Session

from paciente.paciente_model import Paciente
from paciente.paciente_schema import SITUACOES_PACIENTE
from profissional.profissional_model import Profissional
from procedimento.procedimento_model import Procedimento
from procedimento.procedimento_service import get_sigtap_name
from registro.registro_model import Registro
from relatorio.impressao_service import Bloco, Coluna, ETNIAS, SEXOS
from relatorio.relatorio_service import RelatorioService
from sistema.reference_data import atendimento_e_grupo


RELATORIOS_OPERACIONAIS = {
    "atendimentos": {
        "icone": "🗒️",
        "titulo": "Atendimentos realizados",
        "descricao": "Consulte os atendimentos lançados por período, profissional e procedimento.",
    },
    "producao": {
        "icone": "🗒️",
        "titulo": "Produção por profissional",
        "descricao": "Compare a produção dos profissionais e a quantidade de usuários atendidos.",
    },
    "perfil": {
        "icone": "🗒️",
        "titulo": "Perfil dos pacientes",
        "descricao": "Visualize a distribuição dos pacientes por idade, sexo, etnia e bairro.",
    },
    "busca-ativa": {
        "icone": "🗒️",
        "titulo": "Pacientes sem atendimento recente",
        "descricao": "Identifique pacientes em acompanhamento que precisam de busca ativa.",
    },
    "incompletos": {
        "icone": "🗒️",
        "titulo": "Cadastros incompletos",
        "descricao": "Encontre pacientes com informações importantes ainda não preenchidas.",
    },
}


def _data(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _data_br(value):
    parsed = _data(value)
    return parsed.strftime("%d/%m/%Y") if parsed else (value or "")


def _nome_procedimento(procedimento):
    if not procedimento:
        return "Não informado"
    return procedimento.name or get_sigtap_name(procedimento.code) or procedimento.code


def _percentual(parte, total):
    return f"{(parte / total * 100) if total else 0:.1f}%".replace(".", ",")


def _rotulo_situacao(valor):
    return SITUACOES_PACIENTE.get(valor or "", "Sem situação")


def _rotulo_local(valor):
    return {"C": "CAPS", "T": "Território"}.get(valor or "", valor or "Não informado")


def _rotulo_tipo(procedimento, registro):
    nome = procedimento.name if procedimento else ""
    return "Grupo" if atendimento_e_grupo(getattr(registro, "group_id", None), nome) else "Individual"


class RelatoriosOperacionaisService:

    @staticmethod
    def definicoes():
        return RELATORIOS_OPERACIONAIS

    @staticmethod
    def obter_opcoes(db: Session) -> dict:
        profissionais = db.query(Profissional).order_by(Profissional.name.asc()).all()
        procedimentos = db.query(Procedimento).order_by(Procedimento.name.asc()).all()
        bairros = sorted({(p.neighborhood or "").strip() for p in db.query(Paciente).all() if (p.neighborhood or "").strip()})
        return {
            "profissionais": profissionais,
            "procedimentos": procedimentos,
            "bairros": bairros,
            "situacoes": SITUACOES_PACIENTE,
            "sexos": SEXOS,
            "etnias": ETNIAS,
        }

    @staticmethod
    def _filtros(params, chave):
        filtros = {
            "de": (params.get("de") or "").strip(),
            "ate": (params.get("ate") or "").strip(),
            "profissional": (params.get("profissional") or "").strip(),
            "procedimento": (params.get("procedimento") or "").strip(),
            "local": (params.get("local") or "").strip(),
            "situacao": (params.get("situacao") or "").strip(),
            "bairro": (params.get("bairro") or "").strip(),
            "sexo": (params.get("sexo") or "").strip(),
            "etnia": (params.get("etnia") or "").strip(),
            "idade_min": (params.get("idade_min") or "").strip(),
            "idade_max": (params.get("idade_max") or "").strip(),
            "dias": (params.get("dias") or "30").strip(),
            "faltando": (params.get("faltando") or "").strip(),
        }
        if chave not in ("atendimentos", "producao"):
            filtros["de"] = ""
            filtros["ate"] = ""
            filtros["profissional"] = ""
            filtros["procedimento"] = ""
            filtros["local"] = ""
        if chave not in ("perfil", "busca-ativa", "incompletos"):
            filtros["situacao"] = ""
            filtros["bairro"] = ""
            filtros["sexo"] = ""
            filtros["etnia"] = ""
            filtros["idade_min"] = ""
            filtros["idade_max"] = ""
        try:
            filtros["dias_num"] = max(1, int(filtros["dias"]))
        except ValueError:
            filtros["dias_num"] = 30
            filtros["dias"] = "30"
        return filtros

    @staticmethod
    def _carregar(db: Session):
        pacientes = [p for p in db.query(Paciente).order_by(Paciente.name.asc()).all() if not p.anonimizado]
        registros = db.query(Registro).order_by(Registro.service_date.desc()).all()
        profissionais = {p.id: p for p in db.query(Profissional).all()}
        procedimentos = {p.id: p for p in db.query(Procedimento).all()}
        pacientes_map = {p.id: p for p in pacientes}
        return pacientes, registros, profissionais, procedimentos, pacientes_map

    @staticmethod
    def _filtrar_registros(registros, filtros):
        de = _data(filtros["de"])
        ate = _data(filtros["ate"])
        resultado = []
        for registro in registros:
            data = _data(registro.service_date)
            if de and (not data or data < de):
                continue
            if ate and (not data or data > ate):
                continue
            if filtros["profissional"] and registro.professional_id != filtros["profissional"]:
                continue
            if filtros["procedimento"] and registro.procedure_id != filtros["procedimento"]:
                continue
            if filtros["local"] and (registro.local_realizacao or "C") != filtros["local"]:
                continue
            resultado.append(registro)
        return resultado

    @staticmethod
    def _filtrar_pacientes(pacientes, filtros):
        idade_min = int(filtros["idade_min"]) if filtros["idade_min"].isdigit() else None
        idade_max = int(filtros["idade_max"]) if filtros["idade_max"].isdigit() else None
        resultado = []
        for paciente in pacientes:
            if filtros["situacao"] == "sem" and paciente.patient_status:
                continue
            if filtros["situacao"] and filtros["situacao"] != "sem" and paciente.patient_status != filtros["situacao"]:
                continue
            if filtros["bairro"] and filtros["bairro"].lower() not in (paciente.neighborhood or "").lower():
                continue
            if filtros["sexo"] and paciente.gender != filtros["sexo"]:
                continue
            if filtros["etnia"] and paciente.race != filtros["etnia"]:
                continue
            idade = RelatorioService._calc_age(paciente.birth_date)
            if idade_min is not None and (idade is None or idade < idade_min):
                continue
            if idade_max is not None and (idade is None or idade > idade_max):
                continue
            resultado.append(paciente)
        return resultado

    @staticmethod
    def construir(db: Session, chave: str, params) -> dict:
        if chave not in RELATORIOS_OPERACIONAIS:
            raise ValueError("Relatório operacional inválido")
        filtros = RelatoriosOperacionaisService._filtros(params, chave)
        opcoes = RelatoriosOperacionaisService.obter_opcoes(db)
        pacientes, registros, profissionais, procedimentos, pacientes_map = RelatoriosOperacionaisService._carregar(db)
        fabrica = getattr(RelatoriosOperacionaisService, f"_{chave.replace('-', '_')}")
        resultado = fabrica(
            pacientes, registros, profissionais, procedimentos, pacientes_map, filtros
        )
        definicao = RELATORIOS_OPERACIONAIS[chave]
        resultado.update({
            "chave": chave,
            "icone": definicao["icone"],
            "titulo": definicao["titulo"],
            "descricao": definicao["descricao"],
            "filtros": filtros,
            "opcoes": opcoes,
        })
        return resultado

    @staticmethod
    def _atendimentos(pacientes, registros, profissionais, procedimentos, pacientes_map, filtros):
        registros = RelatoriosOperacionaisService._filtrar_registros(registros, filtros)
        colunas = [
            Coluna("data", "Data", 11, centro=True), Coluna("paciente", "Paciente", 34),
            Coluna("profissional", "Profissional", 28), Coluna("procedimento", "Procedimento", 42),
            Coluna("quantidade", "Qtd.", 8, centro=True), Coluna("tipo", "Tipo", 15),
            Coluna("local", "Local", 15),
        ]
        linhas = []
        for registro in registros:
            paciente = pacientes_map.get(registro.patient_id)
            procedimento = procedimentos.get(registro.procedure_id)
            profissional = profissionais.get(registro.professional_id)
            linhas.append([
                _data_br(registro.service_date), paciente.name if paciente else "Paciente não encontrado",
                profissional.name if profissional else "Não informado", _nome_procedimento(procedimento),
                registro.quantity or 1, _rotulo_tipo(procedimento, registro), _rotulo_local(registro.local_realizacao),
            ])
        total = sum((r.quantity or 1) for r in registros)
        bloco = Bloco("Atendimentos realizados", colunas, linhas, vazio="Nenhum atendimento encontrado com esses filtros.")
        return {"resumo": [
            {"icone": "📝", "valor": total, "label": "Atendimentos"},
            {"icone": "👥", "valor": len({r.patient_id for r in registros}), "label": "Pacientes"},
            {"icone": "📋", "valor": len(registros), "label": "Lançamentos"},
        ], "blocos": [bloco]}

    @staticmethod
    def _producao(pacientes, registros, profissionais, procedimentos, pacientes_map, filtros):
        registros = RelatoriosOperacionaisService._filtrar_registros(registros, filtros)
        agrupado = defaultdict(lambda: {"quantidade": 0, "pacientes": set(), "procedimentos": set(), "individual": 0, "grupo": 0, "ultimo": None})
        for registro in registros:
            chave = registro.professional_id or "sem-profissional"
            item = agrupado[chave]
            quantidade = registro.quantity or 1
            procedimento = procedimentos.get(registro.procedure_id)
            item["quantidade"] += quantidade
            item["pacientes"].add(registro.patient_id)
            item["procedimentos"].add(registro.procedure_id)
            item["grupo" if _rotulo_tipo(procedimento, registro) == "Grupo" else "individual"] += quantidade
            item["ultimo"] = max(item["ultimo"] or "", registro.service_date or "")
        colunas = [
            Coluna("profissional", "Profissional", 34), Coluna("atendimentos", "Atendimentos", 14, centro=True),
            Coluna("pacientes", "Pacientes", 12, centro=True), Coluna("procedimentos", "Procedimentos", 14, centro=True),
            Coluna("individual", "Individual", 13, centro=True), Coluna("grupo", "Grupo", 10, centro=True),
            Coluna("ultimo", "Último atendimento", 18, centro=True),
        ]
        linhas = []
        for chave, item in sorted(agrupado.items(), key=lambda par: (-par[1]["quantidade"], par[0])):
            profissional = profissionais.get(chave)
            linhas.append([
                profissional.name if profissional else "Não informado", item["quantidade"], len(item["pacientes"]),
                len(item["procedimentos"]), item["individual"], item["grupo"], _data_br(item["ultimo"]),
            ])
        bloco = Bloco("Produção por profissional", colunas, linhas, vazio="Nenhuma produção encontrada com esses filtros.")
        return {"resumo": [
            {"icone": "📝", "valor": sum((r.quantity or 1) for r in registros), "label": "Atendimentos"},
            {"icone": "👨‍⚕️", "valor": len(agrupado), "label": "Profissionais"},
            {"icone": "👥", "valor": len({r.patient_id for r in registros}), "label": "Pacientes atendidos"},
        ], "blocos": [bloco]}

    @staticmethod
    def _perfil(pacientes, registros, profissionais, procedimentos, pacientes_map, filtros):
        pacientes = RelatoriosOperacionaisService._filtrar_pacientes(pacientes, filtros)
        total = len(pacientes)
        faixas = Counter(RelatorioService._age_group(RelatorioService._calc_age(p.birth_date)) for p in pacientes)
        sexos = Counter(SEXOS.get(p.gender or "", "Não informado") for p in pacientes)
        etnias = Counter(ETNIAS.get(p.race or "", "Não informado") for p in pacientes)
        bairros = Counter((p.neighborhood or "Não informado").strip() or "Não informado" for p in pacientes)

        def bloco_distribuicao(titulo, contagem):
            colunas = [Coluna("categoria", "Categoria", 40), Coluna("quantidade", "Quantidade", 14, centro=True), Coluna("percentual", "%", 12, centro=True)]
            linhas = [[categoria, quantidade, _percentual(quantidade, total)] for categoria, quantidade in sorted(contagem.items(), key=lambda x: (-x[1], x[0]))]
            return Bloco(titulo, colunas, linhas, vazio="Nenhum paciente encontrado com esses filtros.")

        blocos = [
            bloco_distribuicao("Faixa etária", faixas), bloco_distribuicao("Sexo", sexos),
            bloco_distribuicao("Etnia", etnias), bloco_distribuicao("Bairro", bairros),
        ]
        return {"resumo": [
            {"icone": "👥", "valor": total, "label": "Pacientes analisados"},
            {"icone": "🏘️", "valor": len(bairros), "label": "Bairros"},
            {"icone": "🧠", "valor": len({p.cid_main for p in pacientes if p.cid_main}), "label": "CIDs principais"},
        ], "blocos": blocos}

    @staticmethod
    def _busca_ativa(pacientes, registros, profissionais, procedimentos, pacientes_map, filtros):
        por_paciente = {}
        for registro in registros:
            data = _data(registro.service_date)
            if not data:
                continue
            atual = por_paciente.get(registro.patient_id)
            if not atual or data > atual["data"]:
                atual = {"data": data, "profissional": registro.professional_id}
                por_paciente[registro.patient_id] = atual
        hoje = date.today()
        candidatos = []
        for paciente in RelatoriosOperacionaisService._filtrar_pacientes(pacientes, filtros):
            if paciente.conclusion_date:
                continue
            ultimo = por_paciente.get(paciente.id)
            dias = (hoje - ultimo["data"]).days if ultimo else None
            if dias is not None and dias < filtros["dias_num"]:
                continue
            profissional = profissionais.get(ultimo["profissional"]) if ultimo else None
            candidatos.append((paciente, dias, ultimo, profissional))
        candidatos.sort(key=lambda item: (item[1] is not None, -(item[1] or 999999), item[0].name.upper()))
        colunas = [
            Coluna("paciente", "Paciente", 34), Coluna("ultimo", "Último atendimento", 18, centro=True),
            Coluna("dias", "Dias sem atendimento", 18, centro=True), Coluna("profissional", "Profissional", 28),
            Coluna("telefone", "Telefone", 16, centro=True), Coluna("bairro", "Bairro", 24),
            Coluna("situacao", "Situação", 18),
        ]
        linhas = []
        for paciente, dias, ultimo, profissional in candidatos:
            linhas.append([
                paciente.name, _data_br(ultimo["data"] if ultimo else ""), dias if dias is not None else "Nunca",
                profissional.name if profissional else "Não informado", paciente.cell_phone or paciente.phone or "",
                paciente.neighborhood or "Não informado", _rotulo_situacao(paciente.patient_status),
            ])
        bloco = Bloco("Pacientes sem atendimento recente", colunas, linhas, vazio="Nenhum paciente encontrado para busca ativa.")
        return {"resumo": [
            {"icone": "🔎", "valor": len(candidatos), "label": "Para busca ativa"},
            {"icone": "⏱️", "valor": filtros["dias_num"], "label": "Dias considerados"},
            {"icone": "📅", "valor": sum(1 for _, dias, _, _ in candidatos if dias is None), "label": "Nunca atendidos"},
        ], "blocos": [bloco]}

    @staticmethod
    def _incompletos(pacientes, registros, profissionais, procedimentos, pacientes_map, filtros):
        campos = [
            ("cns", "CNS", lambda p: p.cns), ("nascimento", "Data de nascimento", lambda p: p.birth_date),
            ("bairro", "Bairro", lambda p: p.neighborhood), ("situacao", "Situação", lambda p: p.patient_status),
            ("cid", "CID principal", lambda p: p.cid_main), ("psiquiatra", "Psiquiatra", lambda p: p.psychiatrist),
            ("tecnico", "Técnico de referência", lambda p: p.reference_technicians),
        ]
        faltando_filtro = filtros["faltando"]
        linhas = []
        for paciente in RelatoriosOperacionaisService._filtrar_pacientes(pacientes, filtros):
            faltantes = [rotulo for chave, rotulo, extrator in campos if not extrator(paciente) and (not faltando_filtro or chave == faltando_filtro)]
            if not faltantes:
                continue
            if faltando_filtro and len(faltantes) == 0:
                continue
            linhas.append([
                paciente.name, paciente.prontuario or "", paciente.cns or "", ", ".join(faltantes),
                _rotulo_situacao(paciente.patient_status), paciente.neighborhood or "",
            ])
        linhas.sort(key=lambda linha: linha[0].upper())
        colunas = [
            Coluna("paciente", "Paciente", 34), Coluna("prontuario", "Prontuário", 14, centro=True),
            Coluna("cns", "CNS", 18, centro=True), Coluna("faltantes", "Informações pendentes", 48),
            Coluna("situacao", "Situação", 18), Coluna("bairro", "Bairro", 24),
        ]
        bloco = Bloco("Cadastros incompletos", colunas, linhas, vazio="Nenhum cadastro incompleto encontrado.")
        return {"resumo": [
            {"icone": "🧾", "valor": len(linhas), "label": "Cadastros com pendências"},
            {"icone": "👥", "valor": len(pacientes), "label": "Pacientes analisados"},
            {"icone": "✅", "valor": len(pacientes) - len(linhas), "label": "Cadastros completos"},
        ], "blocos": [bloco], "campos_incompletos": campos}
