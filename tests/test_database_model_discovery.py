from sqlalchemy import inspect

import database
from database import Base, engine


def test_novo_modelo_e_descoberto_e_criado_automaticamente(tmp_path, monkeypatch):
    package_dir = tmp_path / "modulo_novo"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "nova_tabela_model.py").write_text(
        "from sqlalchemy import Column, Integer\n"
        "from database import Base\n\n"
        "class NovaTabela(Base):\n"
        "    __tablename__ = 'teste_tabela_descoberta'\n"
        "    id = Column(Integer, primary_key=True)\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    model_modules = database._descobrir_modelos(tmp_path)
    assert model_modules == ["modulo_novo.nova_tabela_model"]
    monkeypatch.setattr(database, "_descobrir_modelos", lambda _: model_modules)

    database.criar_tabelas()
    database.criar_tabelas()

    assert "teste_tabela_descoberta" in Base.metadata.tables
    assert "teste_tabela_descoberta" in inspect(engine).get_table_names()
