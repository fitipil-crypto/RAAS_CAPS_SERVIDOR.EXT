"""
Escopo por unidade: isolamento dos dados de cada CAPS dentro do mesmo banco.

Como funciona
-------------
Toda tabela que guarda dado assistencial herda o mixin ``EscopoUnidade``, que
acrescenta a coluna ``unidade_id``. A cada requisição o ``UnidadeMiddleware``
grava na variável de contexto qual é a unidade ativa daquele usuário, e o
gancho ``do_orm_execute`` abaixo acrescenta ``WHERE unidade_id = :ativa`` em
*todo* SELECT, UPDATE e DELETE do ORM que envolva uma dessas tabelas — sem que
nenhum serviço precise saber disso.

A vantagem sobre filtrar unidade a unidade em cada consulta é que o isolamento
não depende de ninguém lembrar de aplicá-lo: uma consulta nova nasce filtrada.
Esquecer o filtro é o modo clássico de um sistema multiunidade vazar dado de um
serviço para outro, e aqui não há filtro para esquecer.

Uma ``ContextVar`` é usada (e não uma variável global) porque o servidor atende
várias requisições ao mesmo tempo: cada uma enxerga o seu próprio valor, e
tarefas em thread separada (o agendador de backup) não herdam o escopo de quem
estava navegando.

Quem pode ver tudo
------------------
Quando a unidade ativa é ``None`` não há filtro: é o caso do backup completo, da
tela de unidades e do perfil ``gestor``/``admin`` com a visão "Todas as
unidades" selecionada. Para pedir esse acesso explicitamente dentro de um
trecho de código, use ``with sem_escopo():``.
"""
import logging
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import Column, String, event
from sqlalchemy.orm import Session as SessaoORM, declared_attr, with_loader_criteria

logger = logging.getLogger(__name__)

# Unidade ativa da requisição atual (None = sem filtro, vê todas).
_unidade_ativa: ContextVar[str | None] = ContextVar("raas_unidade_ativa", default=None)
# Desliga o filtro mesmo havendo unidade ativa (backup, manutenção).
_escopo_desligado: ContextVar[bool] = ContextVar("raas_escopo_desligado", default=False)

# Chave de execution_options para uma consulta avulsa ignorar o filtro.
OPCAO_SEM_ESCOPO = "sem_escopo_unidade"


class EscopoUnidade:
    """Mixin de modelo: ganha ``unidade_id`` e passa a ser filtrado por unidade.

    O ``default`` preenche a coluna no INSERT com a unidade ativa, então um
    cadastro novo já nasce pertencendo à unidade de quem o criou. A coluna
    aceita nulo para que um banco já existente possa ser migrado sem recriar as
    tabelas (ver ``unidade.migracao``).
    """

    @declared_attr
    def unidade_id(cls):  # noqa: N805
        return Column(String(36), index=True, nullable=True, default=lambda: unidade_ativa())


# ── Leitura e escrita do contexto ───────────────────────────────────────────

def unidade_ativa() -> str | None:
    """Id da unidade ativa nesta requisição, ou None quando a visão é geral."""
    return _unidade_ativa.get()


def definir_unidade_ativa(unidade_id: str | None):
    """Define a unidade ativa e devolve o token para desfazer (``reset``)."""
    return _unidade_ativa.set(unidade_id or None)


def restaurar_unidade_ativa(token) -> None:
    """Desfaz um ``definir_unidade_ativa``, devolvendo o valor anterior.

    Chamado no ``finally`` do middleware: sem isso o valor vazaria para a
    próxima requisição atendida pela mesma tarefa.
    """
    try:
        _unidade_ativa.reset(token)
    except ValueError:
        # Token de outro contexto (ex.: exceção em tarefa aninhada): limpa.
        _unidade_ativa.set(None)


@contextmanager
def sem_escopo():
    """Dentro deste bloco as consultas enxergam todas as unidades.

    Usado pelo backup completo e pela manutenção, que trabalham sobre o banco
    inteiro e não sobre a unidade de quem disparou a ação.
    """
    token = _escopo_desligado.set(True)
    try:
        yield
    finally:
        _escopo_desligado.reset(token)


@contextmanager
def como_unidade(unidade_id: str | None):
    """Executa o bloco como se a unidade ativa fosse ``unidade_id``.

    Útil em scripts e tarefas de fundo (agendador, importação em linha de
    comando), que não passam pelo middleware.
    """
    token = definir_unidade_ativa(unidade_id)
    try:
        yield
    finally:
        restaurar_unidade_ativa(token)


def escopo_ligado() -> bool:
    return not _escopo_desligado.get() and _unidade_ativa.get() is not None


# ── O gancho que filtra as consultas ────────────────────────────────────────

@event.listens_for(SessaoORM, "do_orm_execute")
def _aplicar_escopo_de_unidade(estado) -> None:
    """Acrescenta o filtro de unidade a SELECT, UPDATE e DELETE do ORM.

    O UPDATE e o DELETE são tão importantes quanto o SELECT, e é fácil
    esquecê-los: o sistema tem exclusões em massa (``db.query(Registro)
    .delete()`` na restauração de backup, na limpeza de competência e na tela de
    Excluir Dados). Sem o filtro nessas operações, apagar os dados de um CAPS
    apagaria os de todos — o escopo protegeria a leitura e deixaria a escrita
    passar, que é o pior dos dois mundos.

    ``is_column_load``/``is_relationship_load`` são carregamentos preguiçosos de
    um objeto que já passou pelo filtro; filtrá-los de novo só atrapalharia (um
    atributo deixaria de carregar). ``include_aliases=True`` cobre as consultas
    que usam alias ou subconsulta da mesma tabela.
    """
    if estado.is_column_load or estado.is_relationship_load:
        return
    if not (estado.is_select or estado.is_update or estado.is_delete):
        return
    if estado.execution_options.get(OPCAO_SEM_ESCOPO) or _escopo_desligado.get():
        return
    unidade_id = _unidade_ativa.get()
    if not unidade_id:
        return
    estado.statement = estado.statement.options(
        with_loader_criteria(
            EscopoUnidade,
            lambda cls: cls.unidade_id == unidade_id,
            include_aliases=True,
        )
    )
