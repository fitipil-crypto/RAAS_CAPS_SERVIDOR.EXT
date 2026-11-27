"""
Testes de Eventos (lançamento múltiplo de registros RAAS).
"""
import pytest


@pytest.fixture
def base(auth_client):
    """Cria 2 pacientes, 2 profissionais e 2 procedimentos."""
    pacientes = []
    for i, nome in enumerate(["PACIENTE EVENTO A", "PACIENTE EVENTO B"]):
        r = auth_client.post("/api/pacientes/", json={
            "name": nome, "cns": f"70000000000020{i}",
            "birth_date": "1990-01-01", "gender": "M",
        })
        assert r.status_code == 200, r.text
        pacientes.append(r.json()["id"])

    profissionais = []
    for i, nome in enumerate(["PROF EVENTO A", "PROF EVENTO B"]):
        r = auth_client.post("/api/profissionais/", json={
            "name": nome, "cns": f"70000000000030{i}", "cbo": f"22512{i}",
        })
        assert r.status_code == 200, r.text
        profissionais.append(r.json()["id"])

    procedimentos = []
    for code, nome in [("0301080216", "ATENDIMENTO EM GRUPO"), ("0301080275", "PRATICAS CORPORAIS")]:
        r = auth_client.post("/api/procedimentos/", json={"code": code, "name": nome})
        assert r.status_code == 200, r.text
        procedimentos.append(r.json()["id"])

    return {"pacientes": pacientes, "profissionais": profissionais, "procedimentos": procedimentos}


def criar_evento(client, data="2026-10-05", nome="DIA DAS CRIANCAS"):
    r = client.post("/api/eventos/", json={"name": nome, "event_date": data})
    assert r.status_code == 200, r.text
    return r.json()


def test_criar_evento_deriva_competencia(auth_client):
    evento = criar_evento(auth_client)
    assert evento["service_month"] == "2026-10"
    assert evento["name"] == "DIA DAS CRIANCAS"


def test_adicionar_pacientes_ignora_repetidos(auth_client, base):
    evento = criar_evento(auth_client)
    url = f"/api/eventos/{evento['id']}/pacientes"

    r = auth_client.post(url, json={"patient_ids": base["pacientes"]})
    assert r.json()["adicionados"] == 2

    # reenviar os mesmos não duplica
    r = auth_client.post(url, json={"patient_ids": base["pacientes"]})
    assert r.json()["adicionados"] == 0
    assert len(auth_client.get(url).json()["patient_ids"]) == 2


def test_lancamento_cruza_procedimento_por_profissional(auth_client, base):
    evento = criar_evento(auth_client)
    auth_client.post(f"/api/eventos/{evento['id']}/pacientes", json={"patient_ids": base["pacientes"]})

    r = auth_client.post(f"/api/eventos/{evento['id']}/registros", json={
        "procedures": [{"procedure_id": p, "quantity": 1} for p in base["procedimentos"]],
        "professional_ids": base["profissionais"],
    })
    assert r.status_code == 200, r.text
    # 2 pacientes × 2 procedimentos × 2 profissionais
    assert r.json()["criados"] == 8

    registros = auth_client.get("/api/registros/?month=2026-10").json()
    assert len(registros) == 8
    assert {reg["service_date"] for reg in registros} == {"2026-10-05"}
    assert {reg["service_month"] for reg in registros} == {"2026-10"}
    # cada paciente recebeu as 4 combinações
    for patient_id in base["pacientes"]:
        assert len([r for r in registros if r["patient_id"] == patient_id]) == 4


def test_relancar_evento_nao_duplica(auth_client, base):
    evento = criar_evento(auth_client)
    auth_client.post(f"/api/eventos/{evento['id']}/pacientes", json={"patient_ids": base["pacientes"]})
    payload = {
        "procedures": [{"procedure_id": base["procedimentos"][0], "quantity": 1}],
        "professional_ids": [base["profissionais"][0]],
    }
    url = f"/api/eventos/{evento['id']}/registros"

    assert auth_client.post(url, json=payload).json()["criados"] == 2
    segundo = auth_client.post(url, json=payload).json()
    assert segundo["criados"] == 0
    assert segundo["ignorados"] == 2
    assert len(auth_client.get("/api/registros/?month=2026-10").json()) == 2


def test_ignorados_dizem_quem_e_qual_combinacao(auth_client, base):
    """Quando um atendimento já existe, o resultado precisa dizer de quem e
    qual combinação — senão parece que faltou registro."""
    auth_client.post("/api/registros/", json={
        "service_month": "2026-10", "service_date": "2026-10-05",
        "patient_id": base["pacientes"][0],
        "professional_id": base["profissionais"][0],
        "procedure_id": base["procedimentos"][0],
    })

    evento = criar_evento(auth_client)
    auth_client.post(f"/api/eventos/{evento['id']}/pacientes", json={"patient_ids": base["pacientes"]})
    r = auth_client.post(f"/api/eventos/{evento['id']}/registros", json={
        "procedures": [{"procedure_id": base["procedimentos"][0], "quantity": 1}],
        "professional_ids": [base["profissionais"][0]],
    }).json()

    assert r["criados"] == 1
    assert r["ignorados"] == 1
    assert r["ignorados_detalhe"] == [{
        "paciente": "PACIENTE EVENTO A",
        "procedimento": "ATENDIMENTO EM GRUPO",
        "profissional": "PROF EVENTO A",
    }]


def test_pula_paciente_com_admissao_posterior(auth_client, base):
    """O RAAS não aceita atendimento anterior à admissão — o paciente é
    pulado em vez de derrubar o lançamento inteiro."""
    r = auth_client.post("/api/pacientes/", json={
        "name": "PACIENTE ADMITIDO DEPOIS", "cns": "700000000000299",
        "birth_date": "1990-01-01", "gender": "F", "admission_date": "2026-11-01",
    })
    assert r.status_code == 200, r.text
    tardio = r.json()["id"]

    evento = criar_evento(auth_client)
    auth_client.post(f"/api/eventos/{evento['id']}/pacientes",
                     json={"patient_ids": base["pacientes"] + [tardio]})

    resultado = auth_client.post(f"/api/eventos/{evento['id']}/registros", json={
        "procedures": [{"procedure_id": base["procedimentos"][0], "quantity": 1}],
        "professional_ids": [base["profissionais"][0]],
    }).json()
    assert resultado["criados"] == 2
    assert resultado["pulados"] == ["PACIENTE ADMITIDO DEPOIS"]


def test_lancamento_sem_pacientes_falha(auth_client, base):
    evento = criar_evento(auth_client)
    r = auth_client.post(f"/api/eventos/{evento['id']}/registros", json={
        "procedures": [{"procedure_id": base["procedimentos"][0], "quantity": 1}],
        "professional_ids": [base["profissionais"][0]],
    })
    assert r.status_code == 400
    assert "pacientes" in r.json()["detail"]


def test_limites_de_5_procedimentos_e_10_profissionais(auth_client, base):
    evento = criar_evento(auth_client)
    auth_client.post(f"/api/eventos/{evento['id']}/pacientes", json={"patient_ids": base["pacientes"]})
    url = f"/api/eventos/{evento['id']}/registros"

    seis = [{"procedure_id": base["procedimentos"][0], "quantity": 1} for _ in range(6)]
    assert auth_client.post(url, json={"procedures": seis, "professional_ids": base["profissionais"]}).status_code == 422

    onze = [base["profissionais"][0]] * 11
    um = [{"procedure_id": base["procedimentos"][0], "quantity": 1}]
    assert auth_client.post(url, json={"procedures": um, "professional_ids": onze}).status_code == 422


def test_excluir_evento_apagando_os_atendimentos(auth_client, base):
    evento = criar_evento(auth_client)
    auth_client.post(f"/api/eventos/{evento['id']}/pacientes", json={"patient_ids": base["pacientes"]})
    auth_client.post(f"/api/eventos/{evento['id']}/registros", json={
        "procedures": [{"procedure_id": p, "quantity": 1} for p in base["procedimentos"]],
        "professional_ids": base["profissionais"],
    })
    assert len(auth_client.get("/api/registros/?month=2026-10").json()) == 8

    r = auth_client.delete(f"/api/eventos/{evento['id']}?remover_registros=true")
    assert r.status_code == 200, r.text
    assert r.json()["registros_removidos"] == 8
    assert auth_client.get("/api/registros/?month=2026-10").json() == []


def test_exclusao_nao_apaga_registro_que_ja_existia(auth_client, base):
    """Um atendimento lançado à mão antes do evento é ignorado no lançamento
    (não ganha vínculo) e por isso sobrevive à exclusão com remoção."""
    lancado_a_mao = auth_client.post("/api/registros/", json={
        "service_month": "2026-10", "service_date": "2026-10-05",
        "patient_id": base["pacientes"][0],
        "professional_id": base["profissionais"][0],
        "procedure_id": base["procedimentos"][0],
    })
    assert lancado_a_mao.status_code == 200, lancado_a_mao.text
    id_manual = lancado_a_mao.json()["id"]

    evento = criar_evento(auth_client)
    auth_client.post(f"/api/eventos/{evento['id']}/pacientes", json={"patient_ids": base["pacientes"]})
    resultado = auth_client.post(f"/api/eventos/{evento['id']}/registros", json={
        "procedures": [{"procedure_id": base["procedimentos"][0], "quantity": 1}],
        "professional_ids": [base["profissionais"][0]],
    }).json()
    assert resultado["criados"] == 1 and resultado["ignorados"] == 1

    r = auth_client.delete(f"/api/eventos/{evento['id']}?remover_registros=true")
    assert r.json()["registros_removidos"] == 1
    restantes = auth_client.get("/api/registros/?month=2026-10").json()
    assert [reg["id"] for reg in restantes] == [id_manual]


def test_excluir_evento_preserva_registros(auth_client, base):
    evento = criar_evento(auth_client)
    auth_client.post(f"/api/eventos/{evento['id']}/pacientes", json={"patient_ids": base["pacientes"]})
    auth_client.post(f"/api/eventos/{evento['id']}/registros", json={
        "procedures": [{"procedure_id": base["procedimentos"][0], "quantity": 1}],
        "professional_ids": [base["profissionais"][0]],
    })

    r = auth_client.delete(f"/api/eventos/{evento['id']}")
    assert r.status_code == 200
    assert r.json()["registros_removidos"] == 0
    assert auth_client.get(f"/api/eventos/{evento['id']}").status_code == 404
    # os atendimentos já computados pertencem ao paciente
    assert len(auth_client.get("/api/registros/?month=2026-10").json()) == 2


def test_resumo_vazio_antes_do_lancamento(auth_client, base):
    evento = criar_evento(auth_client)
    auth_client.post(f"/api/eventos/{evento['id']}/pacientes", json={"patient_ids": base["pacientes"]})

    resumo = auth_client.get(f"/api/eventos/{evento['id']}/registros").json()["resumo"]
    assert resumo == {"profissionais": [], "procedimentos": []}


def test_resumo_traz_profissionais_e_procedimentos_em_comum(auth_client, base):
    """Depois do lançamento, o evento sabe dizer quem atendeu a lista e com
    quais procedimentos — sem repetir uma vez por paciente."""
    evento = criar_evento(auth_client)
    auth_client.post(f"/api/eventos/{evento['id']}/pacientes", json={"patient_ids": base["pacientes"]})
    r = auth_client.post(f"/api/eventos/{evento['id']}/registros", json={
        "procedures": [{"procedure_id": p, "quantity": 1} for p in base["procedimentos"]],
        "professional_ids": base["profissionais"],
    })
    assert r.json()["criados"] == 8  # 2 pacientes × 2 procedimentos × 2 profissionais

    resumo = auth_client.get(f"/api/eventos/{evento['id']}/registros").json()["resumo"]
    assert [p["name"] for p in resumo["profissionais"]] == ["PROF EVENTO A", "PROF EVENTO B"]
    assert [p["cbo"] for p in resumo["profissionais"]] == ["225120", "225121"]
    assert [p["code"] for p in resumo["procedimentos"]] == ["0301080216", "0301080275"]


def test_pagina_mostra_marcador_e_rodape_da_lista(auth_client, base):
    evento = criar_evento(auth_client)
    auth_client.post(f"/api/eventos/{evento['id']}/pacientes", json={"patient_ids": base["pacientes"]})
    auth_client.post(f"/api/eventos/{evento['id']}/registros", json={
        "procedures": [{"procedure_id": base["procedimentos"][0], "quantity": 1}],
        "professional_ids": [base["profissionais"][0]],
    })

    html = auth_client.get("/eventos?month=2026-10").text
    assert "05/10/2026" in html and "segunda-feira" in html   # data em pt-BR com o dia da semana
    assert 'data-evento-data="2026-10-05"' in html            # o ISO fica para o JavaScript
    assert "marcador-evento.svg" in html          # marcador em seta de cada participante
    assert "evento-rodape" in html
    assert "PROF EVENTO A" in html                # fecha a lista com quem atendeu
    assert "CBO 225120" in html
    assert "0301080216" in html


def test_eventos_sao_numerados_pela_data_da_competencia(auth_client, base):
    """Como nos grupos, o nº vem da ordem das datas — e acompanha a mudança
    de data, porque não fica gravado no evento."""
    criar_evento(auth_client, data="2026-10-20", nome="FESTA JUNINA")
    criar_evento(auth_client, data="2026-10-05", nome="DIA DAS CRIANCAS")

    html = auth_client.get("/eventos?month=2026-10").text
    cards = html.split('class="card evento-card"')[1:]
    assert len(cards) == 2
    # A lista desce pela data (20/10 em cima), mas o nº 1 é o evento de 05/10,
    # criado depois: o número vem da data, não da ordem de cadastro.
    assert "Evento nº 2" in cards[0] and "FESTA JUNINA" in cards[0]
    assert "Evento nº 1" in cards[1] and "DIA DAS CRIANCAS" in cards[1]


def test_registros_do_evento_saem_marcados_com_o_numero(auth_client, base):
    """A lista de atendimentos mostra 'Evento nº N' ao lado do procedimento,
    no mesmo lugar em que o grupo aparece."""
    criar_evento(auth_client, data="2026-10-01", nome="PRIMEIRO EVENTO")
    evento = criar_evento(auth_client, data="2026-10-15", nome="FESTA JUNINA")
    auth_client.post(f"/api/eventos/{evento['id']}/pacientes", json={"patient_ids": base["pacientes"]})
    auth_client.post(f"/api/eventos/{evento['id']}/registros", json={
        "procedures": [{"procedure_id": base["procedimentos"][0], "quantity": 1}],
        "professional_ids": [base["profissionais"][0]],
    })

    html = auth_client.get("/registros?month=2026-10").text
    assert "Evento nº 2" in html                 # 01/10 é o nº 1; a festa é a nº 2
    assert "FESTA JUNINA — 15/10/2026" in html   # title do badge
    assert "Evento nº 1" not in html             # o evento sem lançamento não marca nada


def _logar_como(client, db_session, role):
    from usuario.usuario_service import UsuarioService
    from usuario.usuario_schema import UsuarioCriar

    UsuarioService.criar(db_session, UsuarioCriar(
        username=f"{role}_evt", password="senha12345", name=role.upper(), role=role,
    ))
    client.post("/login", data={"username": f"{role}_evt", "password": "senha12345"})


def test_operador_nao_acessa_eventos(client, db_session):
    _logar_como(client, db_session, "operador")

    assert client.get("/api/eventos/").status_code == 403
    assert client.post("/api/eventos/", json={"name": "X", "event_date": "2026-10-05"}).status_code == 403
    resp = client.get("/eventos", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"


def test_coordenador_cria_evento_e_lanca_registros(client, db_session, auth_client, base):
    """Coordenador gerencia o evento e lança os registros."""
    _logar_como(client, db_session, "coordenador")

    assert client.get("/eventos", follow_redirects=False).status_code == 200

    evento = client.post("/api/eventos/", json={"name": "FESTA COORD", "event_date": "2026-10-05"})
    assert evento.status_code == 200, evento.text
    evento_id = evento.json()["id"]

    assert client.post(f"/api/eventos/{evento_id}/pacientes",
                       json={"patient_ids": base["pacientes"]}).status_code == 200

    r = client.post(f"/api/eventos/{evento_id}/registros", json={
        "procedures": [{"procedure_id": base["procedimentos"][0], "quantity": 1}],
        "professional_ids": [base["profissionais"][0]],
    })
    assert r.status_code == 200, r.text
    assert r.json()["criados"] == 2


def test_coordenador_nao_apaga_os_atendimentos_do_evento(client, db_session, auth_client, base):
    """Coordenador não exclui registro individualmente — não pode em lote."""
    _logar_como(client, db_session, "coordenador")
    evento_id = client.post("/api/eventos/", json={"name": "FESTA COORD 2", "event_date": "2026-10-05"}).json()["id"]
    client.post(f"/api/eventos/{evento_id}/pacientes", json={"patient_ids": base["pacientes"]})
    client.post(f"/api/eventos/{evento_id}/registros", json={
        "procedures": [{"procedure_id": base["procedimentos"][0], "quantity": 1}],
        "professional_ids": [base["profissionais"][0]],
    })

    negado = client.delete(f"/api/eventos/{evento_id}?remover_registros=true")
    assert negado.status_code == 403
    assert "administrador" in negado.json()["detail"]

    # sem remover os atendimentos, a exclusão é permitida
    ok = client.delete(f"/api/eventos/{evento_id}")
    assert ok.status_code == 200
    assert ok.json()["registros_removidos"] == 0
    assert len(client.get("/api/registros/?month=2026-10").json()) == 2
