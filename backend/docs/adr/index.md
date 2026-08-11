# Índice de ADRs — PIA-OS Backend

Architecture Decision Records consolidados dos Módulos 2.1–2.11. Cada
ADR documenta uma decisão arquitetural real, tomada durante a
implementação — não retroativamente inventada para preencher a lista.

| ADR | Título | Status | Módulos |
|---|---|---|---|
| [ADR-001](ADR-001.md) | `/health` liveness pura, `/status` readiness | Aceito | 2.3, 2.5 |
| [ADR-002](ADR-002.md) | `BaseModel` minimalista — apenas `UUIDMixin` + `TimestampMixin` | Aceito | 2.4 |
| [ADR-003](ADR-003.md) | Exceções em middleware chamam o handler global diretamente | Aceito | 2.7, 2.8 |
| [ADR-004](ADR-004.md) | `ValidationException` é irmã, não subclasse, de `APIException` | Aceito | 2.5, 2.7 |
| [ADR-005](ADR-005.md) | Validação de host confiável é manual, não `TrustedHostMiddleware` | Aceito | 2.8 |
| [ADR-006](ADR-006.md) | CORS via `CORSMiddleware` do Starlette, não reimplementado | Aceito | 2.8 |
| [ADR-007](ADR-007.md) | Filtros de contexto de log por Handler, não por Logger | Aceito | 2.6 |
| [ADR-008](ADR-008.md) | Três Dockerfiles autocontidos, não uma cadeia de imagens-base | Aceito | 2.11 |

## Como adicionar um novo ADR

1. Copie o formato de um ADR existente (Contexto / Decisão /
   Justificativa / Impacto / Alternativas consideradas / Referência).
2. Numere sequencialmente (`ADR-009.md`, etc.) — nunca reutilize um
   número, mesmo que um ADR seja revogado depois.
3. Adicione uma linha nesta tabela.
4. Se o ADR revogar ou substituir um anterior, marque o antigo como
   **Substituído por ADR-0XX** no campo Status dele, sem apagar seu
   conteúdo — o histórico da decisão original continua sendo
   informação útil.

## Critério para merecer um ADR

Nem toda decisão de código vira ADR — só as que atendem pelo menos um
destes critérios: (a) desviam do que a especificação do módulo pedia
literalmente, com justificativa técnica; (b) têm impacto que atravessa
mais de um módulo; (c) foram descobertas por tentativa e erro durante o
desenvolvimento e têm valor real em não serem redescobertas depois. Uma
escolha de nome de variável não é um ADR.
