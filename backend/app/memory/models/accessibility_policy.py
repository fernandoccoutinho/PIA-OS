"""
`AccessibilityPolicy` — política local de admissibilidade e transição de
`AccessibilityState` (`E4.7`).

## O que é, e o que não é

```text
AccessibilityPolicy != AccessibilityState
AccessibilityPolicy != GovernancePolicy
AccessibilityPolicy != CognitiveObject
AccessibilityPolicy != MemoryContext
AccessibilityPolicy != RetentionPolicy
AccessibilityPolicy != ACL de banco ou endpoint
```

É **configuração local**, não patrimônio cognitivo. Não tem COID, CLID,
linhagem, proveniência ou história causal; não participa do Sync:

```text
ACCESSIBILITY_POLICY_PORTABLE = FALSE
ACCESSIBILITY_POLICY_SYNC = NONE
```

A razão é a mesma que a E4.3 congelou para `GovernancePolicy`:
autoridade não é transferível, e uma policy importada produziria
autoridade que ninguém concedeu nesta instalação.

## Subordinada à governança

A E4.7 **não inventa autoridade**. Uma transição só é avaliada depois de
`GovernanceManager.resolve()` autorizar `ACCESSIBILITY_TRANSITION` — a
operação que a E4.3.3 acrescentou ao vocabulário fechado, alcançável
apenas por regra que a enumere expressamente.

```text
GOVERNANCE DECIDES AUTHORITY
ACCESSIBILITY POLICY APPLIES UNDER GOVERNANCE AUTHORITY
```

## Identidade em duas camadas

Mesma disciplina da E4.3: `id` é identidade de **registro** (uma linha,
uma versão) e `policy_key` é identidade **lógica**, estável entre
versões. Uma decisão cita `policy_key` mais a `version` que de fato
avaliou.
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, Integer, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeEngine

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.memory.schemas.accessibility import AccessibilityRule

_RULES_JSON: TypeEngine[Any] = JSON().with_variant(JSONB(), "postgresql")  # type: ignore[no-untyped-call]
"""JSONB no PostgreSQL, JSON nos testes — apenas armazenamento de regras
**tipadas**. O tipo do domínio é `AccessibilityRule`; o JSON é o meio,
não a fonte da verdade."""


class AccessibilityPolicy(BaseModel):
    """Versão publicada de uma política de acessibilidade.

    Publicada é **imutável**: mudar semântica exige nova versão, nunca
    reescrita. Isso vale por três camadas — `UNIQUE(policy_key, version)`
    no banco, override de `update`/`delete` no repositório, e eventos de
    mapper que pegam a mutação feita por fora do repositório.

    A terceira camada existe porque a E4.3.1 reproduziu exatamente esse
    defeito: mutar o atributo do objeto carregado e chamar `commit()`
    contornava o repositório.
    """

    __tablename__ = "accessibility_policies"

    policy_key: Mapped[str] = mapped_column(nullable=False, index=True)
    """Identidade lógica, estável entre versões. Não é o `id`."""

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    """Versão monotônica dentro do `policy_key`, começando em 1."""

    governance_policy_key: Mapped[str] = mapped_column(nullable=False)
    """`policy_key` da `GovernancePolicy` cuja autoridade esta policy
    exige.

    Declarado como **texto**, sem FK: a autoridade é resolvida pelo
    caminho canônico `GovernanceManager.resolve()`, que já busca a
    versão vigente. Uma FK apontaria para uma linha de versão
    específica e congelaria a autoridade numa versão que pode ter sido
    sucedida — exatamente o oposto do versionamento que a E4.3
    estabeleceu.
    """

    rules: Mapped[list[dict[str, Any]]] = mapped_column(_RULES_JSON, nullable=False, default=list)
    """Regras serializadas de forma **determinística**.

    Conjuntos viram listas ordenadas: sem canonicalização, o mesmo
    conjunto de regras produziria bytes diferentes a cada gravação, e
    comparar versões viraria loteria.
    """

    effective_from: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    """Início da vigência. `None` = vigente desde sempre."""

    effective_until: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    """Fim da vigência (**exclusivo**). `None` = sem fim previsto.

    Exclusivo de propósito: com limite inclusivo, duas versões contíguas
    se sobrepõem no instante da virada, e "qual valia?" passa a ter duas
    respostas.
    """

    __table_args__ = (
        UniqueConstraint("policy_key", "version", name="uq_accessibility_policies_key_version"),
        CheckConstraint("version >= 1", name="ck_accessibility_policies_version_positive"),
        CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL "
            "OR effective_until > effective_from",
            name="ck_accessibility_policies_effective_window",
        ),
    )
    """`UNIQUE(policy_key, version)` é a autoridade final contra
    sobrescrita **e** contra a corrida de duas sessões publicando a mesma
    versão. O repositório traduz a violação para exceção de domínio; o
    banco é quem garante."""

    @staticmethod
    def serialize_rules(rules: "tuple[AccessibilityRule, ...]") -> list[dict[str, Any]]:
        """Converte regras tipadas em JSON canônico.

        Estados viram listas ordenadas pelo **token exato** que a E3
        persiste — sem normalização, mesma disciplina congelada na
        E4.5.1 para `qualifier`.
        """
        ids = [rule.rule_id for rule in rules]
        duplicados = sorted({rid for rid in ids if ids.count(rid) > 1})
        if duplicados:
            raise ValueError(
                f"rule_id duplicado na mesma versão: {', '.join(duplicados)} — "
                "duplicata torna o fundamento da decisão ambíguo"
            )
        return [
            {
                "rule_id": rule.rule_id,
                "effect": rule.effect.value,
                "source_states": sorted(rule.source_states),
                "target_states": sorted(rule.target_states),
            }
            for rule in sorted(rules, key=lambda r: r.sort_key())
        ]

    @staticmethod
    def deserialize_rules(payload: list[dict[str, Any]]) -> "tuple[AccessibilityRule, ...]":
        """Reconstrói regras tipadas a partir do JSON.

        Reconstrói **pelo construtor**, que reaplica todos os
        invariantes. Um token fora do vocabulário levanta erro em vez de
        virar regra silenciosamente inerte — que seria o pior desfecho:
        uma policy que parece restringir e não restringe.
        """
        from app.memory.models.governance_enums import GovernanceEffect
        from app.memory.schemas.accessibility import AccessibilityRule

        return tuple(
            AccessibilityRule(
                rule_id=item["rule_id"],
                effect=GovernanceEffect(item["effect"]),
                source_states=frozenset(item["source_states"]),
                target_states=frozenset(item["target_states"]),
            )
            for item in payload
        )


@event.listens_for(AccessibilityPolicy, "before_update")
def _reject_published_accessibility_policy_update(
    mapper: object, connection: object, target: AccessibilityPolicy
) -> None:
    """Rejeita qualquer `UPDATE` numa versão já publicada.

    Sobrescrever `update()` no repositório não basta — a E4.3.1
    reproduziu o defeito contornando o repositório. O evento de mapper
    pega esse caminho, porque só dispara quando o SQLAlchemy já decidiu
    emitir o `UPDATE`.
    """
    from app.memory.errors.exceptions import AccessibilityPolicyImmutableError

    raise AccessibilityPolicyImmutableError(target.id, operation="update")


@event.listens_for(AccessibilityPolicy, "before_delete")
def _reject_published_accessibility_policy_delete(
    mapper: object, connection: object, target: AccessibilityPolicy
) -> None:
    """Rejeita qualquer `DELETE` numa versão já publicada.

    Alcance declarado com honestidade: isto protege o caminho ORM, que é
    o caminho da aplicação. `UPDATE`/`DELETE` por SQL direto continua
    possível — como em toda a E3 — e o documento diz isso em vez de
    afirmar garantia de banco que não existe.
    """
    from app.memory.errors.exceptions import AccessibilityPolicyImmutableError

    raise AccessibilityPolicyImmutableError(target.id, operation="delete")
