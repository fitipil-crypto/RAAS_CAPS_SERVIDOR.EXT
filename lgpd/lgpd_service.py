"""
Serviço LGPD: primeiro acesso (termo + senha), direitos do titular (art. 18),
anonimização, incidentes (art. 48) e dados do controlador/encarregado (art. 41).
"""
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt
from sqlalchemy.orm import Session

from config.config_service import ConfigService
from lgpd.lgpd_model import SolicitacaoTitular, IncidenteSeguranca
from lgpd.lgpd_schema import (
    PrimeiroAcesso, SolicitacaoCriar, SolicitacaoResolver, IncidenteCriar, ConfigLgpd,
)
from paciente.paciente_model import Paciente
from procedimento.procedimento_model import Procedimento
from registro.registro_model import Registro
from usuario.usuario_model import Usuario

# Aumente ao alterar o texto do termo: todos os usuários precisarão aceitar de novo.
TERMO_VERSAO = "1.0"
PRAZO_RESPOSTA_DIAS = 15  # art. 19, II

CONFIG_LGPD = {
    "lgpd_controlador_nome": "controlador_nome",
    "lgpd_controlador_cnpj": "controlador_cnpj",
    "lgpd_encarregado_nome": "encarregado_nome",
    "lgpd_encarregado_email": "encarregado_email",
    "lgpd_encarregado_telefone": "encarregado_telefone",
}

# Campos que identificam o titular e são apagados na anonimização.
CAMPOS_IDENTIFICADORES = [
    "prontuario", "cns", "cpf", "ethnicity", "mother_name", "guardian_name",
    "phone", "cell_phone", "email", "cep", "street_type", "address",
    "street_number", "address_complement", "neighborhood", "street_code",
    "authorization_number", "cnes_usf",
]


def _agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sem_fuso(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=None) if dt else None


class LgpdService:

    # ── Primeiro acesso ──

    @staticmethod
    def contar_usuarios_sem_termo(db: Session) -> int:
        """Usuários ativos que ainda não aceitaram a versão vigente do termo."""
        return db.query(Usuario).filter(
            Usuario.active == True,  # noqa: E712
            (Usuario.termo_versao == None) | (Usuario.termo_versao != TERMO_VERSAO),  # noqa: E711
        ).count()

    @staticmethod
    def primeiro_acesso_pendente(user: Usuario) -> bool:
        return bool(user.must_change_password) or user.termo_versao != TERMO_VERSAO

    @staticmethod
    def concluir_primeiro_acesso(db: Session, user: Usuario, data: PrimeiroAcesso) -> None:
        if not data.aceite:
            raise ValueError("É necessário aceitar o termo de uso e confidencialidade")
        if not _bcrypt.checkpw(data.current_password.encode(), user.password_hash.encode()):
            raise ValueError("Senha atual incorreta")
        if data.new_password != data.confirm_password:
            raise ValueError("As senhas não coincidem")
        if data.new_password == data.current_password and user.must_change_password:
            raise ValueError("A nova senha deve ser diferente da senha atual")
        user.password_hash = _bcrypt.hashpw(data.new_password.encode(), _bcrypt.gensalt()).decode()
        user.senha_alterada_em = _agora()
        user.must_change_password = False
        user.termo_versao = TERMO_VERSAO
        user.termo_aceito_em = _agora()
        db.commit()

    # ── Controlador e encarregado ──

    @staticmethod
    def obter_config(db: Session) -> dict:
        return {campo: ConfigService.obter_valor(db, chave, "") or "" for chave, campo in CONFIG_LGPD.items()}

    @staticmethod
    def salvar_config(db: Session, data: ConfigLgpd) -> dict:
        valores = {}
        for chave, campo in CONFIG_LGPD.items():
            v = getattr(data, campo)
            if v is not None:
                valores[chave] = v.strip()
        if valores:
            ConfigService.atualizar_varios(db, valores)
        return LgpdService.obter_config(db)

    # ── Direitos do titular ──

    @staticmethod
    def criar_solicitacao(db: Session, data: SolicitacaoCriar, username: str) -> SolicitacaoTitular:
        sol = SolicitacaoTitular(
            id=str(uuid_lib.uuid4()),
            paciente_id=data.paciente_id,
            titular_nome=data.titular_nome.strip(),
            tipo=data.tipo,
            descricao=data.descricao,
            status="aberta",
            prazo_em=_agora() + timedelta(days=PRAZO_RESPOSTA_DIAS),
            registrada_por=username,
        )
        db.add(sol)
        db.commit()
        db.refresh(sol)
        return sol

    @staticmethod
    def listar_solicitacoes(db: Session, status: str | None = None) -> list[SolicitacaoTitular]:
        q = db.query(SolicitacaoTitular)
        if status:
            q = q.filter(SolicitacaoTitular.status == status)
        return q.order_by(SolicitacaoTitular.prazo_em.asc()).all()

    @staticmethod
    def obter_solicitacao(db: Session, sol_id: str) -> SolicitacaoTitular | None:
        return db.query(SolicitacaoTitular).filter(SolicitacaoTitular.id == sol_id).first()

    @staticmethod
    def resolver_solicitacao(db: Session, sol_id: str, data: SolicitacaoResolver, username: str) -> SolicitacaoTitular | None:
        sol = LgpdService.obter_solicitacao(db, sol_id)
        if not sol:
            return None
        sol.status = data.status
        sol.resposta = data.resposta
        sol.resolvida_em = _agora()
        sol.resolvida_por = username
        db.commit()
        db.refresh(sol)
        return sol

    @staticmethod
    def atrasada(sol: SolicitacaoTitular) -> bool:
        return sol.status == "aberta" and _sem_fuso(sol.prazo_em) < _agora()

    @staticmethod
    def exportar_titular(db: Session, paciente: Paciente) -> dict:
        """Cópia completa dos dados do titular (acesso/portabilidade, art. 18, II e V)."""
        dados = {c.name: getattr(paciente, c.name) for c in paciente.__table__.columns}
        registros = (
            db.query(Registro).filter(Registro.patient_id == paciente.id)
            .order_by(Registro.service_date.asc()).all()
        )
        procs = {p.id: p for p in db.query(Procedimento).all()}
        atendimentos = []
        for r in registros:
            item = {c.name: getattr(r, c.name) for c in r.__table__.columns}
            proc = procs.get(r.procedure_id)
            item["procedimento_codigo"] = proc.code if proc else None
            item["procedimento_nome"] = proc.name if proc else None
            atendimentos.append(item)
        return {
            "gerado_em": _agora().isoformat(),
            "formato": "RAAS-CAPS/LGPD v1",
            "titular": dados,
            "atendimentos": atendimentos,
        }

    @staticmethod
    def anonimizar_paciente(db: Session, paciente: Paciente) -> Paciente:
        """Remove os identificadores do titular, mantendo apenas dados para estatística/histórico.

        Os atendimentos continuam vinculados ao ID (sem identificação), mas as
        observações livres são apagadas por poderem citar o titular."""
        paciente.name = f"PACIENTE ANONIMIZADO {paciente.id[:8].upper()}"
        for campo in CAMPOS_IDENTIFICADORES:
            setattr(paciente, campo, None)
        if paciente.birth_date and len(paciente.birth_date) >= 4:
            paciente.birth_date = f"{paciente.birth_date[:4]}-01-01"  # mantém só o ano
        paciente.anonimizado = True
        paciente.anonimizado_em = _agora()
        db.query(Registro).filter(Registro.patient_id == paciente.id).update(
            {Registro.notes: None}, synchronize_session=False
        )
        db.commit()
        db.refresh(paciente)
        return paciente

    # ── Incidentes ──

    @staticmethod
    def criar_incidente(db: Session, data: IncidenteCriar, username: str) -> IncidenteSeguranca:
        inc = IncidenteSeguranca(id=str(uuid_lib.uuid4()), registrado_por=username, **data.model_dump())
        db.add(inc)
        db.commit()
        db.refresh(inc)
        return inc

    @staticmethod
    def listar_incidentes(db: Session) -> list[IncidenteSeguranca]:
        return db.query(IncidenteSeguranca).order_by(IncidenteSeguranca.ocorrido_em.desc()).all()
