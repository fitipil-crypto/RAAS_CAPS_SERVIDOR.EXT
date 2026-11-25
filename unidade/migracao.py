"""
Atribui a uma unidade os dados que ainda não têm unidade (``unidade_id`` nulo).

Para que serve
--------------
Um banco que vem da versão local de um único CAPS tem todas as linhas sem
``unidade_id``. Depois que o escopo entra em vigor, linha sem unidade não
aparece para quem está com uma unidade selecionada — e é exatamente o que
acontece no primeiro acesso ao servidor. Esta rotina fecha essa lacuna.

Uso::

    python -m unidade.migracao --listar
    python -m unidade.migracao --unidade <id-da-unidade>
    python -m unidade.migracao --unidade <id> --tabela pacientes --tabela registros_raas

É idempotente: roda sobre ``unidade_id IS NULL``, então repetir não mexe no que
já foi atribuído, e dados de outra unidade nunca são tocados.
"""
import argparse
import sys

from sqlalchemy import text

from database import SessionLocal, engine
from sistema.escopo import sem_escopo


def tabelas_com_escopo() -> list[str]:
    """Tabelas que têm a coluna ``unidade_id`` vinda do mixin EscopoUnidade.

    A tabela ``usuarios`` também tem ``unidade_id``, mas é lotação do usuário e
    não dado assistencial: atribuí-la em massa trancaria o admin em uma unidade.
    Por isso a lista sai dos modelos que herdam o mixin, e não de quem tem a
    coluna.
    """
    from database import Base, _importar_modelos
    from sistema.escopo import EscopoUnidade

    _importar_modelos()
    com_coluna = {
        tabela.name
        for tabela in Base.metadata.sorted_tables
        if "unidade_id" in tabela.columns
    }
    do_mixin = {
        mapeador.class_.__tablename__
        for mapeador in Base.registry.mappers
        if issubclass(mapeador.class_, EscopoUnidade)
    }
    return sorted(com_coluna & do_mixin)


def pendentes(tabelas: list[str] | None = None) -> dict[str, int]:
    """Quantas linhas estão sem unidade em cada tabela."""
    alvo = tabelas or tabelas_com_escopo()
    resultado: dict[str, int] = {}
    with engine.connect() as conn:
        for tabela in alvo:
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM {tabela} WHERE unidade_id IS NULL")  # noqa: S608
            ).scalar()
            resultado[tabela] = total or 0
    return resultado


def atribuir(unidade_id: str, tabelas: list[str] | None = None) -> dict[str, int]:
    """Grava ``unidade_id`` nas linhas que estão sem unidade. Devolve o que mudou."""
    alvo = tabelas or tabelas_com_escopo()
    alterados: dict[str, int] = {}
    with engine.begin() as conn:
        for tabela in alvo:
            resultado = conn.execute(
                text(  # noqa: S608 — nome de tabela vem da lista de modelos, não do usuário
                    f"UPDATE {tabela} SET unidade_id = :uid WHERE unidade_id IS NULL"
                ),
                {"uid": unidade_id},
            )
            alterados[tabela] = resultado.rowcount or 0
    return alterados


def _listar_unidades() -> int:
    from unidade.unidade_service import UnidadeService

    db = SessionLocal()
    try:
        with sem_escopo():
            unidades = UnidadeService.listar(db)
        if not unidades:
            print("Nenhuma unidade cadastrada. Crie a primeira em /unidades.")
            return 1
        print(f"{'ID':38} {'MODALIDADE':12} {'CNES':8} NOME")
        for u in unidades:
            print(f"{u.id:38} {u.modalidade:12} {u.cnes:8} {u.nome}")
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listar", action="store_true", help="lista as unidades e sai")
    parser.add_argument("--unidade", help="id da unidade que receberá os dados sem unidade")
    parser.add_argument(
        "--tabela",
        action="append",
        dest="tabelas",
        help="limita a uma tabela (pode repetir); o padrão é todas",
    )
    parser.add_argument("--conferir", action="store_true", help="só mostra o que está pendente")
    args = parser.parse_args(argv)

    if args.listar:
        return _listar_unidades()

    conhecidas = tabelas_com_escopo()
    alvo = args.tabelas or conhecidas
    desconhecidas = [t for t in alvo if t not in conhecidas]
    if desconhecidas:
        print(f"Tabela sem unidade_id: {', '.join(desconhecidas)}", file=sys.stderr)
        print(f"Disponíveis: {', '.join(conhecidas)}", file=sys.stderr)
        return 2

    faltando = pendentes(alvo)
    total = sum(faltando.values())
    print("Linhas sem unidade:")
    for tabela, quantidade in faltando.items():
        print(f"  {tabela:28} {quantidade}")
    if args.conferir or total == 0:
        if total == 0:
            print("Nada pendente.")
        return 0

    if not args.unidade:
        print("\nInforme --unidade <id> para atribuir (use --listar para ver os ids).",
              file=sys.stderr)
        return 2

    from unidade.unidade_service import UnidadeService

    db = SessionLocal()
    try:
        with sem_escopo():
            unidade = UnidadeService.obter_por_id(db, args.unidade)
    finally:
        db.close()
    if not unidade:
        print(f"Unidade não encontrada: {args.unidade}", file=sys.stderr)
        return 2

    print(f"\nAtribuindo {total} linha(s) a: {unidade.nome} ({unidade.modalidade})")
    alterados = atribuir(args.unidade, alvo)
    for tabela, quantidade in alterados.items():
        if quantidade:
            print(f"  {tabela:28} {quantidade} atualizada(s)")
    print("Concluído.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
