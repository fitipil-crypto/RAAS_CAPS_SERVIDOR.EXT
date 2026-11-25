"""
Rotas da API para backup.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from backup import backup_auto_service as auto
from backup.backup_service import BackupService, BackupInvalidoError
from sistema.auth import require_role

router = APIRouter(prefix="/api/backup", tags=["Backup"])


@router.get("/download")
def download_backup(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin", "coordenador")
    data = BackupService.criar_backup(db)
    content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    from datetime import datetime
    filename = f"backup_raas_caps_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/restaurar")
async def restaurar_backup(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    content = await file.read()
    try:
        data = json.loads(content.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Arquivo inválido: {str(e)}")
    try:
        return BackupService.restaurar_backup(db, data)
    except BackupInvalidoError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Backup automático em pasta da rede local (somente admin) ──
class BackupAutoConfig(BaseModel):
    ativo: bool = False
    destino: str = Field("", max_length=300)
    dias: list[int] = []
    horarios: list[str] = []
    manter: int = 30


class DestinoTeste(BaseModel):
    destino: str = Field("", max_length=300)


class CredencialRede(BaseModel):
    host: str = Field(..., max_length=300)
    usuario: str = Field(..., max_length=120)
    senha: str = Field("", max_length=200)


def _erro(e: auto.BackupAutoInvalido):
    return HTTPException(status_code=400, detail=str(e))


@router.get("/auto")
def obter_backup_auto(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    return auto.obter(db)


@router.put("/auto")
def salvar_backup_auto(data: BackupAutoConfig, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    try:
        return auto.salvar(db, data.ativo, data.destino, data.dias, data.horarios, data.manter)
    except auto.BackupAutoInvalido as e:
        raise _erro(e)


@router.post("/auto/testar")
def testar_backup_auto(data: DestinoTeste, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    try:
        return {"mensagem": auto.testar_destino(data.destino)}
    except auto.BackupAutoInvalido as e:
        raise _erro(e)


@router.post("/auto/executar")
def executar_backup_auto(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    try:
        resultado = auto.executar(db, origem="manual")
    except auto.BackupAutoInvalido as e:
        raise _erro(e)
    if not resultado["ok"]:
        raise HTTPException(status_code=400, detail=resultado["mensagem"])
    return resultado


@router.get("/auto/rede")
def procurar_rede(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    return auto.procurar_computadores()


@router.get("/auto/rede/pastas")
def pastas_do_computador(host: str, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    try:
        return {"host": host, "pastas": auto.listar_compartilhamentos(host)}
    except auto.BackupAutoInvalido as e:
        raise _erro(e)


@router.post("/auto/rede/conectar")
def conectar_rede(data: CredencialRede, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    try:
        return {"mensagem": auto.conectar(data.host, data.usuario, data.senha)}
    except auto.BackupAutoInvalido as e:
        raise _erro(e)
