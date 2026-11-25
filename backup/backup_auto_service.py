"""
Backup automático em uma pasta da rede local.

Nos dias da semana e horários escolhidos, grava em uma pasta compartilhada de
outro computador (ex.: \\\\RECEPCAO\\Backups ou \\\\192.168.0.10\\Backups) um
arquivo .zip com:
  • raas_caps.db — cópia completa do banco (todo o sistema: usuários, eventos,
    logs...), feita pela API de backup do SQLite, segura com o servidor ligado;
  • backup.json — o mesmo arquivo de "Baixar Backup", aceito por "Restaurar".

O agendador roda dentro do servidor (uma thread que confere a cada 30 s).
Senhas de pastas protegidas não ficam no banco: vão para o Gerenciador de
Credenciais do Windows (cmdkey), que o Windows usa ao acessar a pasta.
"""
import json
import logging
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from config.config_model import Configuracao

logger = logging.getLogger("raas_caps")

CATEGORIA = "backup_auto"
PREFIXO_ARQUIVO = "raas_caps_backup_"
DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]  # índice = datetime.weekday()
MAX_HORARIOS = 6
# Tolerância: um horário perdido por poucos minutos (servidor ocupado ou
# acabando de ligar) ainda é executado.
JANELA_MINUTOS = 10

PADRAO = {
    "backup_auto_ativo": "false",
    "backup_auto_destino": "",
    "backup_auto_dias": "0,1,2,3,4",
    "backup_auto_horarios": "12:00,18:00",
    "backup_auto_manter": "30",
    "backup_auto_ultimo_em": "",
    "backup_auto_ultimo_ok": "",
    "backup_auto_ultima_msg": "",
    "backup_auto_ultimo_slot": "",
}

_RE_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_RE_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
_RE_COMPARTILHAMENTO = re.compile(r"^[^\\/:*?\"<>|]{1,80}$")
_trava_execucao = threading.Lock()


class BackupAutoInvalido(ValueError):
    """Configuração ou destino inválido; a mensagem é exibida ao usuário."""


# ── Configuração ────────────────────────────────────────────────────────────
def _ler(db: Session) -> dict:
    linhas = {c.chave: c.valor for c in db.query(Configuracao).filter(Configuracao.chave.in_(list(PADRAO)))}
    return {k: (linhas.get(k) if linhas.get(k) is not None else v) for k, v in PADRAO.items()}


def _gravar(db: Session, valores: dict) -> None:
    for chave, valor in valores.items():
        cfg = db.query(Configuracao).filter(Configuracao.chave == chave).first()
        if cfg:
            cfg.valor = valor
        else:
            db.add(Configuracao(chave=chave, valor=valor, tipo="string", categoria=CATEGORIA,
                                descricao="Backup automático", editavel=False))
    db.commit()


def obter(db: Session) -> dict:
    v = _ler(db)
    return {
        "ativo": v["backup_auto_ativo"] == "true",
        "destino": v["backup_auto_destino"],
        "dias": [int(d) for d in v["backup_auto_dias"].split(",") if d.strip().isdigit()],
        "horarios": [h for h in v["backup_auto_horarios"].split(",") if h],
        "manter": int(v["backup_auto_manter"] or 30),
        "ultimo_em": v["backup_auto_ultimo_em"],
        "ultimo_ok": v["backup_auto_ultimo_ok"] == "true" if v["backup_auto_ultimo_ok"] else None,
        "ultima_msg": v["backup_auto_ultima_msg"],
        "proximo": proximo_horario(v),
    }


def salvar(db: Session, ativo: bool, destino: str, dias: list[int], horarios: list[str], manter: int) -> dict:
    destino = (destino or "").strip()
    dias = sorted({int(d) for d in dias})
    horarios = sorted({h.strip() for h in horarios if h and h.strip()})
    if any(d < 0 or d > 6 for d in dias):
        raise BackupAutoInvalido("Dia da semana inválido.")
    if any(not _RE_HORA.match(h) for h in horarios):
        raise BackupAutoInvalido("Horário inválido. Use o formato HH:MM.")
    if len(horarios) > MAX_HORARIOS:
        raise BackupAutoInvalido(f"No máximo {MAX_HORARIOS} horários.")
    if not 1 <= int(manter) <= 365:
        raise BackupAutoInvalido("Guarde de 1 a 365 backups.")
    if ativo:
        if not destino:
            raise BackupAutoInvalido("Informe a pasta de destino.")
        if not dias:
            raise BackupAutoInvalido("Escolha ao menos um dia da semana.")
        if not horarios:
            raise BackupAutoInvalido("Escolha ao menos um horário.")
    _gravar(db, {
        "backup_auto_ativo": "true" if ativo else "false",
        "backup_auto_destino": destino,
        "backup_auto_dias": ",".join(str(d) for d in dias),
        "backup_auto_horarios": ",".join(horarios),
        "backup_auto_manter": str(int(manter)),
    })
    return obter(db)


def proximo_horario(v: dict, agora: datetime | None = None) -> str:
    """Próximo backup agendado (dd/mm/aaaa HH:MM) ou "" se desligado."""
    if v["backup_auto_ativo"] != "true":
        return ""
    dias = {int(d) for d in v["backup_auto_dias"].split(",") if d.strip().isdigit()}
    horarios = sorted(h for h in v["backup_auto_horarios"].split(",") if _RE_HORA.match(h or ""))
    if not dias or not horarios:
        return ""
    agora = agora or datetime.now()
    for delta in range(8):
        dia = agora + timedelta(days=delta)
        if dia.weekday() not in dias:
            continue
        for h in horarios:
            hh, mm = map(int, h.split(":"))
            quando = dia.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if quando > agora:
                return quando.strftime("%d/%m/%Y %H:%M")
    return ""


# ── Geração do arquivo ──────────────────────────────────────────────────────
def _caminho_sqlite() -> Path | None:
    from database import DATABASE_URL
    if not DATABASE_URL.startswith("sqlite:///"):
        return None
    caminho = DATABASE_URL[len("sqlite:///"):]
    return Path(caminho) if caminho and caminho != ":memory:" else None


def _montar_zip(db: Session, arquivo_zip: Path) -> None:
    from backup.backup_service import BackupService
    with zipfile.ZipFile(arquivo_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        dados = BackupService.criar_backup(db)
        z.writestr("backup.json", json.dumps(dados, ensure_ascii=False, indent=2, default=str))
        origem = _caminho_sqlite()
        if origem and origem.exists():
            copia = arquivo_zip.with_suffix(".db.tmp")
            src, dst = sqlite3.connect(str(origem)), sqlite3.connect(str(copia))
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
            z.write(copia, arcname=origem.name)
            copia.unlink()
        z.writestr("LEIA-ME.txt", (
            "Backup automático do RAAS-CAPS\n"
            f"Gerado em {datetime.now():%d/%m/%Y %H:%M}\n\n"
            "backup.json  -> use em Backup > Restaurar Backup.\n"
            "raas_caps.db -> cópia completa do banco; para voltar tudo, pare o sistema e\n"
            "                substitua o arquivo raas_caps.db da pasta do RAAS-CAPS.\n"))


def _remover_antigos(pasta: Path, manter: int) -> int:
    arquivos = sorted(pasta.glob(f"{PREFIXO_ARQUIVO}*.zip"), key=lambda p: p.name, reverse=True)
    apagados = 0
    for antigo in arquivos[manter:]:
        try:
            antigo.unlink()
            apagados += 1
        except OSError:
            pass
    return apagados


def testar_destino(destino: str) -> str:
    """Confere se a pasta existe e aceita gravação (cria e apaga um arquivo)."""
    destino = (destino or "").strip()
    if not destino:
        raise BackupAutoInvalido("Informe a pasta de destino.")
    pasta = Path(destino)
    if not pasta.is_dir():
        raise BackupAutoInvalido(
            f"Não foi possível acessar {destino}. Confira o nome/IP do computador, se a pasta está "
            "compartilhada e se este computador tem permissão (use Conectar com usuário e senha).")
    teste = pasta / f".raas_teste_{os.getpid()}.tmp"
    try:
        teste.write_text("teste", encoding="utf-8")
        teste.unlink()
    except OSError as e:
        raise BackupAutoInvalido(f"A pasta existe, mas não aceita gravação ({e.strerror or e}).")
    return f"Pasta acessível e com permissão de gravação: {destino}"


def executar(db: Session, origem: str = "manual") -> dict:
    """Gera o .zip e copia para a pasta de destino. Registra o resultado."""
    cfg = obter(db)
    if not _trava_execucao.acquire(blocking=False):
        raise BackupAutoInvalido("Já há um backup em andamento.")
    inicio = time.perf_counter()
    try:
        testar_destino(cfg["destino"])
        nome = f"{PREFIXO_ARQUIVO}{datetime.now():%Y%m%d_%H%M%S}.zip"
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / nome
            _montar_zip(db, local)
            tamanho = local.stat().st_size
            pasta = Path(cfg["destino"])
            parcial = pasta / (nome + ".parcial")
            with open(local, "rb") as fo, open(parcial, "wb") as fd:
                while bloco := fo.read(1024 * 1024):
                    fd.write(bloco)
            os.replace(parcial, pasta / nome)
        apagados = _remover_antigos(Path(cfg["destino"]), cfg["manter"])
        msg = f"{nome} ({tamanho / 1024 / 1024:.1f} MB) em {time.perf_counter() - inicio:.0f}s"
        if apagados:
            msg += f"; {apagados} backup(s) antigo(s) removido(s)"
        ok = True
    except Exception as e:  # noqa: BLE001 — qualquer falha vira status visível na tela
        ok, msg = False, str(e)
        logger.warning("Backup automático (%s) falhou: %s", origem, e)
    finally:
        _trava_execucao.release()
    _gravar(db, {
        "backup_auto_ultimo_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "backup_auto_ultimo_ok": "true" if ok else "false",
        "backup_auto_ultima_msg": msg[:500],
    })
    try:
        from sistema.log_service import LogService
        LogService.registrar(db, action="BACKUP_AUTO", method="SYSTEM", path="/backup",
                             status_code=200 if ok else 500, details=f"{origem}: {msg}"[:500])
    except Exception:  # noqa: BLE001 — o log não pode derrubar o backup
        pass
    if ok:
        logger.info("Backup automático (%s): %s", origem, msg)
    return {"ok": ok, "mensagem": msg}


# ── Agendador ───────────────────────────────────────────────────────────────
def _slot_devido(v: dict, agora: datetime) -> str | None:
    """Horário agendado que caiu nos últimos JANELA_MINUTOS e ainda não rodou."""
    if v["backup_auto_ativo"] != "true" or not v["backup_auto_destino"]:
        return None
    dias = {int(d) for d in v["backup_auto_dias"].split(",") if d.strip().isdigit()}
    if agora.weekday() not in dias:
        return None
    for h in v["backup_auto_horarios"].split(","):
        if not _RE_HORA.match(h or ""):
            continue
        hh, mm = map(int, h.split(":"))
        quando = agora.replace(hour=hh, minute=mm, second=0, microsecond=0)
        slot = quando.strftime("%Y-%m-%d %H:%M")
        if quando <= agora < quando + timedelta(minutes=JANELA_MINUTOS) and v["backup_auto_ultimo_slot"] != slot:
            return slot
    return None


def verificar_agenda(agora: datetime | None = None) -> dict | None:
    from database import SessionLocal
    db = SessionLocal()
    try:
        v = _ler(db)
        slot = _slot_devido(v, agora or datetime.now())
        if not slot:
            return None
        # Marca antes de rodar: uma falha não fica se repetindo a cada 30 s.
        _gravar(db, {"backup_auto_ultimo_slot": slot})
        return executar(db, origem=f"agendado {slot}")
    finally:
        db.close()


def iniciar_agendador(intervalo: int = 30) -> threading.Thread | None:
    """Thread que confere a agenda a cada `intervalo` segundos (não roda nos testes)."""
    if "pytest" in sys.modules or os.getenv("BACKUP_AUTO_DESLIGADO", "").lower() == "true":
        return None

    def laco():
        while True:
            try:
                verificar_agenda()
            except Exception as e:  # noqa: BLE001
                logger.warning("Agendador de backup: %s", e)
            time.sleep(intervalo)

    t = threading.Thread(target=laco, name="backup-automatico", daemon=True)
    t.start()
    return t


# ── Rede local ──────────────────────────────────────────────────────────────
def _rodar(args: list[str], timeout: int = 20) -> tuple[int, str]:
    kwargs = {"capture_output": True, "timeout": timeout}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        r = subprocess.run(args, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    enc = "oem" if sys.platform == "win32" else "utf-8"
    saida = (r.stdout or b"").decode(enc, errors="replace") + (r.stderr or b"").decode(enc, errors="replace")
    return r.returncode, saida


# Quem hospeda pasta compartilhada atende em 445 (SMB) ou 139 (NetBIOS). Testar
# a porta acha mais computador que o `net view` (que depende do serviço Computer
# Browser/SMBv1, desligado no Windows 10/11) e mais que o ping (que o firewall do
# Windows costuma bloquear mesmo com o compartilhamento ligado). É socket puro:
# funciona com o servidor em qualquer sistema, sem depender de programa externo.
_PORTAS_COMPARTILHAMENTO = (445, 139)
_TIMEOUT_PORTA = 0.4
_PARALELO_VARREDURA = 64


def _enderecos_locais() -> list[str]:
    """IPv4 das redes em que esta máquina está, sem loopback."""
    enderecos = []
    # Não envia nada: só faz o sistema escolher a interface de saída.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("203.0.113.1", 9))
            enderecos.append(s.getsockname()[0])
        except OSError:
            pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in enderecos:
                enderecos.append(ip)
    except OSError:
        pass
    return [ip for ip in enderecos if not ip.startswith("127.")]


def _porta_aberta(ip: str, porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(_TIMEOUT_PORTA)
        try:
            return s.connect_ex((ip, porta)) == 0
        except OSError:
            return False


def _atende_compartilhamento(ip: str) -> bool:
    return any(_porta_aberta(ip, porta) for porta in _PORTAS_COMPARTILHAMENTO)


def _nome_do_ip(ip: str) -> str:
    """Nome do computador pelo DNS reverso ('' quando não tem nome)."""
    try:
        return socket.gethostbyaddr(ip)[0].split(".")[0]
    except OSError:
        return ""


def _pacote_nbstat() -> bytes:
    """Pergunta NetBIOS "quem é você?" (node status para o nome curinga '*')."""
    nome = b"*" + b"\x00" * 15
    codificado = bytes(c for b in nome for c in ((b >> 4) + 0x41, (b & 0x0F) + 0x41))
    return (b"\x00\x00"                      # identificador
            b"\x00\x00"                      # flags
            b"\x00\x01"                      # 1 pergunta
            b"\x00\x00" b"\x00\x00" b"\x00\x00"
            + bytes([len(codificado)]) + codificado + b"\x00"
            + b"\x00\x21"                    # tipo NBSTAT
            b"\x00\x01")                     # classe IN


def _pular_nome(dados: bytes, pos: int) -> int:
    """Anda sobre um nome no formato DNS (sequência de pedaços com tamanho)."""
    while pos < len(dados):
        tamanho = dados[pos]
        pos += 1
        if tamanho == 0:
            return pos
        pos += tamanho
    return pos


def _ler_nome_netbios(resposta: bytes) -> str:
    """Nome da máquina na resposta NBSTAT: o registro único com sufixo 0x00."""
    pos = _pular_nome(resposta, 12) + 4      # pergunta repetida + tipo e classe
    pos = _pular_nome(resposta, pos) + 10    # nome da resposta + tipo/classe/ttl/tamanho
    if pos >= len(resposta):
        return ""
    quantos = resposta[pos]
    for i in range(quantos):
        reg = resposta[pos + 1 + i * 18: pos + 19 + i * 18]
        if len(reg) < 18:
            break
        sufixo, flags = reg[15], int.from_bytes(reg[16:18], "big")
        # 0x00 = nome da máquina; o bit 0x8000 marca nome de grupo (o workgroup).
        if sufixo == 0x00 and not flags & 0x8000:
            return reg[:15].decode("ascii", "replace").strip()
    return ""


def _nome_netbios(ip: str, timeout: float = 0.8) -> str:
    """Nome do computador perguntando direto a ele (NetBIOS, UDP 137).
    É assim que uma rede de trabalho do Windows sem DNS resolve os nomes."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        try:
            s.sendto(_pacote_nbstat(), (ip, 137))
            resposta, _ = s.recvfrom(2048)
        except OSError:
            return ""
    try:
        return _ler_nome_netbios(resposta)
    except (IndexError, ValueError):
        return ""


def _nome_do_computador(ip: str) -> str:
    """Nome pelo NetBIOS e, se não vier, pelo DNS reverso."""
    return _nome_netbios(ip) or _nome_do_ip(ip)


def _alvos_da_rede() -> list[str]:
    """Os outros endereços das faixas /24 em que esta máquina está."""
    alvos = []
    meus = _enderecos_locais()
    for meu_ip in meus:
        prefixo = meu_ip.rsplit(".", 1)[0]
        for n in range(1, 255):
            ip = f"{prefixo}.{n}"
            if ip not in meus and ip not in alvos:
                alvos.append(ip)
    return alvos


def _varrer_rede() -> list[tuple[str, str]]:
    """(ip, nome) de quem responde em 445/139 na rede local, pelo fim do IP."""
    alvos = _alvos_da_rede()
    if not alvos:
        return []
    with ThreadPoolExecutor(max_workers=_PARALELO_VARREDURA) as pool:
        vivos = [ip for ip, atende in zip(alvos, pool.map(_atende_compartilhamento, alvos)) if atende]
        nomes = list(pool.map(_nome_do_computador, vivos)) if vivos else []
    achados = list(zip(vivos, nomes))
    achados.sort(key=lambda par: int(par[0].rsplit(".", 1)[1]))
    return achados


def procurar_computadores() -> dict:
    """Computadores da rede local para escolher o destino do backup: a varredura
    de 445/139 na faixa local, mais o `net view` do Windows quando ele responde."""
    computadores, ips = [], []
    if sys.platform == "win32":
        _, saida = _rodar(["net", "view"])
        for linha in saida.splitlines():
            m = re.match(r"^\\\\(\S+)\s*(.*)$", linha.strip())
            if m:
                computadores.append({"nome": m.group(1), "descricao": m.group(2).strip()})

    vistos = {c["nome"].upper() for c in computadores}
    for ip, nome in _varrer_rede():
        if nome and nome.upper() not in vistos:
            vistos.add(nome.upper())
            computadores.append({"nome": nome, "descricao": f"Pasta compartilhada em {ip}"})
        elif not nome:
            ips.append(ip)

    aviso = ""
    if not computadores and not ips:
        aviso = ("Nenhum computador respondeu nessa rede. A busca sai do computador onde o "
                 "servidor do RAAS-CAPS está rodando, e não do computador onde você abriu a "
                 "tela — se o servidor não está na rede da unidade, ele não enxerga esses "
                 "computadores. Confira a rede acima; se estiver certa, digite o endereço da "
                 "pasta direto no campo (ex.: \\\\SAUDE-95896\\Backups).")
    elif not computadores:
        aviso = ("Os computadores abaixo responderam mas não disseram o nome. Use o IP.")
    if sys.platform != "win32":
        aviso = ("O servidor do RAAS-CAPS não está no Windows: a busca funciona, mas gravar em "
                 "pasta \\\\COMPUTADOR\\Pasta só funciona com o servidor no Windows. "
                 + aviso).strip()
    return {"computadores": computadores, "ips": ips, "aviso": aviso, "rede": _descricao_da_rede()}


def _descricao_da_rede() -> str:
    """De qual rede a busca saiu — o que separa 'não achou' de 'procurou no lugar errado'."""
    locais = _enderecos_locais()
    if not locais:
        return "sem rede local"
    return ", ".join(f"{ip} (faixa {ip.rsplit('.', 1)[0]}.x)" for ip in locais)


def listar_compartilhamentos(host: str) -> list[str]:
    host = (host or "").strip().lstrip("\\")
    if not _RE_HOST.match(host):
        raise BackupAutoInvalido("Nome ou IP do computador inválido.")
    if sys.platform != "win32":
        raise BackupAutoInvalido("A busca na rede só funciona com o servidor no Windows.")
    codigo, saida = _rodar(["net", "view", f"\\\\{host}"])
    pastas = []
    for linha in saida.splitlines():
        m = re.match(r"^(.+?)\s{2,}(Disco|Disk)\b", linha)
        if m:
            pastas.append(m.group(1).strip())
    if codigo != 0 and not pastas:
        raise BackupAutoInvalido(
            f"Não foi possível listar as pastas de {host}. Se o computador pede senha, use "
            "Conectar com usuário e senha e tente de novo.")
    return pastas


def conectar(host: str, usuario: str, senha: str) -> str:
    """Guarda usuário e senha do computador no Gerenciador de Credenciais do
    Windows; a partir daí o Windows os usa para acessar a pasta."""
    host = (host or "").strip().lstrip("\\").split("\\")[0]
    if not _RE_HOST.match(host):
        raise BackupAutoInvalido("Nome ou IP do computador inválido.")
    if not usuario:
        raise BackupAutoInvalido("Informe o usuário.")
    if sys.platform != "win32":
        raise BackupAutoInvalido("Disponível apenas com o servidor no Windows.")
    codigo, saida = _rodar(["cmdkey", f"/add:{host}", f"/user:{usuario}", f"/pass:{senha}"])
    if codigo != 0:
        raise BackupAutoInvalido(f"O Windows recusou a credencial: {saida.strip()[:200]}")
    return f"Credencial de {host} salva no Windows."
