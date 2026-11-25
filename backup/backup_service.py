"""
Serviço para backup e restauração.
"""
import uuid as uuid_lib

from pydantic import ValidationError
from sqlalchemy.orm import Session

from paciente.paciente_model import Paciente
from paciente.paciente_service import PacienteService
from paciente.paciente_schema import PacienteBase
from profissional.profissional_model import Profissional
from profissional.profissional_service import ProfissionalService
from profissional.profissional_schema import ProfissionalCriar
from procedimento.procedimento_model import Procedimento
from procedimento.procedimento_service import ProcedimentoService
from procedimento.procedimento_schema import ProcedimentoCriar
from registro.registro_model import Registro
from registro.registro_service import RegistroService
from registro.registro_schema import RegistroCriar
from config.config_service import ConfigService

_SECOES = ("patients", "professionals", "procedures", "records")
_MAX_ERROS_EXIBIDOS = 20


class BackupInvalidoError(ValueError):
    """Backup malformado: nada foi alterado no banco."""

    def __init__(self, erros: list[str]):
        self.erros = erros
        extra = len(erros) - _MAX_ERROS_EXIBIDOS
        resumo = "; ".join(erros[:_MAX_ERROS_EXIBIDOS])
        if extra > 0:
            resumo += f"; ... e mais {extra} erro(s)"
        super().__init__(f"Backup inválido, nada foi restaurado: {resumo}")


class BackupService:

    @staticmethod
    def criar_backup(db: Session) -> dict:
        """Gera um dict com todos os dados do sistema para backup."""
        config = ConfigService.get_config_estabelecimento(db)

        pacientes = PacienteService.listar_todos(db)
        profissionais = ProfissionalService.listar_todos(db)
        procedimentos = ProcedimentoService.listar_todos(db)
        registros = RegistroService.listar_todos(db)

        # Com uma unidade selecionada, o escopo faz o backup sair só com os dados
        # dela — o que é útil para enviar a um CAPS. O campo abaixo registra isso
        # no arquivo, para não restaurar um backup parcial achando que é completo.
        from sistema.escopo import unidade_ativa

        return {
            "version": "5.0-servidor",
            "created_at": __import__("datetime").datetime.now().isoformat(),
            "unidade_id": unidade_ativa(),
            "escopo": "unidade" if unidade_ativa() else "todas as unidades",
            "config": config,
            "patients": [
                {c.name: getattr(p, c.name) for c in p.__table__.columns}
                for p in pacientes
            ],
            "professionals": [
                {c.name: getattr(p, c.name) for c in p.__table__.columns}
                for p in profissionais
            ],
            "procedures": [
                {c.name: getattr(p, c.name) for c in p.__table__.columns}
                for p in procedimentos
            ],
            "records": [
                {c.name: getattr(r, c.name) for c in r.__table__.columns}
                for r in registros
            ],
        }

    @staticmethod
    def _validar_secao(data: dict, chave: str, schema, erros: list[str]) -> list[tuple[str | None, object]]:
        """Valida cada item da seção; devolve (id_antigo, schema). Não toca no banco."""
        itens = data.get(chave, [])
        if not isinstance(itens, list):
            erros.append(f"'{chave}' deve ser uma lista")
            return []
        validados = []
        for n, item in enumerate(itens, start=1):
            if not isinstance(item, dict):
                erros.append(f"{chave}[{n}]: item deve ser um objeto")
                continue
            campos = {k: v for k, v in item.items() if k not in ("id", "created_at", "updated_at") and v is not None}
            try:
                validados.append((item.get("id"), schema(**campos)))
            except ValidationError as e:
                campo = ".".join(str(x) for x in e.errors()[0]["loc"])
                erros.append(f"{chave}[{n}]: {campo}: {e.errors()[0]['msg']}")
        return validados

    @staticmethod
    def restaurar_backup(db: Session, data: dict) -> dict:
        """Restaura dados a partir de um backup, de forma atômica.

        Primeiro valida o arquivo inteiro sem tocar no banco; só então apaga e recria
        tudo numa única transação. Qualquer falha desfaz tudo (os dados atuais ficam).
        """
        erros: list[str] = []
        if not isinstance(data, dict):
            raise BackupInvalidoError(["o arquivo deve conter um objeto JSON"])
        if not any(k in data for k in _SECOES):
            raise BackupInvalidoError(["o arquivo não parece um backup do RAAS-CAPS (nenhuma seção de dados)"])
        config = data.get("config")
        if config is not None and not isinstance(config, dict):
            erros.append("'config' deve ser um objeto")

        # PacienteBase (sem os validadores de formato de CPF/CEP/telefone do
        # PacienteCriar): um backup gerado antes dessas regras pode conter dados
        # que já estiveram no sistema (ex.: CEP com 7 dígitos) e precisa continuar
        # restaurável.
        pacientes = BackupService._validar_secao(data, "patients", PacienteBase, erros)
        profissionais = BackupService._validar_secao(data, "professionals", ProfissionalCriar, erros)
        procedimentos = BackupService._validar_secao(data, "procedures", ProcedimentoCriar, erros)
        registros = BackupService._validar_secao(data, "records", RegistroCriar, erros)
        if erros:
            raise BackupInvalidoError(erros)

        # A restauração limpa e repovoa o banco todo, inclusive o catálogo de
        # procedimentos, que é compartilhado por todas as unidades. Com uma
        # unidade selecionada o escopo limitaria a limpeza a ela, e o resultado
        # seria um banco meio restaurado — então a operação exige a visão geral.
        from sistema.escopo import unidade_ativa

        if unidade_ativa():
            raise BackupInvalidoError([
                "a restauração afeta todas as unidades; selecione 'Todas as unidades' "
                "na barra superior antes de restaurar"
            ])

        log = []
        try:
            # Registros primeiro (referenciam os demais). Nenhum commit até o fim.
            db.query(Registro).delete()
            db.query(Paciente).delete()
            db.query(Profissional).delete()
            db.query(Procedimento).delete()
            log.append("Dados existentes limpos")

            if config:
                ConfigService.atualizar_varios(db, config, commit=False)
                log.append("Configurações restauradas")

            def inserir(modelo, itens):
                mapa = {}
                for old_id, dados in itens:
                    obj = modelo(id=str(uuid_lib.uuid4()), **dados.model_dump())
                    db.add(obj)
                    if old_id:
                        mapa[old_id] = obj.id
                return mapa

            id_map_pat = inserir(Paciente, pacientes)
            log.append(f"{len(id_map_pat)} pacientes restaurados")
            id_map_prof = inserir(Profissional, profissionais)
            log.append(f"{len(id_map_prof)} profissionais restaurados")
            id_map_proc = inserir(Procedimento, procedimentos)
            log.append(f"{len(id_map_proc)} procedimentos restaurados")

            for _, r in registros:
                r.patient_id = id_map_pat.get(r.patient_id, r.patient_id)
                if r.professional_id:
                    r.professional_id = id_map_prof.get(r.professional_id, r.professional_id)
                r.procedure_id = id_map_proc.get(r.procedure_id, r.procedure_id)
                db.add(Registro(id=str(uuid_lib.uuid4()), **r.model_dump()))
            log.append(f"{len(registros)} registros RAAS restaurados")

            db.commit()
        except Exception:
            db.rollback()
            raise

        return {"log": log, "success": True}
