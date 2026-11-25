"""
Schemas Pydantic para validação de pacientes.
"""
from pydantic import ConfigDict, BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


NUMERIC_FIELDS = {
    "prontuario",
    "cns",
    "cpf",
    "phone",
    "cell_phone",
    "cep",
    "municipality_code",
    "cnes_usf",
    "authorization_number",
    "nationality",
    "carate",
    "street_code",
    "mot_saida",
}

BRAZILIAN_STATES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


def _validate_digits_only(value, info):
    if value in (None, ""):
        return value
    text = str(value)
    if not text.isdigit():
        raise ValueError(f"{info.field_name} deve conter apenas numeros")
    return text


def _is_valid_cpf(cpf: str) -> bool:
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    total = sum(int(cpf[i]) * (10 - i) for i in range(9))
    first_digit = (total * 10) % 11
    if first_digit == 10:
        first_digit = 0
    if first_digit != int(cpf[9]):
        return False

    total = sum(int(cpf[i]) * (11 - i) for i in range(10))
    second_digit = (total * 10) % 11
    if second_digit == 10:
        second_digit = 0
    return second_digit == int(cpf[10])


def _validate_cpf(value):
    if value in (None, ""):
        return value
    cpf = str(value)
    if set(cpf) == {"0"}:  # CPF zerado = paciente sem CPF
        return None
    if not _is_valid_cpf(cpf):
        raise ValueError("CPF invalido")
    return cpf


def _validate_phone(value, info):
    if value in (None, ""):
        return value
    phone = str(value)
    if len(phone) > 11:
        raise ValueError(f"{info.field_name} deve ter no maximo 11 digitos")
    return phone


def _validate_cep(value):
    if value in (None, ""):
        return value
    if len(str(value)) != 8:
        raise ValueError("CEP deve ter 8 digitos")
    return value


BASES_LEGAIS = {
    "tutela_saude": "Tutela da saúde (art. 11, II, f)",
    "politica_publica": "Execução de políticas públicas (art. 11, II, b)",
    "obrigacao_legal": "Obrigação legal ou regulatória (art. 11, II, a)",
    "consentimento": "Consentimento do titular (art. 11, I)",
}


def _validate_base_legal(value):
    if value in (None, ""):
        return None
    if value not in BASES_LEGAIS:
        raise ValueError("Base legal invalida")
    return value


# Situação do paciente no acompanhamento do CAPS (valor salvo → rótulo).
SITUACOES_PACIENTE = {
    "ativo": "Ativo",
    "inativo": "Inativo",
    "monitoramento": "Monitoramento",
    "investigacao_cid": "Investigação CID",
}


def _validate_patient_status(value):
    if value in (None, ""):
        return None
    if value not in SITUACOES_PACIENTE:
        raise ValueError("Situação do paciente inválida")
    return value


# CID-10 é gravado como vai no arquivo RAAS: letra maiúscula e sem ponto
# (F840, Z032). Sem isso, "z032" e "Z032" contam como dois diagnósticos nos
# relatórios, e "F84.0" ainda é cortado para "F84." na exportação, porque o
# campo do layout tem só 4 posições. Vale para o formulário e para o que vem
# de um arquivo RAAS importado; digitar com ponto continua valendo.
CID_FIELDS = ("cid_main", "cid_associated1", "cid_associated2", "cid_associated3", "cid_causes")


def _validate_cid(value):
    if value in (None, ""):
        return value
    return str(value).replace(".", "").strip().upper()


def _validate_state(value):
    if value in (None, ""):
        return value
    state = str(value).upper()
    if state not in BRAZILIAN_STATES:
        raise ValueError("UF invalida")
    return state


class PacienteBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    prontuario: Optional[str] = None
    cns: Optional[str] = None
    cpf: Optional[str] = None
    birth_date: Optional[str] = None
    nationality: Optional[str] = Field(default="010")
    gender: Optional[str] = None
    race: Optional[str] = None
    ethnicity: Optional[str] = None
    carate: Optional[str] = None
    street_code: Optional[str] = None
    mot_saida: Optional[str] = None
    mother_name: Optional[str] = None
    guardian_name: Optional[str] = None
    phone: Optional[str] = None
    cell_phone: Optional[str] = None
    email: Optional[str] = None

    cep: Optional[str] = None
    street_type: Optional[str] = None
    address: Optional[str] = None
    street_number: Optional[str] = None
    address_complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    municipality_code: Optional[str] = None

    admission_date: Optional[str] = None
    user_origin: Optional[str] = Field(default="01")
    cid_main: Optional[str] = None
    cid_associated1: Optional[str] = None
    cid_associated2: Optional[str] = None
    cid_associated3: Optional[str] = None
    cid_causes: Optional[str] = None
    esf_coverage: Optional[str] = Field(default="N")
    cnes_usf: Optional[str] = None
    user_destination: Optional[str] = Field(default="00")
    conclusion_date: Optional[str] = None
    street_situation: Optional[str] = Field(default="N")
    drug_user: Optional[str] = Field(default="N")
    alcohol_user: Optional[bool] = False
    crack_user: Optional[bool] = False
    other_drugs_user: Optional[bool] = False
    authorization_number: Optional[str] = None
    reference_technicians: Optional[str] = None
    psychiatrist: Optional[str] = None
    patient_status: Optional[str] = None
    referred_by: Optional[str] = None
    referred_to: Optional[str] = None
    referring_technician: Optional[str] = None
    discharge_technician: Optional[str] = None

    date_ini_valid: Optional[str] = None
    date_fim_valid: Optional[str] = None
    base_legal: Optional[str] = "tutela_saude"


class PacienteCriar(PacienteBase):
    _digits_only = field_validator(*NUMERIC_FIELDS, mode="before", check_fields=False)(_validate_digits_only)
    _cpf_valid = field_validator("cpf", mode="after")(_validate_cpf)
    _phone_size = field_validator("phone", "cell_phone", mode="after")(_validate_phone)
    _cep_size = field_validator("cep", mode="after")(_validate_cep)
    _state_valid = field_validator("state", mode="before")(_validate_state)
    _base_legal_valid = field_validator("base_legal", mode="before")(_validate_base_legal)
    _patient_status_valid = field_validator("patient_status", mode="before")(_validate_patient_status)
    _cid_maiusculo = field_validator(*CID_FIELDS, mode="before", check_fields=False)(_validate_cid)


class PacienteAtualizar(BaseModel):
    name: Optional[str] = None
    prontuario: Optional[str] = None
    cns: Optional[str] = None
    cpf: Optional[str] = None
    birth_date: Optional[str] = None
    nationality: Optional[str] = None
    gender: Optional[str] = None
    race: Optional[str] = None
    ethnicity: Optional[str] = None
    carate: Optional[str] = None
    street_code: Optional[str] = None
    mot_saida: Optional[str] = None
    mother_name: Optional[str] = None
    guardian_name: Optional[str] = None
    phone: Optional[str] = None
    cell_phone: Optional[str] = None
    email: Optional[str] = None
    cep: Optional[str] = None
    street_type: Optional[str] = None
    address: Optional[str] = None
    street_number: Optional[str] = None
    address_complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    municipality_code: Optional[str] = None
    admission_date: Optional[str] = None
    user_origin: Optional[str] = None
    cid_main: Optional[str] = None
    cid_associated1: Optional[str] = None
    cid_associated2: Optional[str] = None
    cid_associated3: Optional[str] = None
    cid_causes: Optional[str] = None
    esf_coverage: Optional[str] = None
    cnes_usf: Optional[str] = None
    user_destination: Optional[str] = None
    conclusion_date: Optional[str] = None
    street_situation: Optional[str] = None
    drug_user: Optional[str] = None
    alcohol_user: Optional[bool] = None
    crack_user: Optional[bool] = None
    other_drugs_user: Optional[bool] = None
    authorization_number: Optional[str] = None
    reference_technicians: Optional[str] = None
    psychiatrist: Optional[str] = None
    patient_status: Optional[str] = None
    referred_by: Optional[str] = None
    referred_to: Optional[str] = None
    referring_technician: Optional[str] = None
    discharge_technician: Optional[str] = None
    date_ini_valid: Optional[str] = None
    date_fim_valid: Optional[str] = None
    base_legal: Optional[str] = None

    _digits_only = field_validator(*NUMERIC_FIELDS, mode="before", check_fields=False)(_validate_digits_only)
    _cpf_valid = field_validator("cpf", mode="after")(_validate_cpf)
    _phone_size = field_validator("phone", "cell_phone", mode="after")(_validate_phone)
    _cep_size = field_validator("cep", mode="after")(_validate_cep)
    _state_valid = field_validator("state", mode="before")(_validate_state)
    _base_legal_valid = field_validator("base_legal", mode="before")(_validate_base_legal)
    _patient_status_valid = field_validator("patient_status", mode="before")(_validate_patient_status)
    _cid_maiusculo = field_validator(*CID_FIELDS, mode="before", check_fields=False)(_validate_cid)


class PacienteResposta(PacienteBase):
    id: str
    anonimizado: Optional[bool] = False
    anonimizado_em: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
