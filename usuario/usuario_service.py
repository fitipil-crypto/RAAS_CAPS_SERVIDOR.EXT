"""
Serviço para gerenciamento de usuários e autenticação.
"""
import os
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
import bcrypt as _bcrypt

from usuario.usuario_model import Usuario
from usuario.usuario_schema import UsuarioCriar, UsuarioAtualizar, SenhaAtualizar


MAX_FALHAS_LOGIN = 5
BLOQUEIO_MINUTOS = 15


def _agora() -> datetime:
    """Horário UTC sem fuso (padrão já usado em last_login)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UsuarioService:

    @staticmethod
    def inicializar_admin_padrao(db: Session):
        """Cria usuário admin padrão se não existir nenhum usuário.

        A senha inicial vem de ADMIN_INITIAL_PASSWORD (padrão "admin") e o
        administrador é obrigado a trocá-la no primeiro acesso."""
        existing = db.query(Usuario).first()
        if existing:
            return
        senha = os.getenv("ADMIN_INITIAL_PASSWORD") or "admin"
        admin = Usuario(
            id=str(uuid_lib.uuid4()),
            username="admin",
            name="Administrador",
            role="admin",
            password_hash=_bcrypt.hashpw(senha.encode(), _bcrypt.gensalt()).decode(),
            active=True,
            must_change_password=True,
        )
        db.add(admin)
        db.commit()

    @staticmethod
    def exigir_troca_de_senha_padrao(db: Session) -> int:
        """Instalações antigas: obriga a trocar a senha caso o admin ainda use "admin"."""
        n = 0
        for u in db.query(Usuario).filter(Usuario.username == "admin").all():
            if not u.must_change_password and _bcrypt.checkpw(b"admin", u.password_hash.encode()):
                u.must_change_password = True
                n += 1
        if n:
            db.commit()
        return n

    @staticmethod
    def esta_bloqueado(user: Usuario) -> bool:
        return bool(user.locked_until and user.locked_until.replace(tzinfo=None) > _agora())

    @staticmethod
    def registrar_falha_login(db: Session, username: str) -> None:
        """Conta a falha e bloqueia a conta por BLOQUEIO_MINUTOS após MAX_FALHAS_LOGIN."""
        user = UsuarioService.obter_por_username(db, username)
        if not user:
            return
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= MAX_FALHAS_LOGIN:
            user.locked_until = _agora() + timedelta(minutes=BLOQUEIO_MINUTOS)
            user.failed_logins = 0
        db.commit()

    @staticmethod
    def autenticar(db: Session, username: str, password: str) -> Usuario | None:
        user = db.query(Usuario).filter(
            Usuario.username == username,
            Usuario.active == True
        ).first()
        if not user:
            return None
        if UsuarioService.esta_bloqueado(user):
            return None
        if not _bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            UsuarioService.registrar_falha_login(db, username)
            return None
        if user.failed_logins or user.locked_until:
            user.failed_logins = 0
            user.locked_until = None
            db.commit()
        return user

    @staticmethod
    def obter_por_id(db: Session, user_id: str) -> Usuario | None:
        return db.query(Usuario).filter(Usuario.id == user_id).first()

    @staticmethod
    def obter_por_username(db: Session, username: str) -> Usuario | None:
        return db.query(Usuario).filter(Usuario.username == username).first()

    @staticmethod
    def listar_todos(db: Session) -> list[Usuario]:
        return db.query(Usuario).order_by(Usuario.created_at.desc()).all()

    @staticmethod
    def criar(db: Session, data: UsuarioCriar) -> Usuario:
        existing = UsuarioService.obter_por_username(db, data.username)
        if existing:
            raise ValueError("Login já existe")
        user = Usuario(
            id=str(uuid_lib.uuid4()),
            username=data.username,
            name=data.name,
            role=data.role,
            password_hash=_bcrypt.hashpw(data.password.encode(), _bcrypt.gensalt()).decode(),
            active=data.active,
            help_enabled=data.help_enabled,
            # Lotação na unidade. Para quem não é admin/gestor, o perfil atende
            # uma unidade por vez, então um usuário sem unidade não veria dado
            # nenhum — o router resolve a unidade antes de chegar aqui.
            unidade_id=data.unidade_id or None,
            must_change_password=True,  # senha definida pelo admin: o usuário troca no 1º acesso
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def atualizar(db: Session, user_id: str, data: UsuarioAtualizar) -> Usuario | None:
        user = UsuarioService.obter_por_id(db, user_id)
        if not user:
            return None
        if data.name is not None:
            user.name = data.name
        if data.role is not None:
            user.role = data.role
        if data.active is not None:
            user.active = data.active
        if data.help_enabled is not None:
            user.help_enabled = data.help_enabled
        if data.unidade_id is not None:
            # String vazia = tirar a lotação (volta a ver todas, se o perfil permitir).
            user.unidade_id = data.unidade_id or None
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def definir_ajuda_em_lote(db: Session, enabled: bool) -> int:
        """Liga/desliga a ajuda de todos os usuários não-admin. Retorna quantos foram alterados."""
        usuarios = db.query(Usuario).filter(Usuario.role != "admin").all()
        for u in usuarios:
            u.help_enabled = enabled
        db.commit()
        return len(usuarios)

    @staticmethod
    def alterar_senha(db: Session, user_id: str, data: SenhaAtualizar, redefinida_por_admin: bool = False) -> bool:
        user = UsuarioService.obter_por_id(db, user_id)
        if not user:
            return False
        if data.current_password:
            if not _bcrypt.checkpw(data.current_password.encode(), user.password_hash.encode()):
                raise ValueError("Senha atual incorreta")
        if data.new_password != data.confirm_password:
            raise ValueError("As senhas não coincidem")
        user.password_hash = _bcrypt.hashpw(data.new_password.encode(), _bcrypt.gensalt()).decode()
        user.senha_alterada_em = _agora()
        user.must_change_password = redefinida_por_admin  # redefinição pelo admin: nova troca no próximo login
        user.failed_logins = 0
        user.locked_until = None
        db.commit()
        return True

    @staticmethod
    def deletar(db: Session, user_id: str) -> bool:
        user = UsuarioService.obter_por_id(db, user_id)
        if not user:
            return False
        db.delete(user)
        db.commit()
        return True

    @staticmethod
    def atualizar_ultimo_login(db: Session, user_id: str):
        user = UsuarioService.obter_por_id(db, user_id)
        if user:
            user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
