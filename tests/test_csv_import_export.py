"""
Testes dos utilitários de CSV usados na importação/exportação de cadastros.
"""
import pytest

from sistema.csv_import_export import build_csv, normalize_bool, normalize_sn, parse_csv


def test_build_csv_tem_bom_cabecalho_e_ponto_e_virgula():
    csv = build_csv(
        [{"name": "ANA", "cns": "700"}, {"name": "BIA", "cns": None}],
        columns=["name", "cns"],
        headers=["Nome", "CNS"],
    )
    assert csv.startswith("﻿")
    linhas = csv.lstrip("﻿").splitlines()
    assert linhas == ["Nome;CNS", "ANA;700", "BIA;"]


def test_build_csv_protege_valor_com_separador():
    csv = build_csv([{"name": "SILVA; JOAO"}], columns=["name"], headers=["Nome"])
    assert '"SILVA; JOAO"' in csv


def test_ida_e_volta_preserva_os_dados():
    original = [{"Nome": "JOSÉ", "CNS": "700"}, {"Nome": "MARIA", "CNS": "701"}]
    csv = build_csv(
        [{"n": r["Nome"], "c": r["CNS"]} for r in original],
        columns=["n", "c"], headers=["Nome", "CNS"],
    )
    assert parse_csv(csv.encode("utf-8")) == original


def test_parse_csv_ignora_linhas_vazias():
    conteudo = "Nome;CNS\nANA;700\n;\nBIA;701\n".encode("utf-8")
    assert [r["Nome"] for r in parse_csv(conteudo)] == ["ANA", "BIA"]


def test_parse_csv_nao_quebra_com_bytes_invalidos():
    conteudo = "Nome\nJOS\xc9\n".encode("latin-1")
    linhas = parse_csv(conteudo)
    assert len(linhas) == 1 and linhas[0]["Nome"].startswith("JOS")


@pytest.mark.parametrize("valor, esperado", [
    (None, True), ("sim", True), ("1", True), ("qualquer", True),
    ("false", False), ("F", False), ("Não", False), ("nao", False),
    ("n", False), ("0", False), ("no", False), ("", False), ("  ", False),
])
def test_normalize_bool(valor, esperado):
    assert normalize_bool(valor) is esperado


@pytest.mark.parametrize("valor, esperado", [
    (None, "N"), ("Sim", "S"), ("s", "S"), ("YES", "S"), ("true", "S"), ("1", "S"),
    ("não", "N"), ("", "N"), ("talvez", "N"),
])
def test_normalize_sn(valor, esperado):
    assert normalize_sn(valor) == esperado
