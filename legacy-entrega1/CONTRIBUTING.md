# Guia de Contribuição

## Ambiente

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1      # Windows (PowerShell)
# source .venv/bin/activate     # Linux/macOS
pip install -e ".[dev]"
pre-commit install
```

## Padrões de código

- **Formatação:** [Black](https://black.readthedocs.io/) (`black .`)
- **Lint / imports:** [Ruff](https://docs.astral.sh/ruff/) (`ruff check .`)
- **Testes:** [Pytest](https://docs.pytest.org/) com cobertura (`pytest`)

Todo o conjunto é validado automaticamente pelos hooks de `pre-commit` e pela
pipeline de CI (GitHub Actions) em cada push e pull request.

## Fluxo de trabalho

1. Crie um branch a partir de `main`.
2. Faça as alterações com testes correspondentes.
3. Garanta que `ruff check .`, `black --check .` e `pytest` passam localmente.
4. Abra um Pull Request; a CI precisa estar verde para o merge.

## Convenção de commits

Usamos [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat:     nova funcionalidade
fix:      correção de bug
docs:     documentação
chore:    manutenção/infra
test:     testes
refactor: refatoração sem mudança de comportamento
```
