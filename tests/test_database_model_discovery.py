import database


def test_novo_modelo_e_descoberto(tmp_path):
    """Todo *_model.py de um pacote é encontrado e importado: é assim que o
    Alembic (migrations/env.py) e o criar_tabelas enxergam os modelos.

    A tabela de um modelo novo não é mais criada sozinha: ela entra por uma
    migração (ver tests/test_migracoes.py)."""
    package_dir = tmp_path / "modulo_novo"
    sub_dir = package_dir / "sub"
    sub_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "nova_tabela_model.py").write_text("", encoding="utf-8")
    (sub_dir / "outra_model.py").write_text("", encoding="utf-8")
    (package_dir / "servico.py").write_text("", encoding="utf-8")
    # Pasta sem __init__.py (como migrations/) e pasta oculta ficam de fora.
    (tmp_path / "sem_pacote").mkdir()
    (tmp_path / "sem_pacote" / "x_model.py").write_text("", encoding="utf-8")
    (tmp_path / ".oculto").mkdir()
    (tmp_path / ".oculto" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / ".oculto" / "y_model.py").write_text("", encoding="utf-8")

    assert database._descobrir_modelos(tmp_path) == [
        "modulo_novo.nova_tabela_model",
        "modulo_novo.sub.outra_model",
    ]
