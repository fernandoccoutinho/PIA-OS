"""
Catálogo de códigos do kernel de conexões — faixa `PIA-8xxx` (`E7.4-1`).

Arquivo próprio da camada, pelo precedente de
`app/orchestration/errors/codes.py`: os catálogos anteriores estão
congelados e não são tocados. `PIA-8064` foi o último da E7.3; a
sequência continua daí, **sem reserva preventiva**.

Invariante de value object continua levantando `ValueError` sem código,
pelo precedente da E3.4.2.1: um valor fora de faixa não é desfecho de
domínio.
"""

from app.core.error_codes import ErrorCategory, ErrorCode, ErrorSeverity

PIA_8065_CONNECTION_SCOPE_VIOLATION = ErrorCode(
    code="PIA-8065",
    default_message="connection_scope_violation",
    category=ErrorCategory.AUTHENTICATION,
    http_status=404,
    severity=ErrorSeverity.WARNING,
)
"""Conexão inexistente **sob o `control_principal_ref` informado**.

404 e não 403, pela mesma disciplina de `PIA-8058`: distinguir "existe
mas é de outro" de "não existe" transformaria a resposta em oráculo de
enumeração.
"""

PIA_8066_CONNECTION_CONTRACT_VIOLATION = ErrorCode(
    code="PIA-8066",
    default_message="connection_contract_violation",
    category=ErrorCategory.VALIDATION,
    http_status=422,
    severity=ErrorSeverity.ERROR,
)
"""Perfil, snapshot ou alegação recusados antes de qualquer persistência.

Inclui método que nasceria `AVAILABLE` sem estar em
`AVAILABLE_CONNECTION_METHODS`, perfil manual com `endpoint_ref`, e
atestação `attested` sem `observed_model`.

```text
ENUM_OR_REGISTRY != AVAILABLE
```
"""

PIA_8067_CONNECTION_RECORD_IMMUTABLE = ErrorCode(
    code="PIA-8067",
    default_message="connection_record_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Recibo de execução, snapshot e evidência são append-only.

Código próprio, e não reuso de `PIA-8060`/`PIA-8064`: aqueles falam de
selamento e de governança, e uma mensagem que confunde as três faria o
operador procurar o problema na tabela errada.
"""

PIA_8068_ENTITLEMENT_SUCCESSION_VIOLATION = ErrorCode(
    code="PIA-8068",
    default_message="entitlement_succession_violation",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Mutação de alegação declarada, autossucessão, ou sucessor incoerente.

```text
USER_DECLARED -> OFFICIALLY_DISCOVERED = PROIBIDO (mutação)
USER_DECLARED -> SUPERSEDED BY OFFICIALLY_DISCOVERED = OBRIGATÓRIO (sucessão)
```
"""
