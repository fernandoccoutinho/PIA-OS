"""
`PlatformSafetyBoundary` — piso de segurança da plataforma (E4.3.1).

```
PLATFORM SAFETY BOUNDARY      ← este módulo, não sobreponível
        ↓
LOCAL GOVERNANCE POLICY       ← E4.3
        ↓
GOVERNANCE RESOLUTION
```

**Vive em código, não em tabela**, e isso decorre diretamente da
palavra "não sobreponível": uma fronteira guardada numa linha que o
operador da instalação pode editar é sobreponível por definição. A
consequência é aceita e desejada — alterá-la exige alterar código e
passar por revisão.

Nenhuma migração, nenhuma linha de banco, nenhum estado mutável.

O que este módulo **não** faz:

- não lê texto livre nem usa palavra-chave como decisão canônica;
- não implementa classificador NLP;
- não chama provider nem ferramenta alguma;
- não calcula score de risco;
- não consulta banco, `Search` ou `Retrieval`;
- não escreve nada.

A avaliação é uma **função pura sobre um descritor tipado**.
"""

from dataclasses import dataclass, field

from app.memory.models.governance_enums import (
    CapabilityEngagement,
    CognitiveOperation,
    CriticalCapability,
    GovernanceOutcome,
)

PLATFORM_SAFETY_BOUNDARY_VERSION = 1
"""Versão da fronteira, citada em toda resolução.

Versionada como as policies locais, pela mesma razão: sem isso é
impossível responder, depois, sob qual fronteira algo foi recusado.
"""

_ENGAGEMENTS_THAT_PROHIBIT: frozenset[CapabilityEngagement] = frozenset(
    {
        CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        CapabilityEngagement.UNSPECIFIED,
    }
)
"""`UNSPECIFIED` proíbe — a decisão mais consequente deste módulo.

Diante de capacidade crítica, ausência de finalidade legítima
demonstrável não autoriza inventar uma:

    MISSING SAFE INTENT != AUTHORIZATION TO INVENT ONE

Tratar "não sei" como "provavelmente tudo bem" seria fabricar
finalidade — o mesmo erro que a E3 proíbe em outro registro
(`MISSING EVIDENCE != AUTHORIZATION TO FABRICATE`).
"""

_ALTERNATIVES_BY_CAPABILITY: dict[CriticalCapability, tuple[str, ...]] = {
    CriticalCapability.CHILD_SEXUAL_EXPLOITATION: (
        "trabalho de prevenção e educação protetiva",
        "detecção e denúncia a canais competentes e a autoridades",
        "apoio a vítimas e encaminhamento a serviços de proteção",
        "pesquisa ética com dados sintéticos e supervisão institucional",
    ),
    CriticalCapability.MINOR_TARGETING_FOR_EXPLOITATION: (
        "reconhecimento de padrões de aliciamento para fins de proteção",
        "capacitação de responsáveis, escolas e moderação de plataformas",
        "detecção e denúncia a canais competentes e a autoridades",
        "pesquisa ética com dados sintéticos e supervisão institucional",
    ),
    CriticalCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT: (
        "história, política e direito de não proliferação",
        "defesa, biossegurança e preparo de resposta a incidentes",
        "análise de tratados, verificação e salvaguardas",
    ),
    CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT: (
        "proteção e resiliência de infraestrutura crítica",
        "detecção, resposta a incidentes e continuidade de operações",
        "análise de risco e regulação de segurança",
    ),
}
"""Catálogo curado de alternativas — **categorias**, nunca procedimento.

São propostas, e propor não autoriza (`REDIRECTION != AUTHORIZATION`).
Nada aqui contém detalhe operacional: o corretivo exige tanto oferecer
alternativa quanto **não conservar detalhe nocivo desnecessário**, e um
catálogo de categorias satisfaz os dois.
"""

_PRESERVABLE_ENGAGEMENTS: frozenset[CapabilityEngagement] = frozenset(
    {CapabilityEngagement.ANALYTICAL, CapabilityEngagement.PREVENTIVE}
)


@dataclass(frozen=True)
class CapabilityDescriptor:
    """Descritor **tipado** da operação submetida à fronteira.

    A classificação semântica que produz este descritor está **fora**
    deste módulo, e a fronteira é declarada em vez de escondida: nada
    aqui lê texto livre para decidir. `stated_intent` existe para
    registro, não para prova —

        CLAIMED PURPOSE != PROVEN PURPOSE

    Quem constrói o descritor assume a responsabilidade da
    classificação; este módulo assume a da consequência.
    """

    operation: CognitiveOperation
    capabilities: frozenset[CriticalCapability] = field(default_factory=frozenset)
    engagement: CapabilityEngagement = CapabilityEngagement.UNSPECIFIED
    stated_intent: str | None = None
    """Descritivo. Nunca é lido para decidir — nem por palavra-chave,
    nem por classificador. Aparece na resolução apenas quando o
    engajamento tipado já a torna preservável."""

    def __post_init__(self) -> None:
        """Invariantes em toda construção — disciplina de E4.2.1."""
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
        if self.stated_intent is not None:
            if not isinstance(self.stated_intent, str):
                raise TypeError("stated_intent deve ser str ou None")
            if not self.stated_intent.strip():
                raise ValueError("stated_intent não pode ser vazio ou apenas espaços — omita-o")


@dataclass(frozen=True)
class SafetyAssessment:
    """Resultado da fronteira. Imutável, transitório, não persistido."""

    outcome: GovernanceOutcome
    boundary_version: int
    blocked_capabilities: tuple[CriticalCapability, ...] = ()
    admissible_alternatives: tuple[str, ...] = ()
    preserved_intent: str | None = None
    rationale: str = ""

    @property
    def prohibits(self) -> bool:
        return self.outcome is GovernanceOutcome.PROHIBITED


def assess_capability(descriptor: CapabilityDescriptor) -> SafetyAssessment:
    """Avalia o descritor contra a fronteira. **Função pura.**

    Regra, inteira:

    ```
    sem capacidade crítica            → NOT_APPLICABLE
    engajamento analítico/preventivo  → NOT_APPLICABLE
    operacional ou não especificado   → PROHIBITED
    ```

    **A fronteira nunca admite.** Ela proíbe ou se cala. Um piso de
    segurança que concedesse permissão seria autoridade concorrente da
    policy local, e a ordem `fronteira → policy → resolução` deixaria
    de significar alguma coisa: `NOT_APPLICABLE` aqui quer dizer "a
    plataforma não se opõe", nunca "está autorizado".

    Analítico e preventivo passam adiante porque bloquear por tema
    destruiria o trabalho de prevenção, detecção e proteção que
    precisa falar sobre esses assuntos —

        TOPIC != CAPABILITY
    """
    if not descriptor.capabilities:
        return SafetyAssessment(
            outcome=GovernanceOutcome.NOT_APPLICABLE,
            boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
            rationale="nenhuma capacidade crítica declarada",
        )

    bloqueadas = tuple(sorted(descriptor.capabilities, key=lambda c: c.value))

    if descriptor.engagement not in _ENGAGEMENTS_THAT_PROHIBIT:
        return SafetyAssessment(
            outcome=GovernanceOutcome.NOT_APPLICABLE,
            boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
            preserved_intent=_preserved_intent(descriptor),
            rationale=(
                f"engajamento '{descriptor.engagement.value}' não habilita capacidade — "
                "a fronteira não se opõe; a policy local decide"
            ),
        )

    return SafetyAssessment(
        outcome=GovernanceOutcome.PROHIBITED,
        boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
        blocked_capabilities=bloqueadas,
        admissible_alternatives=alternatives_for(bloqueadas),
        preserved_intent=_preserved_intent(descriptor),
        rationale=(
            f"engajamento '{descriptor.engagement.value}' sobre capacidade crítica "
            f"({', '.join(c.value for c in bloqueadas)}) — recusado pela fronteira da "
            "plataforma, não sobreponível por policy local"
        ),
    )


def alternatives_for(capabilities: tuple[CriticalCapability, ...]) -> tuple[str, ...]:
    """Alternativas seguras para as capacidades bloqueadas.

    Categorias de trabalho legítimo, sem nenhum detalhe operacional.
    São **propostas**: nada as executa, e oferecê-las não autoriza a
    operação original.
    """
    reunidas: list[str] = []
    for capability in capabilities:
        for alternativa in _ALTERNATIVES_BY_CAPABILITY.get(capability, ()):
            if alternativa not in reunidas:
                reunidas.append(alternativa)
    return tuple(reunidas)


def _preserved_intent(descriptor: CapabilityDescriptor) -> str | None:
    """Intenção preservada — somente quando **demonstrável**.

    Só há o que preservar quando o engajamento tipado já é analítico
    ou preventivo. Em `UNSPECIFIED`, devolve `None`: não existe
    intenção legítima estabelecida, e escrevê-la a partir de
    `stated_intent` seria exatamente fabricar a finalidade ausente que
    a fronteira recusa.
    """
    if descriptor.engagement not in _PRESERVABLE_ENGAGEMENTS:
        return None
    return descriptor.stated_intent
