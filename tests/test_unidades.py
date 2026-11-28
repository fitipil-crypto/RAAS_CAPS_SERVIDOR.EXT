"""
Testes da edição servidor: as 7 modalidades de CAPS e o isolamento por unidade.

O que importa aqui é provar que o escopo funciona de verdade. Um sistema
multiunidade que vaza dado de um CAPS para outro é pior que um sistema de um só
CAPS, porque o vazamento é invisível: ninguém percebe que a lista de pacientes
tem gente de outro serviço até alguém reclamar. Por isso os testes de
isolamento cobrem leitura, contagem agregada e exclusão em massa.
"""
import pytest

from paciente.paciente_model import Paciente
from registro.registro_model import Registro
from sistema.escopo import como_unidade, sem_escopo, unidade_ativa
from unidade import modalidades
from unidade.unidade_model import Unidade


# ── Catálogo das modalidades ────────────────────────────────────────────

def test_sao_exatamente_sete_modalidades():
    assert len(modalidades.listar()) == 7
    assert set(modalidades.CODIGOS) == {
        "CAPS_I", "CAPS_II", "CAPS_III", "CAPS_i", "CAPS_AD", "CAPS_AD_III", "CAPS_AD_IV",
    }


def test_toda_modalidade_tem_fundamento_e_porte():
    """Parâmetro sem fundamento legal não dá para conferir depois."""
    for m in modalidades.listar():
        assert m.fundamento, m.codigo
        assert m.populacao_minima and m.populacao_minima > 0, m.codigo


def test_modalidades_de_24_horas_tem_acolhimento_noturno():
    vinte_e_quatro_horas = {"CAPS_III", "CAPS_AD_III", "CAPS_AD_IV"}
    for m in modalidades.listar():
        assert m.funcionamento_24h == (m.codigo in vinte_e_quatro_horas), m.codigo
        if m.funcionamento_24h:
            assert m.acolhimento_noturno, m.codigo


def test_codigo_desconhecido_nao_e_aceito():
    assert not modalidades.valida("CAPS_V")
    assert modalidades.obter("CAPS_V") is None


# ── Avisos de faixa etária ──────────────────────────────────────────────

def test_capsi_avisa_paciente_adulto():
    aviso = modalidades.aviso_faixa_etaria("CAPS_i", 31)
    assert aviso and "31 anos" in aviso and "CAPS i" in aviso


def test_capsi_nao_avisa_adolescente():
    assert modalidades.aviso_faixa_etaria("CAPS_i", 15) is None
    assert modalidades.aviso_faixa_etaria("CAPS_i", 17) is None


def test_demais_modalidades_atendem_todas_as_idades():
    for codigo in ("CAPS_I", "CAPS_II", "CAPS_III", "CAPS_AD", "CAPS_AD_III", "CAPS_AD_IV"):
        assert modalidades.aviso_faixa_etaria(codigo, 70) is None
        assert modalidades.aviso_faixa_etaria(codigo, 8) is None


def test_sem_data_de_nascimento_nao_ha_aviso():
    """Idade desconhecida não é motivo de alarme: o alarme é a data faltando."""
    assert modalidades.aviso_faixa_etaria("CAPS_i", None) is None


# ── Avisos de leitos e porte ────────────────────────────────────────────

def test_leitos_acima_do_previsto_avisam():
    aviso = modalidades.aviso_leitos("CAPS_AD_III", 20)
    assert aviso and "12" in aviso


def test_leitos_abaixo_do_minimo_avisam():
    aviso = modalidades.aviso_leitos("CAPS_AD_III", 3)
    assert aviso and "mínimo" in aviso


def test_leitos_na_faixa_nao_avisam():
    assert modalidades.aviso_leitos("CAPS_AD_III", 10) is None
    assert modalidades.aviso_leitos("CAPS_AD_IV", 15) is None
    assert modalidades.aviso_leitos("CAPS_III", 5) is None


def test_modalidade_sem_acolhimento_avisa_se_tiver_leitos():
    aviso = modalidades.aviso_leitos("CAPS_I", 4)
    assert aviso and "não tem acolhimento noturno" in aviso
    assert modalidades.aviso_leitos("CAPS_I", 0) is None


def test_porte_populacional_abaixo_do_previsto_avisa():
    aviso = modalidades.aviso_porte("CAPS_III", 50_000)
    assert aviso and "200.000" in aviso
    assert modalidades.aviso_porte("CAPS_III", 300_000) is None


# ── Isolamento dos dados entre unidades ─────────────────────────────────

@pytest.fixture
def duas_unidades(db_session):
    """Dois CAPS de modalidades diferentes, cada um com um paciente e um registro."""
    a = Unidade(nome="CAPS II Centro", sigla="CAPS02", modalidade="CAPS_II",
                cnes="1111111", uf_code="35", populacao=120_000)
    b = Unidade(nome="CAPS AD III Leste", sigla="CAPSAD3", modalidade="CAPS_AD_III",
                cnes="2222222", uf_code="35", populacao=400_000, leitos_acolhimento=10)
    db_session.add_all([a, b])
    db_session.commit()

    for unidade, nome in ((a, "Maria da Silva"), (b, "João Pereira")):
        with como_unidade(unidade.id):
            paciente = Paciente(name=nome, birth_date="1990-05-10")
            db_session.add(paciente)
            db_session.commit()
            db_session.add(Registro(
                service_month="2026-11", service_date="2026-11-10",
                patient_id=paciente.id, procedure_id="proc-1", quantity=1,
            ))
            db_session.commit()
    db_session.expire_all()
    return a, b


def test_paciente_nasce_na_unidade_ativa(duas_unidades, db_session):
    """A coluna unidade_id é preenchida sozinha, sem o serviço ter de passá-la."""
    a, _ = duas_unidades
    with como_unidade(a.id):
        pacientes = db_session.query(Paciente).all()
        assert [p.name for p in pacientes] == ["Maria da Silva"]
        assert pacientes[0].unidade_id == a.id


def test_cada_unidade_so_ve_os_seus_pacientes(duas_unidades, db_session):
    a, b = duas_unidades
    with como_unidade(a.id):
        assert [p.name for p in db_session.query(Paciente).all()] == ["Maria da Silva"]
    db_session.expire_all()
    with como_unidade(b.id):
        assert [p.name for p in db_session.query(Paciente).all()] == ["João Pereira"]


def test_visao_geral_ve_todas_as_unidades(duas_unidades, db_session):
    assert unidade_ativa() is None
    nomes = {p.name for p in db_session.query(Paciente).all()}
    assert nomes == {"Maria da Silva", "João Pereira"}


def test_contagem_agregada_respeita_o_escopo(duas_unidades, db_session):
    """O filtro tem de valer também em COUNT: um total errado no painel é um
    erro silencioso, que ninguém confere."""
    from sqlalchemy import func

    a, _ = duas_unidades
    with como_unidade(a.id):
        assert db_session.query(func.count(Paciente.id)).scalar() == 1
        assert db_session.query(func.count(Registro.id)).scalar() == 1
    db_session.expire_all()
    assert db_session.query(func.count(Paciente.id)).scalar() == 2


def test_busca_por_id_de_outra_unidade_nao_encontra(duas_unidades, db_session):
    """Trocar o id na URL não deve abrir a ficha de paciente de outro CAPS."""
    a, b = duas_unidades
    with como_unidade(b.id):
        paciente_de_b = db_session.query(Paciente).first()
    db_session.expire_all()
    with como_unidade(a.id):
        assert db_session.query(Paciente).filter(Paciente.id == paciente_de_b.id).first() is None


def test_exclusao_em_massa_respeita_o_escopo(duas_unidades, db_session):
    """Limpar a competência de um CAPS não pode apagar a dos outros.

    É o caso mais perigoso do escopo: um DELETE não é um SELECT, e um filtro que
    valesse só para leitura deixaria a tela de Excluir Dados apagar o sistema
    todo.
    """
    a, b = duas_unidades
    with como_unidade(a.id):
        apagados = db_session.query(Registro).delete()
        db_session.commit()
        assert apagados == 1

    db_session.expire_all()
    with sem_escopo():
        restantes = db_session.query(Registro).all()
    assert len(restantes) == 1
    assert restantes[0].unidade_id == b.id


def test_update_em_massa_respeita_o_escopo(duas_unidades, db_session):
    a, b = duas_unidades
    with como_unidade(a.id):
        db_session.query(Paciente).update({Paciente.phone: "1133334444"},
                                          synchronize_session=False)
        db_session.commit()
    db_session.expire_all()
    with sem_escopo():
        telefones = {p.unidade_id: p.phone for p in db_session.query(Paciente).all()}
    assert telefones[a.id] == "1133334444"
    assert telefones[b.id] is None


def test_sem_escopo_libera_a_visao_de_todas(duas_unidades, db_session):
    a, _ = duas_unidades
    with como_unidade(a.id), sem_escopo():
        assert db_session.query(Paciente).count() == 2


def test_tabela_de_unidades_nao_e_filtrada(duas_unidades, db_session):
    """Se as unidades fossem filtradas, ninguém conseguiria trocar de unidade."""
    a, _ = duas_unidades
    with como_unidade(a.id):
        assert db_session.query(Unidade).count() == 2


def test_contexto_nao_vaza_ao_sair_do_bloco(duas_unidades):
    a, _ = duas_unidades
    with como_unidade(a.id):
        assert unidade_ativa() == a.id
    assert unidade_ativa() is None


# ── Dados do estabelecimento vêm da unidade ativa ───────────────────────

def test_exportacao_usa_o_cnes_da_unidade_ativa(duas_unidades, db_session):
    """O arquivo RAAS de cada CAPS tem de sair com o CNES daquele CAPS."""
    from config.config_service import ConfigService

    a, b = duas_unidades
    with como_unidade(a.id):
        config = ConfigService.get_config_estabelecimento(db_session)
        assert config["cnes_code"] == "1111111"
        assert config["organ_name"] == "CAPS II Centro"
    with como_unidade(b.id):
        assert ConfigService.obter_valor(db_session, "cnes_code") == "2222222"


def test_campo_vazio_na_unidade_cai_para_a_configuracao_geral(duas_unidades, db_session):
    """A unidade não preenche 'versao': o valor geral continua valendo."""
    from config.config_service import ConfigService

    a, _ = duas_unidades
    a.versao = None
    db_session.commit()
    ConfigService.atualizar_varios(db_session, {"versao": "04.27"})
    with como_unidade(a.id):
        assert ConfigService.obter_valor(db_session, "versao") == "04.27"


# ── Migração de dados sem unidade ───────────────────────────────────────

def test_migracao_atribui_apenas_as_linhas_sem_unidade(duas_unidades, db_session):
    """O caso de quem vem da versão local: linhas antigas sem unidade_id."""
    from unidade.migracao import atribuir, pendentes

    a, b = duas_unidades
    db_session.add(Paciente(name="Paciente Antigo", unidade_id=None))
    db_session.commit()
    db_session.expire_all()

    assert pendentes(["pacientes"])["pacientes"] == 1
    alterados = atribuir(a.id, ["pacientes"])
    assert alterados["pacientes"] == 1
    assert pendentes(["pacientes"])["pacientes"] == 0

    db_session.expire_all()
    with como_unidade(a.id):
        nomes = {p.name for p in db_session.query(Paciente).all()}
    assert nomes == {"Maria da Silva", "Paciente Antigo"}

    # Nada da outra unidade foi tocado.
    db_session.expire_all()
    with como_unidade(b.id):
        assert {p.name for p in db_session.query(Paciente).all()} == {"João Pereira"}


def test_migracao_e_idempotente(duas_unidades, db_session):
    from unidade.migracao import atribuir

    a, _ = duas_unidades
    db_session.add(Paciente(name="Outro Antigo", unidade_id=None))
    db_session.commit()
    assert atribuir(a.id, ["pacientes"])["pacientes"] == 1
    assert atribuir(a.id, ["pacientes"])["pacientes"] == 0


def test_tabelas_com_escopo_nao_incluem_usuarios():
    """Atribuir usuários em massa trancaria o admin em uma unidade."""
    from unidade.migracao import tabelas_com_escopo

    tabelas = tabelas_com_escopo()
    assert "pacientes" in tabelas
    assert "registros_raas" in tabelas
    assert "usuarios" not in tabelas
    assert "configuracoes" not in tabelas
    assert "procedimentos" not in tabelas
    assert "unidades" not in tabelas


# ── API e permissões ────────────────────────────────────────────────────

def test_admin_cria_unidade_pela_api(auth_client):
    resposta = auth_client.post("/api/unidades/", json={
        "nome": "CAPS i Norte", "sigla": "CAPSI", "modalidade": "CAPS_i",
        "cnes": "3333333", "populacao": 200_000,
    })
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["modalidade_nome"] == "CAPS i"
    assert corpo["avisos"] == []


def test_modalidade_invalida_e_recusada(auth_client):
    resposta = auth_client.post("/api/unidades/", json={
        "nome": "CAPS Inventado", "modalidade": "CAPS_X", "cnes": "4444444",
    })
    assert resposta.status_code == 422


def test_cnes_precisa_de_sete_digitos(auth_client):
    resposta = auth_client.post("/api/unidades/", json={
        "nome": "CAPS Teste", "modalidade": "CAPS_I", "cnes": "123",
    })
    assert resposta.status_code == 422


def test_cnes_repetido_e_recusado(auth_client):
    dados = {"nome": "CAPS A", "modalidade": "CAPS_I", "cnes": "5555555"}
    assert auth_client.post("/api/unidades/", json=dados).status_code == 200
    repetida = auth_client.post("/api/unidades/", json={**dados, "nome": "CAPS B"})
    assert repetida.status_code == 400
    assert "CNES" in repetida.json()["detail"]


def test_unidade_criada_com_leitos_demais_vem_com_aviso(auth_client):
    resposta = auth_client.post("/api/unidades/", json={
        "nome": "CAPS AD III Sul", "modalidade": "CAPS_AD_III",
        "cnes": "6666666", "leitos_acolhimento": 30, "populacao": 400_000,
    })
    # Cadastro aceito (não é erro de arquivo), mas com aviso visível.
    assert resposta.status_code == 200
    assert any("12" in aviso for aviso in resposta.json()["avisos"])


def test_as_sete_modalidades_na_api(auth_client):
    resposta = auth_client.get("/api/unidades/modalidades")
    assert resposta.status_code == 200
    assert len(resposta.json()) == 7


def test_desativar_preserva_a_unidade(auth_client):
    criada = auth_client.post("/api/unidades/", json={
        "nome": "CAPS Para Desativar", "modalidade": "CAPS_II", "cnes": "7777777",
    }).json()
    assert auth_client.delete(f"/api/unidades/{criada['id']}").status_code == 200
    depois = auth_client.get(f"/api/unidades/{criada['id']}").json()
    assert depois["ativa"] is False  # continua existindo, só saiu de uso


def test_operador_nao_alcanca_unidade_de_outro_caps(auth_client, db_session):
    """Um operador lotado em um CAPS não entra em outro nem forçando a sessão."""
    unidade_a = auth_client.post("/api/unidades/", json={
        "nome": "CAPS Um", "modalidade": "CAPS_I", "cnes": "8888881",
    }).json()
    unidade_b = auth_client.post("/api/unidades/", json={
        "nome": "CAPS Dois", "modalidade": "CAPS_II", "cnes": "8888882",
    }).json()

    criado = auth_client.post("/api/usuarios/", json={
        "username": "operador1", "name": "Operador Um", "role": "operador",
        "password": "senha123", "unidade_id": unidade_a["id"],
    })
    assert criado.status_code == 200, criado.text
    assert criado.json()["unidade_id"] == unidade_a["id"]

    from fastapi.testclient import TestClient
    from main import app
    from usuario.usuario_service import UsuarioService

    # Senha definida por admin exige troca no primeiro acesso; aqui interessa só
    # o escopo, então a exigência é removida direto no banco.
    usuario = UsuarioService.obter_por_username(db_session, "operador1")
    usuario.must_change_password = False
    db_session.commit()

    with TestClient(app) as cliente:
        cliente.post("/login", data={"username": "operador1", "password": "senha123"})
        recusado = cliente.post(f"/api/unidades/ativa/{unidade_b['id']}")
        assert recusado.status_code == 403
        # Nem a visão "todas as unidades".
        assert cliente.post("/api/unidades/ativa/todas").status_code == 403
        ativa = cliente.get("/api/unidades/ativa")
        assert ativa.json()["unidade_id"] == unidade_a["id"]


def test_coordenador_precisa_de_unidade_quando_ha_varias(auth_client):
    auth_client.post("/api/unidades/", json={
        "nome": "CAPS Alfa", "modalidade": "CAPS_I", "cnes": "9999991"})
    auth_client.post("/api/unidades/", json={
        "nome": "CAPS Beta", "modalidade": "CAPS_II", "cnes": "9999992"})

    recusado = auth_client.post("/api/usuarios/", json={
        "username": "coord1", "name": "Coordenador", "role": "coordenador",
        "password": "senha123",
    })
    assert recusado.status_code == 400
    assert "unidade" in recusado.json()["detail"].lower()


def test_com_uma_unidade_a_lotacao_e_automatica(auth_client, db_session):
    """Num CAPS só, ninguém deve ter de escolher a unidade."""
    from unidade.unidade_service import UnidadeService

    unidades = UnidadeService.listar(db_session, apenas_ativas=True)
    assert len(unidades) == 1  # criada no boot a partir das Configurações

    criado = auth_client.post("/api/usuarios/", json={
        "username": "operador2", "name": "Operador Dois", "role": "operador",
        "password": "senha123",
    })
    assert criado.status_code == 200, criado.text
    assert criado.json()["unidade_id"] == unidades[0].id


def test_perfil_inexistente_e_recusado(auth_client):
    resposta = auth_client.post("/api/usuarios/", json={
        "username": "qualquer", "name": "Qualquer", "role": "diretor",
        "password": "senha123",
    })
    assert resposta.status_code == 422


def test_gestor_circula_por_todas_as_unidades(auth_client):
    criado = auth_client.post("/api/usuarios/", json={
        "username": "gestor1", "name": "Gestor Rede", "role": "gestor",
        "password": "senha123",
    })
    assert criado.status_code == 200, criado.text
    assert criado.json()["unidade_id"] is None


# ── Unidade ao entrar no sistema ────────────────────────────────────────

@pytest.fixture
def unidades_para_login(auth_client):
    criar = lambda nome, cnes: auth_client.post("/api/unidades/", json={  # noqa: E731
        "nome": nome, "modalidade": "CAPS_II", "cnes": cnes}).json()
    return criar("CAPS Norte", "7777771"), criar("CAPS Sul", "7777772")


def _criar_usuario(auth_client, db_session, username, role, unidade_id=None):
    """Cria o usuário pela API e dispensa a troca de senha do primeiro acesso."""
    from usuario.usuario_service import UsuarioService

    corpo = {"username": username, "name": username, "role": role, "password": "senha123"}
    if unidade_id:
        corpo["unidade_id"] = unidade_id
    criado = auth_client.post("/api/usuarios/", json=corpo)
    assert criado.status_code == 200, criado.text
    usuario = UsuarioService.obter_por_username(db_session, username)
    usuario.must_change_password = False
    db_session.commit()


def _unidade_ativa_apos_login(username):
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as cliente:
        cliente.post("/login", data={"username": username, "password": "senha123"})
        return cliente.get("/api/unidades/ativa").json()["unidade_id"]


@pytest.mark.parametrize("perfil", ["operador", "coordenador", "gestor", "admin"])
def test_login_entra_na_unidade_da_lotacao(auth_client, db_session, unidades_para_login, perfil):
    _, sul = unidades_para_login
    _criar_usuario(auth_client, db_session, f"lotado_{perfil}", perfil, sul["id"])
    ativa = _unidade_ativa_apos_login(f"lotado_{perfil}")
    assert ativa == sul["id"]


def test_gestor_sem_lotacao_entra_em_todas_as_unidades(auth_client, db_session, unidades_para_login):
    _criar_usuario(auth_client, db_session, "gestor_rede", "gestor")
    ativa = _unidade_ativa_apos_login("gestor_rede")
    assert ativa is None


def test_gestor_lotado_ainda_pode_trocar_de_unidade(auth_client, db_session, unidades_para_login):
    """A lotação é só o ponto de partida para quem circula por todas."""
    from fastapi.testclient import TestClient
    from main import app

    norte, sul = unidades_para_login
    _criar_usuario(auth_client, db_session, "gestor_sul", "gestor", sul["id"])
    with TestClient(app) as cliente:
        cliente.post("/login", data={"username": "gestor_sul", "password": "senha123"})
        assert cliente.get("/api/unidades/ativa").json()["unidade_id"] == sul["id"]
        assert cliente.post(f"/api/unidades/ativa/{norte['id']}").status_code == 200
        assert cliente.get("/api/unidades/ativa").json()["unidade_id"] == norte["id"]
        assert cliente.post("/api/unidades/ativa/todas").status_code == 200
        assert cliente.get("/api/unidades/ativa").json()["unidade_id"] is None


def test_gestor_lotado_em_unidade_desativada_entra_em_todas(auth_client, db_session, unidades_para_login):
    _, sul = unidades_para_login
    _criar_usuario(auth_client, db_session, "gestor_x", "gestor", sul["id"])
    assert auth_client.delete(f"/api/unidades/{sul['id']}").status_code == 200
    ativa = _unidade_ativa_apos_login("gestor_x")
    assert ativa is None


# ── Restauração de backup ───────────────────────────────────────────────

@pytest.fixture
def caps_i_e_caps_ad(db_session):
    """Dois CAPS com um paciente e um registro cada, e um procedimento no catálogo."""
    from procedimento.procedimento_model import Procedimento

    caps_i = Unidade(nome="CAPS I Restauro", modalidade="CAPS_I", cnes="1010101")
    caps_ad = Unidade(nome="CAPS AD Restauro", modalidade="CAPS_AD", cnes="1010103")
    proc = Procedimento(code="03.01.08.002-0", name="ACOLHIMENTO")
    db_session.add_all([caps_i, caps_ad, proc])
    db_session.commit()
    for unidade, nome in ((caps_i, "ANTIGO DO CAPS I"), (caps_ad, "PACIENTE DO CAPS AD")):
        with como_unidade(unidade.id):
            pac = Paciente(name=nome)
            db_session.add(pac)
            db_session.commit()
            db_session.add(Registro(service_month="2026-01", service_date="2026-01-10",
                                    patient_id=pac.id, procedure_id=proc.id))
            db_session.commit()
    return caps_i, caps_ad, proc


def _backup_de_um_caps(**extra):
    """Backup como o da versão local de um CAPS só (sem unidade_id)."""
    return {
        "config": {"organ_name": "NAO DEVE MUDAR"},
        "patients": [{"id": "p-antigo", "name": "RESTAURADO"}],
        "professionals": [{"id": "f-antigo", "name": "PROFISSIONAL RESTAURADO"}],
        "procedures": [
            {"id": "x-acolhimento", "code": "0301080020", "name": "ACOLHIMENTO"},
            {"id": "x-novo", "code": "0301080399", "name": "PROCEDIMENTO NOVO"},
        ],
        "records": [
            {"service_month": "2026-02", "service_date": "2026-02-05", "patient_id": "p-antigo",
             "professional_id": "f-antigo", "procedure_id": "x-acolhimento"},
            {"service_month": "2026-02", "service_date": "2026-02-06", "patient_id": "p-antigo",
             "professional_id": "f-antigo", "procedure_id": "x-novo"},
        ],
        **extra,
    }


def test_restauracao_na_unidade_substitui_so_os_dados_dela(db_session, caps_i_e_caps_ad, monkeypatch):
    """Quem trabalha num CAPS restaura o backup dele sem apagar os outros."""
    from backup.backup_service import BackupService
    from config.config_service import ConfigService
    from procedimento.procedimento_model import Procedimento

    caps_i, caps_ad, proc = caps_i_e_caps_ad

    def _proibido(*a, **k):
        raise AssertionError("configurações gerais não podem mudar na restauração por unidade")

    monkeypatch.setattr(ConfigService, "atualizar_varios", _proibido)

    with como_unidade(caps_i.id):
        resultado = BackupService.restaurar_backup(db_session, _backup_de_um_caps())
    assert resultado["success"] is True

    with sem_escopo():
        pacientes = {p.name: p.unidade_id for p in db_session.query(Paciente).all()}
        registros = db_session.query(Registro).all()
        catalogo = {p.code: p.id for p in db_session.query(Procedimento).all()}

    # O CAPS AD ficou intacto; o paciente antigo do CAPS I foi substituído.
    assert pacientes == {"PACIENTE DO CAPS AD": caps_ad.id, "RESTAURADO": caps_i.id}
    assert sorted(r.unidade_id for r in registros) == sorted([caps_ad.id, caps_i.id, caps_i.id])

    # Catálogo: o procedimento existente foi reaproveitado pelo código (com ou
    # sem pontuação) e só o que faltava foi criado.
    assert set(catalogo) == {"03.01.08.002-0", "0301080399"}
    do_caps_i = {r.procedure_id for r in registros if r.unidade_id == caps_i.id}
    assert do_caps_i == {proc.id, catalogo["0301080399"]}


def test_restauracao_recusa_backup_de_outra_unidade(db_session, caps_i_e_caps_ad):
    from backup.backup_service import BackupInvalidoError, BackupService

    caps_i, caps_ad, _ = caps_i_e_caps_ad
    with como_unidade(caps_i.id):
        with pytest.raises(BackupInvalidoError, match="outra unidade"):
            BackupService.restaurar_backup(db_session, _backup_de_um_caps(unidade_id=caps_ad.id))
    with sem_escopo():
        assert db_session.query(Paciente).count() == 2  # nada foi apagado


def test_restauracao_aceita_backup_da_propria_unidade(db_session, caps_i_e_caps_ad):
    from backup.backup_service import BackupService

    caps_i, _, _ = caps_i_e_caps_ad
    with como_unidade(caps_i.id):
        backup = BackupService.criar_backup(db_session)
        assert backup["unidade_id"] == caps_i.id
        BackupService.restaurar_backup(db_session, backup)
        assert [p.name for p in db_session.query(Paciente).all()] == ["ANTIGO DO CAPS I"]


def test_restauracao_em_todas_as_unidades_substitui_o_banco(db_session, caps_i_e_caps_ad):
    from backup.backup_service import BackupService
    from procedimento.procedimento_model import Procedimento

    BackupService.restaurar_backup(db_session, _backup_de_um_caps(config=None))
    with sem_escopo():
        assert [p.name for p in db_session.query(Paciente).all()] == ["RESTAURADO"]
        assert db_session.query(Procedimento).count() == 2


def test_backup_registra_de_que_unidade_e(db_session):
    from backup.backup_service import BackupService

    unidade = Unidade(nome="CAPS Backup", modalidade="CAPS_I", cnes="1010102")
    db_session.add(unidade)
    db_session.commit()

    with como_unidade(unidade.id):
        dados = BackupService.criar_backup(db_session)
    assert dados["unidade_id"] == unidade.id
    assert dados["escopo"] == "unidade"

    geral = BackupService.criar_backup(db_session)
    assert geral["unidade_id"] is None
    assert geral["escopo"] == "todas as unidades"


# ── Auditoria de competência por modalidade ─────────────────────────────

def test_auditoria_avisa_adulto_em_capsi(db_session):
    from competencia.auditoria_service import AuditoriaService

    unidade = Unidade(nome="CAPS i Teste", modalidade="CAPS_i", cnes="2020202",
                      uf_code="35", populacao=200_000)
    db_session.add(unidade)
    db_session.commit()

    with como_unidade(unidade.id):
        paciente = Paciente(name="Adulto Em Capsi", birth_date="1980-01-01",
                            cns="700000000000000")
        db_session.add(paciente)
        db_session.commit()
        db_session.add(Registro(service_month="2026-11", service_date="2026-11-10",
                                patient_id=paciente.id, procedure_id="p1", quantity=1))
        db_session.commit()

        resultado = AuditoriaService.auditar(db_session, "2026-11")

    achados = {a.codigo: a for a in resultado["achados"]}
    assert "M04" in achados
    # Aviso de modalidade não impede a exportação do arquivo.
    assert achados["M04"].gravidade == "alerta"


def test_auditoria_avisa_visao_geral_com_varias_unidades(db_session):
    from competencia.auditoria_service import AuditoriaService

    a = Unidade(nome="CAPS Geral A", modalidade="CAPS_I", cnes="3030301")
    b = Unidade(nome="CAPS Geral B", modalidade="CAPS_II", cnes="3030302")
    db_session.add_all([a, b])
    db_session.commit()

    # A auditoria precisa de atendimentos na competência: sem eles ela para
    # antes, em C01 ("não há atendimentos lançados").
    with como_unidade(a.id):
        paciente = Paciente(name="Paciente Geral", birth_date="1985-03-03",
                            cns="700000000000000")
        db_session.add(paciente)
        db_session.commit()
        db_session.add(Registro(service_month="2026-11", service_date="2026-11-10",
                                patient_id=paciente.id, procedure_id="p1", quantity=1))
        db_session.commit()

    db_session.expire_all()
    assert unidade_ativa() is None
    resultado = AuditoriaService.auditar(db_session, "2026-11")
    assert "M00" in {achado.codigo for achado in resultado["achados"]}


# ── Checagem de saúde ───────────────────────────────────────────────────

def test_endpoint_de_saude_confere_o_banco(client):
    resposta = client.get("/saude")
    assert resposta.status_code == 200
    assert resposta.json()["banco"] == "ok"
