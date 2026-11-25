"""
Utilitários de manutenção chamados pelos scripts .bat (somente biblioteca padrão,
para funcionar antes de as dependências do projeto estarem instaladas).

Uso:  python -m sistema.manutencao <comando> [argumentos]

  requisitos                      imprime o SHA-256 do requirements.txt
  ip                              imprime o IP deste computador na rede local
  agora                           imprime o horário atual em segundos (epoch)
  backup [mantem_dias]            snapshot diário do banco SQLite em backups_auto/
  rotacionar ARQUIVO [mb] [n]     rotaciona o log quando passa de `mb` MB, guardando `n` cópias
  abrir URL [segundos]            abre o navegador padrão após alguns segundos
"""
import hashlib
import os
import socket
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

PASTA_BACKUP = "backups_auto"


def hash_requisitos(arquivo: str = "requirements.txt") -> str:
    return hashlib.sha256(Path(arquivo).read_bytes()).hexdigest()


def ip_local() -> Optional[str]:
    """IP da interface usada para sair para a rede (nenhum pacote é enviado)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def _caminho_sqlite(database_url: str) -> Optional[Path]:
    if not database_url.startswith("sqlite:///"):
        return None
    caminho = database_url[len("sqlite:///"):]
    return Path(caminho) if caminho and caminho != ":memory:" else None


def backup_diario(database_url: str, pasta: str = PASTA_BACKUP, mantem_dias: int = 14,
                  hoje: Optional[datetime] = None) -> str:
    """Cria um snapshot consistente do banco (1 por dia) e apaga os mais antigos.

    Usa a API de backup do SQLite, que é segura mesmo com o modo WAL ligado.
    Retorna uma mensagem descrevendo o que foi feito.
    """
    origem = _caminho_sqlite(database_url)
    if origem is None:
        return "backup automatico ignorado: o banco nao e SQLite"
    if not origem.exists():
        return "backup automatico ignorado: o banco ainda nao existe"

    hoje = hoje or datetime.now()
    destino_dir = Path(pasta)
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"{origem.stem}_{hoje:%Y%m%d}.db"

    if destino.exists():
        msg = f"backup de hoje ja existe: {destino}"
    else:
        temporario = destino.with_suffix(".tmp")
        src = sqlite3.connect(str(origem))
        dst = sqlite3.connect(str(temporario))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        os.replace(temporario, destino)
        msg = f"backup criado: {destino}"

    limite = hoje.timestamp() - mantem_dias * 86400
    apagados = 0
    for antigo in destino_dir.glob(f"{origem.stem}_*.db"):
        if antigo != destino and antigo.stat().st_mtime < limite:
            antigo.unlink()
            apagados += 1
    if apagados:
        msg += f" ({apagados} antigo(s) removido(s))"
    return msg


def rotacionar_log(arquivo: str, max_mb: float = 10, copias: int = 5) -> str:
    """Se o log passou de `max_mb`, vira arquivo.1 (arquivo.1 -> .2 ...), mantendo `copias`."""
    log = Path(arquivo)
    if not log.exists() or log.stat().st_size <= max_mb * 1024 * 1024:
        return ""
    for i in range(copias, 0, -1):
        atual = Path(f"{arquivo}.{i}")
        if not atual.exists():
            continue
        if i == copias:
            atual.unlink()
        else:
            os.replace(atual, Path(f"{arquivo}.{i + 1}"))
    os.replace(log, Path(f"{arquivo}.1"))
    return f"log rotacionado: {arquivo}"


def abrir_navegador(url: str, atraso: float = 5) -> None:
    import webbrowser
    time.sleep(atraso)
    webbrowser.open(url)


def main(argv: list) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "requisitos":
        print(hash_requisitos())
    elif cmd == "ip":
        ip = ip_local()
        if ip:
            print(ip)
    elif cmd == "agora":
        print(int(time.time()))
    elif cmd == "backup":
        url = os.getenv("DATABASE_URL", "sqlite:///./raas_caps.db")
        print(backup_diario(url, mantem_dias=int(args[0]) if args else 14))
    elif cmd == "rotacionar" and args:
        msg = rotacionar_log(args[0], float(args[1]) if len(args) > 1 else 10,
                             int(args[2]) if len(args) > 2 else 5)
        if msg:
            print(msg)
    elif cmd == "abrir" and args:
        abrir_navegador(args[0], float(args[1]) if len(args) > 1 else 5)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
