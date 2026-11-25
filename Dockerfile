# Imagem de produção do RAAS-CAPS (edição servidor).
FROM python:3.12-slim

# Não gerar .pyc e não bufferizar a saída: o log aparece no `docker logs` na hora.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Sao_Paulo

WORKDIR /app

# As dependências vêm antes do código: enquanto o requirements.txt não muda, o
# Docker reaproveita esta camada e o build de uma alteração de código é rápido.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Usuário sem privilégios. Um container que roda como root e é comprometido por
# uma falha da aplicação dá root ao atacante; sem isso o resto do endurecimento
# do servidor conta pouco.
RUN useradd --create-home --shell /usr/sbin/nologin raas \
    && mkdir -p /app/uploads /app/exports /app/logs /app/data \
    && chown -R raas:raas /app
USER raas

EXPOSE 8000

# O healthcheck confere o banco também (/saude faz um SELECT 1): assim o Docker
# reinicia o container que está de pé mas sem conseguir atender.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=4).status == 200 else 1)"

# UvicornWorker: o app é ASGI (FastAPI), não WSGI.
# --forwarded-allow-ips: confia nos X-Forwarded-* do nginx (que está na mesma
# rede do compose), para a aplicação saber que o acesso original foi por HTTPS.
CMD ["gunicorn", "main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "3", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--forwarded-allow-ips", "*"]
