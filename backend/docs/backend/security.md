# Infraestrutura de Segurança Base — PIA-OS Backend

> Movido de `docs/SECURITY.md` para `docs/backend/security.md` no Módulo 2.12.


Segurança de plataforma do PIA-OS (Módulo 2.8). Sem login, JWT, OAuth2,
usuários, permissões, RBAC, MFA ou criptografia de credenciais — isso
pertence a módulos futuros. Esta camada prepara a base.

## Estrutura

```
app/security/
├── headers.py            # Cabeçalhos de segurança estáticos + CSP opcional
├── cors.py                # Tradução Settings -> kwargs do CORSMiddleware
├── trusted_hosts.py        # Validação de host (checagem manual, não o middleware nativo)
├── request_validation.py    # Tamanho máximo + Content-Type permitido
├── sanitization.py           # Limpeza de string, mascaramento de valores sensíveis
├── rate_limit.py               # Interface + implementação em memória (sem Redis)
├── csrf.py                      # Estrutura apenas — não conectada
├── secrets.py                    # Acesso centralizado e mascaramento de segredos
├── policies.py                    # Política de segurança derivada do ambiente
└── middleware.py                   # SecurityMiddleware — orquestra tudo

app/core/
└── security.py             # Bootstrap — o que é registrado e quando
```

## Ordem dos middlewares

```
Requisição
  → CORSMiddleware (mais externo — preflight OPTIONS, headers CORS em toda resposta)
  → RequestIDMiddleware (gera/propaga X-Request-ID)
  → SecurityMiddleware (host confiável, tamanho/Content-Type, headers de segurança)
  → RateLimitMiddleware (só se settings.rate_limit_enabled — desligado por padrão)
  → TimingMiddleware
  → LoggingMiddleware (mais interno)
  → Router
```

`RequestIDMiddleware` precisa vir antes de `SecurityMiddleware` para que
`request_id` já exista quando uma violação é logada. `CORSMiddleware`
precisa ser o mais externo de todos, para responder a preflight o mais
cedo possível e anexar cabeçalhos CORS a toda resposta — inclusive
respostas de erro geradas por camadas mais internas.

## Nota técnica importante: exceções em middleware

Exceções levantadas dentro de um `BaseHTTPMiddleware` **não** passam
pelos handlers registrados via `app.add_exception_handler` para tipos
específicos — essa é uma limitação conhecida do Starlette/FastAPI (só o
catch-all genérico enxerga exceções de middleware, porque
`ExceptionMiddleware`, que despacha por tipo, fica *dentro* da camada de
roteamento, enquanto middlewares de usuário ficam por fora). Descoberto
durante o desenvolvimento deste módulo: as primeiras versões de
`SecurityMiddleware`/`RateLimitMiddleware` levantavam a exceção
normalmente e todas as violações viravam 500 genérico em vez do status
correto (400/413/415/429).

**Solução adotada:** `SecurityMiddleware` e `RateLimitMiddleware`
capturam `PIAOSException` internamente e chamam
`app.exceptions.handlers.piaos_exception_handler` diretamente, reaproveitando
a mesma resposta padronizada e o mesmo logging do Módulo 2.7 — sem
duplicar essa lógica. Qualquer middleware futuro que precise levantar um
erro estruturado deve seguir o mesmo padrão.

## Cabeçalhos de segurança

Aplicados a toda resposta: `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`,
`Permissions-Policy` restritiva, `Cross-Origin-Resource-Policy: same-origin`,
`Cross-Origin-Opener-Policy: same-origin`. `Content-Security-Policy` só é
incluído se `CSP_POLICY` estiver definido — sem política definitiva
nesta etapa (uma CSP mal calibrada quebra a aplicação de formas sutis;
definir a política real é trabalho de quando os endpoints funcionais
existirem para testá-la contra ela).

## CORS

Usa `starlette.middleware.cors.CORSMiddleware` diretamente — decisão
deliberada de não reimplementar a lógica de preflight, que é sutil
(ordem de headers, credenciais, wildcard vs. origem específica) e já
vem testada na própria dependência do FastAPI (nenhuma dependência
nova). Configuração 100% via `Settings` (Módulo 2.2): `CORS_ALLOWED_ORIGINS`,
`CORS_ALLOWED_METHODS`, `CORS_ALLOWED_HEADERS`, `CORS_ALLOW_CREDENTIALS`.

## Trusted Hosts

**Não** usa `starlette.middleware.trustedhost.TrustedHostMiddleware` —
esse middleware nativo responde diretamente com uma `PlainTextResponse`,
sem passar pelos handlers globais de erro (2.7) nem pelo Logger Central
(2.6), o que violaria a exigência explícita do Módulo 2.8 de que toda
violação seja registrada. A checagem é manual, dentro do
`SecurityMiddleware`, contra `settings.trusted_hosts` (`"*"` — padrão de
desenvolvimento — aceita qualquer host; produção deve definir uma lista
explícita).

## Validação de requisição

`request_validation.py` verifica: tamanho (`Content-Length` declarado
vs. `MAX_REQUEST_SIZE_BYTES`) e Content-Type (contra
`ALLOWED_CONTENT_TYPES`, apenas para métodos que tipicamente carregam
corpo). Limite de upload é estrutura apenas — nenhum endpoint de upload
existe ainda.

## Sanitização

Funções genéricas (`sanitize_string`, `remove_control_characters`,
`normalize_unicode`, `mask_sensitive_value`) — nenhuma é aplicada
automaticamente a toda entrada (isso é responsabilidade da validação de
schema Pydantic de cada endpoint, Módulo 2.5). Disponíveis para uso
explícito por módulos futuros.

## Rate Limiting

Interface (`RateLimiter` Protocol) + `InMemoryRateLimiter` (janela
deslizante, em memória do processo — sem Redis). **Desligado por
padrão** (`RATE_LIMIT_ENABLED=false`). `InMemoryRateLimiter` só é
adequado para uma única instância do processo — não compartilha estado
entre réplicas; ativá-lo num deployment com múltiplas réplicas sem um
backend compartilhado subestima a taxa real agregada. Trocar por um
backend distribuído no futuro exige apenas uma nova classe que
implemente o mesmo `RateLimiter` Protocol — nenhum código consumidor muda.

## CSRF

Estrutura apenas (`CSRFPolicy`, `requires_csrf_check`) — **não
conectada** a `main.py`. CSRF é uma preocupação de autenticação baseada
em cookies, que este backend ainda não tem.

## Gestão de segredos

`SecretsManager` estreita ainda mais o acesso a segredos, já
centralizado em `Settings` — ponto único e nomeado especificamente para
valores sensíveis (`secret_key`, credenciais na `database_url`), com
`mask_sensitive_value` para exibição segura (nunca usar para
armazenamento, só para diagnóstico/logs).

## Políticas por ambiente

`get_security_policy(settings)` deriva `SecurityPolicy` do ambiente
ativo: `enforce_https`, `strict_cors` seguem `is_production_like`;
`expose_error_details` segue `settings.debug` diretamente (fonte única
de verdade — evita dois interruptores que poderiam divergir);
`csp_enabled` exige produção/staging **e** uma `CSP_POLICY` definida.

## Configuração (vem inteiramente do Módulo 2.2)

| Variável | Padrão | Descrição |
|---|---|---|
| `CORS_ALLOWED_ORIGINS` | `*` | Lista separada por vírgula |
| `CORS_ALLOWED_METHODS` | `GET,POST,PUT,PATCH,DELETE,OPTIONS` | |
| `CORS_ALLOWED_HEADERS` | `*` | |
| `CORS_ALLOW_CREDENTIALS` | `false` | Nunca `true` com origem `*` |
| `TRUSTED_HOSTS` | `*` | `*` só em desenvolvimento |
| `RATE_LIMIT_ENABLED` | `false` | |
| `RATE_LIMIT_REQUESTS` | `100` | Por janela |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | |
| `MAX_REQUEST_SIZE_BYTES` | `10485760` (10 MiB) | |
| `ALLOWED_CONTENT_TYPES` | `application/json,application/x-www-form-urlencoded` | |
| `CSP_POLICY` | (vazio) | Sem política definitiva ainda |

## Logging de violações

Toda violação (host não confiável, payload grande demais, Content-Type
não permitido, rate limit excedido) gera o evento `security_violation`
via Logger Central: `violation_type`, `ip`, `route`, `method`,
`error_code`, `request_id`. Adicionalmente, como toda violação também
levanta uma `PIAOSException`, o pipeline do Módulo 2.7 gera um segundo
log (`internal_error`, com tipo/mensagem da exceção) — redundância
proposital: uma visão específica de segurança e uma visão genérica de
erro, cada uma útil para um consumidor diferente (dashboard de
segurança vs. monitoramento geral de erros).

## Como adicionar uma nova política de segurança

1. Adicione o campo a `SecurityPolicy` (`app/security/policies.py`).
2. Derive o valor em `get_security_policy` a partir de `settings`/ambiente.
3. Se depender de uma configuração nova, adicione o campo em `Settings`
   (Módulo 2.2) — nunca leia `os.environ` diretamente.

## Como registrar um novo middleware de segurança

1. Crie a classe em `app/security/<nome>.py`, herdando de
   `BaseHTTPMiddleware`.
2. Se ela levanta uma `PIAOSException`, capture-a e chame
   `piaos_exception_handler(request, exc)` diretamente — não apenas
   `raise` (ver "Nota técnica importante" acima).
3. Registre em `app/core/security.py::configure_security_middleware`
   (ou diretamente em `main.py`, se a posição na cadeia for sensível —
   ver "Ordem dos middlewares").

## Boas práticas de segurança

- Nunca leia `os.environ` fora de `app/config/settings.py` — nem para
  segredos, nem para nada mais (Módulo 2.2).
- Nunca logue um segredo em texto puro — use `SecretsManager`/
  `mask_sensitive_value` para qualquer exibição de diagnóstico.
- `CORS_ALLOW_CREDENTIALS=true` nunca deve coexistir com
  `CORS_ALLOWED_ORIGINS=*` — defina origens explícitas.
- Em produção, `TRUSTED_HOSTS` deve ser uma lista explícita, nunca `*`.
- Novo endpoint que aceita corpo deve continuar validando com um schema
  Pydantic (Módulo 2.5) — a validação de Content-Type deste módulo é uma
  camada adicional, não substitui a validação de schema.
