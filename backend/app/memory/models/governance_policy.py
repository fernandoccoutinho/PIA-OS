"""
`GovernancePolicy` — configuração de governança persistida (E4.3).

```
GovernancePolicy = configuração persistida
GovernancePolicy != CognitiveObject
GovernancePolicy != CognitivePatrimony

GOVERNANCE_POLICY_PORTABLE = FALSE
GOVERNANCE_POLICY_SYNC     = NONE
```

Uma policy não tem COID, não tem CLID, não tem linhagem, não tem
proveniência, não tem história causal e não participa de
transformações. É configuração **local** — congelado desde a E4.0:
autoridade não é transferível, e uma policy importada produziria
objetos invisíveis no destino sem que ninguém ali tivesse decidido
isso.

**Versões publicadas são imutáveis.** Mudança semântica cria versão
nova, nunca sobrescreve. É o mesmo princípio append-only que a E3
aplica a `ProvenanceRecord` e `CausalHistoryEvent`, pela mesma razão:
sem ele é impossível responder, meses depois, qual versão fundamentou
determinada decisão.
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, Integer, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeEngine

from app.models.base_model import BaseModel

if TYPE_CHECKING:  # pragma: no cover - somente para tipagem
    from app.memory.schemas.governance import GovernanceRule

_RULES_JSON: TypeEngine[Any] = JSON().with_variant(JSONB(), "postgresql")  # type: ignore[no-untyped-call]
"""JSONB no PostgreSQL, JSON genérico nos demais.

As regras são **tipadas** em memória (`GovernanceRule`); o JSON é
apenas o meio de transporte para o disco. Isso não é "JSON
arbitrário": nada é lido de volta sem passar pelo desserializador
tipado abaixo, que rejeita o que não couber no vocabulário fechado.
"""


class GovernancePolicy(BaseModel):
    """Policy local e versionada.

    Identidade em duas camadas, e a distinção importa:

    - `id` — identidade de **registro** (uma linha, uma versão);
    - `policy_key` — identidade **lógica**, estável entre versões.

    Duas linhas com o mesmo `policy_key` e versões diferentes são a
    mesma policy em momentos diferentes. É `policy_key` que uma
    decisão cita, junto da `version` que efetivamente avaliou.
    """

    __tablename__ = "governance_policies"

    policy_key: Mapped[str] = mapped_column(nullable=False, index=True)
    """Identidade lógica, estável entre versões. Não é o `id`."""

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    """Versão monotônica dentro do `policy_key`, começando em 1.

    Imutável depois de publicada — ver `rules`.
    """

    rules: Mapped[list[dict[str, Any]]] = mapped_column(_RULES_JSON, nullable=False, default=list)
    """Regras serializadas de forma **determinística**.

    Serialização e desserialização passam por `serialize_rules` /
    `deserialize_rules`, que ordenam conjuntos canonicamente. Sem
    isso, dois conjuntos logicamente iguais produziriam JSON diferente
    conforme a ordem de iteração — e comparar versões viraria loteria.
    """

    effective_from: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    """Início da vigência. `None` = vigente desde sempre."""

    effective_until: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    """Fim da vigência (exclusivo). `None` = sem fim previsto.

    Exclusivo de propósito: com limite inclusivo, duas versões
    contíguas se sobrepõem exatamente no instante da virada, e a
    pergunta "qual valia?" passa a ter duas respostas.
    """

    __table_args__ = (
        UniqueConstraint("policy_key", "version", name="uq_governance_policies_key_version"),
        CheckConstraint("version >= 1", name="ck_governance_policies_version_positive"),
        CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL "
            "OR effective_until > effective_from",
            name="ck_governance_policies_effective_window",
        ),
    )
    """`UNIQUE(policy_key, version)` é a autoridade final contra
    sobrescrita silenciosa **e** contra a corrida de duas sessões
    criando a mesma versão ao mesmo tempo. O repositório traduz a
    violação para uma exceção de domínio; o banco é quem garante.

    Os dois `CHECK` fecham o resto: versão sempre `>= 1`, e janela de
    vigência sempre coerente."""

    @staticmethod
    def serialize_rules(rules: "tuple[GovernanceRule, ...]") -> list[dict[str, Any]]:
        """Converte regras tipadas em JSON canônico.

        Todos os conjuntos viram listas **ordenadas**: `frozenset` não
        tem ordem estável entre execuções, e sem canonicalização o
        mesmo conjunto de regras produziria bytes diferentes a cada
        gravação.
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
                "operations": sorted(op.value for op in rule.operations),
                "domain_ids": sorted(str(d) for d in rule.domain_ids),
                "actor_refs": sorted(rule.actor_refs),
                "purposes": sorted(rule.purposes),
            }
            for rule in sorted(rules, key=lambda r: r.sort_key())
        ]

    @staticmethod
    def deserialize_rules(payload: list[dict[str, Any]]) -> "tuple[GovernanceRule, ...]":
        """Reconstrói regras tipadas a partir do JSON.

        Reconstrói **pelo construtor**, que reaplica todos os
        invariantes. Um valor fora do vocabulário fechado levanta erro
        em vez de virar regra silenciosamente inerte — que seria o
        pior desfecho possível: uma policy que parece restringir e não
        restringe.
        """
        from app.memory.models.governance_enums import (
            CognitiveOperation,
            GovernanceEffect,
        )
        from app.memory.schemas.governance import GovernanceRule

        vistos: set[str] = set()
        for item in payload:
            if item["rule_id"] in vistos:
                raise ValueError(
                    f"rule_id duplicado na mesma versão: '{item['rule_id']}' — "
                    "duplicata torna o fundamento da decisão ambíguo"
                )
            vistos.add(item["rule_id"])

        return tuple(
            GovernanceRule(
                rule_id=item["rule_id"],
                effect=GovernanceEffect(item["effect"]),
                operations=frozenset(CognitiveOperation(op) for op in item["operations"]),
                domain_ids=frozenset(uuid.UUID(d) for d in item["domain_ids"]),
                actor_refs=frozenset(item["actor_refs"]),
                purposes=frozenset(item["purposes"]),
            )
            for item in payload
        )

    @property
    def typed_rules(self) -> "tuple[GovernanceRule, ...]":
        """Regras desta versão, já tipadas."""
        return GovernancePolicy.deserialize_rules(self.rules or [])


@event.listens_for(GovernancePolicy, "before_update")
def _reject_published_policy_update(
    mapper: object, connection: object, target: GovernancePolicy
) -> None:
    """Rejeita qualquer `UPDATE` numa versão já publicada (E4.3.1).

    Sobrescrever `update()` no repositório não bastava: o defeito foi
    reproduzido **contornando o repositório**, mutando o atributo do
    objeto carregado e chamando `commit()`. O evento de mapper pega
    esse caminho, porque só dispara quando o SQLAlchemy já decidiu
    emitir um `UPDATE` para a linha existente.

    Mesma técnica que a E3 usa em `CognitiveObject` para recusar
    reatribuição de COID.
    """
    from app.memory.errors.exceptions import GovernancePolicyImmutableError

    raise GovernancePolicyImmutableError(target.id, operation="update")


@event.listens_for(GovernancePolicy, "before_delete")
def _reject_published_policy_delete(
    mapper: object, connection: object, target: GovernancePolicy
) -> None:
    """Rejeita qualquer `DELETE` numa versão já publicada (E4.3.1).

    Nota honesta sobre o alcance: isto protege o caminho ORM, que é o
    caminho da aplicação. Um `UPDATE`/`DELETE` SQL direto continua
    possível — como em toda a E3 — e o documento diz isso em vez de
    afirmar garantia de banco que não existe.
    """
    from app.memory.errors.exceptions import GovernancePolicyImmutableError

    raise GovernancePolicyImmutableError(target.id, operation="delete")
