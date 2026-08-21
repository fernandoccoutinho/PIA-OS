"""`E5.c` — contrato de alegação preditiva.

Extrai do envelope PIAP já validado a alegação a avaliar. Não estima, não
compara alegações e não decide estado.

```text
CLAIM_CONTRACT != ESTIMATION
```
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.predictive_accessibility.piap.envelope import PiapEnvelope


@dataclass(frozen=True)
class PredictiveClaim:
    """Alvo, sinal e horizonte de uma alegação, mais sua chave canônica."""

    target: str
    signal: str
    horizon: timedelta
    reference_time: datetime

    @property
    def subject_key(self) -> str:
        """SHA-256 do JSON canônico da tupla identificadora da alegação."""
        corpo = json.dumps(
            [
                self.target,
                self.signal,
                int(self.horizon / timedelta(microseconds=1)),
                self.reference_time.isoformat().replace("+00:00", "Z"),
            ],
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(corpo.encode("utf-8")).hexdigest()


def predictive_claim_from_envelope(envelope: PiapEnvelope) -> PredictiveClaim:
    if not isinstance(envelope, PiapEnvelope):
        raise TypeError(f"envelope deve ser PiapEnvelope, recebido {type(envelope).__name__}")
    assunto = envelope.subject
    return PredictiveClaim(
        target=assunto.target,
        signal=assunto.signal,
        horizon=assunto.horizon.delta,
        reference_time=assunto.horizon.reference_time,
    )
