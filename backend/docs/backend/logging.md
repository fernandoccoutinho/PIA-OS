# Sistema de Logs e Observabilidade — PIA-OS Backend

> Movido de `docs/LOGGING.md` para `docs/backend/logging.md` no Módulo 2.12.


Infraestrutura completa de logging do PIA-OS (Módulo 2.6). Sem regra de
negócio, autenticação ou IA — apenas a base de observabilidade que todo
módulo futuro usa.

## Estrutura

```
app/logging/
├── logger.py       # Logger Central — única fábrica (`get_logger`)
├── context.py        # LoggingContext — request_id/correlation_id/trace_id/session_id
├── filters.py         # ContextFilter, SensitiveDataFilter, DuplicateFilter, MinLevelFilter
├── formatters.py      # JsonFormatter (produção), TextFormatter (dev)
├── handlers.py        # console, file (rotação real), syslog (estrutura)
├── config.py           # monta tudo a partir de Settings (Módulo 2.2)
├── events.py            # biblioteca de eventos padronizados
└── middleware.py         # LoggingMiddleware — request_received/completed

app/core/
└── logging.py       # setup_logging() — bootstrap oficial, chamado no startup
```

`app/logging/` é infraestrutura genérica (poderia ser extraída para
outro projeto); `app/core/logging.py` é a "cola" específica do PIA-OS que
decide quando/como ela é inicializada — chamado uma única vez, em
`app.core.lifespan`.

## Logger Central — regra obrigatória

**Proibido criar loggers isolados.** Todo módulo usa:

```python
from app.logging import get_logger
logger = get_logger(__name__)
```

`app.utils.logger.get_logger` (Módulos 2.1–2.5) continua funcionando —
é um reexport direto desta mesma fábrica, não uma segunda implementação.
Não crie um terceiro caminho.

## Log estruturado — campos

Cada evento carrega, quando disponível: `timestamp`, `level`,
`request_id`, `correlation_id`, `session_id`, `module`, `function`,
`message`, `duration_ms`, `environment`. Campos ausentes **não aparecem**
no JSON (não como `null`) nem no texto — são genuinamente opcionais.

Níveis: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` — os cinco
padrão do `logging`, nenhum nível customizado.

## Contexto — como funciona

`LoggingContext` usa `contextvars` (não `threading.local`): funciona
corretamente com código assíncrono, onde cada task tem sua própria cópia.
`ContextFilter` injeta os campos setados em todo `LogRecord`, sem exigir
que o chamador passe `extra=` manualmente:

```python
from app.logging import logging_context

with logging_context(request_id="abc-123"):
    logger.info("algo aconteceu")  # request_id aparece automaticamente
    repo.get_by_id(42)  # logs dentro do repositório também incluem request_id
```

`LoggingMiddleware` já faz isso para toda requisição HTTP — nenhum
endpoint precisa gerenciar contexto manualmente.

**Nota técnica relevante para quem for estender isso:** o filtro de
contexto é anexado a cada *handler*, não ao logger raiz. Um filtro
anexado a um `Logger` só roda quando o log é emitido exatamente por
aquele logger — loggers filhos que apenas propagam (o caso normal, já
que o código sempre usa loggers nomeados como `"app.database"`) não
disparam o filtro de um ancestral. Um filtro de `Handler`, em contraste,
roda sempre que aquele handler processa um record, não importa a origem.
Por isso `ContextFilter`/`SensitiveDataFilter` são anexados a cada
handler individualmente em `app/logging/config.py`, não ao logger raiz.

## Como registrar um evento

Use a biblioteca de eventos padronizados em vez de mensagens livres —
mantém os logs pesquisáveis por `event=...` independente do texto:

```python
from app.logging import get_logger, events

logger = get_logger(__name__)
events.log_event(logger, events.DATABASE_UNAVAILABLE, host="db", retry_in_s=5)
```

Eventos já definidos: `APPLICATION_STARTED`, `APPLICATION_STOPPED`,
`CONFIGURATION_LOADED`, `REQUEST_RECEIVED`, `REQUEST_COMPLETED`,
`INTERNAL_ERROR`, `UNHANDLED_EXCEPTION`, `DATABASE_UNAVAILABLE`,
`DATABASE_RECONNECTED`. Para um evento novo, adicione a constante em
`app/logging/events.py` — não use uma string solta no meio do código.

Para registrar uma exceção com stack trace (apenas em desenvolvimento):

```python
events.log_event(logger, events.UNHANDLED_EXCEPTION, level=logging.ERROR, exc_info=exc)
```

`exc_info` é sempre passado como parâmetro nomeado de `log_event`, nunca
dentro de campos livres — colocá-lo em `extra={}` faz o próprio
`logging` da stdlib lançar erro (`exc_info` já é um atributo reservado
de todo `LogRecord`). Isso já aconteceu uma vez durante o desenvolvimento
deste módulo — ver "Erros encontrados e corrigidos" abaixo.

## Middleware de requisição

`LoggingMiddleware` registra automaticamente, para toda requisição:
início (`request_received`), fim (`request_completed` — com status HTTP,
método, rota e duração), e propaga `request_id` (de
`RequestIDMiddleware`) e `X-Correlation-ID` (se o cliente enviar o
header) via `LoggingContext` durante todo o processamento.

Toda exceção tratada pela API é registrada automaticamente por
`app.middleware.exception_handler` — tipo, mensagem, `request_id`, e
stack trace **apenas quando `settings.debug` está ativo** (nunca em
produção, para não vazar detalhes de implementação em um canal —
logs — tipicamente menos controlado que o próprio corpo da resposta
HTTP, que já omite a stack trace sempre).

## Configuração (vem inteiramente do Módulo 2.2)

| Variável | Valores | Padrão |
|---|---|---|
| `LOG_LEVEL` | DEBUG/INFO/WARNING/ERROR/CRITICAL | INFO |
| `LOG_FORMAT` | json / text | json |
| `LOG_DESTINATION` | lista separada por vírgula: console, file, syslog | console |
| `LOG_FILE_PATH` | caminho do arquivo (obrigatório se `file` estiver em `LOG_DESTINATION`) | (vazio) |
| `LOG_ROTATION_MAX_BYTES` | tamanho máximo antes de rotacionar | 10485760 (10 MiB) |
| `LOG_ROTATION_BACKUP_COUNT` | quantos arquivos rotacionados manter | 5 |

`text` é recomendado em desenvolvimento (legível no terminal); `json` é
o padrão de produção (parseável por qualquer coletor de logs).

## Handlers

- **Console** — sempre disponível, é o fallback se nenhum destino
  válido resultar em handler algum (nunca deixamos a aplicação sem
  handler, o que cairia no `logging.lastResort`, sem formatação).
- **File** — rotação **real** via `RotatingFileHandler` da stdlib (não
  apenas estrutura) — testado inclusive quanto à rotação de fato
  ocorrer (`test_logging_handlers.py`).
- **Syslog** — estrutura apenas, como pedido explicitamente no escopo.
  Tenta construir um `SysLogHandler` real, mas retorna `None` (sem
  lançar) se `/dev/log` não estiver disponível — nunca impede a
  aplicação de iniciar por causa de um destino experimental. Nenhuma
  configuração de host/porta de syslog remoto foi adicionada.

## Filtros

- `ContextFilter` — injeta os campos de `LoggingContext` (sempre ativo).
- `SensitiveDataFilter` — mascara `password`, `secret_key`, `token`,
  `authorization`, `api_key`, `access_token`, `refresh_token`,
  `database_url` quando aparecem como campos estruturados (`extra=`),
  não inspeciona o texto livre da mensagem por conteúdo.
- `DuplicateFilter` — disponível, não ativado por padrão (suprime
  mensagens idênticas repetidas numa janela de tempo curta).
- `MinLevelFilter` — disponível, não ativado por padrão (piso de nível
  por handler individual, complementar ao `logger.setLevel()`).

## Observabilidade — preparado, não integrado

Estrutura pensada para permitir integração futura com OpenTelemetry,
Prometheus e Grafana, **sem dependência obrigatória adicionada nesta
etapa**: `trace_id`/`session_id` já existem em `LoggingContext`; o campo
`duration_ms` em `request_completed` já é o dado bruto que um exportador
de métricas consumiria. Nenhuma dessas integrações foi ativada — apenas
os pontos de extensão existem.

## Erros encontrados e corrigidos durante o desenvolvimento

Registrado por transparência, não como curiosidade:

1. **`exc_info` dentro de `extra={}`** quebraria em runtime (`logging`
   trata `exc_info` como atributo reservado de `LogRecord`) — corrigido
   tratando-o como parâmetro nomeado de `log_event`, nunca um campo livre.
2. **Filtro de contexto no logger raiz não funcionaria** — só filtros
   por-handler alcançam registros de loggers filhos que apenas propagam
   (o caso universal aqui, já que todo código usa loggers nomeados).
   Corrigido antes de chegar à entrega final; documentado acima para não
   ser redescoberto por tentativa e erro em um módulo futuro.

## Boas práticas

- Nunca `logging.getLogger(...)` direto fora de `app/logging/` — sempre
  `get_logger(__name__)`.
- Prefira `events.log_event(...)` com uma constante de evento a
  `logger.info("mensagem livre")` para qualquer coisa que precise ser
  filtrável depois.
- Nunca passe segredos como argumento posicional da mensagem — use
  `extra={"password": ...}` apenas se genuinamente necessário (será
  mascarado por `SensitiveDataFilter`); prefira não logar o valor.
- `LoggingContext` é para dados de correlação (IDs), não para dados de
  negócio — não vire um substituto de parâmetros de função.
