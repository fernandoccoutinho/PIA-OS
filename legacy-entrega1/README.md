# PIA-OS — Entrega 1 (Infraestrutura de Engenharia)

Esta pasta contém a **Entrega 1** do PIA-OS: a infraestrutura inicial de
engenharia do projeto (repositório organizado, ambiente reproduzível,
framework de testes, padronização de código e documentação inicial).

O backend operacional (Entrega 2) vive em [`../backend`](../backend) e
substitui esta base a partir do Módulo 2.1. Esta pasta é mantida como
registro histórico da Entrega 1 e não recebe novas funcionalidades.

## Ambiente

```bash
python -m venv .venv
source .venv/bin/activate     # Linux/macOS
# .venv\Scripts\Activate.ps1  # Windows (PowerShell)
pip install -e ".[dev]"
pre-commit install
```

## Padrões de código

- **Formatação:** [Black](https://black.readthedocs.io/) (`black .`)
- **Lint / imports:** [Ruff](https://docs.astral.sh/ruff/) (`ruff check .`)
- **Testes:** [Pytest](https://docs.pytest.org/) com cobertura (`pytest`)

Ver [`CONTRIBUTING.md`](CONTRIBUTING.md) para o guia completo.

## Executando localmente

```bash
uvicorn pia_os.main:app --reload
```

O endpoint `/health` expõe o status do serviço.
