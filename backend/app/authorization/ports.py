"""
Porta semântica da E8 e o formato tipado do que ela devolve.

A produção do descritor é **semântica**, e por isso mora atrás de uma
porta: nem este módulo nem o broker olham o objetivo para decidir. Quem
decide é o adaptador — em produção, um classificador com competência
semântica; em teste, um duplo determinístico.

    TOPIC != CAPABILITY
    ANALYTICAL != OPERATIONAL_ENABLEMENT
    PREVENTIVE != OPERATIONAL_ENABLEMENT

A porta declara **cobertura** além de classificar, e isso não é
cerimônia. Um classificador que não alcança todo o vocabulário fechado
não pode ser distinguido, pela resposta, de um que alcança e não achou
nada: ambos devolvem conjunto vazio. Sem a declaração de cobertura, um
produtor incapaz seria indistinguível de um produtor silencioso — e o
sistema inteiro passaria a rodar sobre proteção vazia acreditando estar
protegido.

    EMPTY RESULT != PROVEN ABSENCE
    UNCOVERED CLASSIFIER != SILENT CLASSIFIER
"""

from dataclasses import dataclass, field
from typing import Protocol

from app.memory.models.governance_enums import (
    CapabilityEngagement,
    CriticalCapability,
)


@dataclass(frozen=True)
class SemanticClassification:
    """O que a porta devolve. Tipado nos valores canônicos, sempre.

    `rationale` é descritivo e nunca é lido para decidir — mesma
    disciplina de `stated_intent` na fronteira E4:

        CLAIMED PURPOSE != PROVEN PURPOSE
    """

    capabilities: frozenset[CriticalCapability] = field(default_factory=frozenset)
    engagement: CapabilityEngagement = CapabilityEngagement.UNSPECIFIED
    rationale: str | None = None

    def __post_init__(self) -> None:
        """Invariantes na construção — disciplina de E4.2.1.

        Validar aqui, e não no broker, importa: uma classificação
        malformada nunca chega a existir como objeto, então não há
        caminho pelo qual ela seja construída em algum outro lugar e
        entregue já inválida.
        """
        capacidades = self.capabilities
        if isinstance(capacidades, str | bytes) or not hasattr(capacidades, "__iter__"):
            raise TypeError("capabilities deve ser um iterável de CriticalCapability")
        itens = tuple(capacidades)
        if any(not isinstance(item, CriticalCapability) for item in itens):
            raise TypeError("capabilities aceita apenas CriticalCapability")
        object.__setattr__(self, "capabilities", frozenset(itens))

        if not isinstance(self.engagement, CapabilityEngagement):
            raise TypeError("engagement deve ser um CapabilityEngagement")

        if self.rationale is not None:
            if not isinstance(self.rationale, str):
                raise TypeError("rationale deve ser str ou None")
            if not self.rationale.strip():
                raise ValueError("rationale não pode ser vazio ou apenas espaços — omita-o")


class SemanticCapabilityClassifierPort(Protocol):
    """Classificador semântico autorizado.

    `classifier_version` identifica a competência que classificou, e
    entra no descritor: sem ela é impossível responder, depois, sob qual
    classificador algo foi liberado ou recusado.

    `covered_capabilities` declara o alcance. O broker exige cobertura
    **total** do vocabulário fechado — ver `ports.py` no topo.
    """

    @property
    def classifier_version(self) -> str:
        """Versão da competência semântica que classifica."""
        ...

    @property
    def covered_capabilities(self) -> frozenset[CriticalCapability]:
        """Capacidades que este classificador é capaz de reconhecer."""
        ...

    def classify(self, *, objective: str) -> SemanticClassification:
        """Classifica o objetivo nos valores canônicos.

        Levantar exceção é resposta legítima — o broker a converte em
        indisponibilidade técnica, nunca em permissão.
        """
        ...
