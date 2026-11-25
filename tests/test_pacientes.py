"""
Testes do módulo de pacientes.
"""


def test_criar_paciente(auth_client):
    """POST /api/pacientes/ deve criar um paciente."""
    resp = auth_client.post("/api/pacientes/", json={
        "name": "João da Silva",
        "cns": "123456789012345",
        "gender": "M",
        "race": "01",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "João da Silva"
    assert data["cns"] == "123456789012345"


def test_listar_pacientes(auth_client):
    """GET /api/pacientes/ deve listar pacientes."""
    auth_client.post("/api/pacientes/", json={"name": "Maria Santos"})
    resp = auth_client.get("/api/pacientes/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(p["name"] == "Maria Santos" for p in data)


def test_obter_paciente(auth_client):
    """GET /api/pacientes/{id} deve retornar um paciente específico."""
    create = auth_client.post("/api/pacientes/", json={"name": "Carlos Souza"})
    pid = create.json()["id"]
    resp = auth_client.get(f"/api/pacientes/{pid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Carlos Souza"


def test_obter_paciente_inexistente(auth_client):
    """GET /api/pacientes/{id} com ID inexistente deve retornar 404."""
    resp = auth_client.get("/api/pacientes/uuid-inexistente")
    assert resp.status_code == 404


def test_atualizar_paciente(auth_client):
    """PUT /api/pacientes/{id} deve atualizar o paciente."""
    create = auth_client.post("/api/pacientes/", json={"name": "Pedro Lima"})
    pid = create.json()["id"]
    resp = auth_client.put(f"/api/pacientes/{pid}", json={"name": "Pedro Lima Jr"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Pedro Lima Jr"


def test_campos_acompanhamento_caps(auth_client):
    """Técnicos de referência, psiquiatra e situação são opcionais e editáveis."""
    create = auth_client.post("/api/pacientes/", json={
        "name": "Lucia Ramos",
        "reference_technicians": "Ana e Bruno",
        "psychiatrist": "Dr. Carlos",
        "patient_status": "monitoramento",
        "referred_by": "UBS Centro",
        "referred_to": "Ambulatório de Saúde Mental",
        "referring_technician": "Maria Souza",
        "discharge_technician": "Joana Lima",
    })
    assert create.status_code == 200
    data = create.json()
    assert data["reference_technicians"] == "Ana e Bruno"
    assert data["psychiatrist"] == "Dr. Carlos"
    assert data["patient_status"] == "monitoramento"
    assert data["referred_by"] == "UBS Centro"
    assert data["referred_to"] == "Ambulatório de Saúde Mental"
    assert data["referring_technician"] == "Maria Souza"
    assert data["discharge_technician"] == "Joana Lima"

    resp = auth_client.put(f"/api/pacientes/{data['id']}", json={"patient_status": "investigacao_cid"})
    assert resp.status_code == 200
    assert resp.json()["patient_status"] == "investigacao_cid"

    alta = auth_client.put(f"/api/pacientes/{data['id']}", json={"discharge_technician": "Pedro Alves"})
    assert alta.status_code == 200
    assert alta.json()["discharge_technician"] == "Pedro Alves"

    sem_campos = auth_client.post("/api/pacientes/", json={"name": "Sem Situacao"})
    assert sem_campos.status_code == 200
    assert sem_campos.json()["patient_status"] is None
    assert sem_campos.json()["discharge_technician"] is None


def test_situacao_paciente_invalida_rejeitada(auth_client):
    resp = auth_client.post("/api/pacientes/", json={"name": "X", "patient_status": "alta"})
    assert resp.status_code == 422


def test_deletar_paciente(auth_client):
    """DELETE /api/pacientes/{id} deve excluir o paciente."""
    create = auth_client.post("/api/pacientes/", json={"name": "Ana Costa"})
    pid = create.json()["id"]
    resp = auth_client.delete(f"/api/pacientes/{pid}")
    assert resp.status_code == 200
    resp = auth_client.get(f"/api/pacientes/{pid}")
    assert resp.status_code == 404


def test_criar_paciente_sem_auth(client):
    """POST /api/pacientes/ sem autenticação deve retornar 401."""
    resp = client.post("/api/pacientes/", json={"name": "Teste"})
    assert resp.status_code == 401


def test_cpf_invalido_rejeitado(auth_client):
    """CPF com dígito verificador inválido deve ser rejeitado."""
    resp = auth_client.post("/api/pacientes/", json={
        "name": "Teste CPF",
        "cpf": "11111111111",
    })
    assert resp.status_code == 422


def test_cpf_valido_aceito(auth_client):
    """CPF válido deve ser aceito."""
    resp = auth_client.post("/api/pacientes/", json={
        "name": "Teste CPF Válido",
        "cpf": "52998224725",
    })
    assert resp.status_code == 200
    assert resp.json()["cpf"] == "52998224725"


def test_buscar_municipios_sem_auth(client):
    resp = client.get("/api/pacientes/municipios/buscar?q=sao+paulo")
    assert resp.status_code == 401


def test_buscar_municipios_prioriza_prefixo(auth_client):
    resp = auth_client.get("/api/pacientes/municipios/buscar?q=sao+paulo")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["nome"] == "São Paulo"
    assert data[0]["uf"] == "SP"
    assert data[0]["codigo"] == "355030"


def test_buscar_municipios_filtra_por_uf(auth_client):
    resp = auth_client.get("/api/pacientes/municipios/buscar?q=sao+carlos&uf=SP")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(m["uf"] == "SP" for m in data)


def test_buscar_municipios_ignora_acento_e_caixa(auth_client):
    resp = auth_client.get("/api/pacientes/municipios/buscar?q=SAO CARLOS")
    assert resp.status_code == 200
    nomes = [m["nome"] for m in resp.json()]
    assert "São Carlos" in nomes


def test_buscar_municipios_query_curta_retorna_vazio(auth_client):
    resp = auth_client.get("/api/pacientes/municipios/buscar?q=s")
    assert resp.status_code == 422  # min_length=2


def test_resolver_municipio_por_codigo(auth_client):
    """Pacientes importados via RAAS têm municipality_code mas nunca tiveram
    city/state digitados; esse endpoint resolve o código pro nome/UF."""
    resp = auth_client.get("/api/pacientes/municipios/codigo/354140")
    assert resp.status_code == 200
    data = resp.json()
    assert data["nome"] == "Presidente Prudente"
    assert data["uf"] == "SP"


def test_resolver_municipio_codigo_invalido(auth_client):
    resp = auth_client.get("/api/pacientes/municipios/codigo/000000")
    assert resp.status_code == 404


def test_resolver_municipio_sem_auth(client):
    resp = client.get("/api/pacientes/municipios/codigo/354140")
    assert resp.status_code == 401


def test_cpf_zerado_vale_como_sem_cpf(auth_client):
    """O cadastro abre o CPF com zeros (= sem CPF); zeros não são CPF inválido."""
    resp = auth_client.post("/api/pacientes/", json={"name": "SEM CPF", "cpf": "00000000000"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["cpf"] is None

    pid = auth_client.post("/api/pacientes/", json={"name": "COM CPF", "cpf": "52998224725"}).json()["id"]
    resp = auth_client.put(f"/api/pacientes/{pid}", json={"cpf": None})
    assert resp.status_code == 200 and resp.json()["cpf"] is None


def test_nao_duplica_paciente_com_mesmo_cpf(auth_client):
    """Dois cadastros com o mesmo CPF: o segundo é recusado com 409."""
    base = {"name": "Ana Duplicada", "cpf": "52175364895", "prontuario": "9001"}
    primeiro = auth_client.post("/api/pacientes/", json=base)
    assert primeiro.status_code == 200

    segundo = auth_client.post("/api/pacientes/", json=base)
    assert segundo.status_code == 409
    assert "CPF" in segundo.json()["detail"]

    lista = auth_client.get("/api/pacientes/?search=52175364895").json()
    assert len(lista) == 1


def test_nao_duplica_paciente_com_mesmo_prontuario(auth_client):
    """Prontuário repetido também é barrado, mesmo com nome diferente."""
    auth_client.post("/api/pacientes/", json={"name": "Bruno Um", "prontuario": "9002"})
    resp = auth_client.post("/api/pacientes/", json={"name": "Bruno Dois", "prontuario": "9002"})
    assert resp.status_code == 409
    assert "prontuário" in resp.json()["detail"]


def test_paciente_sem_documento_pode_repetir(auth_client):
    """Sem CPF, CNS e prontuário não há como afirmar duplicidade: permite."""
    primeiro = auth_client.post("/api/pacientes/", json={"name": "Carla Sem Documento"})
    segundo = auth_client.post("/api/pacientes/", json={"name": "Carla Sem Documento"})
    assert primeiro.status_code == 200
    assert segundo.status_code == 200


def test_editar_paciente_nao_acusa_ele_mesmo(auth_client):
    """Salvar a edição mantendo o próprio CPF/prontuário não pode dar 409."""
    criado = auth_client.post("/api/pacientes/", json={
        "name": "Diego Editado", "cpf": "11144477735", "prontuario": "9003",
    })
    pid = criado.json()["id"]
    resp = auth_client.put(f"/api/pacientes/{pid}", json={
        "name": "Diego Editado Jr", "cpf": "11144477735", "prontuario": "9003",
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "Diego Editado Jr"


def test_editar_paciente_para_cpf_de_outro_e_barrado(auth_client):
    """Edição não pode transformar um paciente em cópia de outro."""
    auth_client.post("/api/pacientes/", json={"name": "Elena Base", "cpf": "52998224725"})
    outro = auth_client.post("/api/pacientes/", json={"name": "Fabio Outro", "prontuario": "9004"})
    pid = outro.json()["id"]
    resp = auth_client.put(f"/api/pacientes/{pid}", json={"cpf": "52998224725"})
    assert resp.status_code == 409


def test_cid_e_gravado_em_maiusculas_e_sem_ponto(auth_client):
    """CID-10 é gravado como vai no arquivo RAAS: maiúsculo e sem ponto.
    Em minúsculas o mesmo diagnóstico contaria duas vezes nos relatórios, e com
    ponto sairia cortado na exportação (o campo do layout tem 4 posições)."""
    criado = auth_client.post("/api/pacientes/", json={
        "name": "PACIENTE CID", "cns": "700000000000300",
        "birth_date": "1990-01-01", "gender": "M",
        "cid_main": " z032 ", "cid_associated1": "f84.0", "cid_causes": "X60.0",
    })
    assert criado.status_code == 200, criado.text
    paciente = criado.json()
    assert paciente["cid_main"] == "Z032"
    assert paciente["cid_associated1"] == "F840"
    assert paciente["cid_causes"] == "X600"

    atualizado = auth_client.put(f"/api/pacientes/{paciente['id']}", json={"cid_main": "f20.0"})
    assert atualizado.status_code == 200, atualizado.text
    assert atualizado.json()["cid_main"] == "F200"


def test_cids_fora_do_padrao_sao_corrigidos_na_inicializacao(auth_client, db_session):
    """A varredura do boot acerta o que foi gravado antes da normalização."""
    from database import _padronizar_cids
    from paciente.paciente_model import Paciente

    pid = auth_client.post("/api/pacientes/", json={
        "name": "PACIENTE ANTIGO", "cns": "700000000000301",
        "birth_date": "1990-01-01", "gender": "M", "cid_main": "Z032",
    }).json()["id"]
    # Simula o dado antigo, gravado direto no banco sem passar pelo schema.
    db_session.query(Paciente).filter_by(id=pid).update(
        {"cid_main": "z032", "cid_associated1": "f84.0", "cid_associated2": "F90.0"}
    )
    db_session.commit()

    _padronizar_cids()

    db_session.expire_all()
    corrigido = db_session.query(Paciente).filter_by(id=pid).first()
    assert corrigido.cid_main == "Z032"
    assert corrigido.cid_associated1 == "F840"
    assert corrigido.cid_associated2 == "F900"
