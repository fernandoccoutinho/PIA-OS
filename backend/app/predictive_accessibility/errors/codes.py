"""
Catálogo de códigos de erro do PIAP — faixa `PIA-8xxx` (`E5.a`).

Arquivo **próprio** da camada, como manda o precedente de
`app/memory/errors/codes.py`: os catálogos de E3 e E4 estão congelados e
não são tocados. A sequência numérica continua de onde parou —
`PIA-8051` foi o último de E4.

Como em E3 e E4, estes códigos usam os tipos públicos de
`app.core.error_codes` sem editar `ALL_ERROR_CODES`.

Apenas os dois códigos realmente necessários a `E5.a` existem aqui.
Nenhuma reserva preventiva.

```text
NEGATIVE_APPROVAL_OUTCOME != EXCEPTION
```

Resultado negativo de aprovação é valor de `ApprovalValidationOutcome`,
não exceção — e por isso não consome código nenhum.
"""

from app.core.error_codes import ErrorCategory, ErrorCode, ErrorSeverity

PIA_8052_PIAP_UNSUPPORTED_VERSION = ErrorCode(
    code="PIA-8052",
    default_message="piap_unsupported_version",
    category=ErrorCategory.VALIDATION,
    http_status=422,
    severity=ErrorSeverity.ERROR,
)
"""A versão de contrato recebida não está na allowlist de `version.py`.

Falha **fechada**. Uma versão que não sabemos ler não pode ser
interpretada na melhor das hipóteses — mesma disciplina que a E3 fixou
em `_validate_envelope` do pacote de sincronização."""

PIA_8053_PIAP_CONTRACT_VIOLATION = ErrorCode(
    code="PIA-8053",
    default_message="piap_contract_violation",
    category=ErrorCategory.VALIDATION,
    http_status=422,
    severity=ErrorSeverity.ERROR,
)
"""Forma serializada fora do contrato: campo ausente, campo extra, chave
JSON duplicada, tipo errado ou JSON malformado.

Não é o mesmo que valor inválido num value object — aquele levanta
`TypeError`/`ValueError` pelo precedente medido. Este código pertence à
fronteira de serialização, onde o problema é a **forma** do payload."""
