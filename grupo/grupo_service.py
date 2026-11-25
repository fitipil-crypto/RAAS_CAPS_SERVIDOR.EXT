"""
Serviço dos grupos de atendimento.

Regras do domínio:

* O número do grupo é a posição dele na competência, ordenada por data e
  horário (no empate, pela ordem de criação) — nunca é gravado, sempre
  calculado (``numerar``).
* Um profissional não pode estar em dois grupos com a mesma data e o mesmo
  horário (``outro_grupo_do_profissional``).
* O grupo comporta ``people_count`` pacientes distintos.
"""
import uuid as uuid_lib

from sqlalchemy import func
from sqlalchemy.orm import Session

from grupo.grupo_model import Grupo
from grupo.grupo_schema import GrupoAtualizar, GrupoCriar
from registro.registro_model import Registro


class GrupoService:

    # ── Consultas ──────────────────────────────────────────────────────────
    @staticmethod
    def listar_por_mes(db: Session, month: str) -> list[Grupo]:
        """Grupos da competência na ordem em que são numerados."""
        return (
            db.query(Grupo)
            .filter(Grupo.service_month == month)
            .order_by(Grupo.group_date, Grupo.group_time, Grupo.created_seq, Grupo.id)
            .all()
        )

    @staticmethod
    def numerar(grupos: list[Grupo]) -> dict[str, int]:
        """{id do grupo: nº}, em sequência crescente por data e horário."""
        return {g.id: i for i, g in enumerate(grupos, start=1)}

    @staticmethod
    def numero_de(db: Session, grupo: Grupo) -> int:
        """Número do grupo dentro da competência dele (0 se não encontrado)."""
        return GrupoService.numerar(GrupoService.listar_por_mes(db, grupo.service_month)).get(grupo.id, 0)

    @staticmethod
    def obter_por_id(db: Session, grupo_id: str) -> Grupo | None:
        return db.query(Grupo).filter(Grupo.id == grupo_id).first()

    @staticmethod
    def existe_igual(db: Session, description: str, group_date: str, group_time: str,
                     excluir_id: str | None = None) -> bool:
        """Mesma descrição, data e horário — seria o mesmo grupo lançado duas vezes."""
        query = db.query(Grupo).filter(
            func.lower(Grupo.description) == (description or "").strip().lower(),
            Grupo.group_date == group_date,
            Grupo.group_time == group_time,
        )
        if excluir_id:
            query = query.filter(Grupo.id != excluir_id)
        return db.query(query.exists()).scalar()

    # ── Registros do grupo ─────────────────────────────────────────────────
    @staticmethod
    def registros(db: Session, grupo_id: str) -> list[Registro]:
        return db.query(Registro).filter(Registro.group_id == grupo_id).all()

    @staticmethod
    def pacientes(db: Session, grupo_id: str) -> set[str]:
        linhas = db.query(Registro.patient_id).filter(Registro.group_id == grupo_id).distinct().all()
        return {pid for (pid,) in linhas}

    @staticmethod
    def tem_registros(db: Session, grupo_id: str) -> bool:
        return db.query(
            db.query(Registro).filter(Registro.group_id == grupo_id).exists()
        ).scalar()

    @staticmethod
    def outro_grupo_do_profissional(db: Session, grupo: Grupo, professional_id: str | None) -> Grupo | None:
        """Grupo diferente, com a mesma data e horário, em que o profissional já lançou.

        É o que impede o mesmo profissional de estar em dois grupos ao mesmo
        tempo: ele é uma pessoa só, não pode atender dois grupos às 13:00 do
        mesmo dia."""
        if not professional_id or not grupo:
            return None
        concorrentes = (
            db.query(Grupo)
            .filter(
                Grupo.group_date == grupo.group_date,
                Grupo.group_time == grupo.group_time,
                Grupo.id != grupo.id,
            )
            .all()
        )
        if not concorrentes:
            return None
        ocupados = {
            gid for (gid,) in db.query(Registro.group_id)
            .filter(
                Registro.professional_id == professional_id,
                Registro.group_id.in_([g.id for g in concorrentes]),
            )
            .distinct()
            .all()
        }
        return next((g for g in concorrentes if g.id in ocupados), None)

    @staticmethod
    def sessoes_por_profissional(db: Session, month: str) -> dict[str, int]:
        """{id do profissional: quantos grupos da competência ele atendeu}.

        É a contagem de sessões do relatório Individual × Grupo: cada grupo em
        que o profissional lançou pelo menos um atendimento conta uma vez,
        independentemente de quantos pacientes ou procedimentos ele lançou."""
        linhas = (
            db.query(Registro.professional_id, Registro.group_id)
            .join(Grupo, Grupo.id == Registro.group_id)
            .filter(Grupo.service_month == month, Registro.professional_id.isnot(None))
            .distinct()
            .all()
        )
        contagem: dict[str, int] = {}
        for professional_id, _ in linhas:
            contagem[professional_id] = contagem.get(professional_id, 0) + 1
        return contagem

    @staticmethod
    def detalhar(db: Session, grupos: list[Grupo]) -> list[dict]:
        """Grupos com os pacientes e, em cada um, os atendimentos já com os
        nomes resolvidos — é o que a caixa de grupos da digitação em lote e a
        tela de Grupos desenham, na disposição da relação impressa."""
        from paciente.paciente_service import PacienteService
        from procedimento.procedimento_service import ProcedimentoService
        from profissional.profissional_service import ProfissionalService

        # A numeração é sempre a da competência inteira: pedir um grupo só não
        # pode fazer dele o nº 1.
        numeros: dict[str, int] = {}
        for month in {g.service_month for g in grupos}:
            numeros.update(GrupoService.numerar(GrupoService.listar_por_mes(db, month)))
        pacientes = {p.id: p for p in PacienteService.listar_todos(db)}
        profissionais = {p.id: p for p in ProfissionalService.listar_todos(db)}
        procedimentos = {p.id: p for p in ProcedimentoService.listar_todos(db)}

        # Ordem estável: pacientes em ordem alfabética e, dentro de cada um, os
        # procedimentos pelo código (o created_at do SQLite só tem segundos,
        # então a ordem de gravação não serve de critério).
        def ordem(r):
            pac = pacientes.get(r.patient_id)
            proc = procedimentos.get(r.procedure_id)
            prof = profissionais.get(r.professional_id)
            return (
                (pac.name if pac else "").upper(),
                (proc.code if proc else ""),
                (proc.name if proc else ""),
                (prof.name if prof else ""),
            )

        detalhes = []
        for grupo in grupos:
            registros = sorted(GrupoService.registros(db, grupo.id), key=ordem)
            por_paciente: dict[str, dict] = {}
            for r in registros:
                pac = pacientes.get(r.patient_id)
                proc = procedimentos.get(r.procedure_id)
                prof = profissionais.get(r.professional_id)
                bloco = por_paciente.get(r.patient_id)
                if bloco is None:
                    bloco = {
                        "patient_id": r.patient_id,
                        "patient_name": pac.name if pac else "Paciente não encontrado",
                        "patient_prontuario": pac.prontuario if pac else None,
                        "registros": [],
                    }
                    por_paciente[r.patient_id] = bloco
                bloco["registros"].append({
                    "id": r.id,
                    "patient_id": r.patient_id,
                    "patient_name": bloco["patient_name"],
                    "patient_prontuario": bloco["patient_prontuario"],
                    "procedure_id": r.procedure_id,
                    "procedure_code": proc.code if proc else None,
                    "procedure_name": proc.name if proc else "Procedimento não encontrado",
                    "professional_id": r.professional_id,
                    "professional_name": prof.name if prof else "Não informado",
                    "quantity": r.quantity or 1,
                })
            detalhes.append({
                "id": grupo.id,
                "service_month": grupo.service_month,
                "description": grupo.description,
                "group_date": grupo.group_date,
                "group_time": grupo.group_time,
                "people_count": grupo.people_count,
                "numero": numeros.get(grupo.id, 0),
                "created_at": grupo.created_at,
                "updated_at": grupo.updated_at,
                "pacientes": list(por_paciente.values()),
                "total_registros": len(registros),
            })
        return detalhes

    # ── Escrita ────────────────────────────────────────────────────────────
    @staticmethod
    def criar(db: Session, data: GrupoCriar) -> Grupo:
        grupo = Grupo(
            id=str(uuid_lib.uuid4()),
            service_month=data.group_date[:7],
            created_seq=(db.query(func.max(Grupo.created_seq)).scalar() or 0) + 1,
            **data.model_dump(),
        )
        db.add(grupo)
        db.commit()
        db.refresh(grupo)
        return grupo

    @staticmethod
    def atualizar(db: Session, grupo_id: str, data: GrupoAtualizar) -> Grupo | None:
        grupo = GrupoService.obter_por_id(db, grupo_id)
        if not grupo:
            return None
        novos = data.model_dump(exclude_unset=True, exclude_none=True)
        for chave, valor in novos.items():
            setattr(grupo, chave, valor)
        if "group_date" in novos:
            grupo.service_month = novos["group_date"][:7]
        db.commit()
        db.refresh(grupo)
        return grupo

    @staticmethod
    def deletar(db: Session, grupo_id: str) -> bool:
        grupo = GrupoService.obter_por_id(db, grupo_id)
        if not grupo:
            return False
        db.delete(grupo)
        db.commit()
        return True
