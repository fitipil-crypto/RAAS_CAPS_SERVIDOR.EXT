"""Esquema de base: o banco como estava quando o Alembic foi adotado.

Gerada com --autogenerate a partir dos modelos e revisada à mão (os padrões
de data passaram a usar sa.func.now(), que vale em SQLite e PostgreSQL).

É idempotente de propósito: num banco criado antes do Alembic (pela antiga
create_all + lista _MIGRATIONS do database.py) ela cria só as tabelas, colunas
e índices que faltam e não mexe no resto. Assim, uma instalação antiga de
qualquer versão chega ao esquema de base com um simples "upgrade head".

Não altere este arquivo: mudanças no esquema entram em migrações novas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0001_base'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Valor gravado nas linhas que já existiam quando a coluna é acrescentada a um
# banco antigo (as mesmas regras da antiga lista _MIGRATIONS do database.py).
_PADRAO_AO_COMPLETAR = {
    ("usuarios", "help_enabled"): sa.true(),
    ("usuarios", "must_change_password"): sa.false(),
    ("usuarios", "failed_logins"): sa.text("0"),
    ("pacientes", "anonimizado"): sa.false(),
    ("grupos", "created_seq"): sa.text("0"),
}


def _inspetor():
    return sa.inspect(op.get_bind())


def _criar_tabela(nome, *itens):
    """Cria a tabela; se ela já existe (banco anterior ao Alembic), só
    acrescenta as colunas que faltam. Coluna acrescentada entra aceitando nulo,
    como fazia o ALTER TABLE da versão antiga, para não falhar em tabela com
    linhas."""
    insp = _inspetor()
    if not insp.has_table(nome):
        op.create_table(nome, *itens)
        return
    existentes = {c["name"] for c in insp.get_columns(nome)}
    for item in itens:
        if isinstance(item, sa.Column) and item.name not in existentes:
            # Sem herdar o server_default da coluna: o SQLite recusa ADD COLUMN
            # com padrão não constante (ex.: CURRENT_TIMESTAMP).
            op.add_column(nome, sa.Column(
                item.name, item.type, nullable=True,
                server_default=_PADRAO_AO_COMPLETAR.get((nome, item.name)),
            ))


def _criar_indice(tabela, nome, colunas, unique=False):
    if nome not in {i["name"] for i in _inspetor().get_indexes(tabela)}:
        op.create_index(nome, tabela, colunas, unique=unique)


def upgrade() -> None:
    _criar_tabela('configuracoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('chave', sa.String(length=100), nullable=False),
    sa.Column('valor', sa.Text(), nullable=True),
    sa.Column('tipo', sa.String(length=50), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('categoria', sa.String(length=50), nullable=False),
    sa.Column('editavel', sa.Boolean(), nullable=True),
    sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('configuracoes', 'ix_configuracoes_chave', ['chave'], unique=True)
    _criar_indice('configuracoes', 'ix_configuracoes_id', ['id'], unique=False)

    _criar_tabela('evento_pacientes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('event_id', sa.String(length=36), nullable=False),
    sa.Column('patient_id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('unidade_id', sa.String(length=36), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('evento_pacientes', 'ix_evento_pacientes_event_id', ['event_id'], unique=False)
    _criar_indice('evento_pacientes', 'ix_evento_pacientes_patient_id', ['patient_id'], unique=False)
    _criar_indice('evento_pacientes', 'ix_evento_pacientes_unidade_id', ['unidade_id'], unique=False)

    _criar_tabela('evento_registros',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('event_id', sa.String(length=36), nullable=False),
    sa.Column('registro_id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('unidade_id', sa.String(length=36), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('evento_registros', 'ix_evento_registros_event_id', ['event_id'], unique=False)
    _criar_indice('evento_registros', 'ix_evento_registros_registro_id', ['registro_id'], unique=False)
    _criar_indice('evento_registros', 'ix_evento_registros_unidade_id', ['unidade_id'], unique=False)

    _criar_tabela('eventos',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('event_date', sa.String(length=10), nullable=False),
    sa.Column('service_month', sa.String(length=7), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('unidade_id', sa.String(length=36), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('eventos', 'ix_eventos_event_date', ['event_date'], unique=False)
    _criar_indice('eventos', 'ix_eventos_service_month', ['service_month'], unique=False)
    _criar_indice('eventos', 'ix_eventos_unidade_id', ['unidade_id'], unique=False)
    _criar_indice('eventos', 'ix_eventos_unidade', ['unidade_id'], unique=False)

    _criar_tabela('grupos',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('service_month', sa.String(length=7), nullable=False),
    sa.Column('description', sa.String(length=30), nullable=False),
    sa.Column('group_date', sa.String(length=10), nullable=False),
    sa.Column('group_time', sa.String(length=5), nullable=False),
    sa.Column('people_count', sa.Integer(), nullable=False),
    sa.Column('created_seq', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('unidade_id', sa.String(length=36), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('grupos', 'ix_grupos_created_seq', ['created_seq'], unique=False)
    _criar_indice('grupos', 'ix_grupos_group_date', ['group_date'], unique=False)
    _criar_indice('grupos', 'ix_grupos_service_month', ['service_month'], unique=False)
    _criar_indice('grupos', 'ix_grupos_unidade_id', ['unidade_id'], unique=False)
    _criar_indice('grupos', 'ix_grupos_unidade', ['unidade_id'], unique=False)

    _criar_tabela('lgpd_incidentes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('ocorrido_em', sa.String(length=10), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=False),
    sa.Column('dados_afetados', sa.Text(), nullable=True),
    sa.Column('titulares_afetados', sa.String(length=50), nullable=True),
    sa.Column('risco', sa.String(length=10), nullable=False),
    sa.Column('medidas', sa.Text(), nullable=True),
    sa.Column('comunicado_anpd', sa.Boolean(), nullable=True),
    sa.Column('comunicado_titulares', sa.Boolean(), nullable=True),
    sa.Column('registrado_por', sa.String(length=100), nullable=True),
    sa.Column('registrado_em', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('unidade_id', sa.String(length=36), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('lgpd_incidentes', 'ix_lgpd_incidentes_unidade_id', ['unidade_id'], unique=False)

    _criar_tabela('lgpd_solicitacoes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('paciente_id', sa.String(length=36), nullable=True),
    sa.Column('titular_nome', sa.String(length=200), nullable=False),
    sa.Column('tipo', sa.String(length=30), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('solicitada_em', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('prazo_em', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolvida_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolvida_por', sa.String(length=100), nullable=True),
    sa.Column('resposta', sa.Text(), nullable=True),
    sa.Column('registrada_por', sa.String(length=100), nullable=True),
    sa.Column('unidade_id', sa.String(length=36), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('lgpd_solicitacoes', 'ix_lgpd_solicitacoes_paciente_id', ['paciente_id'], unique=False)
    _criar_indice('lgpd_solicitacoes', 'ix_lgpd_solicitacoes_status', ['status'], unique=False)
    _criar_indice('lgpd_solicitacoes', 'ix_lgpd_solicitacoes_unidade_id', ['unidade_id'], unique=False)

    _criar_tabela('logs_sistema',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('username', sa.String(length=100), nullable=True),
    sa.Column('action', sa.String(length=50), nullable=False),
    sa.Column('resource_type', sa.String(length=50), nullable=True),
    sa.Column('resource_id', sa.String(length=36), nullable=True),
    sa.Column('method', sa.String(length=10), nullable=True),
    sa.Column('path', sa.String(length=255), nullable=True),
    sa.Column('status_code', sa.Integer(), nullable=True),
    sa.Column('details', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('unidade_id', sa.String(length=36), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('logs_sistema', 'ix_logs_sistema_action', ['action'], unique=False)
    _criar_indice('logs_sistema', 'ix_logs_sistema_timestamp', ['timestamp'], unique=False)
    _criar_indice('logs_sistema', 'ix_logs_sistema_unidade_id', ['unidade_id'], unique=False)
    _criar_indice('logs_sistema', 'ix_logs_sistema_user_id', ['user_id'], unique=False)
    _criar_indice('logs_sistema', 'ix_logs_unidade', ['unidade_id'], unique=False)

    _criar_tabela('pacientes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('prontuario', sa.String(length=50), nullable=True),
    sa.Column('cns', sa.String(length=20), nullable=True),
    sa.Column('cpf', sa.String(length=14), nullable=True),
    sa.Column('birth_date', sa.String(length=10), nullable=True),
    sa.Column('nationality', sa.String(length=10), nullable=True),
    sa.Column('gender', sa.String(length=1), nullable=True),
    sa.Column('race', sa.String(length=2), nullable=True),
    sa.Column('ethnicity', sa.String(length=50), nullable=True),
    sa.Column('carate', sa.String(length=2), nullable=True),
    sa.Column('street_code', sa.String(length=10), nullable=True),
    sa.Column('mot_saida', sa.String(length=2), nullable=True),
    sa.Column('mother_name', sa.String(length=200), nullable=True),
    sa.Column('guardian_name', sa.String(length=200), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('cell_phone', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=100), nullable=True),
    sa.Column('cep', sa.String(length=10), nullable=True),
    sa.Column('street_type', sa.String(length=20), nullable=True),
    sa.Column('address', sa.String(length=200), nullable=True),
    sa.Column('street_number', sa.String(length=10), nullable=True),
    sa.Column('address_complement', sa.String(length=50), nullable=True),
    sa.Column('neighborhood', sa.String(length=100), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('state', sa.String(length=2), nullable=True),
    sa.Column('municipality_code', sa.String(length=10), nullable=True),
    sa.Column('admission_date', sa.String(length=10), nullable=True),
    sa.Column('user_origin', sa.String(length=2), nullable=True),
    sa.Column('cid_main', sa.String(length=10), nullable=True),
    sa.Column('cid_associated1', sa.String(length=10), nullable=True),
    sa.Column('cid_associated2', sa.String(length=10), nullable=True),
    sa.Column('cid_associated3', sa.String(length=10), nullable=True),
    sa.Column('cid_causes', sa.String(length=10), nullable=True),
    sa.Column('esf_coverage', sa.String(length=1), nullable=True),
    sa.Column('cnes_usf', sa.String(length=10), nullable=True),
    sa.Column('user_destination', sa.String(length=2), nullable=True),
    sa.Column('conclusion_date', sa.String(length=10), nullable=True),
    sa.Column('street_situation', sa.String(length=1), nullable=True),
    sa.Column('drug_user', sa.String(length=1), nullable=True),
    sa.Column('alcohol_user', sa.Boolean(), nullable=True),
    sa.Column('crack_user', sa.Boolean(), nullable=True),
    sa.Column('other_drugs_user', sa.Boolean(), nullable=True),
    sa.Column('authorization_number', sa.String(length=20), nullable=True),
    sa.Column('reference_technicians', sa.String(length=200), nullable=True),
    sa.Column('psychiatrist', sa.String(length=100), nullable=True),
    sa.Column('patient_status', sa.String(length=20), nullable=True),
    sa.Column('referred_by', sa.String(length=100), nullable=True),
    sa.Column('referred_to', sa.String(length=100), nullable=True),
    sa.Column('referring_technician', sa.String(length=100), nullable=True),
    sa.Column('discharge_technician', sa.String(length=100), nullable=True),
    sa.Column('base_legal', sa.String(length=40), nullable=True),
    sa.Column('anonimizado', sa.Boolean(), nullable=True),
    sa.Column('anonimizado_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('date_ini_valid', sa.String(length=10), nullable=True),
    sa.Column('date_fim_valid', sa.String(length=10), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('unidade_id', sa.String(length=36), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('pacientes', 'ix_pacientes_cns', ['cns'], unique=False)
    _criar_indice('pacientes', 'ix_pacientes_cpf', ['cpf'], unique=False)
    _criar_indice('pacientes', 'ix_pacientes_unidade_id', ['unidade_id'], unique=False)
    _criar_indice('pacientes', 'ix_pacientes_unidade', ['unidade_id'], unique=False)
    _criar_indice('pacientes', 'ix_pacientes_unidade_nome', ['unidade_id', 'name'], unique=False)

    _criar_tabela('procedimentos',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('procedimentos', 'ix_procedimentos_code', ['code'], unique=False)

    _criar_tabela('profissionais',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('cpf', sa.String(length=14), nullable=True),
    sa.Column('cns', sa.String(length=20), nullable=True),
    sa.Column('birth_date', sa.String(length=10), nullable=True),
    sa.Column('cbo', sa.String(length=10), nullable=True),
    sa.Column('specialty', sa.String(length=100), nullable=True),
    sa.Column('team', sa.String(length=100), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('unidade_id', sa.String(length=36), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('profissionais', 'ix_profissionais_cns', ['cns'], unique=False)
    _criar_indice('profissionais', 'ix_profissionais_unidade_id', ['unidade_id'], unique=False)
    _criar_indice('profissionais', 'ix_profissionais_unidade', ['unidade_id'], unique=False)

    _criar_tabela('registros_raas',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('service_month', sa.String(length=7), nullable=False),
    sa.Column('service_date', sa.String(length=10), nullable=False),
    sa.Column('patient_id', sa.String(length=36), nullable=False),
    sa.Column('professional_id', sa.String(length=36), nullable=True),
    sa.Column('procedure_id', sa.String(length=36), nullable=False),
    sa.Column('cbo_code', sa.String(length=10), nullable=True),
    sa.Column('service_type', sa.String(length=2), nullable=True),
    sa.Column('local_realizacao', sa.String(length=1), nullable=True),
    sa.Column('authorization', sa.String(length=20), nullable=True),
    sa.Column('srv', sa.String(length=3), nullable=True),
    sa.Column('cls', sa.String(length=3), nullable=True),
    sa.Column('team_code', sa.String(length=10), nullable=True),
    sa.Column('team_type', sa.String(length=3), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.String(length=36), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('unidade_id', sa.String(length=36), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('registros_raas', 'ix_registros_raas_group_id', ['group_id'], unique=False)
    _criar_indice('registros_raas', 'ix_registros_raas_patient_id', ['patient_id'], unique=False)
    _criar_indice('registros_raas', 'ix_registros_raas_procedure_id', ['procedure_id'], unique=False)
    _criar_indice('registros_raas', 'ix_registros_raas_professional_id', ['professional_id'], unique=False)
    _criar_indice('registros_raas', 'ix_registros_raas_service_date', ['service_date'], unique=False)
    _criar_indice('registros_raas', 'ix_registros_raas_service_month', ['service_month'], unique=False)
    _criar_indice('registros_raas', 'ix_registros_raas_unidade_id', ['unidade_id'], unique=False)
    _criar_indice('registros_raas', 'ix_registros_unidade', ['unidade_id'], unique=False)
    _criar_indice('registros_raas', 'ix_registros_unidade_mes', ['unidade_id', 'service_month'], unique=False)

    _criar_tabela('roadmap_items',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('priority', sa.String(length=20), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('done', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_tabela('unidades',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('sigla', sa.String(length=20), nullable=True),
    sa.Column('modalidade', sa.String(length=20), nullable=False),
    sa.Column('cnes', sa.String(length=7), nullable=False),
    sa.Column('cnpj', sa.String(length=20), nullable=True),
    sa.Column('uf_code', sa.String(length=2), nullable=True),
    sa.Column('municipio_codigo', sa.String(length=10), nullable=True),
    sa.Column('municipio_nome', sa.String(length=120), nullable=True),
    sa.Column('populacao', sa.Integer(), nullable=True),
    sa.Column('destination_organ', sa.String(length=60), nullable=True),
    sa.Column('destination_indicator', sa.String(length=1), nullable=True),
    sa.Column('versao', sa.String(length=10), nullable=True),
    sa.Column('bdversao', sa.String(length=10), nullable=True),
    sa.Column('leitos_acolhimento', sa.Integer(), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('ativa', sa.Boolean(), nullable=False),
    sa.Column('criada_em', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('atualizada_em', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('unidades', 'ix_unidades_cnes', ['cnes'], unique=False)
    _criar_indice('unidades', 'ix_unidades_modalidade', ['modalidade'], unique=False)

    _criar_tabela('usuarios',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('username', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=True),
    sa.Column('help_enabled', sa.Boolean(), nullable=True),
    sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
    sa.Column('unidade_id', sa.String(length=36), nullable=True),
    sa.Column('must_change_password', sa.Boolean(), nullable=True),
    sa.Column('senha_alterada_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failed_logins', sa.Integer(), nullable=True),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('termo_versao', sa.String(length=20), nullable=True),
    sa.Column('termo_aceito_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _criar_indice('usuarios', 'ix_usuarios_unidade_id', ['unidade_id'], unique=False)
    _criar_indice('usuarios', 'ix_usuarios_username', ['username'], unique=True)

def downgrade() -> None:
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_usuarios_username'))
        batch_op.drop_index(batch_op.f('ix_usuarios_unidade_id'))

    op.drop_table('usuarios')
    with op.batch_alter_table('unidades', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_unidades_modalidade'))
        batch_op.drop_index(batch_op.f('ix_unidades_cnes'))

    op.drop_table('unidades')
    op.drop_table('roadmap_items')
    with op.batch_alter_table('registros_raas', schema=None) as batch_op:
        batch_op.drop_index('ix_registros_unidade_mes')
        batch_op.drop_index('ix_registros_unidade')
        batch_op.drop_index(batch_op.f('ix_registros_raas_unidade_id'))
        batch_op.drop_index(batch_op.f('ix_registros_raas_service_month'))
        batch_op.drop_index(batch_op.f('ix_registros_raas_service_date'))
        batch_op.drop_index(batch_op.f('ix_registros_raas_professional_id'))
        batch_op.drop_index(batch_op.f('ix_registros_raas_procedure_id'))
        batch_op.drop_index(batch_op.f('ix_registros_raas_patient_id'))
        batch_op.drop_index(batch_op.f('ix_registros_raas_group_id'))

    op.drop_table('registros_raas')
    with op.batch_alter_table('profissionais', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profissionais_unidade_id'))
        batch_op.drop_index('ix_profissionais_unidade')
        batch_op.drop_index(batch_op.f('ix_profissionais_cns'))

    op.drop_table('profissionais')
    with op.batch_alter_table('procedimentos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_procedimentos_code'))

    op.drop_table('procedimentos')
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.drop_index('ix_pacientes_unidade_nome')
        batch_op.drop_index(batch_op.f('ix_pacientes_unidade_id'))
        batch_op.drop_index('ix_pacientes_unidade')
        batch_op.drop_index(batch_op.f('ix_pacientes_cpf'))
        batch_op.drop_index(batch_op.f('ix_pacientes_cns'))

    op.drop_table('pacientes')
    with op.batch_alter_table('logs_sistema', schema=None) as batch_op:
        batch_op.drop_index('ix_logs_unidade')
        batch_op.drop_index(batch_op.f('ix_logs_sistema_user_id'))
        batch_op.drop_index(batch_op.f('ix_logs_sistema_unidade_id'))
        batch_op.drop_index(batch_op.f('ix_logs_sistema_timestamp'))
        batch_op.drop_index(batch_op.f('ix_logs_sistema_action'))

    op.drop_table('logs_sistema')
    with op.batch_alter_table('lgpd_solicitacoes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lgpd_solicitacoes_unidade_id'))
        batch_op.drop_index(batch_op.f('ix_lgpd_solicitacoes_status'))
        batch_op.drop_index(batch_op.f('ix_lgpd_solicitacoes_paciente_id'))

    op.drop_table('lgpd_solicitacoes')
    with op.batch_alter_table('lgpd_incidentes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lgpd_incidentes_unidade_id'))

    op.drop_table('lgpd_incidentes')
    with op.batch_alter_table('grupos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_grupos_unidade_id'))
        batch_op.drop_index('ix_grupos_unidade')
        batch_op.drop_index(batch_op.f('ix_grupos_service_month'))
        batch_op.drop_index(batch_op.f('ix_grupos_group_date'))
        batch_op.drop_index(batch_op.f('ix_grupos_created_seq'))

    op.drop_table('grupos')
    with op.batch_alter_table('eventos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_eventos_unidade_id'))
        batch_op.drop_index('ix_eventos_unidade')
        batch_op.drop_index(batch_op.f('ix_eventos_service_month'))
        batch_op.drop_index(batch_op.f('ix_eventos_event_date'))

    op.drop_table('eventos')
    with op.batch_alter_table('evento_registros', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_evento_registros_unidade_id'))
        batch_op.drop_index(batch_op.f('ix_evento_registros_registro_id'))
        batch_op.drop_index(batch_op.f('ix_evento_registros_event_id'))

    op.drop_table('evento_registros')
    with op.batch_alter_table('evento_pacientes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_evento_pacientes_unidade_id'))
        batch_op.drop_index(batch_op.f('ix_evento_pacientes_patient_id'))
        batch_op.drop_index(batch_op.f('ix_evento_pacientes_event_id'))

    op.drop_table('evento_pacientes')
    with op.batch_alter_table('configuracoes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_configuracoes_id'))
        batch_op.drop_index(batch_op.f('ix_configuracoes_chave'))

    op.drop_table('configuracoes')
