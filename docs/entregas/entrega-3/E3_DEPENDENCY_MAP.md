# E3 — Dependency Map

Módulo E3.0. Direção da seta = "depende de". A regra geral, em uma linha:
**E3 se adapta às interfaces aprovadas de E1/E2 — E1/E2 nunca se
adaptam a E3.**

## Visão geral

```text
                        ┌──────────────────────────┐
                        │   app.api (router/deps)   │  E2 — sem mudança
                        └────────────┬──────────────┘
                                     │ (quando E3 expuser endpoints —
                                     │  fora do escopo de E3.0)
                                     ▼
┌────────────────────────────────────────────────────────────────┐
│                     app.cognitive (E3, NOVO)                    │
│                                                                  │
│   app.cognitive.schemas   (Pydantic — request/response/DTO)     │
│              │                                                  │
│              ▼                                                  │
│   app.cognitive.services  (LIB-04..LIB-11 — orquestração)       │
│              │                                                  │
│              ▼                                                  │
│   app.cognitive.repositories (LIB-01..LIB-03 — persistência)    │
│              │                                                  │
│              ▼                                                  │
│   app.cognitive.models    (CognitiveObject, CognitiveDistinction,│
│                             ProvenanceRecord, CausalHistory,     │
│                             AccessibilityState, CausalClassRef,  │
│                             TransformationRecord,                │
│                             CausalComparison, LineageEdge)       │
└───────────────────────────┬──────────────────────────────────────┘
                             │ depende de (baseline congelada)
                             ▼
┌────────────────────────────────────────────────────────────────┐
│                    Baseline E1/E2 (PASS, congelada)              │
│                                                                  │
│  app.database.base.Base          app.repositories.base_repository│
│  app.database.session (get_db,   app.repositories.unit_of_work   │
│    session_scope, async_*)       app.repositories.exceptions     │
│  app.models.base_model/mixins    app.repositories.repository_protocol│
│  app.exceptions.base (PIAOSException)                            │
│  app.core.error_codes (PIA-8xxx: PROPOSTA/RESERVADA — ver         │
│    "Error Code Integration Status" abaixo; não incorporada)      │
│  app.logging.context (correlation_id/session_id/trace_id)        │
│  app.utils.logger (get_logger)                                   │
│  app.config.settings (Settings)                                  │
│  app.schemas.common / app.api.responses                          │
└────────────────────────────────────────────────────────────────┘
```

`app.cognitive.*` é a localização **formalmente decidida** — não mais
apresentada como consequência automática da arquitetura de E1/E2 (ver
`EDR_E3_COGNITIVE_PACKAGING.md`, correção E3.0.1, para a comparação
com a alternativa horizontal e a justificativa da escolha). Nenhum
destes arquivos é criado neste módulo E3.0.

A categorização de camadas no diagrama acima (`schemas` → `services`
→ `repositories` → `models`, com `LIB-01..03` associado a
`repositories` e `LIB-04..11` a `services`) é ilustrativa da
arquitetura em camadas dentro do bounded context — não é a mesma
dimensão da sequência de módulos de entrega (`E3.1`–`E3.12`) definida
em `E3_IMPLEMENTATION_SEQUENCE.md`. Um módulo de entrega (ex.: `E3.2`
= `LIB-02` COID Manager) tipicamente toca mais de uma camada (um
`CoidManager` em `services/` que usa um repositório em
`repositories/`) — as duas classificações não precisam, e não
precisarão, coincidir 1:1.

## Dependências permitidas (lista fechada)

- `app.database.base.Base` — única hierarquia declarativa.
- `app.database.session.{get_db,get_async_db,session_scope,async_session_scope,SessionLocal}`.
- `app.models.base_model.BaseModel` + mixins de `app.models.mixins`.
- `app.repositories.base_repository.{BaseRepository,Page}`.
- `app.repositories.repository_protocol.RepositoryProtocol`.
- `app.repositories.unit_of_work.UnitOfWork`.
- `app.repositories.exceptions.{RepositoryError,EntityNotFoundError,PersistenceError,TransactionError}`.
- `app.exceptions.base.PIAOSException`.
- `app.core.error_codes.{ErrorCode,ErrorCategory,ErrorSeverity}` — os **tipos** (dataclass/enums) são públicos e reutilizáveis para instanciar códigos `PIA-8xxx` próprios de E3 **em um catálogo separado, dentro de `app.cognitive`** (ver "Error Code Integration Status" abaixo) — nunca para editar `ALL_ERROR_CODES`/`error_codes.py` em si, e nunca para reutilizar um código já publicado (`PIA-0xxx`–`PIA-7xxx`).
- `app.utils.logger.get_logger`.
- `app.logging.context.{LoggingContext,logging_context,ContextSnapshot}`.
- `app.config.settings.{Settings,settings}` / `app.api.dependencies.get_app_settings`.
- `app.api.dependencies.{get_db_session,get_request_context,RequestContext}` — apenas quando E3 expuser endpoints (fora de E3.0).
- `app.schemas.common.*`, `app.api.responses.*`, `app.schemas.error.*` — idem, apenas na camada de API.
- `app.api.router.{api_router,root_router}` + `app.api.module_registry.REGISTERED_MODULE_NAMES` — idem.

## Dependências explicitamente proibidas

| Proibição | Motivo |
|---|---|
| SDK de qualquer provider de IA (Anthropic, OpenAI, Google, Meta, DeepSeek, Qwen, etc.) como dependência obrigatória de `app.cognitive.*` | §14 do prompt — arquitetura provider-agnostic; Claude é ferramenta de desenvolvimento, não parte da arquitetura |
| Import de `sqlalchemy` fora de `app.cognitive.repositories`/`app.cognitive.models` | Regra já em vigor desde o Módulo 2.3 (`base_repository.py`) — vale igualmente para E3 |
| Segunda `DeclarativeBase` | Uma única hierarquia ORM no projeto |
| Escrita direta em sessão sem passar por `UnitOfWork`/`session_scope` | Mesma regra de E2, sem exceção para E3 |
| `os.environ` fora de `app/config/settings.py` | Regra já em vigor — nenhuma configuração de E3 foge disso |
| Reutilização de um código `ErrorCode` já publicado (`PIA-0xxx`–`PIA-7xxx`) para um erro novo de domínio | Códigos são imutáveis após publicados |
| Lógica de decisão/seleção automática dentro de `app.cognitive.*` (scoring, ranking, "melhor caminho cognitivo") | §5–§6 do prompt — COUT-PIA representa e avalia, não decide; decisão é de Policy/Arbiter, camada que não existe ainda e não é criada por E3 |
| `A_COUT = R * P * T` ou qualquer scalarização canônica | §5 do prompt — proibição explícita |
| Dedução automática de `CAUSALLY_EXTINCT` pela ausência de informação no contexto atual | §9 do prompt |
| Deduplicação automática de objetos por igualdade de conteúdo | §8 do prompt — duas histórias podem convergir em conteúdo e continuar causalmente distintas |
| Confundir `COID` e `CLID` em um único campo/conceito | §8 do prompt |
| Implementação de políticas de memória/ACL/domínio/consolidação/promoção/retenção/esquecimento/governança | §13 do prompt — isso é E4, não E3 |
| Multi-AI Orchestrator / hypervisor de agentes | §14 do prompt — isso é E7 |
| Qualquer alteração em arquivo dentro de `app/config`, `app/database`, `app/repositories/base_repository.py`, `app/repositories/unit_of_work.py`, `app/models/base_model.py`, `app/models/mixins.py`, `app/exceptions/base.py`, `app/core/error_codes.py`, `app/logging/*`, `app/api/dependencies.py` para "melhorar" ou "adaptar" a E3 | Baseline congelada — mudança aqui só é patch de bug real, nunca acomodação de E3 |

## Error Code Integration Status (correção E3.0.1 §4-5)

A faixa `PIA-8xxx` está aparentemente livre no catálogo atual (nenhum
`ErrorCode` publicado usa esse prefixo — confirmado por inspeção de
`ALL_ERROR_CODES`). **Isso não autoriza alteração automática de
`app/core/error_codes.py`** ou qualquer outro arquivo da baseline
E1/E2. `PIA-8xxx = PROPOSTA/RESERVADA para E3`, não incorporada ao
catálogo existente até uma decisão de integração explícita — que este
documento agora registra.

### Opções avaliadas

**Opção A — mecanismo público/extensível existente, sem modificar
contratos congelados.** Inspeção da baseline: `ExceptionRegistry`
(`app.exceptions.registry`) é extensível, mas registra *handlers* por
**tipo de exceção**, não códigos de erro — não é o mecanismo certo
para este problema. Não existe, em E1/E2, um `register_error_code()`
ou equivalente para adicionar entradas a `ALL_ERROR_CODES` de fora de
`app/core/error_codes.py`. Opção A, no sentido estrito de "usar um
registry de códigos já existente", não está disponível.

**Opção B — catálogo de erros do domínio cognitivo em E3, integrado
via interface pública aprovada.** `ErrorCode` (dataclass),
`ErrorCategory` e `ErrorSeverity` (enums) são tipos públicos e
livremente instanciáveis fora de `app/core/error_codes.py` —
`PIAOSException.__init__` aceita qualquer instância de `ErrorCode`,
sem exigir que ela pertença a `ALL_ERROR_CODES`. Isso permite a E3
declarar seus próprios `ErrorCode` (`PIA-8xxx`) em um módulo próprio
(`app.cognitive.errors`, a ser criado em código funcional apenas
quando o primeiro erro de domínio for necessário — não neste módulo
E3.0) **sem editar nenhum arquivo de E1/E2**. Consequência aceita: um
código `PIA-8xxx` não aparece em `ALL_ERROR_CODES`/
`ERROR_CODE_BY_CODE` (o mapa reverso de E1/E2) — qualquer endpoint
futuro de catálogo de erros que dependa dessas estruturas precisará
consultar também o catálogo de E3, ou (decisão de módulo futuro,
fora do escopo de E3.0) um mecanismo de composição de catálogos pode
ser proposto sem alterar a baseline.

**Opção C — modificação de contrato público E1/E2.** Não avaliada em
profundidade porque a Opção B resolve o problema sem exigir isso —
manter aqui apenas como registro de que foi considerada e descartada
por não ser necessária, não porque fosse impossível.

### Decisão

**`ERROR_CODE_INTEGRATION_STATUS = RESOLVED`**, via **Opção B**: E3
declarará seu próprio catálogo de `ErrorCode` (`PIA-8xxx`) usando os
tipos públicos de `app.core.error_codes`, em um módulo próprio dentro
de `app.cognitive`, sem modificar `error_codes.py` nem
`ALL_ERROR_CODES`. Isso não é implementado neste módulo E3.0 — a
decisão apenas remove a ambiguidade para quando `E3.1` (ou qualquer
módulo posterior) precisar do primeiro erro de domínio.

## Checagem de dependência circular

`app.cognitive.*` depende de `app.{database,models,repositories,exceptions,core,logging,utils,config,schemas,api}` — todos módulos de E1/E2, nenhum dos quais importa (nem pode passar a importar) de volta `app.cognitive.*`. Não há ciclo possível enquanto essa direção única for respeitada; é a mesma verificação estrutural aplicada em E1/E2 (nenhuma camada mais baixa importa uma mais alta).
