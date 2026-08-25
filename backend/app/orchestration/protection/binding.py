"""
`GovernanceBinding` — identidade da **aplicação** do gate (`E7.4-1 B1a`).

```text
DECISION_IS_ABOUT_AN_OBJECTIVE · APPLICATION_IS_ABOUT_A_GATE
G3_APPLICATION_WITHOUT_ATTEMPT_ID = STALE_ATTEMPT_PROOF
```

Dez campos, congelados. `attempt_id` é o id **prealocado** da tentativa —
nulo em G1, G2 e G4, obrigatório em G3. Com ele dentro do binding, uma nova
submissão produz outra chave de idempotência e o evento anterior deixa de ser
reencontrável: é a chave, e não um `CHECK` isolado, que fecha o buraco da
prova de tentativa velha.

Os invariantes vivem em `__post_init__`, e não num construtor de conveniência:
`frozen=True` protege a referência, não o conteúdo, e uma regra que só existe
na fábrica é contornável pelo construtor direto. Lição repetida nas E4.2.1,
E4.3.2, E4.4.1, E4.5.1 e E3.4.2.1.

Camada de garantia (Master Parte III §15.2): `APPLICATION_LEVEL`. As mesmas
regras existem em `DB_LEVEL` como `CHECK`, e as duas camadas são exigidas —
o value object recusa antes de qualquer I/O, o banco recusa quem chegar por
SQL bruto ou por um caminho que ainda não existe.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.orchestration.ports.governance_vocabulary import BoundaryOperation
from app.orchestration.protection.vocabulary import GatePosition
from app.orchestration.schemas.envelope import MAX_REF_LENGTH

SHA256_LOWER_HEX = re.compile(r"^[0-9a-f]{64}$")
"""Minúsculo e exato. Aceitar maiúsculo faria o mesmo digest ter duas
representações e, portanto, duas chaves de idempotência distintas."""

MAX_CLASSIFIER_VERSION_LENGTH = 16
"""Espelha `varchar(16)` da coluna. Sem isto o desfecho de um valor longo
dependeria do driver, e não do contrato — mesma correção da E3.4.2.1."""


def _texto(nome: str, valor: object, limite: int) -> str:
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser str, recebido {type(valor).__name__}")
    if not valor.strip():
        raise ValueError(f"{nome} não pode ser vazio ou apenas espaços")
    if len(valor) > limite:
        raise ValueError(f"{nome} excede {limite} caracteres")
    return valor


def _uuid_opcional(nome: str, valor: object) -> uuid.UUID | None:
    if valor is None:
        return None
    if not isinstance(valor, uuid.UUID):
        raise TypeError(f"{nome} deve ser uuid.UUID ou None, recebido {type(valor).__name__}")
    return valor


@dataclass(frozen=True)
class GovernanceBinding:
    """A pergunta que este gate, nesta posição, fez sobre este objetivo."""

    operation: BoundaryOperation
    principal_ref: str
    schedule_id: uuid.UUID | None
    step_id: uuid.UUID | None
    attempt_id: uuid.UUID | None
    objective_sha256: str
    gate_position: GatePosition
    boundary_version: int
    classifier_version: str
    valid_until: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.operation, BoundaryOperation):
            raise TypeError("operation deve ser um BoundaryOperation")
        if not isinstance(self.gate_position, GatePosition):
            raise TypeError("gate_position deve ser um GatePosition")

        object.__setattr__(
            self, "principal_ref", _texto("principal_ref", self.principal_ref, MAX_REF_LENGTH)
        )
        object.__setattr__(
            self,
            "classifier_version",
            _texto("classifier_version", self.classifier_version, MAX_CLASSIFIER_VERSION_LENGTH),
        )

        if not isinstance(self.objective_sha256, str) or not SHA256_LOWER_HEX.match(
            self.objective_sha256
        ):
            raise ValueError(
                "objective_sha256 deve ser sha-256 hexadecimal minúsculo de 64 dígitos"
            )

        if isinstance(self.boundary_version, bool) or not isinstance(self.boundary_version, int):
            raise TypeError("boundary_version deve ser int")
        if self.boundary_version < 1:
            raise ValueError("boundary_version deve ser >= 1")

        if not isinstance(self.valid_until, datetime):
            raise TypeError("valid_until deve ser datetime")
        if self.valid_until.tzinfo is None or self.valid_until.utcoffset() is None:
            raise ValueError(
                "valid_until deve ser datetime com fuso — instante ingênuo não é instante"
            )

        for campo in ("schedule_id", "step_id", "attempt_id"):
            object.__setattr__(self, campo, _uuid_opcional(campo, getattr(self, campo)))

        self._validar_posicao()

    def _validar_posicao(self) -> None:
        """Coerência entre a posição do gate e o que ela pode citar.

        G1 avalia **antes** de o Schedule existir; citar `schedule_id` ali
        seria afirmar que algo foi escrito antes da decisão. As demais
        posições sempre têm Schedule e etapa. Só G3 corre sob o lock final,
        e é a única que carrega a tentativa prealocada.
        """
        e_g1 = self.gate_position is GatePosition.G1
        if e_g1 and (self.schedule_id is not None or self.step_id is not None):
            raise ValueError("g1 avalia antes da criação — schedule_id e step_id devem ser nulos")
        if not e_g1 and (self.schedule_id is None or self.step_id is None):
            raise ValueError(f"{self.gate_position.value} exige schedule_id e step_id")

        e_g3 = self.gate_position is GatePosition.G3
        if e_g3 and self.attempt_id is None:
            raise ValueError("g3 exige attempt_id prealocado")
        if not e_g3 and self.attempt_id is not None:
            raise ValueError("somente g3 carrega attempt_id no binding")
