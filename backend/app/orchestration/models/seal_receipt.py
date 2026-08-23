"""
`SealReceipt` — o ato de selar, registrado à parte do conteúdo.

```text
SEAL_RECEIPT = {content_sha256, sealed_at, attempt_id, sealer_ref}
SEALED_AT_IN_CONTENT_HASH = FALSE
```

Este é o objeto que a correção C3 do MAI criou. A versão anterior punha
`sealed_at` dentro do hash e prometia determinismo por conteúdo — dois
selamentos do mesmo conteúdo em instantes distintos nunca dariam o mesmo
hash. Separar recibo de conteúdo dá as duas garantias juntas: um hash,
dois recibos.

Append-only em três camadas, no precedente da E4.11 e da E5.l:

```text
1. serviço produtor único   (HandoffService)
2. repositório recusa       update / delete
3. trigger PostgreSQL       BEFORE UPDATE OR DELETE OR TRUNCATE
```
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel
from app.orchestration.models.attempt import SHA256_HEX_LENGTH
from app.orchestration.schemas.envelope import MAX_REF_LENGTH


class SealReceipt(BaseModel):
    """Recibo imutável de um selamento."""

    __tablename__ = "seal_receipts"

    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_seal_receipts_attempt"),
        CheckConstraint(
            f"length(content_sha256) = {SHA256_HEX_LENGTH}",
            name="ck_seal_receipts_content_sha256_length",
        ),
        CheckConstraint(
            "length(btrim(sealer_ref)) > 0",
            name="ck_seal_receipts_sealer_ref_not_blank",
        ),
        Index("ix_seal_receipts_content_sha256", "content_sha256"),
    )
    """`attempt_id` único materializa `Attempt 1..1 SealReceipt` (§17).

    Dois recibos para a mesma tentativa descreveriam o mesmo ato duas
    vezes; dois recibos para o mesmo **conteúdo** são o resultado esperado
    e continuam permitidos, porque são tentativas diferentes.
    """

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handoff_attempts.id", name="fk_seal_receipts_attempt"), nullable=False
    )

    content_sha256: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    """Cópia do hash do conteúdo selado.

    Guardar o valor em vez de sempre derivá-lo da tentativa é o que faz o
    recibo continuar verdadeiro se alguém, um dia, alterar a tentativa: o
    recibo diz o que foi selado **naquele** ato.
    """

    sealed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """Instante do selamento, lido do relógio do **PostgreSQL**.

    Relógio de aplicação diverge entre réplicas; o precedente medido é o
    `database_now()` da E6.2. Este campo não entra em hash algum.
    """

    sealer_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Quem selou — referência opaca, nunca credencial.

    ```text
    PROVIDER_CREDENTIAL NOT IN {envelope, prompt, log, persistência comum}
    ```
    """
