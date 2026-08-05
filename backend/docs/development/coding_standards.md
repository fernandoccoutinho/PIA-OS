# Coding Standards — PIA-OS Backend

Convenções de nomenclatura e estrutura de camadas já estão documentadas
em [`CONTRIBUTING.md`](../../CONTRIBUTING.md) (seções "Convenções de
nomenclatura" e "Estrutura de camadas") — este documento não as repete,
só complementa com o que `CONTRIBUTING.md` não cobre em detalhe.

## Ferramentas (fonte de verdade: configuração real, não esta lista)

- **Ruff** — `pyproject.toml::[tool.ruff]`. Regras ativas: `E`, `F`, `I`,
  `UP`, `B`, `SIM`.
- **Black** — `pyproject.toml::[tool.black]`. `line-length = 100`.
- **mypy** — `pyproject.toml::[tool.mypy]`. `strict = true` (não rodado
  automaticamente no CI ainda — ver `docs/backend/testing.md`).

```bash
make check   # ruff + black --check + pytest — o que o CI roda
```

## Tipagem

Type hints completos em toda função pública — já é o padrão em 100% do
código existente (verificável: nenhuma função pública em `app/` está sem
anotação de tipo). `Any` só com justificativa explícita em comentário.

## Docstrings

Português, no topo do módulo — explicam *por que*, não *o que* (o
código já diz o quê). Um docstring que só repete o nome da função em
prosa não agrega nada. Ver qualquer arquivo em `app/` como referência de
tom — ex.: `app/exceptions/base.py`, `app/security/middleware.py`.

## Comentários arquiteturais

Quando uma decisão não é óbvia a partir do código (por que um padrão
comum foi evitado, por que uma dependência não foi usada), um comentário
curto no local + um ADR (se o impacto atravessar módulos) — ver
[`docs/adr/index.md`](../adr/index.md) para o critério de quando algo
vira ADR.

## Referências cruzadas

Toda decisão não-óbvia documentada tanto no código (comentário curto)
quanto na documentação (`docs/backend/<camada>.md` ou um ADR) — nunca só
num lugar. Isso é o que permite a um desenvolvedor novo entender uma
escolha sem depender de perguntar para quem a fez.
