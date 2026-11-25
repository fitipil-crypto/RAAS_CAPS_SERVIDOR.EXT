"""
Serviço de retenção de competências para uso controlado e explícito.

Não é executado automaticamente na inicialização nem após importações.
Registros de competências mais antigas só são purgados se uma funcionalidade
manual chamar explicitamente o método de limpeza.
"""
from datetime import datetime
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from registro.registro_model import Registro


class RetentionService:
    KEEP_PREVIOUS = 3

    @staticmethod
    def allowed_competencias() -> list:
        """Retorna lista de competências permitidas (YYYYMM) — atual + 3 anteriores."""
        now = datetime.now().replace(day=1)
        comps = []
        for i in range(RetentionService.KEEP_PREVIOUS + 1):
            d = now - relativedelta(months=i)
            comps.append(d.strftime("%Y%m"))
        return comps

    @staticmethod
    def purge_old_competencias(db: Session) -> int:
        """Remove registros cuja competência (service_month) não está na janela permitida.
        Retorna o número de registros removidos."""
        allowed = RetentionService.allowed_competencias()
        allowed_set = set(allowed)

        all_regs = db.query(Registro).all()
        to_delete = []
        for reg in all_regs:
            cmp = (reg.service_month or "").replace("-", "")
            if cmp and cmp not in allowed_set:
                to_delete.append(reg.id)

        if to_delete:
            db.query(Registro).filter(Registro.id.in_(to_delete)).delete(synchronize_session=False)
            db.commit()

        return len(to_delete)
