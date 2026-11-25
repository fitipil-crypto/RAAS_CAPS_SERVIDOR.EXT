"""
Testes dos grupos de atendimento da Digitação RAAS.
"""
import pytest


@pytest.fixture
def base(auth_client):
    """Paciente, profissional e procedimento de grupo."""
    pac = auth_client.post("/api/pacientes/", json={
        "name": "PACIENTE GRUPO", "cns": "700000000000100",
        "birth_date": "1990-01-01", "gender": "M",
    })
    assert pac.status_code == 200, pac.text
    prof = auth_client.post("/api/profissionais/", json={
        "name": "PROFISSIONAL GRUPO", "cns": "700000000000101", "cbo": "225125",
    })
    assert prof.status_code == 200, prof.text
    proc = auth_client.post("/api/procedimentos/", json={
        "code": "0301080216", "name": "ATENDIMENTO EM GRUPO DE PACIENTE EM CENTRO DE ATENÇÃO PSICOSSOCIAL",
    })
    assert proc.status_code == 200, proc.text
    return {
        "patient_id": pac.json()["id"],
        "professional_id": prof.json()["id"],
        "procedure_id": proc.json()["id"],
    }


def _criar_grupo(auth_client, description, group_date, group_time, people_count=5):
    resp = auth_client.post("/api/grupos/", json={
        "description": description, "group_date": group_date,
        "group_time": group_time, "people_count": people_count,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_numeracao_segue_data_e_horario(auth_client):
    """Os grupos são numerados pela ordem de data e horário da competência —
    um grupo lançado fora de ordem entra na posição certa sem renumeração."""
    tarde = _criar_grupo(auth_client, "MUSICA TARDE", "2026-11-19", "15:00")
    manha = _criar_grupo(auth_client, "MUSICA MANHA", "2026-11-02", "13:00")
    cedo = _criar_grupo(auth_client, "MUSICA CEDO", "2026-11-19", "08:00")

    lista = auth_client.get("/api/grupos/", params={"month": "2026-11"}).json()
    assert [(g["numero"], g["description"]) for g in lista] == [
        (1, "MUSICA MANHA"), (2, "MUSICA CEDO"), (3, "MUSICA TARDE"),
    ]
    # O grupo criado primeiro passou a ser o nº 3 sozinho.
    assert auth_client.get(f"/api/grupos/{tarde['id']}").json()["numero"] == 3
    assert auth_client.get(f"/api/grupos/{manha['id']}").json()["numero"] == 1
    assert cedo["numero"] == 2


def test_competencia_vem_da_data_do_grupo(auth_client):
    grupo = _criar_grupo(auth_client, "MUSICA", "2026-11-19", "13:00")
    assert grupo["service_month"] == "2026-11"
    assert auth_client.get("/api/grupos/", params={"month": "2026-10"}).json() == []


def test_horario_e_descricao_sao_validados(auth_client):
    assert auth_client.post("/api/grupos/", json={
        "description": "MUSICA", "group_date": "2026-11-19", "group_time": "25:00", "people_count": 3,
    }).status_code == 422
    assert auth_client.post("/api/grupos/", json={
        "description": "X" * 31, "group_date": "2026-11-19", "group_time": "13:00", "people_count": 3,
    }).status_code == 422
    # 8:00 é aceito e normalizado para 08:00.
    assert _criar_grupo(auth_client, "MUSICA", "2026-11-19", "8:00")["group_time"] == "08:00"


def test_grupo_repetido_e_recusado(auth_client):
    _criar_grupo(auth_client, "MUSICA", "2026-11-19", "13:00")
    repetido = auth_client.post("/api/grupos/", json={
        "description": "musica", "group_date": "2026-11-19", "group_time": "13:00", "people_count": 5,
    })
    assert repetido.status_code == 400
    assert "Já existe um grupo" in repetido.json()["detail"]


def test_conteudo_do_grupo_traz_pacientes_e_procedimentos(auth_client, base):
    grupo = _criar_grupo(auth_client, "MUSICA", "2026-11-19", "13:00")
    resp = auth_client.post("/api/registros/lote", json={"registros": [{
        **base, "service_month": "2026-11", "service_date": "2026-11-19",
        "group_id": grupo["id"], "quantity": 2,
    }]})
    assert resp.status_code == 200, resp.text

    detalhe = auth_client.get(f"/api/grupos/{grupo['id']}").json()
    assert detalhe["total_registros"] == 1
    assert len(detalhe["pacientes"]) == 1
    paciente = detalhe["pacientes"][0]
    assert paciente["patient_name"] == "PACIENTE GRUPO"
    assert paciente["registros"][0]["professional_name"] == "PROFISSIONAL GRUPO"
    assert paciente["registros"][0]["procedure_code"] == "0301080216"
    assert paciente["registros"][0]["quantity"] == 2


def test_grupo_com_atendimentos_nao_muda_de_data_nem_e_excluido(auth_client, base):
    grupo = _criar_grupo(auth_client, "MUSICA", "2026-11-19", "13:00")
    assert auth_client.post("/api/registros/lote", json={"registros": [{
        **base, "service_month": "2026-11", "service_date": "2026-11-19", "group_id": grupo["id"],
    }]}).status_code == 200

    mudanca = auth_client.put(f"/api/grupos/{grupo['id']}", json={"group_date": "2026-11-20"})
    assert mudanca.status_code == 400
    assert "mudar a data" in mudanca.json()["detail"]

    exclusao = auth_client.delete(f"/api/grupos/{grupo['id']}")
    assert exclusao.status_code == 400
    assert "não pode ser excluído" in exclusao.json()["detail"]

    # O horário e a descrição continuam editáveis.
    assert auth_client.put(f"/api/grupos/{grupo['id']}", json={
        "description": "MUSICA E DANCA", "group_time": "14:30",
    }).status_code == 200


def test_quantidade_de_pessoas_nao_fica_menor_que_o_grupo(auth_client, base):
    grupo = _criar_grupo(auth_client, "MUSICA", "2026-11-19", "13:00", people_count=3)
    assert auth_client.post("/api/registros/lote", json={"registros": [{
        **base, "service_month": "2026-11", "service_date": "2026-11-19", "group_id": grupo["id"],
    }]}).status_code == 200

    menor = auth_client.put(f"/api/grupos/{grupo['id']}", json={"people_count": 0})
    assert menor.status_code == 422  # abaixo do mínimo do schema
    assert auth_client.put(f"/api/grupos/{grupo['id']}", json={"people_count": 1}).status_code == 200


def test_grupo_vazio_pode_ser_excluido(auth_client):
    grupo = _criar_grupo(auth_client, "MUSICA", "2026-11-19", "13:00")
    assert auth_client.delete(f"/api/grupos/{grupo['id']}").status_code == 200
    assert auth_client.get(f"/api/grupos/{grupo['id']}").status_code == 404


def test_tela_de_grupos_mostra_descricao_data_e_horario(auth_client, base):
    grupo = _criar_grupo(auth_client, "MUSICA", "2026-11-19", "15:00")
    assert auth_client.post("/api/registros/lote", json={"registros": [{
        **base, "service_month": "2026-11", "service_date": "2026-11-19", "group_id": grupo["id"],
    }]}).status_code == 200

    html = auth_client.get("/grupos", params={"month": "2026-11"}).text
    # Sem depender da quebra de linha do template.
    uma_linha = " ".join(html.split())
    assert "Grupo nº 1 – MUSICA - Data 19/11/2026 – 15:00 hrs" in uma_linha
    assert "1) PACIENTE GRUPO" in uma_linha
    assert "ATENDIMENTO EM GRUPO DE PACIENTE EM CENTRO DE ATENÇÃO PSICOSSOCIAL" in html
    assert "PROFISSIONAL GRUPO" in html
    # O item do menu aparece em todas as telas.
    assert '<a href="/grupos"' in html
    assert '<a href="/grupos"' in auth_client.get("/registros").text


def test_tela_de_grupos_sem_grupos_explica_onde_criar(auth_client):
    html = auth_client.get("/grupos", params={"month": "2026-12"}).text
    assert "Nenhum grupo nesta competência" in html
    assert "Digitação RAAS" in html


def test_tela_de_grupos_exige_login(client):
    resp = client.get("/grupos", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


def test_tela_de_grupos_abre_e_fecha_grupo_e_paciente(auth_client, base):
    """Dois níveis, cada um com a sua seta: a barra abre e fecha o grupo e o
    nome do paciente abre e fecha os atendimentos dele."""
    grupo = _criar_grupo(auth_client, "MUSICA", "2026-11-19", "15:00")
    assert auth_client.post("/api/registros/lote", json={"registros": [{
        **base, "service_month": "2026-11", "service_date": "2026-11-19", "group_id": grupo["id"],
    }]}).status_code == 200

    html = auth_client.get("/grupos", params={"month": "2026-11"}).text
    assert html.count('data-acao="grupo"') == 1
    assert html.count('data-acao="paciente"') == 1
    assert html.count('class="gr-seta"') == 1            # seta do grupo
    assert html.count('gr-seta gr-seta-pac') == 1        # seta do paciente
    assert html.count('aria-expanded="true"') == 2
    # O seletor de modo mostra em qual estado a tela está.
    assert 'data-modo="pacientes"' in html and 'data-modo="tudo"' in html
    assert '1 atend.' in html


def test_tela_de_grupos_colore_atendimentos_como_registros(auth_client, base):
    """Mesmo padrão de cores dos Registros RAAS: 2+ atendimentos seguidos do
    mesmo procedimento ficam rosa; do mesmo profissional, amarelo."""
    outro = auth_client.post("/api/profissionais/", json={
        "name": "OUTRO PROFISSIONAL", "cns": "700000000000102", "cbo": "225125",
    }).json()
    grupo = _criar_grupo(auth_client, "MUSICA", "2026-11-19", "15:00")
    comum = {"service_month": "2026-11", "service_date": "2026-11-19", "group_id": grupo["id"]}
    resp = auth_client.post("/api/registros/lote", json={"registros": [
        {**base, **comum},
        {**base, **comum, "professional_id": outro["id"]},
    ]})
    assert resp.status_code == 200, resp.text

    html = auth_client.get("/grupos", params={"month": "2026-11"}).text
    # Mesmo procedimento com dois profissionais: bloco rosa de 2 linhas.
    assert html.count('<li class="reg-proc-rosa">') == 2
    assert "gr-legenda" in html


def test_atendimento_lancado_no_grupo_conta_como_grupo(auth_client, base):
    """Práticas corporais e expressivas podem ser individuais ou em grupo:
    lançadas dentro de um grupo contam como Grupo; fora dele, Individual."""
    praticas = auth_client.post("/api/procedimentos/", json={
        "code": "0301080275", "name": "PRATICAS CORPORAIS EM CENTRO DE ATENÇÃO PSICOSSOCIAL",
    }).json()
    grupo = _criar_grupo(auth_client, "MUSICA", "2026-11-19", "15:00")
    comum = {"service_month": "2026-11", "service_date": "2026-11-19"}
    resp = auth_client.post("/api/registros/lote", json={"registros": [
        {**base, **comum, "group_id": grupo["id"]},
        {**base, **comum, "group_id": grupo["id"], "procedure_id": praticas["id"]},
        {**base, **comum, "service_date": "2026-11-20", "procedure_id": praticas["id"]},
    ]})
    assert resp.status_code == 200, resp.text

    tipos = {(r["procedure_id"], bool(r["group_id"])): r["service_type"]
             for r in auth_client.get("/api/registros/", params={"month": "2026-11"}).json()}
    assert tipos[(praticas["id"], True)] == "02"
    assert tipos[(praticas["id"], False)] == "01"

    indicadores = auth_client.get("/api/relatorios/indicadores-caps", params={"month": "2026-11"}).json()
    assert indicadores["tipo_atendimento"] == {"Individual": 1, "Grupo": 2}

    csv = auth_client.get("/api/relatorios/impressao/exportar", params={
        "tipo": "indicadores", "formato": "csv", "mes": "2026-11",
        "secoes_enviadas": "1", "secao": "prof_tipo",
    }).content.decode("utf-8-sig")
    # Profissional;Individual;Grupo;Sessões;Total
    assert "PROFISSIONAL GRUPO;1;2;1;3" in csv


def test_busca_da_tela_de_grupos_cobre_descricao_data_nome_e_prontuario(auth_client, base):
    """O filtro da tela procura em texto (descrição, nome, profissional) e em
    números sem pontuação (data e prontuário), que é o que permite achar o
    grupo digitando 18/11, 1811 ou o nº do prontuário."""
    import re

    grupo = _criar_grupo(auth_client, "MUSICA", "2026-11-18", "08:00")
    assert auth_client.post("/api/registros/lote", json={"registros": [{
        **base, "service_month": "2026-11", "service_date": "2026-11-18", "group_id": grupo["id"],
    }]}).status_code == 200
    # O paciente da fixture precisa de prontuário para entrar na busca por número.
    auth_client.put(f"/api/pacientes/{base['patient_id']}", json={"prontuario": "1417"})

    html = auth_client.get("/grupos", params={"month": "2026-11"}).text
    busca, numeros = re.search(
        r'<section class="gr-card" data-busca="(.*?)" data-num="(.*?)">', html, re.S
    ).groups()

    for termo in ["musica", "18/11/2026", "2026-11-18", "08:00", "paciente grupo",
                  "profissional grupo", "grupo nº 1"]:
        assert termo in busca, termo
    assert set(numeros.split()) >= {"18112026", "20261118", "0800", "1417"}
