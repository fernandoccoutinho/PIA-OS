# Primeiros passos

## Pré-requisitos

- [Python 3.12+](https://www.python.org/)
- [Docker](https://www.docker.com/) e Docker Compose (para o ambiente completo)
- [Git](https://git-scm.com/)

## Opção A — Ambiente completo via Docker (recomendado)

Sobe a API + PostgreSQL com um comando:

```bash
cp .env.example .env
docker compose up --build
```

A API fica disponível em <http://localhost:8000> e a documentação interativa
(Swagger) em <http://localhost:8000/docs>.

Verifique a saúde do serviço:

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"pia-os","version":"0.1.0"}
```

## Opção B — Ambiente Python local (sem Docker)

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
uvicorn pia_os.main:app --reload
```

## Fluxo de desenvolvimento

```bash
ruff check .        # lint
black .             # formatação
pytest              # testes + cobertura
pre-commit install  # (uma vez) ativa os hooks de commit
mkdocs serve        # documentação em http://localhost:8000
```
