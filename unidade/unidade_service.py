"""
Serviço das unidades (CAPS) e da escolha da unidade ativa.
"""
import logging

from sqlalchemy.orm import Session

from sistema.escopo import sem_escopo
from unidade import modalidades
from unidade.unidade_model import Unidade
from unidade.unidade_schema import UnidadeAtualizar, UnidadeCriar

logger = logging.getLogger(__name__)

# Perfis que podem alternar entre unidades e usar a visão "Todas as unidades".
PERFIS_MULTIUNIDADE = ("admin", "gestor")


class UnidadeInvalida(ValueError):
    """Erro de regra de negócio; a mensagem vai para o usuário."""


class UnidadeService:
    """A tabela de unidades nunca é filtrada por escopo (ver unidade_model)."""

    @staticmethod
    def listar(db: Session, apenas_ativas: bool = False) -> list[Unidade]:
        query = db.query(Unidade)
        if apenas_ativas:
            query = query.filter(Unidade.ativa.is_(True))
        return query.order_by(Unidade.nome).all()

    @staticmethod
    def obter_por_id(db: Session, unidade_id: str | None) -> Unidade | None:
        if not unidade_id:
            return None
        return db.query(Unidade).filter(Unidade.id == unidade_id).first()

    @staticmethod
    def obter_por_cnes(db: Session, cnes: str) -> Unidade | None:
        return db.query(Unidade).filter(Unidade.cnes == cnes).first()

    @staticmethod
    def contar(db: Session) -> int:
        return db.query(Unidade).count()

    @staticmethod
    def criar(db: Session, dados: UnidadeCriar) -> Unidade:
        if UnidadeService.obter_por_cnes(db, dados.cnes):
            raise UnidadeInvalida(f"Já existe uma unidade com o CNES {dados.cnes}.")
        unidade = Unidade(**dados.model_dump())
        db.add(unidade)
        db.commit()
        db.refresh(unidade)
        logger.info("Unidade criada: %s (%s, CNES %s)", unidade.nome, unidade.modalidade, unidade.cnes)
        return unidade

    @staticmethod
    def atualizar(db: Session, unidade_id: str, dados: UnidadeAtualizar) -> Unidade | None:
        unidade = UnidadeService.obter_por_id(db, unidade_id)
        if not unidade:
            return None
        alteracoes = dados.model_dump(exclude_unset=True)
        novo_cnes = alteracoes.get("cnes")
        if novo_cnes and novo_cnes != unidade.cnes:
            existente = UnidadeService.obter_por_cnes(db, novo_cnes)
            if existente and existente.id != unidade_id:
                raise UnidadeInvalida(f"Já existe uma unidade com o CNES {novo_cnes}.")
        for campo, valor in alteracoes.items():
            setattr(unidade, campo, valor)
        db.commit()
        db.refresh(unidade)
        return unidade

    @staticmethod
    def desativar(db: Session, unidade_id: str) -> bool:
        """Unidade sai de uso sem perder o histórico.

        Não há exclusão: apagar a unidade deixaria os atendimentos, pacientes e
        registros dela órfãos — e o arquivo RAAS já enviado continua precisando
        do CNES que o gerou. Quem precisa remover de vez usa a tela de
        "Excluir Dados" depois de exportar.
        """
        unidade = UnidadeService.obter_por_id(db, unidade_id)
        if not unidade:
            return False
        unidade.ativa = False
        db.commit()
        return True

    # ── Dados por unidade ────────────────────────────────────────────────

    @staticmethod
    def totais_por_unidade(db: Session) -> dict[str, dict[str, int]]:
        """Quantos pacientes e registros cada unidade tem (visão do gestor).

        Roda com o escopo desligado de propósito: é a tela que compara as
        unidades entre si.
        """
        from sqlalchemy import func

        from paciente.paciente_model import Paciente
        from registro.registro_model import Registro

        totais: dict[str, dict[str, int]] = {}
        with sem_escopo():
            for modelo, chave in ((Paciente, "pacientes"), (Registro, "registros")):
                linhas = (
                    db.query(modelo.unidade_id, func.count(modelo.id))
                    .group_by(modelo.unidade_id)
                    .all()
                )
                for unidade_id, total in linhas:
                    totais.setdefault(unidade_id or "", {})[chave] = total
        return totais

    # ── Unidade ativa da sessão ──────────────────────────────────────────

    @staticmethod
    def unidades_do_usuario(db: Session, usuario) -> list[Unidade]:
        """Unidades que este usuário pode acessar.

        admin e gestor circulam por todas; os demais perfis ficam na unidade
        que lhes foi atribuída.
        """
        if usuario is None:
            return []
        ativas = UnidadeService.listar(db, apenas_ativas=True)
        if usuario.role in PERFIS_MULTIUNIDADE:
            return ativas
        return [u for u in ativas if u.id == usuario.unidade_id]

    @staticmethod
    def pode_ver_todas(usuario) -> bool:
        return bool(usuario is not None and usuario.role in PERFIS_MULTIUNIDADE)

    @staticmethod
    def resolver_unidade_ativa(db: Session, usuario, escolhida: str | None) -> str | None:
        """Qual unidade vale para esta requisição.

        Devolve None quando a visão é "todas as unidades" — permitido apenas a
        admin e gestor. Um operador que tente forçar outra unidade pela sessão
        cai de volta na sua própria: a decisão nunca fica com o que veio do
        navegador.
        """
        if usuario is None:
            return None
        if usuario.role not in PERFIS_MULTIUNIDADE:
            return usuario.unidade_id
        if not escolhida:
            return None  # admin/gestor sem escolha: vê todas
        permitidas = {u.id for u in UnidadeService.unidades_do_usuario(db, usuario)}
        return escolhida if escolhida in permitidas else None

    @staticmethod
    def unidade_ao_entrar(db: Session, usuario) -> str | None:
        """Unidade em que o usuário cai logo depois do login: a da sua lotação.

        Para coordenador e operador isso só antecipa o que o middleware já
        garante. Para admin e gestor, que podem circular por todas, é o ponto
        de partida: quem está lotado num CAPS começa nele e, se quiser, troca
        de unidade (ou escolhe "Todas as unidades") pelo seletor. Sem lotação,
        ou com a unidade da lotação desativada, a visão começa em todas.
        """
        if usuario is None or not usuario.unidade_id:
            return None
        return UnidadeService.resolver_unidade_ativa(db, usuario, usuario.unidade_id)

    @staticmethod
    def unidade_padrao(db: Session) -> Unidade | None:
        """Primeira unidade ativa — usada quando só existe uma."""
        ativas = UnidadeService.listar(db, apenas_ativas=True)
        return ativas[0] if len(ativas) == 1 else None

    # ── Primeira instalação ──────────────────────────────────────────────

    @staticmethod
    def inicializar_unidade_padrao(db: Session) -> Unidade | None:
        """Na primeira subida, cria uma unidade a partir de `configuracoes`.

        Um banco que vem da versão local tem os dados do estabelecimento em
        `configuracoes` e nenhuma unidade. Sem isto, todo dado existente ficaria
        sem unidade e invisível depois que o escopo entrasse em vigor. A unidade
        nasce com os valores que já estavam lá; a modalidade começa como CAPS I
        e é corrigida na tela de Unidades.
        """
        if UnidadeService.contar(db) > 0:
            return None

        from config.config_service import ConfigService

        cnes = (ConfigService.obter_valor(db, "cnes_code", "") or "").strip()
        cnes = "".join(c for c in cnes if c.isdigit()).zfill(7)[:7] or "0000000"
        unidade = Unidade(
            nome=ConfigService.obter_valor(db, "organ_name", "CAPS MUNICIPAL") or "CAPS MUNICIPAL",
            sigla=ConfigService.obter_valor(db, "organ_code", "CAPS01"),
            modalidade="CAPS_I",
            cnes=cnes,
            cnpj=ConfigService.obter_valor(db, "cnpj", ""),
            uf_code=ConfigService.obter_valor(db, "uf_code", ""),
            municipio_codigo=ConfigService.obter_valor(db, "default_municipality_code", ""),
            municipio_nome=ConfigService.obter_valor(db, "default_city", ""),
            destination_organ=ConfigService.obter_valor(db, "destination_organ", ""),
            destination_indicator=ConfigService.obter_valor(db, "destination_indicator", "M") or "M",
            versao=ConfigService.obter_valor(db, "versao", "02.31"),
            bdversao=ConfigService.obter_valor(db, "bdversao", ""),
            leitos_acolhimento=0,
            ativa=True,
            observacoes=(
                "Unidade criada automaticamente na migração para o servidor, a partir das "
                "Configurações do estabelecimento. Confirme a modalidade."
            ),
        )
        db.add(unidade)
        db.commit()
        db.refresh(unidade)
        logger.info("Unidade padrão criada na migração: %s (CNES %s)", unidade.nome, unidade.cnes)
        return unidade

    # ── Resposta para a API ──────────────────────────────────────────────

    @staticmethod
    def para_resposta(unidade: Unidade) -> dict:
        dados = {
            coluna.name: getattr(unidade, coluna.name)
            for coluna in Unidade.__table__.columns
            if coluna.name not in ("criada_em", "atualizada_em")
        }
        dados["modalidade_nome"] = modalidades.nome(unidade.modalidade)
        dados["avisos"] = modalidades.avisos_da_unidade(
            unidade.modalidade,
            populacao=unidade.populacao,
            leitos=unidade.leitos_acolhimento,
        )
        return dados
