"""
Testes unitários das regras de negócio de registro RAAS (registro_validacao).

Chamam as funções direto, sem passar pela API: cada regra é conferida isolada,
inclusive os ramos que a tela não exercita com facilidade.
"""
import re

import pytest

from grupo.grupo_model import Grupo
from paciente.paciente_model import Paciente
from procedimento.procedimento_model import Procedimento
from profissional.profissional_model import Profissional
from registro.registro_model import Registro
from registro import registro_validacao as rv
from registro.registro_validacao import RegistroInvalido


# ── Fábricas ────────────────────────────────────────────────────────────────

def _paciente(db, admission_date=None, name="PACIENTE"):
    p = Paciente(name=name, admission_date=admission_date)
    db.add(p)
    db.commit()
    return p


def _profissional(db, name="PROFISSIONAL"):
    p = Profissional(name=name)
    db.add(p)
    db.commit()
    return p


def _procedimento(db, code="0301080020", name="ATENDIMENTO INDIVIDUAL"):
    p = Procedimento(code=code, name=name)
    db.add(p)
    db.commit()
    return p


def _grupo(db, data="2026-08-10", hora="13:00", pessoas=2, descricao="GRUPO"):
    g = Grupo(service_month=data[:7], description=descricao, group_date=data,
              group_time=hora, people_count=pessoas)
    db.add(g)
    db.commit()
    return g


def _registro(db, paciente, profissional, procedimento, data="2026-08-10", grupo=None):
    r = Registro(service_month=data[:7], service_date=data, patient_id=paciente.id,
                 professional_id=profissional.id, procedure_id=procedimento.id,
                 group_id=grupo.id if grupo else None)
    db.add(r)
    db.commit()
    return r


@pytest.fixture
def base(db_session):
    return {
        "paciente": _paciente(db_session, admission_date="2026-01-01"),
        "profissional": _profissional(db_session),
        "procedimento": _procedimento(db_session),
    }


def _kwargs(base, data="2026-08-10", **extra):
    return {
        "service_month": data[:7],
        "service_date": data,
        "patient_id": base["paciente"].id,
        "professional_id": base["profissional"].id,
        "procedure_id": base["procedimento"].id,
        **extra,
    }


# ── Funções puras ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("perfil, esperado", [
    ("admin", rv.MAX_PROFISSIONAIS_LOTE_ADMIN),
    ("operador", rv.MAX_PROFISSIONAIS_LOTE),
    (None, rv.MAX_PROFISSIONAIS_LOTE),
])
def test_max_profissionais_lote_por_perfil(perfil, esperado):
    assert rv.max_profissionais_lote(perfil) == esperado


@pytest.mark.parametrize("iso, esperado", [
    ("2026-08-10", "10/08/2026"),
    ("", ""),
    (None, ""),
    ("2026-08", "2026-08"),  # formato inesperado volta como veio
])
def test_data_br(iso, esperado):
    assert rv._data_br(iso) == esperado


def test_competencia_igual_ao_mes_da_data_passa():
    rv.validar_competencia("2026-08", "2026-08-31")


def test_competencia_diferente_do_mes_da_data_recusa():
    with pytest.raises(RegistroInvalido, match="competência"):
        rv.validar_competencia("2026-08", "2026-09-01")


@pytest.mark.parametrize("mes, data", [("", "2026-08-10"), ("2026-08", ""), (None, None)])
def test_competencia_sem_dado_nao_valida(mes, data):
    rv.validar_competencia(mes, data)


# ── Procedimento de grupo ───────────────────────────────────────────────────

@pytest.mark.parametrize("codigo", ["0301080216", "03.01.08.021-6"])
def test_eh_proc_grupo_aceita_codigo_com_ou_sem_pontuacao(db_session, codigo):
    proc = _procedimento(db_session, code=codigo, name="ATENDIMENTO EM GRUPO")
    assert rv.eh_proc_grupo(db_session, proc.id) is True


def test_eh_proc_grupo_falso_para_outro_codigo_ou_id_vazio(db_session):
    proc = _procedimento(db_session)
    assert rv.eh_proc_grupo(db_session, proc.id) is False
    assert rv.eh_proc_grupo(db_session, None) is False
    assert rv.eh_proc_grupo(db_session, "id-que-nao-existe") is False


# ── Data de admissão ────────────────────────────────────────────────────────

def test_atendimento_antes_da_admissao_recusa(db_session):
    pac = _paciente(db_session, admission_date="2026-08-15")
    with pytest.raises(RegistroInvalido, match="admissão"):
        rv.validar_data_admissao(db_session, pac.id, "2026-08-14")


def test_atendimento_no_dia_da_admissao_passa(db_session):
    pac = _paciente(db_session, admission_date="2026-08-15")
    rv.validar_data_admissao(db_session, pac.id, "2026-08-15")


def test_paciente_sem_admissao_nao_valida(db_session):
    pac = _paciente(db_session, admission_date=None)
    rv.validar_data_admissao(db_session, pac.id, "1990-01-01")


# ── Registro completo / duplicidade ─────────────────────────────────────────

def test_registro_valido_passa(db_session, base):
    rv.validar_registro(db_session, **_kwargs(base))


def test_registro_duplicado_no_banco_recusa(db_session, base):
    _registro(db_session, base["paciente"], base["profissional"], base["procedimento"])
    with pytest.raises(RegistroInvalido, match=re.escape(rv.MSG_DUPLICADO)):
        rv.validar_registro(db_session, **_kwargs(base))


def test_edicao_do_proprio_registro_nao_conta_como_duplicado(db_session, base):
    reg = _registro(db_session, base["paciente"], base["profissional"], base["procedimento"])
    rv.validar_registro(db_session, **_kwargs(base, excluir_id=reg.id))


def test_duplicado_dentro_do_mesmo_lote_recusa(db_session, base):
    vistos: set = set()
    rv.validar_registro(db_session, **_kwargs(base, vistos=vistos))
    assert len(vistos) == 1
    with pytest.raises(RegistroInvalido, match=re.escape(rv.MSG_DUPLICADO)):
        rv.validar_registro(db_session, **_kwargs(base, vistos=vistos))


def test_mesmo_paciente_em_grupos_diferentes_no_mesmo_dia_passa(db_session, base):
    g1 = _grupo(db_session, hora="09:00", descricao="G1")
    g2 = _grupo(db_session, hora="14:00", descricao="G2")
    _registro(db_session, base["paciente"], base["profissional"], base["procedimento"], grupo=g1)
    rv.validar_registro(db_session, **_kwargs(base, group_id=g2.id))


def test_registro_valida_competencia_antes_de_consultar_banco(db_session, base):
    with pytest.raises(RegistroInvalido, match="competência"):
        rv.validar_registro(db_session, **{**_kwargs(base), "service_month": "2026-07"})


# ── Grupo ───────────────────────────────────────────────────────────────────

def test_sem_grupo_nao_valida(db_session):
    rv.validar_grupo(db_session, group_id=None, professional_id="x", service_date="2026-08-10")


def test_grupo_inexistente_recusa(db_session):
    with pytest.raises(RegistroInvalido, match=rv.MSG_GRUPO_INEXISTENTE):
        rv.validar_grupo(db_session, group_id="nao-existe", professional_id=None,
                         service_date="2026-08-10")


def test_data_diferente_da_do_grupo_recusa(db_session):
    g = _grupo(db_session, data="2026-08-10")
    with pytest.raises(RegistroInvalido, match="10/08/2026"):
        rv.validar_grupo(db_session, group_id=g.id, professional_id=None,
                         service_date="2026-08-11")


def test_grupo_lotado_recusa(db_session, base):
    g = _grupo(db_session, pessoas=1)
    _registro(db_session, base["paciente"], base["profissional"], base["procedimento"], grupo=g)
    outro = _paciente(db_session, name="OUTRO")
    with pytest.raises(RegistroInvalido, match="1 pessoa"):
        rv.validar_grupo(db_session, group_id=g.id, professional_id=base["profissional"].id,
                         service_date=g.group_date, patient_ids={outro.id})


def test_paciente_ja_no_grupo_nao_conta_duas_vezes(db_session, base):
    g = _grupo(db_session, pessoas=1)
    _registro(db_session, base["paciente"], base["profissional"], base["procedimento"], grupo=g)
    rv.validar_grupo(db_session, group_id=g.id, professional_id=base["profissional"].id,
                     service_date=g.group_date, patient_ids={base["paciente"].id})


def test_profissional_em_outro_grupo_no_mesmo_horario_recusa(db_session, base):
    ocupado = _grupo(db_session, descricao="OFICINA")
    novo = _grupo(db_session, descricao="ACOLHIMENTO")
    _registro(db_session, base["paciente"], base["profissional"], base["procedimento"], grupo=ocupado)
    with pytest.raises(RegistroInvalido, match="OFICINA"):
        rv.validar_grupo(db_session, group_id=novo.id, professional_id=base["profissional"].id,
                         service_date=novo.group_date)


def test_profissional_em_outro_grupo_em_outro_horario_passa(db_session, base):
    manha = _grupo(db_session, hora="09:00", descricao="MANHA")
    tarde = _grupo(db_session, hora="14:00", descricao="TARDE")
    _registro(db_session, base["paciente"], base["profissional"], base["procedimento"], grupo=manha)
    rv.validar_grupo(db_session, group_id=tarde.id, professional_id=base["profissional"].id,
                     service_date=tarde.group_date)
