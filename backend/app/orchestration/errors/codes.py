"""
Catálogo de códigos de erro da orquestração — faixa `PIA-8xxx` (`E7.1`).

Arquivo **próprio** da camada, como manda o precedente de
`app/memory/errors/codes.py` e `app/predictive_accessibility/errors/
codes.py`: os catálogos anteriores estão congelados e não são tocados. A
sequência continua de onde parou — `PIA-8056` foi o último da E5.

Quatro códigos, nenhuma reserva preventiva. Invariante de value object
continua levantando `ValueError` sem código, pelo precedente medido da
E3.4.2.1: um valor fora de faixa não é um desfecho de domínio.
"""

from app.core.error_codes import ErrorCategory, ErrorCode, ErrorSeverity

PIA_8057_ORCHESTRATION_CONTRACT_VIOLATION = ErrorCode(
    code="PIA-8057",
    default_message="orchestration_contract_violation",
    category=ErrorCategory.VALIDATION,
    http_status=422,
    severity=ErrorSeverity.ERROR,
)
"""Declaração fora do contrato antes de qualquer persistência.

Inclui `context_ref` sem SHA-256 válido, modo de execução declarado mas
não executável e rascunho malformado.

```text
INLINE_CONTENT_WITHOUT_HASH = FORBIDDEN
```
"""

PIA_8058_ORCHESTRATION_SCOPE_VIOLATION = ErrorCode(
    code="PIA-8058",
    default_message="orchestration_scope_violation",
    category=ErrorCategory.AUTHENTICATION,
    http_status=404,
    severity=ErrorSeverity.WARNING,
)
"""Schedule ou etapa inexistente **sob o `control_principal_ref` informado**.

```text
SAME_SCOPE != SAME_WORK_OWNERSHIP
CROSS_PRINCIPAL_SCHEDULE_READ = FORBIDDEN
```

404 e não 403 de propósito: distinguir "existe mas é de outro" de "não
existe" transformaria a resposta em oráculo de enumeração — a mesma
disciplina que a E6.2 aplicou à credencial ausente contra a inválida.
"""

PIA_8059_ORCHESTRATION_LIFECYCLE_VIOLATION = ErrorCode(
    code="PIA-8059",
    default_message="orchestration_lifecycle_violation",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Transição ou operação pedida fora do estado em que ela existe.

Selar exige Schedule `ACTIVE` e etapa `PENDING`. Ativar exige `DRAFT`.
Nenhuma outra transição é executada pela E7.1.
"""

PIA_8060_SEAL_RECEIPT_IMMUTABLE = ErrorCode(
    code="PIA-8060",
    default_message="seal_receipt_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de alterar ou remover um recibo de selamento.

Append-only em três camadas, como a E4.11: value object congelado,
repositório que recusa, trigger no PostgreSQL. Um recibo alterado faria o
passado responder por um conteúdo que não era o dele.
"""

PIA_8061_HANDOFF_RECORD_IMMUTABLE = ErrorCode(
    code="PIA-8061",
    default_message="handoff_record_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de alterar ou remover veredito ou atribuição (`E7.2`).

```text
RESULT_REJECTED != RESULT_DISCARDED
```

Código próprio, e não reuso de `PIA-8060`: aquele fala de recibo de
selamento, e uma mensagem que confunde as duas coisas faria o operador
procurar o problema na tabela errada. A faixa segue a sequência sem
reservar códigos sem caminho real.
"""

PIA_8062_DISPATCH_BLOCKED = ErrorCode(
    code="PIA-8062",
    default_message="dispatch_blocked_by_gate",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.WARNING,
)
"""Despacho recusado por gate: delegação ausente, expirada, com hash
divergente, ou porta humana indisponível.

```text
BLOCKED_GATE_PERSISTS_PAUSE_WITH_ZERO_COMMAND_EFFECT
```

409 e não 403: o pedido é legítimo e o principal tem autoridade; o que
falta é uma autorização de despacho que o próprio cliente pode conceder.
"""

PIA_8063_DELEGATION_IMMUTABLE = ErrorCode(
    code="PIA-8063",
    default_message="delegation_binding_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Vínculo de delegação é imutável e estado terminal não retorna a ACTIVE."""

PIA_8064_AUDIT_RECORD_IMMUTABLE = ErrorCode(
    code="PIA-8064",
    default_message="governance_record_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Evento de controle, observação e parecer são append-only."""

PIA_8069_HUMAN_PROTECTION_GATE_UNAVAILABLE = ErrorCode(
    code="PIA-8069",
    default_message="human_protection_gate_unavailable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Indisponibilidade **técnica** do gate de proteção humana (`E7.4-1`).

```text
SOFTWARE_FAILURE != HUMAN_HARM_CATEGORY
MISSING_AUTHORIZED_DESCRIPTOR != AUTHORIZED_NOT_APPLICABLE
```

Cobre resolução ausente, expirada, incompatível com o binding, desfecho fora
de `{prohibited, not_applicable}`, porta que levanta, e vencedor de corrida
divergente do que esta transação aplicaria.

Falha do gate **não** é categoria de dano humano: ela não cria
`ProtectionOutcome`, capacidade, sinal nem evento de proteção. O código é
próprio, e não reuso de `PIA-8062`: aquele fala de despacho recusado por gate
de delegação, e confundir os dois mandaria o operador procurar o problema na
tabela errada.

A faixa `PIA-8065..8068` pertence ao kernel de conexões
(`app/connections/errors/codes.py`). Próximo global livre: `PIA-8070`.
"""
