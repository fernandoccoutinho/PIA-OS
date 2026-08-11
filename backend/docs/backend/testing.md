# Infraestrutura de Testes — PIA-OS Backend

> Movido de `docs/TESTING.md` para `docs/backend/testing.md` no Módulo 2.12.


Suíte unificada, organizada e pronta para CI/CD (Módulo 2.10). Reorganiza
integralmente os testes dos Módulos 2.1-2.9 — nenhum teste foi
duplicado, todos foram reaproveitados.

## Estrutura

```
tests/
├── unit/                    # testes isolados, sem dependências externas reais
│   ├── api/                   # app/api/, app/docs/
│   ├── config/                  # app/config/
│   ├── database/                  # app/database/ (sem Postgres real)
│   ├── exceptions/                   # app/exceptions/
│   ├── logging/                        # app/logging/, app/utils/logger.py
│   ├── middleware/                        # app/middleware/
│   ├── models/                              # app/models/
│   ├── repositories/                          # app/repositories/
│   └── security/                                # app/security/
├── integration/              # via TestClient contra o app real (main.app)
│   ├── api/                    # endpoints, ciclo de vida da aplicação
│   ├── database/                 # conectividade real (skip gracioso sem Postgres)
│   └── logging/                    # logging de requisição ponta a ponta
├── fixtures/                 # aplicação, banco, configuração, usuário (estrutura)
├── factories/                  # geração de dados de teste
├── helpers/                      # assertions e mocks reutilizáveis
├── conftest.py                     # reexporta as fixtures para toda a árvore
└── test_infrastructure.py            # testa a própria infraestrutura de teste

pytest.ini       # configuração do pytest (testpaths, markers, cobertura)
coverage.ini      # configuração de cobertura (fonte, relatórios, meta 95%)
```

## Como executar localmente

```bash
make test              # suíte completa, com cobertura
make check              # lint + format-check + testes (o que o CI roda)
make ci                   # mesmo que make check, via script portátil
```

Ou diretamente:

```bash
pytest                                    # tudo
pytest tests/unit                          # só unitários
pytest tests/integration                    # só integração
pytest tests/unit/security                    # só um módulo
pytest -k "test_trusted_host"                   # por nome
```

Relatórios de cobertura: terminal (sempre), HTML em `htmlcov/index.html`,
XML em `coverage.xml` (consumível por ferramentas de CI de terceiros —
Codecov, SonarQube, etc.).

## Test Pyramid

- **Unitário** (`tests/unit/`) — maioria da suíte. Isola uma função/classe,
  sem banco real, sem servidor HTTP real. Rápido, determinístico.
- **Integração** (`tests/integration/`) — sobe a aplicação real
  (`TestClient(app)`, frequentemente como context manager para disparar
  o ciclo de vida) e verifica o comportamento ponta a ponta através de
  várias camadas.
- **Fora de escopo nesta etapa** (conforme a especificação do Módulo
  2.10): testes de carga, E2E, UI, IA, Objetos Cognitivos.

## Fixtures

| Arquivo | Fixtures |
|---|---|
| `fixtures/database.py` | `sqlite_engine`, `sqlite_session`, `sqlite_session_factory`, `SampleModel` |
| `fixtures/application.py` | `client` (com lifespan), `client_no_lifespan` |
| `fixtures/settings.py` | `test_settings`, `production_settings` |
| `fixtures/users.py` | `fake_user_payload` (estrutura — sem modelo de usuário real ainda) |

Todas expostas via `tests/conftest.py` — nenhum subdiretório precisa de
um `conftest.py` próprio. `client` dispara o startup/shutdown real da
aplicação (`with TestClient(app)`); testes existentes que criam
`TestClient(app)` diretamente no módulo continuam funcionando sem
alteração — não foram retroativamente migrados para a fixture central,
para não arriscar regressão numa suíte que já estava verde.

## Factories

`factories/models.py::make_sample_model()` / `make_sample_models(n)` —
gera instâncias de `SampleModel` (o modelo de teste genérico da suíte de
persistência/ORM) com campos únicos por padrão, sobrescrevíveis via kwargs.
Nenhum modelo de domínio existe ainda — o padrão aqui é o que factories
de modelos futuros devem seguir.

## Helpers

- `helpers/assertions.py` — `assert_error_envelope(body, status_code=..., code=...)`,
  `assert_has_standard_headers(headers)`, `assert_valid_component_status(component)`.
- `helpers/mocks.py` — `make_async_session_mock()`, `make_failing_engine_mock(exc)`,
  `make_session_factory_mock()`.

## Cobertura

Meta: **95% da infraestrutura** (`coverage.ini`, `fail_under = 95`) —
atingida (**96,34%** na entrega deste módulo). `pytest` falha
automaticamente se a cobertura cair abaixo da meta (via `--cov-fail-under`
implícito em `fail_under` do `coverage.ini`).

Lacunas conhecidas e aceitas (não atingem 100%, mas não bloqueiam a meta):
alguns branches de `database/engine.py`/`session.py`/`migrations.py`
exigem uma conexão PostgreSQL real (não disponível neste ambiente de
sandbox/CI) — cobertos onde possível chamando os listeners/funções
diretamente com dados simulados; o restante fica documentado, não escondido.

## Testes negativos

Cenários de falha cobertos deliberadamente, não só o caminho feliz:
configuração inválida em produção (`test_startup_validation.py`), banco
indisponível (`test_database_health.py`, mockado), exceções em toda a
hierarquia (`tests/unit/exceptions/`), headers/hosts/Content-Type
inválidos (`tests/unit/security/`), payload grande demais, rate limit
excedido, erro interno inesperado nunca vazando stack trace
(`tests/unit/exceptions/test_exceptions_environment_behavior.py`).

## CI/CD

`scripts/run_ci_checks.sh` — script portátil (bash puro, sem depender de
`make` nem de sintaxe de um CI específico): lint, format check, testes
com cobertura. Usável por GitHub Actions, GitLab CI, CircleCI, Jenkins,
ou localmente. `.github/workflows/ci.yml` (Módulo 2.1, atualizado aqui)
chama `make check`, que roda os mesmos três passos.

```bash
bash scripts/run_ci_checks.sh   # ou: make ci
```

## Performance

Estrutura preparada (a suíte já roda em poucos segundos, sem qualquer
teste lento) — nenhum benchmark implementado nesta etapa, conforme o
escopo do Módulo 2.10. O marker `slow` já está declarado em `pytest.ini`
para quando a suíte crescer o suficiente para precisar segmentar
execução por velocidade.

## Como criar um novo teste

1. Descubra a pasta certa: `tests/unit/<camada>/` para algo isolado,
   `tests/integration/<camada>/` para algo que sobe o app real.
2. Nomeie o arquivo `test_<assunto>.py`, funções `test_<comportamento>`.
3. Reaproveite fixtures/factories/helpers existentes antes de escrever
   um mock do zero — ver tabelas acima.
4. Rode `make check` antes de abrir um PR.

## Como criar uma nova fixture/factory/helper

- **Fixture** nova de infraestrutura compartilhada → `tests/fixtures/<assunto>.py`,
  depois reexporte em `tests/conftest.py` (`from tests.fixtures.<assunto> import <nome>  # noqa: F401`).
- **Factory** de um modelo novo → `tests/factories/models.py` (ou um
  arquivo novo, se o volume justificar), seguindo o padrão de contador
  incremental para campos únicos.
- **Helper** de asserção/mock repetido em 3+ testes → `tests/helpers/`.
  Menos que isso, mantenha inline — abstração prematura custa mais do
  que economiza.
