# Relatório — Entrega 1: Infraestrutura de Engenharia

**Projeto:** PIA-OS V1.0
**Data:** 2026-08-03
**Status:** ✅ Concluída
**Aceite:** *Projeto pronto para desenvolvimento.*

## Resumo

Estabelecida a base de engenharia da plataforma: estrutura do projeto,
ambiente reproduzível via Docker, pipeline de CI, testes automatizados,
padronização de código e documentação inicial. Nenhuma decisão arquitetural do
produto foi tomada nesta fase — o escopo foi estritamente infraestrutura.

## Entregáveis

| Entregável | Implementação | Verificação |
|------------|---------------|-------------|
| Repositório Git organizado | `main`, Conventional Commits, autenticação SSH, `.gitattributes` (LF) | — |
| Estrutura inicial do projeto | Layout `src/`, application factory FastAPI, `/health` e `/` | — |
| Docker configurado | `Dockerfile` multi-stage (usuário não-root, healthcheck) + `docker-compose.yml` (API + PostgreSQL 16) | `docker compose up --build` → ambos *healthy* |
| Ambiente reproduzível | `pyproject.toml`, `.env.example`, `pydantic-settings` (prefixo `PIA_`) | — |
| GitHub Actions | `.github/workflows/ci.yml` — Ruff, Black, Pytest, build da imagem | CI verde no `main` |
| Framework de testes | Pytest + cobertura | **2 passed, 100%** |
| Padronização de código | Ruff + Black + `pre-commit` | `ruff check` e `black --check` sem apontamentos |
| Documentação inicial | MkDocs Material (`docs/`), `README.md`, `CONTRIBUTING.md` | — |

## Verificações realizadas

- `ruff check .` → *All checks passed*
- `black --check .` → *8 files unchanged*
- `pytest` → *2 passed*, cobertura **100%**
- `docker compose up --build` → `pia-os-db` e `pia-os-api` *(healthy)*
- `GET /health` → `{"status":"ok","service":"pia-os","version":"0.1.0"}`
- CI (GitHub Actions) → verde no `main`

## Fora do escopo (por design)

Adiado para as próximas entregas, conforme o Plano de Entregas:

- Camada de banco (SQLAlchemy), migrações (Alembic), logging, tratamento de erros → **Entrega 2**
- Modelos de dados, CRUD, versionamento, metadados → **Entrega 3**

## Como executar

```bash
# Ambiente completo (Docker)
cp .env.example .env
docker compose up --build
# → http://localhost:8000/health  |  http://localhost:8000/docs

# Ambiente local (Python 3.12+)
pip install -e ".[dev]"
uvicorn pia_os.main:app --reload
```

## Pendências / notas para o cliente

- **Pré-requisito de ambiente:** o Docker Desktop no Windows exige WSL2
  (`wsl --install`). Validado nesta máquina.
- Antes das Entregas 3–4, é necessária a especificação do **modelo de memória**
  e da **governança de acesso** para prosseguir sem retrabalho.
