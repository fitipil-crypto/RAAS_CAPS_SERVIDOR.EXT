"""
Testes de aniversariantes (pacientes e profissionais).
"""
from datetime import date

from aniversariantes.aniversariantes_service import AniversariantesService


def _paciente(client, nome, nasc, i, **extra):
    r = client.post("/api/pacientes/", json={
        "name": nome, "cns": f"70000000000{i:04d}", "birth_date": nasc, "gender": "F", **extra,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _profissional(client, nome, nasc, **extra):
    r = client.post("/api/profissionais/", json={"name": nome, "birth_date": nasc, "cbo": "225133", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_profissional_guarda_nascimento(auth_client):
    prof = _profissional(auth_client, "PROF NASC", "1985-03-10")
    assert auth_client.get(f"/api/profissionais/{prof['id']}").json()["birth_date"] == "1985-03-10"


def test_mes_inclui_pacientes_e_profissionais(auth_client, db_session):
    _paciente(auth_client, "PACIENTE MARCO", "1990-03-15", 1)
    _paciente(auth_client, "PACIENTE ABRIL", "1990-04-15", 2)
    _profissional(auth_client, "PROF MARCO", "1980-03-02")
    itens = AniversariantesService.do_mes(db_session, 3, hoje=date(2026, 3, 1))
    assert [i["nome"] for i in itens] == ["PROF MARCO", "PACIENTE MARCO"]
    assert itens[0]["idade"] == 46 and itens[1]["idade"] == 36
    assert [i["nome"] for i in AniversariantesService.do_mes(db_session, 3, "profissional", hoje=date(2026, 3, 1))] == ["PROF MARCO"]


def test_inativos_ficam_de_fora_por_padrao(auth_client, db_session):
    _paciente(auth_client, "PACIENTE ALTA", "1990-03-15", 1, mot_saida="11")
    _profissional(auth_client, "PROF INATIVO", "1980-03-02", active=False)
    assert AniversariantesService.do_mes(db_session, 3, hoje=date(2026, 3, 1)) == []
    assert len(AniversariantesService.do_mes(db_session, 3, incluir_inativos=True, hoje=date(2026, 3, 1))) == 2


def test_proximos_atravessa_virada_de_ano_e_hoje(auth_client, db_session):
    _paciente(auth_client, "PACIENTE NATAL", "2000-12-30", 1)
    _paciente(auth_client, "PACIENTE ANO NOVO", "2000-01-02", 2)
    _paciente(auth_client, "PACIENTE LONGE", "2000-06-01", 3)
    itens = AniversariantesService.proximos(db_session, 7, hoje=date(2026, 12, 30))
    assert [(i["nome"], i["dias_restantes"], i["hoje"], i["idade"]) for i in itens] == [
        ("PACIENTE NATAL", 0, True, 26),
        ("PACIENTE ANO NOVO", 3, False, 27),
    ]


def test_29_de_fevereiro_em_ano_nao_bissexto(auth_client, db_session):
    _paciente(auth_client, "PACIENTE BISSEXTO", "2000-02-29", 1)
    itens = AniversariantesService.do_mes(db_session, 2, hoje=date(2026, 2, 1))
    assert itens[0]["aniversario"] == "2026-02-28"


def test_api_e_pagina(auth_client):
    _paciente(auth_client, "PACIENTE HOJE", date.today().replace(year=1990).isoformat(), 1)
    dados = auth_client.get("/api/aniversariantes/").json()
    assert dados["total_mes"] == 1 and dados["hoje"][0]["nome"] == "PACIENTE HOJE"
    assert len(auth_client.get("/api/aniversariantes/hoje").json()) == 1
    assert auth_client.get("/api/aniversariantes/?mes=13").status_code == 422

    pagina = auth_client.get("/aniversariantes")
    assert pagina.status_code == 200 and "PACIENTE HOJE" in pagina.text
    assert "PACIENTE HOJE" in auth_client.get("/").text
    assert auth_client.get("/aniversariantes?mes=99&tipo=xx").status_code == 200


def test_exige_login(client):
    assert client.get("/api/aniversariantes/").status_code == 401
    assert client.get("/aniversariantes", follow_redirects=False).status_code == 302
