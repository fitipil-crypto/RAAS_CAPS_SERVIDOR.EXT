"""
Serviço para gerenciamento de eventos e do lançamento em lote.
"""
import uuid as uuid_lib
from sqlalchemy.orm import Session
from sqlalchemy import func

from evento.evento_model import Evento, EventoPaciente, EventoRegistro
from evento.evento_schema import EventoCriar, EventoAtualizar, EventoLancamento
from registro.registro_model import Registro
from registro.registro_service import RegistroService
from paciente.paciente_service import PacienteService
from profissional.profissional_service import ProfissionalService
from procedimento.procedimento_service import ProcedimentoService


class EventoService:

    # ─── Evento ──────────────────────────────────────────────────────

    @staticmethod
    def listar_por_mes(db: Session, month: str = None) -> list[Evento]:
        query = db.query(Evento)
        if month:
            query = query.filter(Evento.service_month == month)
        return query.order_by(Evento.event_date.desc()).all()

    @staticmethod
    def numerar(eventos: list[Evento]) -> dict[str, int]:
        """{id do evento: nº}, em sequência crescente por data.

        Igual aos grupos, o número não é gravado: é a posição do evento
        dentro da competência, então mudar a data de um evento renumera a
        competência inteira sem deixar buraco na sequência.
        """
        ordenados = sorted(
            eventos,
            key=lambda e: (e.event_date or "", str(e.created_at or ""), e.id),
        )
        return {evento.id: i for i, evento in enumerate(ordenados, start=1)}

    @staticmethod
    def numero_de(db: Session, evento: Evento) -> int:
        """Número do evento dentro da competência dele (0 se não encontrado)."""
        eventos = EventoService.listar_por_mes(db, evento.service_month)
        return EventoService.numerar(eventos).get(evento.id, 0)

    @staticmethod
    def eventos_por_registro(db: Session, event_ids: list[str]) -> dict[str, str]:
        """{id do registro: id do evento que o lançou}, para os eventos dados."""
        if not event_ids:
            return {}
        linhas = (
            db.query(EventoRegistro.registro_id, EventoRegistro.event_id)
            .filter(EventoRegistro.event_id.in_(event_ids))
            .all()
        )
        return {registro_id: event_id for registro_id, event_id in linhas}

    @staticmethod
    def obter_por_id(db: Session, evento_id: str) -> Evento | None:
        return db.query(Evento).filter(Evento.id == evento_id).first()

    @staticmethod
    def criar(db: Session, data: EventoCriar) -> Evento:
        evento = Evento(
            id=str(uuid_lib.uuid4()),
            name=data.name.strip(),
            event_date=data.event_date,
            service_month=data.event_date[:7],
            notes=data.notes,
        )
        db.add(evento)
        db.commit()
        db.refresh(evento)
        return evento

    @staticmethod
    def atualizar(db: Session, evento_id: str, data: EventoAtualizar) -> Evento | None:
        evento = EventoService.obter_por_id(db, evento_id)
        if not evento:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(evento, key, value.strip() if key == "name" and value else value)
        # A competência acompanha a data do evento.
        if update_data.get("event_date"):
            evento.service_month = evento.event_date[:7]
        db.commit()
        db.refresh(evento)
        return evento

    @staticmethod
    def deletar(db: Session, evento_id: str, remover_registros: bool = False) -> dict | None:
        """Remove o evento e sua lista de participantes.

        Por padrão os registros RAAS lançados são preservados — uma vez
        computados, pertencem ao paciente. Com remover_registros=True são
        apagados também, mas só os que este evento criou: registros que já
        existiam e foram ignorados no lançamento não têm vínculo e ficam.
        """
        evento = EventoService.obter_por_id(db, evento_id)
        if not evento:
            return None

        registros_removidos = 0
        if remover_registros:
            registro_ids = EventoService.listar_registro_ids(db, evento_id)
            if registro_ids:
                registros_removidos = (
                    db.query(Registro)
                    .filter(Registro.id.in_(registro_ids))
                    .delete(synchronize_session=False)
                )

        db.query(EventoRegistro).filter(EventoRegistro.event_id == evento_id).delete()
        db.query(EventoPaciente).filter(EventoPaciente.event_id == evento_id).delete()
        db.delete(evento)
        db.commit()
        return {"registros_removidos": registros_removidos}

    @staticmethod
    def listar_registro_ids(db: Session, evento_id: str) -> list[str]:
        """Ids dos registros RAAS gerados por este evento."""
        linhas = (
            db.query(EventoRegistro.registro_id)
            .filter(EventoRegistro.event_id == evento_id)
            .all()
        )
        return [linha[0] for linha in linhas]

    # ─── Participantes ───────────────────────────────────────────────

    @staticmethod
    def listar_patient_ids(db: Session, evento_id: str) -> list[str]:
        linhas = (
            db.query(EventoPaciente.patient_id)
            .filter(EventoPaciente.event_id == evento_id)
            .all()
        )
        return [linha[0] for linha in linhas]

    @staticmethod
    def contar_pacientes(db: Session, evento_id: str) -> int:
        return (
            db.query(func.count(EventoPaciente.id))
            .filter(EventoPaciente.event_id == evento_id)
            .scalar()
            or 0
        )

    @staticmethod
    def adicionar_pacientes(db: Session, evento_id: str, patient_ids: list[str]) -> dict:
        """Acrescenta pacientes à lista, ignorando os que já estão nela."""
        existentes = set(EventoService.listar_patient_ids(db, evento_id))
        adicionados = 0
        for patient_id in patient_ids:
            if patient_id in existentes:
                continue
            if not PacienteService.obter_por_id(db, patient_id):
                continue
            db.add(EventoPaciente(
                id=str(uuid_lib.uuid4()), event_id=evento_id, patient_id=patient_id,
            ))
            existentes.add(patient_id)
            adicionados += 1
        db.commit()
        return {"adicionados": adicionados, "ja_estavam": len(patient_ids) - adicionados}

    @staticmethod
    def remover_paciente(db: Session, evento_id: str, patient_id: str) -> bool:
        removidos = (
            db.query(EventoPaciente)
            .filter(EventoPaciente.event_id == evento_id, EventoPaciente.patient_id == patient_id)
            .delete()
        )
        db.commit()
        return removidos > 0

    # ─── Lançamento em lote ──────────────────────────────────────────

    @staticmethod
    def lancar_registros(db: Session, evento_id: str, data: EventoLancamento) -> dict:
        # Mesma trava dos registros: conferir duplicidade e gravar sem intercalar.
        from registro.registro_validacao import TRAVA_GRAVACAO
        with TRAVA_GRAVACAO:
            return EventoService._lancar_registros(db, evento_id, data)

    @staticmethod
    def _lancar_registros(db: Session, evento_id: str, data: EventoLancamento) -> dict:
        """Cruza cada procedimento com cada profissional e grava um Registro
        RAAS para todos os pacientes da lista.

        Pacientes com admissão posterior à data do evento são pulados (o RAAS
        não aceita atendimento antes da admissão), e combinações que já existem
        são ignoradas em vez de duplicar — relançar o evento é seguro.
        """
        evento = EventoService.obter_por_id(db, evento_id)
        if not evento:
            return {"erro": "Evento não encontrado"}

        patient_ids = EventoService.listar_patient_ids(db, evento_id)
        if not patient_ids:
            return {"erro": "O evento não tem pacientes na lista"}

        # CBO de cada profissional, para gravar junto com o registro.
        cbo_por_profissional = {}
        for professional_id in data.professional_ids:
            profissional = ProfissionalService.obter_por_id(db, professional_id)
            cbo_por_profissional[professional_id] = profissional.cbo if profissional else None

        # Nomes para explicar na tela o que foi ignorado/pulado.
        nomes_profissional = {}
        for professional_id in data.professional_ids:
            profissional = ProfissionalService.obter_por_id(db, professional_id)
            nomes_profissional[professional_id] = profissional.name if profissional else "—"
        nomes_procedimento = {}
        for proc in data.procedures:
            procedimento = ProcedimentoService.obter_por_id(db, proc.procedure_id)
            nomes_procedimento[proc.procedure_id] = procedimento.name if procedimento else "—"

        criados = 0
        ignorados = 0
        ignorados_detalhe = []
        pulados = []
        novos = []
        vinculos = []

        for patient_id in patient_ids:
            paciente = PacienteService.obter_por_id(db, patient_id)
            if not paciente:
                continue
            if paciente.admission_date and evento.event_date < paciente.admission_date:
                pulados.append(paciente.name)
                continue

            for proc in data.procedures:
                for professional_id in data.professional_ids:
                    if RegistroService.existe_duplicado(
                        db, evento.event_date, patient_id, professional_id, proc.procedure_id
                    ):
                        ignorados += 1
                        ignorados_detalhe.append({
                            "paciente": paciente.name,
                            "procedimento": nomes_procedimento.get(proc.procedure_id, "—"),
                            "profissional": nomes_profissional.get(professional_id, "—"),
                        })
                        continue
                    registro_id = str(uuid_lib.uuid4())
                    vinculos.append(EventoRegistro(
                        id=str(uuid_lib.uuid4()),
                        event_id=evento_id,
                        registro_id=registro_id,
                    ))
                    novos.append(Registro(
                        id=registro_id,
                        service_month=evento.service_month,
                        service_date=evento.event_date,
                        patient_id=patient_id,
                        professional_id=professional_id,
                        procedure_id=proc.procedure_id,
                        cbo_code=cbo_por_profissional.get(professional_id),
                        service_type=data.service_type,
                        local_realizacao=data.local_realizacao,
                        srv=data.srv,
                        cls=data.cls,
                        quantity=proc.quantity,
                        notes=f"Evento: {evento.name}",
                    ))
                    criados += 1

        db.add_all(novos)
        db.add_all(vinculos)
        db.commit()
        return {
            "criados": criados,
            "ignorados": ignorados,
            "ignorados_detalhe": ignorados_detalhe,
            "pacientes": len(patient_ids),
            "pulados": pulados,
        }

    @staticmethod
    def resumo_lancamento(db: Session, evento_id: str) -> dict:
        """Profissionais e procedimentos que a lista recebeu em comum.

        O lançamento cruza os mesmos profissionais e procedimentos com todos
        os participantes, então o distinto dos registros vinculados ao evento
        é justamente o que foi feito em comum na lista. Serve para a ficha do
        evento mostrar, no fim da lista, quem atendeu e com quais atividades.
        """
        linhas = (
            db.query(Registro.professional_id, Registro.procedure_id)
            .join(EventoRegistro, EventoRegistro.registro_id == Registro.id)
            .filter(EventoRegistro.event_id == evento_id)
            .distinct()
            .all()
        )
        if not linhas:
            return {"profissionais": [], "procedimentos": []}

        profissionais = {}
        for professional_id in {linha[0] for linha in linhas if linha[0]}:
            profissional = ProfissionalService.obter_por_id(db, professional_id)
            if profissional:
                profissionais[professional_id] = {
                    "name": profissional.name,
                    "cbo": profissional.cbo,
                }

        procedimentos = {}
        for procedure_id in {linha[1] for linha in linhas if linha[1]}:
            procedimento = ProcedimentoService.obter_por_id(db, procedure_id)
            if procedimento:
                procedimentos[procedure_id] = {
                    "code": procedimento.code,
                    "name": procedimento.name,
                }

        return {
            "profissionais": sorted(profissionais.values(), key=lambda p: (p["name"] or "").upper()),
            "procedimentos": sorted(procedimentos.values(), key=lambda p: (p["code"] or "")),
        }

    @staticmethod
    def contar_registros(db: Session, evento_id: str) -> int:
        """Quantos registros lançados por este evento ainda existem — os
        excluídos à mão depois do lançamento não são contados."""
        registro_ids = EventoService.listar_registro_ids(db, evento_id)
        if not registro_ids:
            return 0
        return (
            db.query(func.count(Registro.id))
            .filter(Registro.id.in_(registro_ids))
            .scalar()
            or 0
        )
