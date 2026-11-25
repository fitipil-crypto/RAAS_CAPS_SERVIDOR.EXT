"""
Testes de lançamento manual de registros RAAS.
"""
import pytest


@pytest.fixture
def base_ids(auth_client):
    """Cria paciente, profissional e procedimento e devolve seus ids."""
    pac = auth_client.post("/api/pacientes/", json={
        "name": "PACIENTE TESTE", "cns": "700000000000000",
        "birth_date": "1990-01-01", "gender": "M",
    })
    assert pac.status_code == 200, pac.text
    prof = auth_client.post("/api/profissionais/", json={
        "name": "PROFISSIONAL TESTE", "cns": "700000000000001", "cbo": "225125",
    })
    assert prof.status_code == 200, prof.text
    proc = auth_client.post("/api/procedimentos/", json={
        "code": "0301080020", "name": "ATENDIMENTO INDIVIDUAL",
    })
    assert proc.status_code == 200, proc.text
    return {
        "patient_id": pac.json()["id"],
        "professional_id": prof.json()["id"],
        "procedure_id": proc.json()["id"],
    }


def _payload(base_ids, service_month, service_date):
    return {**base_ids, "service_month": service_month, "service_date": service_date}


def test_criar_registro_na_competencia_correta(auth_client, base_ids):
    resp = auth_client.post("/api/registros/", json=_payload(base_ids, "2026-08", "2026-08-15"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["service_month"] == "2026-08"


def test_recusa_registro_de_outro_mes(auth_client, base_ids):
    resp = auth_client.post("/api/registros/", json=_payload(base_ids, "2026-08", "2026-09-10"))
    assert resp.status_code == 400
    assert "competência" in resp.json()["detail"]


def test_recusa_lote_com_data_de_outro_mes(auth_client, base_ids):
    payloads = [
        _payload(base_ids, "2026-08", "2026-08-10"),
        _payload(base_ids, "2026-08", "2026-09-10"),
    ]
    resp = auth_client.post("/api/registros/varios", json=payloads)
    assert resp.status_code == 400
    assert "competência" in resp.json()["detail"]
    # nenhum dos dois pode ter sido gravado
    assert auth_client.get("/api/registros/?month=2026-08").json() == []


def test_recusa_edicao_que_joga_data_para_outro_mes(auth_client, base_ids):
    criado = auth_client.post("/api/registros/", json=_payload(base_ids, "2026-08", "2026-08-15"))
    reg_id = criado.json()["id"]
    resp = auth_client.put(f"/api/registros/{reg_id}", json={"service_date": "2026-09-15"})
    assert resp.status_code == 400
    assert "competência" in resp.json()["detail"]
    assert auth_client.get(f"/api/registros/{reg_id}").json()["service_date"] == "2026-08-15"


def test_pagina_marca_linhas_com_id_do_registro(auth_client, base_ids):
    """A exclusão no front usa data-registro-id para achar o grupo do paciente
    e reabri-lo, em vez de recarregar a página (que fecharia todos os grupos)."""
    criado = auth_client.post("/api/registros/", json=_payload(base_ids, "2026-08", "2026-08-15"))
    reg_id = criado.json()["id"]

    html = auth_client.get("/registros?month=2026-08").text
    assert f'data-registro-id="{reg_id}"' in html
    assert f'data-patient-id="{base_ids["patient_id"]}"' in html


def test_indicadores_caps(auth_client, base_ids):
    """API e página de indicadores CAPS refletem os registros do mês."""
    resp = auth_client.post("/api/registros/", json=_payload(base_ids, "2026-03", "2026-03-10"))
    assert resp.status_code == 200, resp.text

    resp = auth_client.get("/api/relatorios/indicadores-caps?month=2026-03")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_atendimentos"] == 1
    assert data["usuarios_atendidos"] == 1
    assert data["genero"] == {"Masculino": 1}
    assert len(data["producao_mensal"]) == 12

    assert auth_client.get("/api/relatorios/indicadores-caps?month=abc").status_code == 400

    page = auth_client.get("/indicadores?month=2026-03")
    assert page.status_code == 200
    assert "Indicadores CAPS" in page.text


def test_indicadores_caps_vazio(auth_client):
    """Sem dados, a página renderiza sem erro."""
    assert auth_client.get("/indicadores").status_code == 200


@pytest.fixture
def grupo_ids(auth_client, base_ids):
    """Como base_ids, mas com o procedimento de atendimento em grupo."""
    proc = auth_client.post("/api/procedimentos/", json={
        "code": "03.01.08.021-6", "name": "ATENDIMENTO EM GRUPO DE PACIENTE EM CENTRO DE ATENÇÃO PSICOSSOCIAL",
    })
    assert proc.status_code == 200, proc.text
    return {**base_ids, "procedure_id": proc.json()["id"]}


def test_grupo_nao_e_mais_exigido_pelo_procedimento(auth_client, grupo_ids):
    """O esquema de sessão 1 a 5 foi revogado: o atendimento em grupo pode ser
    lançado solto, sem nenhum campo extra obrigatório."""
    resp = auth_client.post("/api/registros/", json=_payload(grupo_ids, "2026-03", "2026-03-10"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["group_id"] is None


def test_duplicado_considera_o_grupo(auth_client, grupo_ids):
    """Mesmo paciente, profissional, procedimento e data: em outro grupo pode,
    no mesmo grupo é lançamento repetido (no lote e no lançamento avulso)."""
    grupos = [auth_client.post("/api/grupos/", json={
        "description": f"MUSICA {n}", "group_date": "2026-03-10",
        "group_time": hora, "people_count": 3,
    }).json() for n, hora in [(1, "13:00"), (2, "15:00")]]

    payload = {**_payload(grupo_ids, "2026-03", "2026-03-10"), "group_id": grupos[0]["id"]}
    assert auth_client.post("/api/registros/", json=payload).status_code == 200

    repetido = auth_client.post("/api/registros/", json=payload)
    assert repetido.status_code == 400
    assert "já informada" in repetido.json()["detail"]
    assert auth_client.post("/api/registros/lote", json={"registros": [payload]}).status_code == 400

    # No outro grupo do mesmo dia, o mesmo lançamento passa.
    em_outro_grupo = {**payload, "group_id": grupos[1]["id"]}
    assert auth_client.post("/api/registros/lote", json={"registros": [em_outro_grupo]}).status_code == 200

    # Dentro do mesmo lote a repetição também é barrada.
    terceiro = auth_client.post("/api/grupos/", json={
        "description": "MUSICA 3", "group_date": "2026-03-10", "group_time": "17:00", "people_count": 3,
    }).json()
    repetida = {**payload, "group_id": terceiro["id"]}
    resp = auth_client.post("/api/registros/lote", json={"registros": [repetida, repetida]})
    assert resp.status_code == 400 and resp.json()["erros"][0]["linha"] == 1


def test_salvamentos_simultaneos_nao_duplicam(auth_client, base_ids):
    """8 salvamentos do mesmo registro ao mesmo tempo: só um pode entrar."""
    import threading
    from fastapi.testclient import TestClient
    from main import app

    cookies = dict(auth_client.cookies)
    payload = {"registros": [_payload(base_ids, "2026-08", "2026-08-20")]}
    barreira = threading.Barrier(8)
    status = []

    def salvar():
        with TestClient(app, cookies=cookies) as c:
            barreira.wait()
            status.append(c.post("/api/registros/lote", json=payload).status_code)

    threads = [threading.Thread(target=salvar) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(status) == [200] + [400] * 7
    assert len(auth_client.get("/api/registros/?month=2026-08").json()) == 1


def test_profissional_nao_pode_estar_em_dois_grupos_no_mesmo_horario(auth_client, grupo_ids):
    """Mesma data e mesmo horário: o profissional é uma pessoa só."""
    primeiro = auth_client.post("/api/grupos/", json={
        "description": "MUSICA", "group_date": "2026-03-10", "group_time": "13:00", "people_count": 5,
    }).json()
    segundo = auth_client.post("/api/grupos/", json={
        "description": "ARTESANATO", "group_date": "2026-03-10", "group_time": "13:00", "people_count": 5,
    }).json()

    payload = _payload(grupo_ids, "2026-03", "2026-03-10")
    assert auth_client.post("/api/registros/", json={**payload, "group_id": primeiro["id"]}).status_code == 200

    conflito = auth_client.post("/api/registros/lote", json={
        "registros": [{**payload, "group_id": segundo["id"]}],
    })
    assert conflito.status_code == 400
    assert "já está em outro grupo" in conflito.json()["detail"]

    # Em outro horário o mesmo profissional pode.
    outro_horario = auth_client.post("/api/grupos/", json={
        "description": "TEATRO", "group_date": "2026-03-10", "group_time": "15:00", "people_count": 5,
    }).json()
    liberado = auth_client.post("/api/registros/lote", json={
        "registros": [{**payload, "group_id": outro_horario["id"]}],
    })
    assert liberado.status_code == 200, liberado.text


def test_lote_respeita_a_quantidade_de_pessoas_do_grupo(auth_client, grupo_ids):
    grupo = auth_client.post("/api/grupos/", json={
        "description": "MUSICA", "group_date": "2026-03-10", "group_time": "13:00", "people_count": 1,
    }).json()
    outro = auth_client.post("/api/pacientes/", json={
        "name": "PACIENTE DOIS", "cns": "700000000000009", "birth_date": "1991-02-02", "gender": "F",
    }).json()

    payload = _payload(grupo_ids, "2026-03", "2026-03-10")
    resp = auth_client.post("/api/registros/lote", json={"registros": [
        {**payload, "group_id": grupo["id"]},
        {**payload, "group_id": grupo["id"], "patient_id": outro["id"]},
    ]})
    assert resp.status_code == 400
    assert "Quantidade de pessoas do grupo excedida" in resp.json()["detail"]
    assert auth_client.get("/api/registros/?month=2026-03").json() == []


def test_lote_recusa_data_diferente_da_data_do_grupo(auth_client, grupo_ids):
    grupo = auth_client.post("/api/grupos/", json={
        "description": "MUSICA", "group_date": "2026-03-10", "group_time": "13:00", "people_count": 5,
    }).json()
    resp = auth_client.post("/api/registros/lote", json={"registros": [
        {**_payload(grupo_ids, "2026-03", "2026-03-11"), "group_id": grupo["id"]},
    ]})
    assert resp.status_code == 400
    assert "Data diferente da data do grupo" in resp.json()["detail"]


def test_sessoes_sao_os_grupos_do_profissional(auth_client, grupo_ids, base_ids):
    """Cada grupo em que o profissional lançou conta uma sessão, não importa
    quantos atendimentos ele lançou dentro dele."""
    for dia, hora, qtd in [("10", "13:00", 1), ("11", "13:00", 2), ("12", "08:00", 1)]:
        grupo = auth_client.post("/api/grupos/", json={
            "description": f"MUSICA {dia}", "group_date": f"2026-03-{dia}",
            "group_time": hora, "people_count": 5,
        }).json()
        resp = auth_client.post("/api/registros/", json={
            **_payload(grupo_ids, "2026-03", f"2026-03-{dia}"), "group_id": grupo["id"], "quantity": qtd,
        })
        assert resp.status_code == 200, resp.text
    assert auth_client.post("/api/registros/", json=_payload(base_ids, "2026-03", "2026-03-10")).status_code == 200

    html = auth_client.get("/indicadores", params={"month": "2026-03"}).text
    assert "Sessões (grupos)" in html

    csv = auth_client.get("/api/relatorios/impressao/exportar", params={
        "tipo": "indicadores", "formato": "csv", "mes": "2026-03",
        "secoes_enviadas": "1", "secao": "prof_tipo",
    }).content.decode("utf-8-sig")
    assert "Profissional;Individual;Grupo;Sessões;Total" in csv
    assert "PROFISSIONAL TESTE;1;4;3;5" in csv


def test_lote_cria_todos_os_registros(auth_client, base_ids):
    lote = {"registros": [
        _payload(base_ids, "2026-08", "2026-08-10"),
        _payload(base_ids, "2026-08", "2026-08-11"),
    ]}
    resp = auth_client.post("/api/registros/lote", json=lote)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"criados": 2}
    assert len(auth_client.get("/api/registros/?month=2026-08").json()) == 2


def test_lote_limita_registros(auth_client, base_ids):
    from registro.registro_router import MAX_REGISTROS_LOTE
    lote = {"registros": [_payload(base_ids, "2026-08", "2026-08-10")] * (MAX_REGISTROS_LOTE + 1)}
    assert auth_client.post("/api/registros/lote", json=lote).status_code == 422


def test_lote_recusa_atendimento_em_grupo_fora_de_grupo(auth_client, grupo_ids):
    """Na digitação em lote o 03.01.08.021-6 só entra pelo Lançar grupo."""
    resp = auth_client.post("/api/registros/lote", json={"registros": [_payload(grupo_ids, "2026-03", "2026-03-10")]})
    assert resp.status_code == 400
    assert "Lançar grupo" in resp.json()["erros"][0]["mensagem"]

    grupo = auth_client.post("/api/grupos/", json={
        "description": "Música", "group_date": "2026-03-10", "group_time": "09:00", "people_count": 5}).json()
    resp = auth_client.post("/api/registros/lote", json={
        "registros": [{**_payload(grupo_ids, "2026-03", "2026-03-10"), "group_id": grupo["id"]}]})
    assert resp.status_code == 200, resp.text


def _profissionais(auth_client, n):
    ids = []
    for i in range(n):
        resp = auth_client.post("/api/profissionais/", json={
            "name": f"PROF EXTRA {i}", "cns": f"7000000000001{i:02d}", "cbo": "225125"})
        assert resp.status_code == 200, resp.text
        ids.append(resp.json()["id"])
    return ids


def test_lote_com_varios_profissionais(auth_client, base_ids):
    """Cada profissional recebe o seu registro; o limite é 5 (10 para o administrador)."""
    profs = _profissionais(auth_client, 10)
    lote = {"registros": [{**_payload(base_ids, "2026-08", "2026-08-10"), "professional_id": p} for p in profs]}
    resp = auth_client.post("/api/registros/lote", json=lote)  # auth_client é administrador
    assert resp.status_code == 200, resp.text
    assert resp.json()["criados"] == 10

    extra = _profissionais(auth_client, 1)
    lote["registros"].append({**_payload(base_ids, "2026-08", "2026-08-11"), "professional_id": extra[0]})
    resp = auth_client.post("/api/registros/lote", json=lote)
    assert resp.status_code == 400 and "10 profissionais" in resp.json()["detail"]


def test_operador_lanca_ate_5_profissionais(auth_client, client, base_ids):
    auth_client.post("/api/usuarios/", json={
        "username": "op_profs", "name": "Op", "role": "operador", "password": "senha123", "active": True})
    profs = _profissionais(auth_client, 6)
    client.post("/login", data={"username": "op_profs", "password": "senha123"})
    lote = {"registros": [{**_payload(base_ids, "2026-08", "2026-08-10"), "professional_id": p} for p in profs]}
    resp = client.post("/api/registros/lote", json=lote)
    assert resp.status_code == 400 and "5 profissionais" in resp.json()["detail"]
    lote["registros"].pop()
    assert client.post("/api/registros/lote", json=lote).status_code == 200


def test_tela_sem_novo_registro_e_com_equipe_no_lote(auth_client):
    html = auth_client.get("/registros").text
    assert "＋ Novo Registro" not in html
    assert "lote-equipe" in html and "LOTE_MAX_PROFS = 10" in html


def test_lote_aponta_linhas_com_erro_e_nao_grava_nada(auth_client, base_ids):
    lote = {"registros": [
        _payload(base_ids, "2026-08", "2026-08-10"),   # ok
        _payload(base_ids, "2026-08", "2026-09-10"),   # fora da competência
        _payload(base_ids, "2026-08", "2026-08-10"),   # duplicada da linha 0
    ]}
    resp = auth_client.post("/api/registros/lote", json=lote)
    assert resp.status_code == 400
    erros = {e["linha"]: e["mensagem"] for e in resp.json()["erros"]}
    assert set(erros) == {1, 2}
    assert "competência" in erros[1]
    assert "já informada" in erros[2]
    assert auth_client.get("/api/registros/?month=2026-08").json() == []


def test_lote_recusa_duplicado_ja_existente(auth_client, base_ids):
    auth_client.post("/api/registros/", json=_payload(base_ids, "2026-08", "2026-08-10"))
    resp = auth_client.post("/api/registros/lote", json={"registros": [_payload(base_ids, "2026-08", "2026-08-10")]})
    assert resp.status_code == 400
    assert resp.json()["erros"][0]["linha"] == 0


def test_lote_vazio_e_recusado(auth_client):
    assert auth_client.post("/api/registros/lote", json={"registros": []}).status_code == 422


def test_lote_exige_login(client, base_ids):
    assert client.post("/api/registros/lote", json={"registros": [_payload(base_ids, "2026-08", "2026-08-10")]}).status_code == 401


def test_pagina_registros_tem_digitacao_em_lote(auth_client):
    html = auth_client.get("/registros").text
    assert 'id="loteModal"' in html
    assert "registros_lote.js" in html


def test_menu_lateral_agrupado(auth_client):
    html = auth_client.get("/registros").text
    for grupo in ("cadastros", "atendimentos", "raas", "analises", "relatorios", "sistema"):
        assert f'data-group="{grupo}"' in html
    assert 'class="nav-group" data-group="relatorios"' in html
    assert 'href="/relatorios"' not in html  # incorporado aos Indicadores CAPS
    assert 'href="/indicadores"' in html
    assert 'href="/relatorios-impressao"' in html



def _cores_das_linhas(html, data):
    """Cor de fundo de cada linha da lista, na ordem em que aparecem naquela data."""
    import re
    classes = {
        "amarelo": "reg-bloco-amarelo", "azul": "reg-bloco-azul",
        "rosa": "reg-proc-rosa", "vermelho": "reg-proc-vermelho",
    }
    cores = []
    for tr in re.findall(rf'<tr data-date="{data}"[^>]*>', html):
        cores.append(next((cor for cor, cls in classes.items() if cls in tr), "branco"))
    return cores


def _lancar(auth_client, base_ids, data, lancamentos):
    for prof, proc in lancamentos:
        resp = auth_client.post("/api/registros/", json={
            **_payload(base_ids, "2026-03", data), "professional_id": prof, "procedure_id": proc,
        })
        assert resp.status_code == 200, resp.text


@pytest.fixture
def cenario_cores(auth_client, base_ids):
    """Dois profissionais, três procedimentos e os ids do fixture base."""
    prof2 = auth_client.post("/api/profissionais/", json={
        "name": "SEGUNDO PROFISSIONAL", "cns": "700000000000002", "cbo": "225125",
    }).json()["id"]
    prof3 = auth_client.post("/api/profissionais/", json={
        "name": "TERCEIRO PROFISSIONAL", "cns": "700000000000003", "cbo": "225125",
    }).json()["id"]
    proc2 = auth_client.post("/api/procedimentos/", json={"code": "0301080030", "name": "OUTRO PROC"}).json()["id"]
    proc3 = auth_client.post("/api/procedimentos/", json={"code": "0301080040", "name": "TERCEIRO PROC"}).json()["id"]
    return {
        "prof1": base_ids["professional_id"], "prof2": prof2, "prof3": prof3,
        "proc1": base_ids["procedure_id"], "proc2": proc2, "proc3": proc3,
    }


def test_blocos_de_profissional_pintam_a_linha_de_amarelo_e_azul(auth_client, base_ids, cenario_cores):
    """Na mesma data, 2+ lançamentos seguidos de um profissional pintam a linha,
    alternando amarelo e azul a cada bloco. Atendimento isolado fica branco e não
    entra na alternância, que segue correndo de um dia para o outro."""
    c = cenario_cores
    # A lista sai da data mais recente para a mais antiga: 13, 12, 11 e 10.
    # O dia 13 tem um único bloco, então vira a cor para o dia seguinte da lista.
    _lancar(auth_client, base_ids, "2026-03-13", [
        (c["prof1"], c["proc1"]), (c["prof1"], c["proc2"]),
    ])
    # Isolado no meio: fica branco sem consumir cor, e o bloco seguinte alterna.
    _lancar(auth_client, base_ids, "2026-03-12", [
        (c["prof1"], c["proc1"]), (c["prof1"], c["proc2"]),
        (c["prof2"], c["proc3"]),
        (c["prof3"], c["proc1"]), (c["prof3"], c["proc2"]),
    ])
    _lancar(auth_client, base_ids, "2026-03-11", [
        (c["prof2"], c["proc1"]), (c["prof2"], c["proc2"]),
        (c["prof1"], c["proc1"]), (c["prof1"], c["proc2"]),
    ])
    _lancar(auth_client, base_ids, "2026-03-10", [
        (c["prof1"], c["proc1"]), (c["prof1"], c["proc2"]),
        (c["prof2"], c["proc1"]), (c["prof2"], c["proc2"]),
        (c["prof1"], c["proc3"]),
    ])

    html = auth_client.get("/registros", params={"month": "2026-03"}).text
    assert _cores_das_linhas(html, "2026-03-13") == ["amarelo", "amarelo"]
    # O dia 13 terminou no amarelo, então o 12 começa no azul.
    assert _cores_das_linhas(html, "2026-03-12") == ["azul", "azul", "branco", "amarelo", "amarelo"]
    assert _cores_das_linhas(html, "2026-03-11") == ["azul", "azul", "amarelo", "amarelo"]
    assert _cores_das_linhas(html, "2026-03-10") == ["azul", "azul", "amarelo", "amarelo", "branco"]


def test_blocos_de_procedimento_pintam_a_linha_de_rosa_e_vermelho(auth_client, base_ids, cenario_cores):
    """Na mesma data, 2+ lançamentos seguidos do mesmo procedimento pintam a linha
    de rosa e vermelho claro, seguindo as mesmas regras do bloco de profissional —
    inclusive a alternância que continua de um dia para o outro. Aqui os
    profissionais se alternam, então nenhum bloco de profissional se forma."""
    c = cenario_cores
    _lancar(auth_client, base_ids, "2026-03-13", [
        (c["prof1"], c["proc1"]), (c["prof2"], c["proc1"]),
    ])
    _lancar(auth_client, base_ids, "2026-03-12", [
        (c["prof1"], c["proc1"]), (c["prof2"], c["proc1"]),
        (c["prof1"], c["proc2"]),
        (c["prof2"], c["proc3"]), (c["prof1"], c["proc3"]),
    ])
    _lancar(auth_client, base_ids, "2026-03-11", [
        (c["prof1"], c["proc2"]), (c["prof2"], c["proc2"]),
        (c["prof1"], c["proc1"]), (c["prof2"], c["proc1"]),
    ])
    _lancar(auth_client, base_ids, "2026-03-10", [
        (c["prof1"], c["proc1"]), (c["prof2"], c["proc1"]),
        (c["prof1"], c["proc2"]), (c["prof2"], c["proc2"]),
        (c["prof1"], c["proc3"]),
    ])

    html = auth_client.get("/registros", params={"month": "2026-03"}).text
    assert _cores_das_linhas(html, "2026-03-13") == ["rosa", "rosa"]
    # O dia 13 terminou no rosa, então o 12 começa no vermelho.
    assert _cores_das_linhas(html, "2026-03-12") == ["vermelho", "vermelho", "branco", "rosa", "rosa"]
    assert _cores_das_linhas(html, "2026-03-11") == ["vermelho", "vermelho", "rosa", "rosa"]
    assert _cores_das_linhas(html, "2026-03-10") == ["vermelho", "vermelho", "rosa", "rosa", "branco"]


def test_bloco_de_procedimento_so_pinta_o_que_sobra_se_sobrarem_2_linhas(auth_client, base_ids, cenario_cores):
    """O profissional tem prioridade quando a linha cai nos dois blocos. O que
    sobra do bloco de procedimento só é pintado se ficarem 2+ linhas seguidas sem
    cor — se sobrar uma só, ela fica branca, porque um lançamento sozinho nunca
    aparece colorido."""
    c = cenario_cores
    # Sobram duas linhas de proc2 depois do bloco do prof1: elas viram rosa.
    _lancar(auth_client, base_ids, "2026-03-11", [
        (c["prof1"], c["proc1"]), (c["prof1"], c["proc2"]),
        (c["prof2"], c["proc2"]), (c["prof3"], c["proc2"]),
    ])
    # Aqui sobra só uma linha de proc2: fica branca.
    _lancar(auth_client, base_ids, "2026-03-10", [
        (c["prof1"], c["proc1"]), (c["prof1"], c["proc2"]),
        (c["prof2"], c["proc2"]),
    ])

    html = auth_client.get("/registros", params={"month": "2026-03"}).text
    assert _cores_das_linhas(html, "2026-03-11") == ["amarelo", "amarelo", "rosa", "rosa"]
    assert _cores_das_linhas(html, "2026-03-10") == ["azul", "azul", "branco"]


def test_registro_de_grupo_grava_tipo_grupo(auth_client, base_ids):
    """Procedimento com 'grupo' no nome é lançado como Grupo ('02')."""
    proc = auth_client.post("/api/procedimentos/", json={
        "code": "0301080216", "name": "ATENDIMENTO EM GRUPO DE PACIENTE EM CENTRO DE ATENCAO PSICOSSOCIAL",
    })
    assert proc.status_code == 200, proc.text
    payload = _payload({**base_ids, "procedure_id": proc.json()["id"]}, "2026-08", "2026-08-10")
    resp = auth_client.post("/api/registros/", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["service_type"] == "02"


def test_registro_individual_continua_individual(auth_client, base_ids):
    resp = auth_client.post("/api/registros/", json=_payload(base_ids, "2026-08", "2026-08-11"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["service_type"] == "01"


def test_trocar_para_procedimento_de_grupo_atualiza_o_tipo(auth_client, base_ids):
    """Editar o registro e escolher procedimento de grupo acerta o tipo junto."""
    criado = auth_client.post("/api/registros/", json=_payload(base_ids, "2026-08", "2026-08-12"))
    assert criado.status_code == 200, criado.text
    assert criado.json()["service_type"] == "01"
    rid = criado.json()["id"]

    proc = auth_client.post("/api/procedimentos/", json={
        "code": "0301080224", "name": "PRATICA CORPORAL EM GRUPO",
    })
    assert proc.status_code == 200, proc.text
    resp = auth_client.put(f"/api/registros/{rid}", json={"procedure_id": proc.json()["id"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["service_type"] == "02"
