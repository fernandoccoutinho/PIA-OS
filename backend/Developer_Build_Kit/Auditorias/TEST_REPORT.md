# Relatório de Testes — Módulo 2.13

## Execução completa

```
454 passed, 1 skipped in ~5s
TOTAL coverage: 96.36% (meta: ≥95%)
```

O único skip é conhecido e documentado desde o Módulo 2.3: `checkedout()`
do pool de conexões não é suportado pelo `SingletonThreadPool` do SQLite
(usado nos testes de repositório/UoW em memória) — não é uma falha, é
uma limitação da engine de teste que não existe com o PostgreSQL real.

## Distribuição por camada

| Categoria | Local | O que cobre |
|---|---|---|
| Unitário | `tests/unit/{api,config,database,deploy,exceptions,logging,middleware,models,repositories,security,docs}/` | Isolado, sem infraestrutura externa real |
| Integração | `tests/integration/{api,database,logging}/` | Via `TestClient` contra o app real, incluindo ciclo de vida (`with TestClient(app):`) |
| Infraestrutura de teste | `tests/test_infrastructure.py` | Valida que fixtures/factories/helpers funcionam de verdade |

## Cobertura por área (resumo — detalhe completo em `htmlcov/index.html`, gerado a cada `make test`)

- `app/security/`, `app/exceptions/`, `app/logging/`, `app/schemas/`,
  `app/routers/` (majoritariamente), `app/utils/logger.py`: **100%**.
- `app/database/engine.py`, `app/database/session.py`: cobertos via
  chamada direta dos listeners/funções com dados simulados — sem
  PostgreSQL real neste ambiente de sandbox/CI.
- `app/repositories/repository_protocol.py`: 67% — métodos de `Protocol`
  (`...` no corpo) não são chamados diretamente, são contratos de
  tipagem; a cobertura "faltante" aqui é estrutural, não uma lacuna de
  teste real.
- `app/core/lifespan.py`: coberto desde a correção do Módulo 2.10 (testes
  usam `with TestClient(app):` para disparar o ciclo de vida real).

## Testes negativos (amostra — não exaustivo)

- Configuração inválida em produção (`SECRET_KEY` padrão rejeitado).
- Banco indisponível (mockado — `check_database_health` retorna
  `unavailable` sem lançar exceção).
- Toda a hierarquia de exceções (`PIAOSException` e subclasses) testada
  individualmente, incluindo o handler de `SQLAlchemyError` que nunca
  vaza mensagem do driver.
- Segurança: host não confiável, payload grande demais, Content-Type não
  suportado, rate limit excedido — todos com verificação do código de
  erro E do log de violação gerado.
- Erro interno inesperado nunca expõe stack trace em produção (`debug=False`).

## Validações específicas desta etapa (Módulo 2.13)

- Suíte completa re-executada após todas as correções de tipo do
  `CODE_QUALITY_REPORT.md` — **zero regressão** (454 → 454 passando).
- `make check-docs` — zero problema de consistência documental.
- YAML dos 4 `docker-compose.*.yml` — todos válidos.
- XML dos 4 `.drawio` — todos bem formados.
- Geração do schema OpenAPI (`app.openapi()`) — sem erros, `/docs`,
  `/redoc`, `/openapi.json` todos HTTP 200.

## Conclusão

Suíte estável, determinística, sem flakiness observada em múltiplas
execuções ao longo desta sessão. Meta de cobertura mantida acima do
mínimo em todas as reverificações desta etapa.
