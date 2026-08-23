"""
`CommandReceipt` — identidade de **comando**, separada da de conteúdo.

```text
COMMAND_IDEMPOTENCY_SCOPE = (technical_principal_ref, operation, command_key)
GLOBAL_COMMAND_KEY_ALONE = INSUFFICIENT
SAME_COMMAND_KEY -> SAME_RECEIPT, NO_DUPLICATE_EFFECT
RETRY -> NEW_COMMAND_KEY -> NEW_ATTEMPT
```

A correção C4 do MAI trocou `(schedule_id, step_id, content_sha256)` por
uma chave escolhida pelo chamador. A tripla antiga não distinguia reenvio
acidental de retry legítimo: as duas coisas têm o mesmo conteúdo. Com a
chave de comando separada, reenvio não duplica e repetir a mesma
instrução continua sendo tentativa nova.

O escopo é composto porque `command_key` é escolhida pelo cliente e dois
clientes podem escolher a mesma. Unicidade global colidiria trabalhos de
principais diferentes — e a colisão apareceria como "idempotência", isto
é, como um efeito silenciosamente não executado.
"""

from sqlalchemy import CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel
from app.orchestration.schemas.envelope import MAX_REF_LENGTH

MAX_OPERATION_LENGTH = 64
MAX_COMMAND_KEY_LENGTH = 255


class CommandReceipt(BaseModel):
    """Recibo de um comando aceito, com a referência do efeito produzido."""

    __tablename__ = "command_receipts"

    __table_args__ = (
        UniqueConstraint(
            "technical_principal_ref",
            "operation",
            "command_key",
            name="uq_command_receipts_principal_operation_key",
        ),
        CheckConstraint(
            "length(btrim(technical_principal_ref)) > 0",
            name="ck_command_receipts_principal_not_blank",
        ),
        CheckConstraint(
            "length(btrim(operation)) > 0",
            name="ck_command_receipts_operation_not_blank",
        ),
        CheckConstraint(
            "length(btrim(command_key)) > 0",
            name="ck_command_receipts_command_key_not_blank",
        ),
        CheckConstraint(
            "length(btrim(outcome_ref)) > 0",
            name="ck_command_receipts_outcome_ref_not_blank",
        ),
        CheckConstraint(
            "request_sha256 IS NULL OR length(request_sha256) = 64",
            name="ck_command_receipts_request_sha256_length",
        ),
        Index("ix_command_receipts_principal", "technical_principal_ref"),
    )
    """A unicidade composta não é conveniência de consulta: é o alvo do
    `ON CONFLICT` que torna a reivindicação do comando atômica no banco.

    Sem ela o `INSERT ... ON CONFLICT` não teria alvo, e duas réplicas
    produziriam dois efeitos para o mesmo comando — o mesmo raciocínio
    que a E6.2 aplicou ao bucket de cota.
    """

    technical_principal_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)

    operation: Mapped[str] = mapped_column(String(MAX_OPERATION_LENGTH), nullable=False)
    """Vocabulário de `CommandOperation`, gravado como texto.

    Texto e não enum tipado: a faixa de operações cresce a cada fatia da
    E7, e um enum no banco exigiria migração de vocabulário por fatia. A
    validação do vocabulário vive no serviço, que é o único escritor.
    """

    command_key: Mapped[str] = mapped_column(String(MAX_COMMAND_KEY_LENGTH), nullable=False)
    """Escolhida pelo **chamador**. Opaca para a E7."""

    request_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Impressão digital canônica da requisição que criou este recibo.

    ```text
    SAME_COMMAND_KEY + DIFFERENT_REQUEST = CONFLICT
    IDEMPOTENCY_WITHOUT_REQUEST_BINDING = SILENT_WRONG_ANSWER
    ```

    Sem este vínculo, reusar a mesma `command_key` com corpo diferente
    devolveria o recurso antigo como se fosse a resposta do pedido novo —
    idempotência virando resposta errada em silêncio, que é pior que erro.

    `nullable` por causa das linhas históricas, criadas antes desta
    coluna existir: preenchê-las exigiria inventar a requisição que as
    originou. Obrigatória para todo comando público novo, e o serviço
    recusa quando falta.

    Guarda o hash, nunca o corpo — `RAW_OUTPUT_IN_DATABASE = FORBIDDEN`.
    """

    outcome_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Referência do efeito produzido por este comando.

    `NOT NULL` é possível porque a identidade do efeito é gerada **antes**
    da reivindicação: o serviço propõe o `outcome_ref`, e só produz o
    efeito quando descobre que foi ele quem inseriu a linha. Uma coluna
    anulável admitiria um recibo comprometido sem efeito registrado.
    """
