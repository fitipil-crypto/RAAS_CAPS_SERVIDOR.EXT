"""
Testes do Relatórios Impressão (lista de pacientes e exportações).
"""
import io
from datetime import date

from relatorio.impressao_service import idade_anos_meses


def _criar_pacientes(client):
    client.post("/api/pacientes/", json={
        "name": "Bruna Teste", "cns": "700000000000001", "prontuario": "1292",
        "birth_date": "2015-08-12", "admission_date": "2024-03-13", "race": "03",
        "neighborhood": "Jardim Maracanã", "cid_main": "F84.0", "cid_associated1": "F90.0",
        "psychiatrist": "Drª Stephanie", "reference_technicians": "Thaís",
        "referred_by": "Hospital Regional", "patient_status": "ativo",
        "referred_to": "CAPS AD", "referring_technician": "Marcos",
        "discharge_technician": "Joana Lima",
    })
    client.post("/api/pacientes/", json={
        "name": "Ana Teste", "psychiatrist": "Drª Camila", "patient_status": "monitoramento",
    })


def test_idade_anos_meses():
    assert idade_anos_meses("2015-08-12", date(2026, 10, 22)) == "11 a 2 m"
    assert idade_anos_meses("2015-10-23", date(2026, 10, 22)) == "10 a 11 m"
    assert idade_anos_meses(None) == ""


def test_pagina_lista_pacientes_com_filtros(auth_client):
    _criar_pacientes(auth_client)
    resp = auth_client.get("/relatorios-impressao")
    assert resp.status_code == 200
    html = resp.text
    assert "Relatórios Impressão" in html
    assert 'class="sidebar collapsed"' in html  # menu abre recolhido
    assert "page-content-larga" in html  # tabela usa a largura toda
    assert 'class="sidebar collapsed"' not in auth_client.get("/pacientes").text
    assert "Bruna Teste" in html and "Ana Teste" in html
    assert html.index("Ana Teste") < html.index("Bruna Teste")
    assert "PARDA" in html and "Hospital Regional" in html
    assert "color:#0099CC" in html  # CID de TEA em azul

    filtrado = auth_client.get("/relatorios-impressao", params={"medico": "Drª Camila"}).text
    assert "Ana Teste" in filtrado and "Bruna Teste" not in filtrado

    filtrado = auth_client.get("/relatorios-impressao", params={"situacao": "ativo"}).text
    assert "Bruna Teste" in filtrado and "Ana Teste" not in filtrado


def test_pagina_relatorio_pacientes_reutilizavel(auth_client):
    _criar_pacientes(auth_client)
    resp = auth_client.get("/relatorios/pacientes")
    assert resp.status_code == 200
    assert "Relatório de Pacientes" in resp.text
    assert "this.form.target" in resp.text and "'_blank'" in resp.text
    assert 'formaction="/api/relatorios/impressao/exportar"' in resp.text
    assert 'name="formato"' in resp.text
    assert ">PDF</option>" in resp.text and ">CSV</option>" in resp.text and ">TXT</option>" in resp.text
    assert "2 paciente(s)" in resp.text
    assert "Bruna Teste" not in resp.text and "Ana Teste" not in resp.text


def test_relatorios_operacionais_e_pdf(auth_client):
    _criar_pacientes(auth_client)
    chaves = ["atendimentos", "producao", "perfil", "busca-ativa", "incompletos"]
    pagina = auth_client.get("/relatorios/operacionais/perfil")
    assert pagina.status_code == 200
    assert "this.form.target" in pagina.text and "'_blank'" in pagina.text
    for chave in chaves:

        pdf = auth_client.get("/api/relatorios/operacional/exportar", params={
            "relatorio": chave, "formato": "pdf",
        })
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")
        assert "inline" in pdf.headers["content-disposition"]


def test_exportar_csv(auth_client):
    _criar_pacientes(auth_client)
    resp = auth_client.get("/api/relatorios/impressao/exportar", params={"formato": "csv", "tecnico": "thaís"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    texto = resp.content.decode("utf-8-sig")
    # Campos do Acompanhamento ficam juntos, sempre no fim do relatório.
    assert texto.splitlines()[0].startswith("Nº;Paciente;CNS;CPF")
    assert texto.splitlines()[0].endswith(";Bairro;TRS;Drª;Situação;Encam. por")
    assert "Bruna Teste" in texto and "Ana Teste" not in texto


def test_exportar_campos_dados_do_atendimento(auth_client):
    _criar_pacientes(auth_client)
    resp = auth_client.get("/api/relatorios/impressao/exportar", params={
        "formato": "csv", "campos_enviados": "1", "situacao": "ativo",
        "campo": ["encaminhado", "encaminhado_para", "tecnico_encaminhou"],
    })
    linhas = resp.content.decode("utf-8-sig").splitlines()
    assert linhas[0] == "Nº;Paciente;Encam. por;Encam. p/ trat. em;Téc. que encam."
    assert "Bruna Teste;Hospital Regional;CAPS AD;Marcos" in linhas[1]


def test_exportar_coluna_do_tecnico_que_deu_alta(auth_client):
    _criar_pacientes(auth_client)
    resp = auth_client.get("/api/relatorios/impressao/exportar", params={
        "formato": "csv", "campos_enviados": "1", "situacao": "ativo",
        "campo": ["tecnico_alta"],
    })
    linhas = resp.content.decode("utf-8-sig").splitlines()
    assert linhas[0] == "Nº;Paciente;Téc. que deu alta"
    assert any(l.endswith(";Joana Lima") for l in linhas[1:])


def test_exportar_txt(auth_client):
    _criar_pacientes(auth_client)
    resp = auth_client.get("/api/relatorios/impressao/exportar", params={"formato": "txt"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.headers["content-disposition"].endswith('.txt"')
    assert b"Paciente" in resp.content


def test_exportar_excel(auth_client):
    from openpyxl import load_workbook

    _criar_pacientes(auth_client)
    resp = auth_client.get("/api/relatorios/impressao/exportar", params={"formato": "excel"})
    assert resp.status_code == 200
    ws = load_workbook(io.BytesIO(resp.content)).active
    assert ws.cell(row=2, column=2).value == "Paciente"
    assert ws.cell(row=2, column=2).fill.fgColor.rgb.endswith("C4D79B")
    nomes = [ws.cell(row=r, column=2).value for r in range(4, ws.max_row + 1)]
    assert nomes == ["Ana Teste", "Bruna Teste"]


def test_exportar_pdf(auth_client):
    _criar_pacientes(auth_client)
    resp = auth_client.get("/api/relatorios/impressao/exportar", params={"formato": "pdf"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "inline" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")


def test_pdf_mostra_campos_selecionados(auth_client, monkeypatch):
    from relatorio.impressao_service import ImpressaoService

    enviados = {}
    gerar_original = ImpressaoService.gerar_pdf

    def capturar(blocos, *args, **kwargs):
        enviados["blocos"] = blocos
        return gerar_original(blocos, *args, **kwargs)

    monkeypatch.setattr(ImpressaoService, "gerar_pdf", staticmethod(capturar))
    _criar_pacientes(auth_client)
    campos = ["medico", "trs", "situacao", "encaminhado", "encaminhado_para", "tecnico_encaminhou", "qtd_atend"]
    resp = auth_client.get("/api/relatorios/impressao/exportar", params={
        "formato": "pdf", "campos_enviados": "1", "campo": campos, "situacao": "ativo",
    })
    assert resp.content.startswith(b"%PDF")
    bloco = enviados["blocos"][0]
    assert [c.chave for c in bloco.colunas] == [
        "n", "nome", "qtd_atend", "trs", "medico", "situacao", "encaminhado", "encaminhado_para", "tecnico_encaminhou"]
    linha = " ".join(str(v.get("v") if isinstance(v, dict) else v) for v in bloco.linhas[0])
    for valor in ("Stephanie", "Thaís", "Ativo", "Hospital Regional", "CAPS AD", "Marcos"):
        assert valor in linha


def test_formato_invalido(auth_client):
    resp = auth_client.get("/api/relatorios/impressao/exportar", params={"formato": "doc"})
    assert resp.status_code == 400


def test_operador_nao_acessa(client, db_session):
    from usuario.usuario_service import UsuarioService
    from usuario.usuario_schema import UsuarioCriar

    UsuarioService.criar(db_session, UsuarioCriar(
        username="operador_imp", password="senha12345", name="OPERADOR", role="operador",
    ))
    client.post("/login", data={"username": "operador_imp", "password": "senha12345"})
    assert client.get("/api/relatorios/impressao/exportar", params={"formato": "csv"}).status_code == 403
    resp = client.get("/relatorios-impressao", follow_redirects=False)
    assert resp.status_code == 302


def test_escolha_de_campos_vale_para_tela_e_exportacao(auth_client):
    _criar_pacientes(auth_client)
    params = {"campos_enviados": "1", "campo": ["cns", "bairro", "qtd_atend"]}
    html = auth_client.get("/relatorios-impressao", params=params).text
    assert "<th>Bairro</th>" in html and "<th>Atendimentos</th>" in html
    assert "<th>Drª</th>" not in html

    texto = auth_client.get("/api/relatorios/impressao/exportar",
                            params={"formato": "csv", **params}).content.decode("utf-8-sig")
    # O nome sempre entra, e os campos seguem a ordem do catálogo.
    assert texto.splitlines()[0] == "Nº;Paciente;CNS;Bairro;Atendimentos"

    # A escolha fica lembrada para a próxima visita.
    html = auth_client.get("/relatorios-impressao").text
    assert "<th>Bairro</th>" in html and "<th>Drª</th>" not in html


def test_filtros_detalhados_e_ordenacao(auth_client):
    _criar_pacientes(auth_client)
    auth_client.post("/api/pacientes/", json={
        "name": "Caio Teste", "gender": "M", "birth_date": "1990-01-01", "cid_main": "F20.0",
        "neighborhood": "Vila Real",
    })

    def nomes(**params):
        texto = auth_client.get("/api/relatorios/impressao/exportar",
                                params={"formato": "csv", **params}).content.decode("utf-8-sig")
        return [l.split(";")[1] for l in texto.splitlines()[1:]]

    assert nomes(sexo="M") == ["Caio Teste"]
    assert nomes(cid="f84") == ["Bruna Teste"]
    assert nomes(idade_min="18") == ["Caio Teste"]
    assert nomes(idade_max="17") == ["Bruna Teste"]
    assert nomes(bairro="maracan") == ["Bruna Teste"]
    assert nomes(admissao_de="2024-01-01", admissao_ate="2024-12-31") == ["Bruna Teste"]
    assert nomes(ordenar="bairro") == ["Bruna Teste", "Caio Teste", "Ana Teste"]


def test_indicadores_tela_e_exportacoes(auth_client):
    from openpyxl import load_workbook

    params = {"tipo": "indicadores", "mes": "2026-09", "secoes_enviadas": "1", "secao": ["resumo", "genero"]}
    html = auth_client.get("/relatorios-impressao", params=params).text
    assert "Resumo" in html and "Distribuição por Gênero" in html
    assert "Top 10 Profissionais" not in html.split('class="rimp-folha')[1]
    assert "Set/2026" in html

    texto = auth_client.get("/api/relatorios/impressao/exportar",
                            params={"formato": "csv", **params}).content.decode("utf-8-sig")
    assert texto.splitlines()[0] == "Resumo"
    assert "Distribuição por Gênero" in texto

    xlsx = auth_client.get("/api/relatorios/impressao/exportar", params={"formato": "excel", **params})
    assert load_workbook(io.BytesIO(xlsx.content)).sheetnames == ["Resumo", "Distribuição por Gênero"]

    pdf = auth_client.get("/api/relatorios/impressao/exportar", params={"formato": "pdf", "tipo": "indicadores"})
    assert pdf.content.startswith(b"%PDF")


def test_indicadores_tem_atalho_para_impressao(auth_client):
    html = auth_client.get("/indicadores?month=2026-09").text
    assert "/relatorios-impressao?tipo=indicadores&mes=2026-09" in html


def test_relatorios_incorporado_aos_indicadores(auth_client):
    resp = auth_client.get("/relatorios?month=2026-09", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/indicadores?month=2026-09"
    assert auth_client.get("/relatorios", follow_redirects=False).headers["location"] == "/indicadores"

    html = auth_client.get("/indicadores?month=2026-09").text
    for secao in ("Comparativo mês a mês", "Profissionais com mais atendimentos",
                  "Atendimentos por dia da semana", "Individual × Grupo por profissional",
                  "Novos pacientes", "Total cadastrados"):
        assert secao in html


def test_impressao_indicadores_de_cuidado(auth_client):
    params = {"tipo": "indicadores", "mes": "2026-09", "secoes_enviadas": "1", "secao": ["cuidado"]}
    texto = auth_client.get("/api/relatorios/impressao/exportar",
                            params={"formato": "csv", **params}).content.decode("utf-8-sig")
    assert "Indicador;Valor" in texto and "Sem atendimento no mês (busca ativa)" in texto


def test_relatorios_operacionais_viraram_abas(auth_client):
    _criar_pacientes(auth_client)
    for chave in ("atendimentos", "producao", "busca-ativa", "incompletos"):
        resp = auth_client.get(f"/relatorios/operacionais/{chave}?bairro=Centro", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == f"/relatorios-impressao?tipo={chave}&bairro=Centro"

        html = auth_client.get("/relatorios-impressao", params={"tipo": chave}).text
        assert f'href="/relatorios-impressao?tipo={chave}" class="active"' in html
        for outra in ("atendimentos", "producao", "busca-ativa", "incompletos"):
            assert f"/relatorios-impressao?tipo={outra}" in html

        for formato in ("csv", "excel", "pdf"):
            exp = auth_client.get("/api/relatorios/impressao/exportar", params={"tipo": chave, "formato": formato})
            assert exp.status_code == 200

    # Filtros das abas valem para a tela e para a exportação.
    html = auth_client.get("/relatorios-impressao", params={"tipo": "incompletos", "faltando": "psiquiatra"}).text
    assert "Ana Teste" not in html and "Bruna Teste" not in html
    texto = auth_client.get("/api/relatorios/impressao/exportar", params={
        "tipo": "incompletos", "faltando": "cns", "formato": "csv",
    }).content.decode("utf-8-sig")
    assert "Ana Teste" in texto and "Bruna Teste" not in texto

    menu = auth_client.get("/registros").text
    for chave in ("atendimentos", "producao", "busca-ativa", "incompletos"):
        assert f'href="/relatorios/operacionais/{chave}"' not in menu
