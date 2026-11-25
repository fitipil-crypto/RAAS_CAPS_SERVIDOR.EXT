"""
Serviço para gerenciamento de registros RAAS.
"""
import uuid as uuid_lib
from sqlalchemy.orm import Session
from sqlalchemy import func

from registro.registro_model import Registro
from registro.registro_schema import RegistroCriar, RegistroAtualizar
from sistema.reference_data import TIPO_GRUPO, tipo_atendimento_do_procedimento


# Valor padrão de existe_duplicado: não filtra pelo grupo.
QUALQUER_GRUPO = object()


class RegistroService:

    @staticmethod
    def listar_todos(db: Session, month: str = None) -> list[Registro]:
        query = db.query(Registro)
        if month:
            query = query.filter(Registro.service_month == month)
        return query.order_by(Registro.service_date.desc()).all()

    @staticmethod
    def contar_todos(db: Session) -> int:
        return db.query(func.count(Registro.id)).scalar() or 0

    @staticmethod
    def estatisticas_mes(db: Session, month: str) -> dict:
        """Contagens agregadas (via SQL, sem carregar os registros) para o dashboard."""
        base = db.query(Registro).filter(Registro.service_month == month)
        return {
            "registros": base.with_entities(func.count(Registro.id)).scalar() or 0,
            "pacientes": base.with_entities(func.count(func.distinct(Registro.patient_id))).scalar() or 0,
            "procedimentos": base.with_entities(func.count(func.distinct(Registro.procedure_id))).scalar() or 0,
        }

    @staticmethod
    def top_procedimentos_mes(db: Session, month: str, limite: int = 5) -> list[dict]:
        """Procedimentos mais lançados na competência, com a quantidade de atendimentos."""
        linhas = (
            db.query(Registro.procedure_id, func.count(Registro.id).label("total"))
            .filter(Registro.service_month == month)
            .group_by(Registro.procedure_id)
            .order_by(func.count(Registro.id).desc())
            .limit(limite)
            .all()
        )
        return [{"procedure_id": pid, "total": total} for pid, total in linhas]

    @staticmethod
    def contagem_por_dia(db: Session, data_inicio: str) -> dict[str, int]:
        """Quantidade de registros por service_date, a partir de data_inicio (YYYY-MM-DD)."""
        linhas = (
            db.query(Registro.service_date, func.count(Registro.id))
            .filter(Registro.service_date >= data_inicio)
            .group_by(Registro.service_date)
            .all()
        )
        return dict(linhas)

    @staticmethod
    def obter_por_id(db: Session, registro_id: str) -> Registro | None:
        return db.query(Registro).filter(Registro.id == registro_id).first()

    @staticmethod
    def existe_duplicado(
        db: Session,
        service_date: str,
        patient_id: str,
        professional_id: str | None,
        procedure_id: str,
        excluir_id: str = None,
        group_id=QUALQUER_GRUPO,
    ) -> bool:
        """Verifica se já existe um registro para a mesma data, paciente,
        profissional e procedimento (usado no lançamento manual; a importação
        em lote tem sua própria lógica de deduplicação, pois o RAAS legitimamente
        repete essa combinação em arquivos oficiais).

        Com ``group_id`` informado (inclusive None), o grupo também precisa
        coincidir: o mesmo paciente pode estar em dois grupos diferentes no
        mesmo dia, mas não duas vezes no mesmo grupo."""
        query = db.query(Registro).filter(
            Registro.service_date == service_date,
            Registro.patient_id == patient_id,
            Registro.professional_id == professional_id,
            Registro.procedure_id == procedure_id,
        )
        if group_id is not QUALQUER_GRUPO:
            query = query.filter(
                Registro.group_id.is_(None) if group_id is None
                else Registro.group_id == group_id
            )
        if excluir_id:
            query = query.filter(Registro.id != excluir_id)
        return db.query(query.exists()).scalar()

    @staticmethod
    def listar_por_mes(db: Session, month: str) -> list[Registro]:
        return db.query(Registro).filter(Registro.service_month == month).order_by(Registro.service_date.desc()).all()

    @staticmethod
    def listar_por_paciente(db: Session, patient_id: str) -> list[Registro]:
        return db.query(Registro).filter(Registro.patient_id == patient_id).order_by(Registro.service_date.desc()).all()

    @staticmethod
    def _tipo_atendimento(db: Session, procedure_id: str) -> str | None:
        """Individual ('01') ou Grupo ('02'), conforme o procedimento lançado.

        A tela de lançamento não pergunta o tipo — antes disso, todo registro
        ficava gravado como Individual, mesmo o atendimento em grupo, e o
        histórico mostrava 'Individual' num procedimento de grupo."""
        if not procedure_id:
            return None
        from procedimento.procedimento_model import Procedimento
        proc = db.query(Procedimento).filter(Procedimento.id == procedure_id).first()
        if not proc:
            return None
        return tipo_atendimento_do_procedimento(proc.name)

    @staticmethod
    def _dados_com_tipo(db: Session, data: RegistroCriar) -> dict:
        """model_dump() com o service_type deduzido do procedimento.

        Um service_type enviado de propósito pela API é respeitado; o valor
        apenas padrão do schema é substituído pelo tipo do procedimento."""
        dados = data.model_dump()
        if "service_type" not in data.model_fields_set:
            # Lançado dentro de um grupo é sempre Grupo, qualquer que seja o
            # procedimento (Práticas corporais em grupo, por exemplo).
            tipo = TIPO_GRUPO if dados.get("group_id") else RegistroService._tipo_atendimento(db, dados.get("procedure_id"))
            if tipo:
                dados["service_type"] = tipo
        return dados

    @staticmethod
    def criar(db: Session, data: RegistroCriar) -> Registro:
        reg = Registro(
            id=str(uuid_lib.uuid4()),
            **RegistroService._dados_com_tipo(db, data)
        )
        db.add(reg)
        db.commit()
        db.refresh(reg)
        return reg

    @staticmethod
    def criar_varios(db: Session, registros: list[RegistroCriar]) -> list[Registro]:
        result = []
        for data in registros:
            reg = Registro(
                id=str(uuid_lib.uuid4()),
                **RegistroService._dados_com_tipo(db, data)
            )
            db.add(reg)
            result.append(reg)
        db.commit()
        for r in result:
            db.refresh(r)
        return result

    @staticmethod
    def atualizar(db: Session, registro_id: str, data: RegistroAtualizar) -> Registro | None:
        reg = RegistroService.obter_por_id(db, registro_id)
        if not reg:
            return None
        update_data = data.model_dump(exclude_unset=True)
        # Trocar o procedimento troca o tipo junto (grupo ↔ individual),
        # a não ser que o tipo tenha vindo explícito na própria edição.
        if "procedure_id" in update_data and "service_type" not in update_data:
            grupo = update_data.get("group_id", reg.group_id)
            tipo = TIPO_GRUPO if grupo else RegistroService._tipo_atendimento(db, update_data["procedure_id"])
            if tipo:
                update_data["service_type"] = tipo
        for key, value in update_data.items():
            setattr(reg, key, value)
        db.commit()
        db.refresh(reg)
        return reg

    @staticmethod
    def deletar(db: Session, registro_id: str) -> bool:
        reg = RegistroService.obter_por_id(db, registro_id)
        if not reg:
            return False
        db.delete(reg)
        db.commit()
        return True

    @staticmethod
    def deletar_varios(db: Session, ids: list[str]) -> int:
        count = 0
        for rid in ids:
            if RegistroService.deletar(db, rid):
                count += 1
        return count

    @staticmethod
    def deletar_todos(db: Session) -> int:
        count = db.query(Registro).count()
        db.query(Registro).delete()
        db.commit()
        return count

    @staticmethod
    def contar_por_mes(db: Session, month: str) -> int:
        return db.query(func.count(Registro.id)).filter(Registro.service_month == month).scalar() or 0

    @staticmethod
    def deletar_por_mes(db: Session, month: str) -> int:
        count = db.query(Registro).filter(Registro.service_month == month).count()
        db.query(Registro).filter(Registro.service_month == month).delete()
        db.commit()
        return count
