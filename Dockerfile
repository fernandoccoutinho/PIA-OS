# syntax=docker/dockerfile:1

# ---------- Estágio de build ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copia apenas os metadados primeiro para aproveitar o cache de camadas.
COPY pyproject.toml README.md ./
COPY src ./src

# Instala o projeto em um prefixo isolado que será copiado para a imagem final.
RUN pip install --upgrade pip build && \
    pip install --prefix=/install .

# ---------- Imagem final ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Usuário não-root por segurança.
RUN groupadd --system pia && useradd --system --gid pia --create-home pia

WORKDIR /app

COPY --from=builder /install /usr/local
COPY src ./src

USER pia

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/health').status==200 else sys.exit(1)"

CMD ["uvicorn", "pia_os.main:app", "--host", "0.0.0.0", "--port", "8000"]
