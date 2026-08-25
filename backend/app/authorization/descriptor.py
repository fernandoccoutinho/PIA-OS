"""
`AuthorizedCapabilityDescriptor` — a saída da E8.

Descritor tipado **vinculado**: ao objetivo exato (por hash), à
competência que classificou (por versão) e a uma janela de validade.

    DESCRIPTOR WITHOUT BINDING = REUSABLE PERMISSION

Sem o vínculo ao `objective_sha256`, um descritor produzido para um
objetivo benigno serviria a qualquer outro — e a proteção viraria um
token portátil. Sem validade, uma classificação de ontem autorizaria
hoje.

A janela é **semiaberta**, `[evaluated_at, valid_until)`, pelo mesmo
motivo já fixado no corretivo C123-2 da Chain124: o instante exato de
expiração pertence ao lado de fora, e duas convenções diferentes no
mesmo programa produziriam um vão de um tique.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.memory.models.governance_enums import (
    CapabilityEngagement,
    CognitiveOperation,
    CriticalCapability,
)
from app.memory.services.platform_safety_boundary import CapabilityDescriptor


def objective_digest(objective: str) -> str:
    """Hash canônico do objetivo, em minúsculas hexadecimais.

    O objetivo entra codificado em UTF-8 sem normalização adicional: o
    vínculo é ao byte exato que foi classificado, não a uma forma
    aproximada dele.
    """
    if not isinstance(objective, str):
        raise TypeError("objective deve ser str")
    if not objective.strip():
        raise ValueError("objective não pode ser vazio ou apenas espaços")
    return hashlib.sha256(objective.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthorizedCapabilityDescriptor:
    """Descritor produzido pela E8 e consumido pela fronteira E4."""

    operation: CognitiveOperation
    capabilities: frozenset[CriticalCapability]
    engagement: CapabilityEngagement
    objective_sha256: str
    classifier_version: str
    evaluated_at: datetime
    valid_until: datetime
    stated_intent: str | None = field(default=None)

    def __post_init__(self) -> None:
        if not isinstance(self.operation, CognitiveOperation):
            raise TypeError("operation deve ser um CognitiveOperation")
        if not isinstance(self.engagement, CapabilityEngagement):
            raise TypeError("engagement deve ser um CapabilityEngagement")

        capacidades = self.capabilities
        if isinstance(capacidades, str | bytes) or not hasattr(capacidades, "__iter__"):
            raise TypeError("capabilities deve ser um iterável de CriticalCapability")
        itens = tuple(capacidades)
        if any(not isinstance(item, CriticalCapability) for item in itens):
            raise TypeError("capabilities aceita apenas CriticalCapability")
        object.__setattr__(self, "capabilities", frozenset(itens))

        digest = self.objective_sha256
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("objective_sha256 deve ser um sha256 hexadecimal de 64 caracteres")
        if digest != digest.lower() or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("objective_sha256 deve ser hexadecimal minúsculo")

        if not isinstance(self.classifier_version, str) or not self.classifier_version.strip():
            raise ValueError("classifier_version é obrigatório")

        for nome, valor in (
            ("evaluated_at", self.evaluated_at),
            ("valid_until", self.valid_until),
        ):
            if not isinstance(valor, datetime):
                raise TypeError(f"{nome} deve ser datetime")
            if valor.tzinfo is None:
                raise ValueError(f"{nome} deve ser consciente de fuso")
            object.__setattr__(self, nome, valor.astimezone(UTC))

        if self.valid_until <= self.evaluated_at:
            raise ValueError(
                "valid_until deve ser estritamente posterior a evaluated_at — "
                "janela semiaberta [evaluated_at, valid_until)"
            )

        if self.stated_intent is not None:
            if not isinstance(self.stated_intent, str):
                raise TypeError("stated_intent deve ser str ou None")
            if not self.stated_intent.strip():
                raise ValueError("stated_intent não pode ser vazio ou apenas espaços — omita-o")

    def is_valid_at(self, moment: datetime) -> bool:
        """Vigência na janela semiaberta `[evaluated_at, valid_until)`."""
        if not isinstance(moment, datetime) or moment.tzinfo is None:
            raise ValueError("moment deve ser um datetime consciente de fuso")
        instante = moment.astimezone(UTC)
        return self.evaluated_at <= instante < self.valid_until

    def matches_objective(self, objective: str) -> bool:
        """Este descritor foi produzido para **este** objetivo?"""
        return objective_digest(objective) == self.objective_sha256

    def to_boundary_descriptor(self) -> CapabilityDescriptor:
        """Projeta no descritor que a fronteira E4 avalia.

        Projeção, não conversão de autoridade: a E4 continua sendo quem
        decide, e este método só entrega a ela o que ela já espera.
        """
        return CapabilityDescriptor(
            operation=self.operation,
            capabilities=self.capabilities,
            engagement=self.engagement,
            stated_intent=self.stated_intent,
        )
