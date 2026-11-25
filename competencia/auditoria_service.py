"""Auditoria de consistência da competência antes da exportação RAAS.

A auditoria só lê dados: confere o estabelecimento (Registro 01), os pacientes
(Registro 15) e os atendimentos (Registro 16) do mês e devolve uma lista de
``Achado``. Cada achado tem um código estável, uma gravidade e a orientação
para corrigir.

Gravidades:
  • BLOQUEIO — o arquivo seria rejeitado ou sairia com dado errado;
  • ALERTA   — provável erro de digitação ou inconsistência a conferir;
  • INFO     — observação que não impede a exportação.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from config.config_service import ConfigService
from competencia import regras_raas as regras
from paciente.paciente_model import Paciente
from paciente.paciente_schema import SITUACOES_PACIENTE
from procedimento.procedimento_model import Procedimento
from profissional.profissional_model import Profissional
from registro.registro_model import Registro
from sistema.reference_data import (
    CBO_NAMES, CLS_OPTS, NACIONALIDADES, ORIGIN_MAP, SERVICE_TYPE_MAP, SRV_OPTS,
)

BLOQUEIO = "bloqueio"
ALERTA = "alerta"
INFO = "info"
ROTULO_GRAVIDADE = {BLOQUEIO: "Bloqueia", ALERTA: "Alerta", INFO: "Informativo"}
ORDEM_GRAVIDADE = {BLOQUEIO: 0, ALERTA: 1, INFO: 2}

GRUPO_ESTAB = "Estabelecimento"
GRUPO_PACIENTE = "Paciente (Reg. 15)"
GRUPO_ATEND = "Atendimento (Reg. 16)"
GRUPO_MODALIDADE = "Modalidade do CAPS"

_SRV_VALIDOS = {o["value"] for o in SRV_OPTS}
_CLS_VALIDOS = {o["value"] for o in CLS_OPTS}
_NACIONALIDADES = {n["code"] for n in NACIONALIDADES}


@dataclass(frozen=True)
class Achado:
    codigo: str
    gravidade: str
    grupo: str
    mensagem: str
    correcao: str = ""
    paciente: str = ""
    link: str = ""


class AuditoriaService:
    """Executa as regras e consolida o resultado."""

    @staticmethod
    def auditar(db: Session, month: str, hoje: date | None = None) -> dict:
        """Audita a competência ``month`` (YYYY-MM). ``hoje`` existe para testes."""
        hoje = hoje or date.today()
        achados: list[Achado] = []

        if not regras.competencia_valida(month):
            achados.append(Achado("C00", BLOQUEIO, GRUPO_ESTAB, f"Competência inválida: {month!r}.",
                                  "Use o formato AAAA-MM."))
            return AuditoriaService._consolidar(month, achados, 0, 0)

        registros = db.query(Registro).filter(Registro.service_month == month).all()
        achados += AuditoriaService._estabelecimento(ConfigService.get_config_estabelecimento(db) or {})
        if not registros:
            achados.append(Achado("C01", BLOQUEIO, GRUPO_ESTAB, "Não há atendimentos lançados nesta competência.",
                                  "Lance os atendimentos ou escolha outra competência."))
            return AuditoriaService._consolidar(month, achados, 0, 0)

        pacientes = {p.id: p for p in db.query(Paciente).all()}
        profissionais = {p.id: p for p in db.query(Profissional).all()}
        procedimentos = {p.id: p for p in db.query(Procedimento).all()}

        ids_pacientes = {r.patient_id for r in registros}
        for pid in sorted(ids_pacientes, key=lambda i: (pacientes[i].name if i in pacientes else "")):
            paciente = pacientes.get(pid)
            if paciente and not paciente.anonimizado:
                achados += AuditoriaService._paciente(paciente, hoje, month)
        achados += AuditoriaService._cns_duplicados([pacientes[i] for i in ids_pacientes if i in pacientes])

        achados += AuditoriaService._modalidade(
            db, hoje, [pacientes[i] for i in ids_pacientes if i in pacientes]
        )

        vistos: dict[tuple, int] = defaultdict(int)
        for registro in registros:
            achados += AuditoriaService._registro(
                registro, month, hoje, pacientes.get(registro.patient_id),
                profissionais.get(registro.professional_id), procedimentos.get(registro.procedure_id), vistos,
            )
        return AuditoriaService._consolidar(month, achados, len(registros), len(ids_pacientes))

    # ── consolidação ────────────────────────────────────────────────
    @staticmethod
    def _consolidar(month, achados, total_registros, total_pacientes) -> dict:
        achados = sorted(achados, key=lambda a: (ORDEM_GRAVIDADE[a.gravidade], a.codigo, a.paciente))
        contagem = {g: sum(1 for a in achados if a.gravidade == g) for g in ORDEM_GRAVIDADE}
        return {
            "competencia": month,
            "achados": achados,
            "contagem": contagem,
            "total_registros": total_registros,
            "total_pacientes": total_pacientes,
            "pode_exportar": contagem[BLOQUEIO] == 0,
        }

    # ── Registro 01: estabelecimento ────────────────────────────────
    @staticmethod
    def _estabelecimento(config: dict) -> list[Achado]:
        link = "/configuracoes"
        achados = []
        if not regras.cnes_valido(config.get("cnes_code")):
            achados.append(Achado("E01", BLOQUEIO, GRUPO_ESTAB, "CNES ausente ou diferente de 7 dígitos.",
                                  "Informe o CNES do estabelecimento em Configurações.", link=link))
        if len(regras.only_digits(config.get("uf_code"))) != 2:
            achados.append(Achado("E02", BLOQUEIO, GRUPO_ESTAB, "Código da UF ausente ou diferente de 2 dígitos.",
                                  "Informe o código IBGE da UF (ex.: 35) em Configurações.", link=link))
        if not regras.cnpj_valido(config.get("cnpj")):
            achados.append(Achado("E03", BLOQUEIO, GRUPO_ESTAB, "CNPJ do órgão ausente ou inválido.",
                                  "Informe um CNPJ válido (14 dígitos) em Configurações.", link=link))
        elif regras.cnpj_alfanumerico(config.get("cnpj")):
            achados.append(Achado("E05", ALERTA, GRUPO_ESTAB,
                                  "CNPJ alfanumérico: o arquivo RAAS grava apenas os dígitos e sairia incorreto.",
                                  "Confirme com o DATASUS o layout aceito para CNPJ alfanumérico.", link=link))
        if not (config.get("organ_name") or "").strip():
            achados.append(Achado("E04", ALERTA, GRUPO_ESTAB, "Nome do órgão de origem não informado.",
                                  "Preencha o nome do órgão em Configurações.", link=link))
        return achados

    # ── Modalidade do CAPS ──────────────────────────────────────────
    @staticmethod
    def _modalidade(db: Session, hoje: date, pacientes: list[Paciente]) -> list[Achado]:
        """Confere a competência contra os parâmetros da modalidade da unidade.

        São achados de ALERTA e INFO, nunca de BLOQUEIO: porte populacional,
        leitos e faixa etária são parâmetros de habilitação e decisão clínica,
        não validações do arquivo RAAS — o DATASUS não recusa o arquivo por
        causa deles. Quem decide é a equipe; o sistema só mostra.
        """
        from sistema.escopo import unidade_ativa
        from unidade import modalidades
        from unidade.unidade_service import UnidadeService

        unidade = UnidadeService.obter_por_id(db, unidade_ativa())
        if unidade is None:
            # Visão "todas as unidades". Com um único CAPS cadastrado — o caso de
            # quem só tem um — essa visão *é* aquele CAPS, e a auditoria usa os
            # parâmetros dele. Só faz sentido avisar quando há mais de uma
            # unidade, porque aí os parâmetros de cada uma são diferentes e a
            # auditoria não tem como escolher.
            unidade = UnidadeService.unidade_padrao(db)
            if unidade is None:
                if UnidadeService.contar(db) > 1:
                    return [Achado(
                        "M00", INFO, GRUPO_MODALIDADE,
                        "Auditoria rodando na visão de todas as unidades.",
                        "Selecione a unidade na barra superior para conferir os parâmetros "
                        "da modalidade e exportar o arquivo de um CAPS por vez.",
                    )]
                return []

        achados: list[Achado] = []
        modalidade = modalidades.obter(unidade.modalidade)
        if modalidade is None:
            return [Achado(
                "M01", ALERTA, GRUPO_MODALIDADE,
                f"Modalidade desconhecida na unidade: {unidade.modalidade!r}.",
                "Corrija a modalidade em Unidades.", link="/unidades",
            )]

        aviso_porte = modalidades.aviso_porte(unidade.modalidade, unidade.populacao)
        if aviso_porte:
            achados.append(Achado(
                "M02", INFO, GRUPO_MODALIDADE, aviso_porte,
                "Confira a habilitação da unidade; a cobertura pode ser regional.",
                link="/unidades",
            ))

        aviso_leitos = modalidades.aviso_leitos(unidade.modalidade, unidade.leitos_acolhimento)
        if aviso_leitos:
            achados.append(Achado(
                "M03", ALERTA, GRUPO_MODALIDADE, aviso_leitos,
                "Ajuste os leitos de acolhimento noturno em Unidades.", link="/unidades",
            ))

        # Faixa etária: só o CAPS i tem teto, então na prática este laço só
        # produz achado nessa modalidade.
        if modalidade.idade_maxima is not None or modalidade.idade_minima is not None:
            for paciente in sorted(pacientes, key=lambda p: p.name or ""):
                if paciente.anonimizado:
                    continue
                idade = regras.idade_em(regras.parse_data(paciente.birth_date), hoje)
                aviso = modalidades.aviso_faixa_etaria(unidade.modalidade, idade)
                if aviso:
                    achados.append(Achado(
                        "M04", ALERTA, GRUPO_MODALIDADE, aviso,
                        "Decisão clínica: mantenha o acompanhamento se for o caso, ou "
                        "encaminhe o paciente ao serviço da faixa etária dele.",
                        paciente.name, f"/pacientes/{paciente.id}",
                    ))
        return achados

    # ── Registro 15: paciente ───────────────────────────────────────
    @staticmethod
    def _paciente(p: Paciente, hoje: date, month: str) -> list[Achado]:
        link = f"/pacientes/{p.id}"
        achados: list[Achado] = []

        def add(codigo, gravidade, mensagem, correcao):
            achados.append(Achado(codigo, gravidade, GRUPO_PACIENTE, mensagem, correcao, p.name, link))

        cns = regras.only_digits(p.cns)
        # O layout RAAS aceita CNS ou CPF (o que faltar vai zerado no arquivo).
        if not cns and not regras.only_digits(p.cpf):
            add("P01", BLOQUEIO, "CNS e CPF ausentes.", "Informe o CNS (CAD SUS) ou o CPF do paciente.")
        elif not regras.cns_valido(cns):
            add("P02", BLOQUEIO, "CNS inválido (tamanho ou dígito verificador).", "Confira o CNS no cartão do paciente.")

        if not (p.name or "").strip():
            add("P03", BLOQUEIO, "Nome ausente.", "Informe o nome completo.")
        elif len(p.name.strip()) > regras.TAM_NOME:
            add("P04", INFO, f"Nome com mais de {regras.TAM_NOME} caracteres será truncado no arquivo.",
                "Nenhuma ação necessária; o arquivo usa os 30 primeiros caracteres.")

        nascimento = regras.parse_data(p.birth_date)
        if not p.birth_date:
            add("P05", BLOQUEIO, "Data de nascimento ausente.", "Informe a data de nascimento.")
        elif not nascimento or nascimento > hoje:
            add("P06", BLOQUEIO, "Data de nascimento inválida ou no futuro.", "Corrija a data de nascimento.")

        if p.gender not in regras.SEXOS_VALIDOS:
            add("P07", BLOQUEIO, "Sexo ausente ou inválido (o arquivo assumiria Masculino).", "Informe M ou F.")

        if not p.race:
            add("P08", ALERTA, "Raça/cor ausente (o arquivo assumiria Branca).", "Informe a raça/cor do paciente.")
        elif p.race not in regras.RACAS_VALIDAS:
            add("P09", BLOQUEIO, f"Raça/cor {p.race!r} fora do domínio do RAAS.", "Use 01 a 05 ou 99.")
        elif p.race == regras.RACA_INDIGENA and not regras.only_digits(p.ethnicity):
            add("P10", BLOQUEIO, "Paciente indígena sem etnia informada.", "Informe o código da etnia (4 dígitos).")

        if not regras.municipio_valido(p.municipality_code):
            add("P11", BLOQUEIO, "Município de residência ausente ou com código IBGE inválido.",
                "Selecione o município pelo código IBGE (6 ou 7 dígitos).")
        if not regras.cep_valido(p.cep):
            add("P12", BLOQUEIO, "CEP ausente ou diferente de 8 dígitos.", "Informe o CEP completo.")
        if not (p.address or "").strip():
            add("P13", ALERTA, "Endereço (logradouro) ausente.", "Informe o logradouro.")
        if not (p.neighborhood or "").strip():
            add("P14", ALERTA, "Bairro ausente.", "Informe o bairro.")

        if not (p.mother_name or "").strip():
            add("P15", ALERTA, "Nome da mãe ausente.", "Informe o nome da mãe.")
        if nascimento and regras.idade_em(nascimento, hoje) < 18 and not (p.guardian_name or "").strip():
            add("P16", ALERTA, "Menor de idade sem responsável (o arquivo repetiria o nome do paciente).",
                "Informe o nome do responsável.")

        if not (p.cid_main or "").strip():
            add("P17", BLOQUEIO, "CID principal ausente.", "Informe o CID principal do paciente.")
        elif not regras.cid_valido(p.cid_main):
            add("P18", BLOQUEIO, f"CID principal {p.cid_main!r} em formato inválido.", "Use o formato F84.0 ou F840.")
        for rotulo, valor in (("secundário 1", p.cid_associated1), ("secundário 2", p.cid_associated2),
                              ("secundário 3", p.cid_associated3), ("de causas associadas", p.cid_causes)):
            if (valor or "").strip() and not regras.cid_valido(valor):
                add("P19", ALERTA, f"CID {rotulo} {valor!r} em formato inválido.", "Use o formato F84.0 ou F840.")

        if (p.cpf or "").strip() and not regras.cpf_valido(p.cpf):
            add("P20", ALERTA, "CPF informado é inválido.", "Corrija ou remova o CPF.")

        if p.esf_coverage == "S" and not regras.cnes_valido(p.cnes_usf):
            add("P21", BLOQUEIO, "Cobertura ESF marcada sem CNES da USF (7 dígitos); o campo sairia em branco.",
                "Informe o CNES da USF ou desmarque a cobertura ESF.")
        if p.street_situation and p.street_situation not in regras.SIM_NAO:
            add("P22", ALERTA, "Situação de rua com valor diferente de S/N.", "Informe Sim ou Não.")
        usa_tipo = p.alcohol_user or p.crack_user or p.other_drugs_user
        if p.drug_user == "S" and not usa_tipo:
            add("P23", ALERTA, "Usuário de drogas sem a substância informada (álcool, crack ou outras).",
                "Marque ao menos uma substância.")
        if usa_tipo and p.drug_user != "S":
            add("P24", ALERTA, "Substância informada, mas 'usuário de drogas' não está marcado como Sim.",
                "Marque 'usuário de drogas' como Sim ou remova a substância.")

        if p.user_origin and p.user_origin not in ORIGIN_MAP:
            add("P25", ALERTA, f"Origem do usuário {p.user_origin!r} fora da tabela.", "Selecione uma origem válida.")
        if p.nationality and p.nationality not in _NACIONALIDADES:
            add("P26", ALERTA, f"Nacionalidade {p.nationality!r} fora da tabela.", "Selecione uma nacionalidade válida.")

        ini, fim = regras.parse_data(p.date_ini_valid), regras.parse_data(p.date_fim_valid)
        if ini and fim and fim < ini:
            add("P27", BLOQUEIO, "Fim da validade anterior ao início.", "Corrija as datas de validação.")
        conclusao = regras.parse_data(p.conclusion_date)
        if p.conclusion_date and not conclusao:
            add("P28", BLOQUEIO, "Data de conclusão inválida.", "Corrija a data de conclusão.")
        if p.patient_status and p.patient_status not in SITUACOES_PACIENTE:
            add("P29", INFO, "Situação do paciente fora da tabela.", "Selecione uma situação válida.")
        elif p.patient_status == "inativo":
            add("P30", ALERTA, "Paciente inativo com atendimento nesta competência.",
                "Confirme se a situação do paciente está correta.")
        return achados

    @staticmethod
    def _cns_duplicados(pacientes: list[Paciente]) -> list[Achado]:
        por_cns = defaultdict(list)
        for p in pacientes:
            numero = regras.only_digits(p.cns)
            if numero:
                por_cns[numero].append(p)
        achados = []
        for numero, grupo in por_cns.items():
            if len(grupo) > 1:
                nomes = ", ".join(sorted(p.name for p in grupo))
                for p in grupo:
                    achados.append(Achado(
                        "P31", BLOQUEIO, GRUPO_PACIENTE,
                        f"CNS {numero} repetido em {len(grupo)} cadastros ({nomes}); o arquivo teria 2 Registros 15 do mesmo usuário.",
                        "Una os cadastros duplicados ou corrija o CNS.", p.name, f"/pacientes/{p.id}",
                    ))
        return achados

    # ── Registro 16: atendimento ────────────────────────────────────
    @staticmethod
    def _registro(r: Registro, month: str, hoje: date, paciente, profissional, procedimento, vistos) -> list[Achado]:
        nome = paciente.name if paciente else "Paciente não encontrado"
        achados: list[Achado] = []
        data_br = regras.parse_data(r.service_date)
        rotulo = r.service_date or "sem data"

        def add(codigo, gravidade, mensagem, correcao):
            achados.append(Achado(codigo, gravidade, GRUPO_ATEND, f"{rotulo}: {mensagem}", correcao, nome,
                                  f"/registros?month={month}"))

        if not data_br:
            add("A01", BLOQUEIO, "data do atendimento inválida.", "Corrija a data do lançamento.")
        else:
            if data_br.strftime("%Y-%m") != month:
                add("A02", BLOQUEIO, f"data fora da competência {month}.", "Corrija a data ou a competência do lançamento.")
            if data_br > hoje:
                add("A03", BLOQUEIO, "data de atendimento no futuro.", "Corrija a data do lançamento.")

        if not paciente:
            add("A04", BLOQUEIO, "paciente inexistente (o arquivo omitiria o atendimento, mas o cabeçalho o contaria).",
                "Reassocie o lançamento a um paciente ou exclua-o.")
        elif paciente.anonimizado:
            add("A05", BLOQUEIO, "paciente anonimizado (LGPD) não pode ir no arquivo.",
                "Revise o lançamento; dados anonimizados não geram RAAS válido.")
        else:
            nascimento = regras.parse_data(paciente.birth_date)
            admissao = regras.parse_data(paciente.admission_date)
            conclusao = regras.parse_data(paciente.conclusion_date)
            if data_br and nascimento and data_br < nascimento:
                add("A06", BLOQUEIO, "atendimento anterior ao nascimento do paciente.", "Corrija a data de nascimento ou do atendimento.")
            if data_br and admissao and data_br < admissao:
                add("A07", ALERTA, "atendimento anterior à data de admissão do paciente.", "Confira a admissão e a data do atendimento.")
            if data_br and conclusao and data_br > conclusao:
                add("A08", ALERTA, "atendimento posterior à conclusão do tratamento.", "Confira a data de conclusão do paciente.")

        if not procedimento:
            add("A09", BLOQUEIO, "procedimento inexistente.", "Selecione um procedimento válido.")
        else:
            if not regras.procedimento_valido(procedimento.code):
                add("A10", BLOQUEIO, f"código do procedimento {procedimento.code!r} não tem 10 dígitos.", "Corrija o código SIGTAP.")
            elif not regras.procedimento_psicossocial(procedimento.code):
                add("A11", ALERTA, f"procedimento {procedimento.code} fora do grupo 03.01.08 (atenção psicossocial).",
                    "Confirme se o procedimento é de RAAS.")
            if procedimento.active is False:
                add("A12", ALERTA, "procedimento inativo no cadastro.", "Reative o procedimento ou troque o lançamento.")
            if regras.only_digits(procedimento.code) == regras.PROCEDIMENTO_DOMICILIAR and (r.local_realizacao or "C") == "C":
                add("A13", ALERTA, "atendimento domiciliar lançado como realizado no CAPS.", "Altere o local para Território.")

        if not profissional:
            add("A14", BLOQUEIO, "profissional não informado ou inexistente.", "Informe o profissional que realizou o atendimento.")
        else:
            if not regras.cns_valido(profissional.cns):
                add("A15", BLOQUEIO, f"CNS do profissional {profissional.name} ausente ou inválido.", "Corrija o CNS no cadastro do profissional.")
            if profissional.active is False:
                add("A16", ALERTA, f"profissional {profissional.name} inativo.", "Confirme se o profissional atuou na competência.")

        cbo = r.cbo_code or (profissional.cbo if profissional else None)
        if not regras.cbo_valido(cbo):
            add("A17", BLOQUEIO, "CBO ausente ou diferente de 6 dígitos.", "Informe o CBO no lançamento ou no profissional.")
        elif regras.only_digits(cbo) not in CBO_NAMES:
            add("A18", INFO, f"CBO {cbo} não consta na tabela de referência do sistema.", "Confirme o CBO do profissional.")

        quantidade = r.quantity or 0
        if quantidade < 1 or quantidade > regras.QTD_MAXIMA_LAYOUT:
            add("A19", BLOQUEIO, f"quantidade {quantidade} fora do limite (1 a {regras.QTD_MAXIMA_LAYOUT}).", "Corrija a quantidade.")
        elif quantidade > regras.QTD_ATENCAO:
            add("A20", ALERTA, f"quantidade {quantidade} acima do usual para um lançamento.", "Confira se não houve erro de digitação.")

        if r.srv and (not r.srv.isdigit() or len(r.srv) != 3):
            add("A21", BLOQUEIO, f"serviço {r.srv!r} deve ter 3 dígitos.", "Corrija o código do serviço.")
        elif r.srv and r.srv not in _SRV_VALIDOS:
            add("A22", ALERTA, f"serviço {r.srv} fora da tabela do sistema.", "Confirme o serviço/classificação.")
        if r.cls and (not r.cls.isdigit() or len(r.cls) != 3):
            add("A23", BLOQUEIO, f"classificação {r.cls!r} deve ter 3 dígitos.", "Corrija a classificação.")
        elif r.cls and r.cls not in _CLS_VALIDOS:
            add("A24", ALERTA, f"classificação {r.cls} fora da tabela do sistema.", "Confirme o serviço/classificação.")
        if (r.local_realizacao or "C") not in regras.LOCAIS_VALIDOS:
            add("A25", BLOQUEIO, f"local de realização {r.local_realizacao!r} inválido.", "Use C (CAPS) ou T (Território).")
        if r.service_type and r.service_type not in SERVICE_TYPE_MAP:
            add("A26", ALERTA, f"tipo de atendimento {r.service_type!r} fora da tabela.", "Selecione Individual, Grupo ou Família.")

        chave = (r.patient_id, r.procedure_id, r.professional_id, r.service_date, r.local_realizacao or "C")
        vistos[chave] += 1
        if vistos[chave] == 2:
            add("A27", ALERTA, "lançamento duplicado (mesmo paciente, procedimento, profissional, data e local).",
                "Exclua o duplicado ou some as quantidades.")
        return achados
