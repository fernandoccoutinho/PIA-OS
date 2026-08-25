"""
`app.mcp` — boundary MCP inbound da E7.4-2.

```text
E7_4_2   = PROVIDER_NATIVE_MCP_INBOUND
PIA_ROLE = OAUTH_RESOURCE_SERVER_ONLY
MCP      = TRANSPORT_NOT_AUTHORITY
```

Uma IA ou cliente oficial autenticado chama ferramentas **estreitas** do
PIA. O PIA não entra em conta de provedor, não implementa authorization
server, não guarda token e não repassa credencial adiante.

## Transporte, não autoridade

A última linha é a que decide o desenho inteiro. MCP aqui é encanamento:
não concede permissão, não decide admissibilidade e não inventa
capacidade. Toda decisão continua nos donos que já a tinham — E4 para a
fronteira, E7 para o gate, E8 para o descritor.

```text
TOOL_THAT_DECIDES = SECOND_AUTHORITY
SECOND_AUTHORITY  = THE_ONE_NOBODY_AUDITS
```

## Superfície fechada

Exatamente cinco ferramentas, cada uma compondo serviço público que já
existe. Nenhuma tool genérica de SQL, shell, arquivo, URL, HTTP, Python,
memória, administração, segredo ou execução arbitrária — uma só delas
transformaria o boundary num interpretador com credencial.

```text
GENERIC_TOOL = ARBITRARY_EXECUTION_WITH_A_POLITE_NAME
```

O módulo `boundary_guard.py` transforma essa proibição em prova
mecânica: o pacote não pode alcançar repositório, ORM, SQLAlchemy,
modelo de banco, shell, filesystem ou cliente HTTP arbitrário.

## Produção desabilitada nesta entrega

O runtime existe como aplicação ASGI executável em desenvolvimento e
teste, e **não** é montado na composição produtiva padrão. Não há flag
que contorne a ausência do gate integrado final.

```text
MCP_PRODUCTION     = BLOCKED
PRODUCTION_DEFAULT = DISABLED
```
"""

TOOL_NAMES: tuple[str, ...] = (
    "schedule.read",
    "handoff.export",
    "return.import",
    "attempts.list",
    "governance.read",
)
"""As cinco autorizadas, escritas literalmente.

Enumerado e não derivado de registro: derivar faria uma tool nova entrar
na superfície só por existir no código, que é exatamente como uma
superfície fechada deixa de ser fechada.

```text
DERIVED_SURFACE = SURFACE_THAT_GROWS_BY_ACCIDENT
```
"""

__all__ = ["TOOL_NAMES"]
