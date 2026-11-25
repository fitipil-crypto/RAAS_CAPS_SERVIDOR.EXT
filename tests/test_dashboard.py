"""
Testes da dashboard: indicadores com variação, top procedimentos e gráfico de 7 dias.
"""
from datetime import datetime

import pytest

from dashboard.dashboard_service import _variacao


def _mes_atual_e_anterior():
    agora = datetime.now()
    atual = agora.strftime("%Y-%m")
    ano, mes = (agora.year, agora.month - 1) if agora.month > 1 else (agora.year - 1, 12)
    return atual, f"{ano}-{mes:02d}"


@pytest.fixture
def base_ids(auth_client):
    pac = auth_client.post("/api/pacientes/", json={
        "name": "PACIENTE DASHBOARD", "cns": "700000000000010",
        "birth_date": "1990-01-01", "gender": "F",
    })
    assert pac.status_code == 200, pac.text
    prof = auth_client.post("/api/profissionais/", json={
        "name": "PROFISSIONAL DASHBOARD", "cns": "700000000000011", "cbo": "225125",
    })
    assert prof.status_code == 200, prof.text
    proc = auth_client.post("/api/procedimentos/", json={
        "code": "0301080020", "name": "ATENDIMENTO INDIVIDUAL DASHBOARD",
    })
    assert proc.status_code == 200, proc.text
    return {
        "patient_id": pac.json()["id"],
        "professional_id": prof.json()["id"],
        "procedure_id": proc.json()["id"],
    }


def _lancar(auth_client, base_ids, competencia, data):
    resp = auth_client.post("/api/registros/", json={
        **base_ids, "service_month": competencia, "service_date": data,
    })
    assert resp.status_code == 200, resp.text


def test_variacao_sem_base_de_comparacao_retorna_none():
    assert _variacao(5, 0) is None


def test_variacao_percentual_arredondada():
    assert _variacao(3, 2) == 50
    assert _variacao(1, 2) == -50
    assert _variacao(2, 2) == 0


def test_dashboard_sem_dados_mostra_estado_vazio(auth_client):
    resp = auth_client.get("/")
    assert resp.status_code == 200
    assert "Nenhum atendimento lançado" in resp.text
    assert "sem base" in resp.text


def test_dashboard_mostra_variacao_contra_mes_anterior(auth_client, base_ids):
    atual, anterior = _mes_atual_e_anterior()
    _lancar(auth_client, base_ids, anterior, f"{anterior}-10")
    _lancar(auth_client, base_ids, atual, f"{atual}-01")
    _lancar(auth_client, base_ids, atual, f"{atual}-02")

    resp = auth_client.get("/")
    assert resp.status_code == 200
    # 2 atendimentos no mês atual contra 1 no anterior = +100%
    assert "▲ 100%" in resp.text


def test_dashboard_lista_procedimentos_mais_usados(auth_client, base_ids):
    atual, _ = _mes_atual_e_anterior()
    _lancar(auth_client, base_ids, atual, f"{atual}-01")
    _lancar(auth_client, base_ids, atual, f"{atual}-02")

    resp = auth_client.get("/")
    assert resp.status_code == 200
    assert "Procedimentos mais usados no mês" in resp.text
    assert "ATENDIMENTO INDIVIDUAL DASHBOARD" in resp.text
    assert "0301080020" in resp.text


def test_dashboard_grafico_tem_rotulo_acessivel(auth_client, base_ids):
    resp = auth_client.get("/")
    assert 'role="img"' in resp.text
    assert "Atendimentos por dia nos últimos 7 dias" in resp.text
