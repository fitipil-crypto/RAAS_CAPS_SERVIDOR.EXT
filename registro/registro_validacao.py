"""
Regras de validação de negócio dos registros RAAS (independentes de HTTP).
"""
import re
import threading

from sqlalchemy.orm import Session

from paciente.paciente_service import PacienteService
from procedimento.procedimento_model import Procedimento
from registro.registro_service import RegistroService

MSG_DUPLICADO = "Ação já informada (mesma data e profissional)"
MSG_DATA_ANTES_ADMISSAO = "Data de atendimento menor que a data de admissão"
MSG_MES_DIVERGENTE = "Data do atendimento fora da competência selecionada"
MSG_GRUPO_INEXISTENTE = "Grupo não encontrado"
MSG_DATA_FORA_DO_GRUPO = "Data diferente da data do grupo"
MSG_PROFISSIONAL_EM_OUTRO_GRUPO = "O profissional já está em outro grupo nesse dia e horário"
MSG_GRUPO_LOTADO = "Quantidade de pessoas do grupo excedida"
MSG_PROC_GRUPO_SEM_GRUPO = "O atendimento em grupo (03.01.08.021-6) só pode ser lançado pelo 👥 Lançar grupo"
MSG_PROFISSIONAIS_DEMAIS = "No máximo {limite} profissionais por lançamento"

# 03.01.08.021-6 — ATENDIMENTO EM GRUPO DE PACIENTE EM CENTRO DE ATENÇÃO PSICOSSOCIAL
CODIGO_PROC_GRUPO = "0301080216"

# Profissionais que podem ser escolhidos de uma vez na digitação em lote.
MAX_PROFISSIONAIS_LOTE = 5
MAX_PROFISSIONAIS_LOTE_ADMIN = 10


def max_profissionais_lote(perfil: str | None) -> int:
    return MAX_PROFISSIONAIS_LOTE_ADMIN if perfil == "admin" else MAX_PROFISSIONAIS_LOTE


def eh_proc_grupo(db: Session, procedure_id: str | None) -> bool:
    """Compara só os dígitos: o código pode estar salvo com ou sem pontuação."""
    proc = db.get(Procedimento, procedure_id) if procedure_id else None
    return bool(proc and re.sub(r"\D", "", proc.code or "") == CODIGO_PROC_GRUPO)


# Conferir duplicidade e gravar precisam acontecer juntos: sem a trava, dois
# salvamentos simultâneos passam pela conferência antes de qualquer um gravar e
# o mesmo registro entra duas vezes. Vale para o servidor em um único processo
# (o padrão do RAAS-CAPS); com vários workers seria preciso travar no banco.
TRAVA_GRAVACAO = threading.RLock()


class RegistroInvalido(ValueError):
    """Violação de regra de negócio; a mensagem é exibida ao usuário."""


def _data_br(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso and len(iso) == 10 else (iso or "")


def validar_competencia(service_month: str, service_date: str) -> None:
    """Impede lançar um atendimento de um mês dentro da competência de outro."""
    if not service_month or not service_date:
        return
    if service_date[:7] != service_month:
        raise RegistroInvalido(f"{MSG_MES_DIVERGENTE} ({service_month})")


def validar_data_admissao(db: Session, patient_id: str, service_date: str) -> None:
    paciente = PacienteService.obter_por_id(db, patient_id)
    if paciente and paciente.admission_date and service_date < paciente.admission_date:
        raise RegistroInvalido(MSG_DATA_ANTES_ADMISSAO)


def validar_grupo(
    db: Session,
    *,
    group_id: str | None,
    professional_id: str | None,
    service_date: str,
    patient_ids: set[str] | None = None,
) -> None:
    """Regras do lançamento dentro de um grupo de atendimento.

    * o atendimento tem de ser no dia do grupo;
    * o mesmo profissional não pode estar em dois grupos com data e horário
      iguais — ele é uma pessoa só;
    * o grupo não comporta mais pacientes distintos do que a quantidade de
      pessoas informada ao criá-lo.

    `patient_ids` são os pacientes desta gravação (um registro ou um lote
    inteiro), somados aos que o grupo já tem."""
    if not group_id:
        return
    from grupo.grupo_service import GrupoService

    grupo = GrupoService.obter_por_id(db, group_id)
    if not grupo:
        raise RegistroInvalido(MSG_GRUPO_INEXISTENTE)
    if service_date and service_date != grupo.group_date:
        raise RegistroInvalido(f"{MSG_DATA_FORA_DO_GRUPO} ({_data_br(grupo.group_date)})")

    outro = GrupoService.outro_grupo_do_profissional(db, grupo, professional_id)
    if outro:
        numero = GrupoService.numero_de(db, outro)
        raise RegistroInvalido(
            f"{MSG_PROFISSIONAL_EM_OUTRO_GRUPO} (Grupo nº {numero} — {outro.description}, "
            f"{_data_br(outro.group_date)} às {outro.group_time})"
        )

    total = len(GrupoService.pacientes(db, group_id) | (patient_ids or set()))
    if total > grupo.people_count:
        raise RegistroInvalido(f"{MSG_GRUPO_LOTADO}: {grupo.people_count} pessoa(s)")


def validar_registro(
    db: Session,
    *,
    service_month: str,
    service_date: str,
    patient_id: str,
    professional_id: str,
    procedure_id: str,
    vistos: set | None = None,
    excluir_id: str | None = None,
    group_id: str | None = None,
) -> None:
    """Aplica todas as regras. `vistos` detecta duplicidade dentro de um mesmo lote."""
    validar_competencia(service_month, service_date)
    validar_data_admissao(db, patient_id, service_date)
    # O grupo entra na chave: o mesmo paciente pode estar em dois grupos no
    # mesmo dia, mas não duas vezes no mesmo grupo.
    chave = (service_date, patient_id, professional_id, procedure_id, group_id)
    if (vistos is not None and chave in vistos) or RegistroService.existe_duplicado(
        db, service_date, patient_id, professional_id, procedure_id, excluir_id=excluir_id,
        group_id=group_id,
    ):
        raise RegistroInvalido(MSG_DUPLICADO)
    if vistos is not None:
        vistos.add(chave)
