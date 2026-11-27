"""
Testes do serviço de retenção de competências (sistema/retention_service).

A purga apaga dados de saúde de forma definitiva, então cada borda da janela é
conferida: o que fica, o que sai e o que nunca pode ser tocado (outra unidade).
"""
from datetime import datetime

import pytest

from registro.registro_model import Registro
from sistema import retention_service
from sistema.escopo import como_unidade, sem_escopo
from sistema.retention_service import RetentionService


class _DataFixa(datetime):
    """Congela "agora" em 15/03/2026 para a janela ser previsível."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 3, 15, 10, 30)


@pytest.fixture(autouse=True)
def hoje_fixo(monkeypatch):
    monkeypatch.setattr(retention_service, "datetime", _DataFixa)


def _registro(db, mes, unidade_id=None):
    r = Registro(service_month=mes, service_date=f"{mes}-01" if mes else "2026-03-01",
                 patient_id="p", professional_id="f", procedure_id="x",
                 unidade_id=unidade_id)
    db.add(r)
    db.commit()
    return r


def _meses(db):
    with sem_escopo():
        return sorted(r.service_month for r in db.query(Registro).all())


def test_janela_e_mes_atual_mais_tres_anteriores():
    assert RetentionService.allowed_competencias() == ["202603", "202602", "202601", "202512"]


def test_janela_atravessa_virada_de_ano(monkeypatch):
    class _Janeiro(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 31)

    monkeypatch.setattr(retention_service, "datetime", _Janeiro)
    assert RetentionService.allowed_competencias() == ["202601", "202512", "202511", "202510"]


def test_purga_remove_so_o_que_esta_fora_da_janela(db_session):
    for mes in ["2025-10", "2025-11", "2025-12", "2026-01", "2026-03"]:
        _registro(db_session, mes)

    removidos = RetentionService.purge_old_competencias(db_session)

    assert removidos == 2
    assert _meses(db_session) == ["2025-12", "2026-01", "2026-03"]


def test_purga_aceita_competencia_sem_hifen(db_session):
    _registro(db_session, "202603")
    _registro(db_session, "202509")
    assert RetentionService.purge_old_competencias(db_session) == 1
    assert _meses(db_session) == ["202603"]


def test_purga_nao_toca_registro_sem_competencia(db_session):
    _registro(db_session, "")
    assert RetentionService.purge_old_competencias(db_session) == 0
    assert _meses(db_session) == [""]


def test_purga_sem_nada_antigo_nao_remove(db_session):
    _registro(db_session, "2026-02")
    assert RetentionService.purge_old_competencias(db_session) == 0


def test_purga_com_unidade_ativa_nao_apaga_outra_unidade(db_session):
    """Com o escopo ligado, a purga só enxerga a unidade de quem a disparou."""
    _registro(db_session, "2025-01", unidade_id="caps-a")
    _registro(db_session, "2025-01", unidade_id="caps-b")

    with como_unidade("caps-a"):
        removidos = RetentionService.purge_old_competencias(db_session)

    assert removidos == 1
    with sem_escopo():
        restantes = db_session.query(Registro).all()
    assert [r.unidade_id for r in restantes] == ["caps-b"]
