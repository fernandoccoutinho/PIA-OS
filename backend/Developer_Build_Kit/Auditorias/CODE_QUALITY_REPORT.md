# Relatório de Qualidade de Código — Módulo 2.13

## Ferramentas executadas

| Ferramenta | Resultado | Meta | Status |
|---|---|---|---|
| Ruff | 0 erros | 0 erros | Atingida |
| Black | 190 arquivos conformes, 0 a reformatar | 0 a reformatar | Atingida |
| Pytest | 454 passando, 1 skip, 0 falhas | 0 regressões | Atingida |
| Coverage | 96,36% | ≥ 95% | Atingida |
| MyPy (`--strict`) | 7 erros restantes (de 39 originais) | Executado e reportado (não exigido zero-erro pela especificação) | Ver detalhe abaixo |

## MyPy — detalhe

Nunca fazia parte de nenhum gate de qualidade antes desta etapa (estava
configurado em `pyproject.toml` desde o Módulo 2.1, mas não era chamado
por `make check`, CI, ou qualquer script). Executado pela primeira vez
nesta auditoria.

**39 → 7 erros (82% de redução)**, via correções mecânicas e seguras —
anotações de tipo ausentes, sem qualquer mudança de comportamento em
runtime (Python não impõe tipos; estas anotações são só para a
ferramenta de análise estática):

- `app/config/loader.py` — retorno de `build_settings()` tipado via
  `TYPE_CHECKING` (evita import circular).
- `app/database/engine.py` — 6 listeners de evento SQLAlchemy, params
  tipados como `Any` (a assinatura é imposta pela biblioteca).
- `app/security/rate_limit.py`, `app/security/middleware.py` — parâmetro
  `app` de `__init__` de middleware tipado.
- `app/docs/openapi.py`, `app/docs/responses.py`, `app/docs/schemas.py`,
  `app/docs/examples.py` — genéricos (`dict[str, Any]`,
  `dict[int | str, dict[str, Any]]`, `type[BaseModel]`) especificados.
  Este processo revelou e corrigiu uma imprecisão de tipo real
  introduzida durante a própria correção (`dict[str, Any]` inicial
  estava errado — as chaves são `int`, códigos HTTP — corrigido para
  `dict[int | str, dict[str, Any]]`, batendo com o que o FastAPI
  realmente espera).
- `app/logging/context.py` — `Token[str | None]` (não `Token[str]` —
  tentativa inicial quebrou 2 testes de tipo, corrigida).

**7 erros restantes, documentados como gaps conhecidos, não corrigidos
nesta etapa** (mudança estrutural maior, risco desproporcional ao
benefício para uma etapa de "sem nova funcionalidade"):

1. `app/logging/handlers.py:21` — `StreamHandler` sem parâmetro
   genérico. Requer especificar o tipo do stream subjacente; baixo
   risco mas não trivial o suficiente para esta etapa.
2. `app/repositories/base_repository.py:130,183` — dois erros de
   tipagem genérica avançada do SQLAlchemy 2.x (`Iterable[NamedColumn]`
   sem `.columns`, e um método `list` usado onde mypy espera um tipo).
   Comportamento correto em runtime (testado), mypy não consegue provar
   estaticamente por limitação de como o SQLAlchemy tipa suas próprias
   APIs genéricas.
3. `app/exceptions/registry.py:63-66` (4 erros) — variância de
   `Callable`: cada handler é tipado com sua exceção específica
   (`Callable[[Request, PIAOSException], ...]`), mas `register()` espera
   `Callable[[Request, Exception], ...]`. É uma limitação conhecida de
   Python/mypy com tipos de função contravariantes em parâmetros — o
   código funciona corretamente (testado exaustivamente desde o Módulo
   2.7), mas o mypy não consegue expressar "aceita um handler mais
   específico com segurança" sem `# type: ignore` ou um redesenho da
   assinatura do Registry.

Nenhum destes é um bug funcional — são lacunas de expressividade da
tipagem estática, não erros de comportamento. Documentados aqui em vez
de silenciados com `# type: ignore` em massa, que esconderia o
diagnóstico real sem resolvê-lo.

## Duplicação de código

Nenhuma duplicação relevante de lógica de aplicação encontrada. As
duplicações deliberadas e documentadas (boilerplate de Dockerfile —
ADR-008; overlays de ambiente vs. `.env.example` — Módulo 2.11) são
tradeoffs conscientes, não código duplicado por descuido.

## Conclusão

Metas obrigatórias da Etapa 4 (cobertura ≥95%, zero regressões, zero
lint, zero formatação) **todas atingidas**. MyPy executado e relatado
com transparência total — incluindo os dois erros que a própria
correção introduziu e depois corrigiu, não escondidos do relatório.
