"""
Testes do módulo Competência: regras RAAS, auditoria, comparativo e previsão.
"""
from datetime import date

import pytest

from competencia import regras_raas as regras
from competencia.auditoria_service import AuditoriaService
from competencia.comparativo_service import (
    ComparativoService, linha_comparacao, variacao_percentual,
)
from competencia.periodos import dias_uteis, mes_anterior, meses_anteriores
from competencia.previsao_service import (
    PrevisaoService, faixa_historica, projetar_total, situacao,
)
from config.config_service import ConfigService
from paciente.paciente_model import Paciente
from procedimento.procedimento_model import Procedimento
from profissional.profissional_model import Profissional
from registro.registro_model import Registro


# ─── geradores de documentos válidos ─────────────────────────────────
def cns_provisorio(base: str = "70000000000000") -> str:
    soma = sum(int(base[i]) * (15 - i) for i in range(14))
    return base + str((-soma) % 11)


def cns_definitivo(pis: str = "12345678901") -> str:
    soma = sum(int(pis[i]) * (15 - i) for i in range(11))
    resto = soma % 11
    dv = 11 - resto if resto else 0
    if dv == 10:
        soma += 2
        dv = 11 - soma % 11
        return f"{pis}001{dv}"
    return f"{pis}000{dv}"


def cpf(base: str = "123456789") -> str:
    numeros = [int(c) for c in base]
    for tamanho in (9, 10):
        soma = sum(numeros[i] * (tamanho + 1 - i) for i in range(tamanho))
        numeros.append((soma * 10) % 11 % 10)
    return "".join(map(str, numeros))


def cnpj(base: str = "12ABC34501DE") -> str:
    numeros = [ord(c) - 48 for c in base]
    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        resto = sum(numeros[i] * pesos[i] for i in range(tamanho)) % 11
        numeros.append(0 if resto < 2 else 11 - resto)
    return base + "".join(map(str, numeros[12:]))


CNS_ATENDIMENTO = cns_provisorio()
CNS_PROFISSIONAL = cns_definitivo()


# ─── regras puras ────────────────────────────────────────────────────
def test_cns_valido():
    assert regras.cns_valido(CNS_ATENDIMENTO)
    assert regras.cns_valido(CNS_PROFISSIONAL)
    assert regras.cns_valido(cns_definitivo("10000000000"))
    assert not regras.cns_valido(CNS_ATENDIMENTO[:-1] + str((int(CNS_ATENDIMENTO[-1]) + 1) % 10))
    assert not regras.cns_valido("123")
    assert not regras.cns_valido(None)
    assert not regras.cns_valido("300000000000000")


def test_cpf_cnpj_validos():
    assert regras.cpf_valido(cpf())
    assert not regras.cpf_valido("11111111111")
    assert not regras.cpf_valido("12345678900")
    assert regras.cnpj_valido(cnpj("112223330001"))
    assert regras.cnpj_valido(cnpj("12ABC34501DE"))
    assert regras.cnpj_alfanumerico(cnpj("12ABC34501DE"))
    assert not regras.cnpj_valido("00000000000000")
    assert not regras.cnpj_valido("12ABC34501DE00")


@pytest.mark.parametrize("cid,esperado", [("F84.0", True), ("F840", True), ("f90", True), ("84", False), ("", False), ("F8", False)])
def test_cid_valido(cid, esperado):
    assert regras.cid_valido(cid) is esperado


def test_campos_numericos():
    assert regras.procedimento_valido("03.01.08.020-8")
    assert not regras.procedimento_valido("0301")
    assert regras.procedimento_psicossocial("0301080208")
    assert not regras.procedimento_psicossocial("0101010010")
    assert regras.cbo_valido("225133") and not regras.cbo_valido("2251")
    assert regras.cep_valido("12345-678") and not regras.cep_valido("12345")
    assert regras.municipio_valido("354870") and regras.municipio_valido("3548708")
    assert regras.competencia_valida("2026-10") and not regras.competencia_valida("2026-13")


# ─── períodos ────────────────────────────────────────────────────────
def test_periodos():
    assert mes_anterior("2026-01") == "2025-12"
    assert meses_anteriores("2026-02", 3) == ["2025-11", "2025-12", "2026-01"]
    assert dias_uteis("2026-10") == 22
    assert dias_uteis("2026-10", date(2026, 10, 9)) == 7


# ─── previsão (funções puras) ────────────────────────────────────────
def test_projetar_total():
    assert projetar_total(100, 10, 20) == 200
    assert projetar_total(100, 20, 20) == 100
    assert projetar_total(0, 0, 20) is None


def test_faixa_e_situacao():
    assert faixa_historica([10, 10], 20) is None
    minimo, media, maximo = faixa_historica([10, 10, 10], 20)
    assert (minimo, media, maximo) == (200, 200, 200)
    assert situacao(100, 200) == "Abaixo do ritmo"
    assert situacao(190, 200) == "Dentro do esperado"
    assert situacao(None, 200) == "Sem base"


def test_variacao():
    assert variacao_percentual(150, 100) == 50.0
    assert variacao_percentual(5, 0) is None
    assert linha_comparacao("x", 100, 130)["destaque"] is True
    assert linha_comparacao("x", 100, 105)["destaque"] is False


# ─── fixtures de banco ───────────────────────────────────────────────
@pytest.fixture
def base(db_session):
    ConfigService.atualizar_varios(db_session, {"cnpj": cnpj("112223330001"), "cnes_code": "1234567", "uf_code": "35"})
    paciente = Paciente(
        name="Ana Souza", cns=CNS_ATENDIMENTO, cpf=cpf(), birth_date="2000-05-10", gender="F", race="03",
        mother_name="Maria Souza", municipality_code="354870", cep="13000000", address="Rua A", neighborhood="Centro",
        cid_main="F840", admission_date="2024-01-10", esf_coverage="N", drug_user="N", patient_status="ativo",
    )
    profissional = Profissional(name="Dr. Paulo", cns=CNS_PROFISSIONAL, cbo="225133", active=True)
    procedimento = Procedimento(code="0301080208", name="Atendimento Individual", active=True)
    db_session.add_all([paciente, profissional, procedimento])
    db_session.commit()
    return {"db": db_session, "pac": paciente, "prof": profissional, "proc": procedimento}


def _registro(base, data="2026-10-05", quantidade=1, **extra):
    r = Registro(
        service_month=data[:7], service_date=data, patient_id=base["pac"].id, professional_id=base["prof"].id,
        procedure_id=base["proc"].id, cbo_code="225133", quantity=quantidade, **extra,
    )
    base["db"].add(r)
    base["db"].commit()
    return r


def _codigos(resultado):
    return {a.codigo for a in resultado["achados"]}


HOJE = date(2026, 10, 22)


# ─── auditoria ───────────────────────────────────────────────────────
def test_auditoria_competencia_limpa(base):
    _registro(base)
    r = AuditoriaService.auditar(base["db"], "2026-10", HOJE)
    assert r["achados"] == [], [a.mensagem for a in r["achados"]]
    assert r["pode_exportar"] is True


def test_auditoria_competencia_sem_registros(base):
    r = AuditoriaService.auditar(base["db"], "2026-10", HOJE)
    assert "C01" in _codigos(r) and not r["pode_exportar"]


def test_auditoria_competencia_invalida(base):
    r = AuditoriaService.auditar(base["db"], "2026-99", HOJE)
    assert _codigos(r) == {"C00"}


def test_auditoria_paciente(base):
    pac = base["pac"]
    pac.cns, pac.gender, pac.race, pac.cep, pac.cid_main = "123", None, "05", "123", "84"
    pac.municipality_code, pac.esf_coverage, pac.birth_date = "1", "S", None
    base["db"].commit()
    _registro(base)
    codigos = _codigos(AuditoriaService.auditar(base["db"], "2026-10", HOJE))
    assert {"P02", "P05", "P07", "P10", "P11", "P12", "P18", "P21"} <= codigos


def test_auditoria_cns_duplicado(base):
    outro = Paciente(name="Ana Clone", cns=CNS_ATENDIMENTO, birth_date="2001-01-01")
    base["db"].add(outro)
    base["db"].commit()
    _registro(base)
    base["db"].add(Registro(service_month="2026-10", service_date="2026-10-06", patient_id=outro.id,
                            professional_id=base["prof"].id, procedure_id=base["proc"].id, cbo_code="225133"))
    base["db"].commit()
    assert "P31" in _codigos(AuditoriaService.auditar(base["db"], "2026-10", HOJE))


def test_auditoria_atendimento(base):
    base["prof"].cns = ""
    base["db"].commit()
    _registro(base, data="2026-10-30")                       # futuro
    _registro(base, data="2026-10-05", quantidade=99, local_realizacao="X")
    _registro(base, data="2026-10-05", quantidade=99, local_realizacao="X")  # duplicado
    r = Registro(service_month="2026-10", service_date="2026-09-30", patient_id=base["pac"].id,
                 procedure_id=base["proc"].id, quantity=1)  # fora da competência, sem profissional/CBO
    base["db"].add(r)
    base["db"].commit()
    codigos = _codigos(AuditoriaService.auditar(base["db"], "2026-10", HOJE))
    assert {"A02", "A03", "A14", "A15", "A20", "A25", "A27"} <= codigos


def test_auditoria_paciente_inexistente_e_anonimizado(base):
    base["pac"].anonimizado = True
    base["db"].commit()
    _registro(base)
    base["db"].add(Registro(service_month="2026-10", service_date="2026-10-06", patient_id="fantasma",
                            professional_id=base["prof"].id, procedure_id=base["proc"].id, cbo_code="225133"))
    base["db"].commit()
    codigos = _codigos(AuditoriaService.auditar(base["db"], "2026-10", HOJE))
    assert {"A04", "A05"} <= codigos


def test_auditoria_procedimento_e_datas(base):
    base["proc"].code, base["proc"].active = "0101010010", False
    base["pac"].conclusion_date = "2026-09-01"
    base["db"].commit()
    _registro(base, data="2024-01-01")  # antes da admissão... mas fora da competência
    _registro(base)
    r = AuditoriaService.auditar(base["db"], "2026-10", HOJE)
    assert {"A11", "A12", "A08"} <= _codigos(r)


def test_auditoria_estabelecimento(base):
    ConfigService.atualizar_varios(base["db"], {"cnpj": "123", "cnes_code": "12"})
    _registro(base)
    codigos = _codigos(AuditoriaService.auditar(base["db"], "2026-10", HOJE))
    assert {"E01", "E03"} <= codigos
    ConfigService.atualizar_varios(base["db"], {"cnpj": cnpj("12ABC34501DE"), "cnes_code": "1234567"})
    assert "E05" in _codigos(AuditoriaService.auditar(base["db"], "2026-10", HOJE))


# ─── comparativo ─────────────────────────────────────────────────────
def test_comparativo(base):
    _registro(base, data="2026-09-10", quantidade=10)
    _registro(base, data="2026-10-10", quantidade=15)
    r = ComparativoService.comparar(base["db"], "2026-09", "2026-10")
    atend = next(l for l in r["linhas"] if l["rotulo"].startswith("Atendimentos"))
    assert (atend["a"], atend["b"], atend["diferenca"], atend["pct"]) == (10, 15, 5, 50.0)
    assert r["por_profissional"][0]["rotulo"] == "Dr. Paulo"
    assert r["por_profissional"][0]["pct"] == 50.0


# ─── previsão ────────────────────────────────────────────────────────
def test_previsao_mes_corrente(base):
    for mes in ("2026-04", "2026-05", "2026-06", "2026-07"):
        _registro(base, data=f"{mes}-10", quantidade=100)
    for dia in range(1, 12):  # 8 dias úteis (1-2, 5-9) até 11/10... segue ritmo constante
        _registro(base, data=f"2026-10-{dia:02d}", quantidade=10)
    p = PrevisaoService.prever(base["db"], "2026-10", HOJE)
    assert p["estado"] == "corrente"
    assert p["meses_historico"] == 4 and p["faixa"] is not None
    assert p["projecao"] > p["atual"]
    assert p["situacao"] in ("Dentro do esperado", "Abaixo do ritmo")
    assert p["profissionais"][0]["profissional"] == "Dr. Paulo"


def test_previsao_historico_insuficiente_e_futuro(base):
    _registro(base, data="2026-10-05")
    p = PrevisaoService.prever(base["db"], "2026-10", HOJE)
    assert p["faixa"] is None and p["situacao"] == "Histórico insuficiente"
    assert PrevisaoService.prever(base["db"], "2026-12", HOJE)["estado"] == "futuro"


def test_previsao_mes_fechado(base):
    _registro(base, data="2026-09-10", quantidade=40)
    p = PrevisaoService.prever(base["db"], "2026-09", HOJE)
    assert p["estado"] == "fechado" and p["projecao"] == 40


# ─── telas e API ─────────────────────────────────────────────────────
def test_paginas_e_exportacao(auth_client, base):
    _registro(base, data=f"{date.today():%Y-%m}-01")
    for aba in ("auditoria", "comparar", "previsao"):
        pagina = auth_client.get("/competencia", params={"aba": aba})
        assert pagina.status_code == 200 and "Competência" in pagina.text
        for formato, tipo in (("pdf", b"%PDF"), ("csv", b""), ("txt", b"")):
            resp = auth_client.get("/api/competencia/exportar", params={"aba": aba, "formato": formato})
            assert resp.status_code == 200 and resp.content.startswith(tipo)


def test_api_json(auth_client, base):
    _registro(base, data=f"{date.today():%Y-%m}-01")
    assert "achados" in auth_client.get("/api/competencia/auditoria").json()
    assert "linhas" in auth_client.get("/api/competencia/comparar").json()
    assert auth_client.get("/api/competencia/previsao").json()["competencia"]


def test_formato_e_aba_invalidos(auth_client):
    assert auth_client.get("/api/competencia/exportar", params={"aba": "auditoria", "formato": "doc"}).status_code == 400
    assert auth_client.get("/api/competencia/exportar", params={"aba": "x"}).status_code == 400


def test_acesso_restrito(client, db_session):
    from usuario.usuario_schema import UsuarioCriar
    from usuario.usuario_service import UsuarioService

    assert client.get("/api/competencia/auditoria").status_code == 401
    UsuarioService.criar(db_session, UsuarioCriar(
        username="operador_comp", password="senha12345", name="OPERADOR", role="operador"))
    client.post("/login", data={"username": "operador_comp", "password": "senha12345"})
    assert client.get("/api/competencia/auditoria").status_code == 403
    resp = client.get("/competencia", follow_redirects=False)
    assert resp.status_code == 302 and resp.headers["location"] == "/"
