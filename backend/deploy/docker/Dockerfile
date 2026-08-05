# Dockerfile padrão — usado por deploy/compose/docker-compose.yml (o
# "just works" para self-hosted). Paridade de produção: usuário não-root,
# HEALTHCHECK real via GET /health, sem dependências de desenvolvimento.
#
# Para desenvolvimento (hot reload) ou uma imagem de produção multi-stage
# ainda mais enxuta, ver Dockerfile.dev / Dockerfile.prod neste mesmo
# diretório — cada um é buildável isoladamente (ver docs/DOCKER.md sobre
# a decisão de manter os três arquivos autocontidos, com pequena
# duplicação de setup, em vez de uma cadeia de imagens-base).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system piaos \
    && useradd --system --gid piaos --home-dir /srv/app --shell /usr/sbin/nologin piaos

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .
RUN chown -R piaos:piaos /srv/app

USER piaos

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
