"""
`RetentionPolicy` — configuração de retenção persistida (`E4.9.6`).

```text
RetentionPolicy != CognitiveObject
RetentionPolicy != CognitivePatrimony
RetentionPolicy != ApprovalRecord
RetentionPolicy != ErasureRecord

RETENTION_POLICY_PORTABLE = FALSE
RETENTION_POLICY_SYNC     = NONE
```

Uma policy não tem COID, não tem CLID, não tem linhagem, não tem
proveniência, não tem história causal e não participa de
transformações. É configuração **local**, pela mesma razão congelada
na E4.0 para `GovernancePolicy`: autoridade não é transferível, e uma
policy importada regularia patrimônio alheio sem que ninguém no
destino tivesse decidido isso.

**Versões publicadas são imutáveis.** Correção semântica cria versão
nova, nunca sobrescreve — sem isso, é impossível responder meses
depois sob qual regra determinado item se tornou elegível a avaliação.

## O que esta tabela NÃO faz

```text
RETENTION_POLICY_PERSISTENCE != RETENTION_EVALUATION
RETENTION_EVALUATION         != USER_DECISION
USER_DECISION                != DESTRUCTIVE_EXECUTION
```

Publicar uma policy é **configurar uma regra futura**, não rodá-la.
Nenhum avaliador foi composto; nada consulta esta tabela para agir.
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeEngine

from app.models.base_model import BaseModel

if TYPE_CHECKING:  # pragma: no cover - somente para tipagem
    from app.memory.schemas.retention import RetentionRule

_RULES_JSON: TypeEngine[Any] = JSON().with_variant(JSONB(), "postgresql")  # type: ignore[no-untyped-call]
"""JSONB no PostgreSQL, JSON genérico nos demais.

Mesmo precedente de `GovernancePolicy` e `AccessibilityPolicy`: o JSON
é **meio de transporte para o disco**, não contrato de domínio. Nada é
lido de volta sem passar pelo desserializador tipado, que reconstrói
pelo construtor de `RetentionRule` e reaplica todos os invariantes.

Limite declarado honestamente: o banco garante que a coluna é JSON
válido e não vazio. A **forma** das regras é garantia do tipo, não da
constraint — e afirmar o contrário seria alegar verificação que o
banco não faz.
"""

MAX_KEY_LENGTH = 256
"""Teto das identidades lógicas, alinhado ao limite da E4.9.5."""


class RetentionPolicy(BaseModel):
    """Policy de retenção local e versionada.

    Identidade em duas camadas, como as policies existentes:

    - `id` — identidade de **registro** (uma linha, uma versão);
    - `policy_key` — identidade **lógica**, estável entre versões.
    """

    __tablename__ = "retention_policies"

    policy_key: Mapped[str] = mapped_column(String(MAX_KEY_LENGTH), nullable=False, index=True)
    """Identidade lógica, estável entre versões. Não é o `id`."""

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    """Versão monotônica dentro do `policy_key`, começando em 1."""

    governance_policy_key: Mapped[str] = mapped_column(String(MAX_KEY_LENGTH), nullable=False)
    """`policy_key` da `GovernancePolicy` cuja autoridade esta policy exige.

    Texto, **sem FK** — mesmo raciocínio de `AccessibilityPolicy`: uma
    FK apontaria para a linha de uma versão específica e congelaria a
    autoridade numa versão que pode ter sido sucedida, o oposto do
    versionamento que a E4.3 estabeleceu.
    """

    rules: Mapped[list[dict[str, Any]]] = mapped_column(_RULES_JSON, nullable=False)
    """Regras serializadas de forma **determinística**, nunca vazias.

    Sem `default`: uma policy publicada sem regra não expressa retenção
    alguma, e ausência de policy já representa ausência de regra
    aplicável. Um default de lista vazia tornaria trivial publicar uma
    policy que parece regular algo e não regula nada.

    Conjuntos viram listas ordenadas na serialização: `frozenset` não
    tem ordem estável entre execuções, e sem canonicalização o mesmo
    conjunto de regras produziria bytes diferentes a cada gravação.
    """

    effective_from: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    """Início da vigência. `None` = vigente desde sempre."""

    effective_until: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    """Fim da vigência (**exclusivo**). `None` = sem fim previsto.

    Exclusivo de propósito: com limite inclusivo, duas versões
    contíguas se sobrepõem exatamente no instante da virada, e a
    pergunta "qual valia?" passa a ter duas respostas.
    """

    __table_args__ = (
        UniqueConstraint("policy_key", "version", name="uq_retention_policies_key_version"),
        CheckConstraint("version >= 1", name="ck_retention_policies_version_positive"),
        CheckConstraint(
            "length(btrim(policy_key)) > 0",
            name="ck_retention_policies_policy_key_not_blank",
        ),
        CheckConstraint(
            "length(btrim(governance_policy_key)) > 0",
            name="ck_retention_policies_governance_key_not_blank",
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL "
            "OR effective_until > effective_from",
            name="ck_retention_policies_effective_window",
        ),
    )
    """`UNIQUE(policy_key, version)` é a autoridade final contra
    sobrescrita silenciosa **e** contra a corrida de duas sessões
    publicando a mesma versão. O repositório traduz a violação para
    exceção de domínio; o banco é quem garante.

    Não há `CHECK` sobre o conteúdo de `rules` além de `NOT NULL`. A
    não vacuidade e a forma das regras são impostas pelo tipo, na
    serialização — e este docstring diz isso em vez de sugerir uma
    garantia de banco que não existe.
    """

    @staticmethod
    def serialize_rules(rules: "tuple[RetentionRule, ...]") -> list[dict[str, Any]]:
        """Converte regras tipadas em JSON canônico.

        Recusa conjunto vazio e `rule_id` duplicado. Duplicata tornaria
        o fundamento de uma avaliação ambíguo — mesma disciplina de
        `GovernancePolicy.serialize_rules`.
        """
        if not rules:
            raise ValueError(
                "uma versão de RetentionPolicy exige ao menos uma regra — "
                "policy sem regra não expressa retenção alguma"
            )

        ids = [regra.rule_id for regra in rules]
        duplicados = sorted({rid for rid in ids if ids.count(rid) > 1})
        if duplicados:
            raise ValueError(
                f"rule_id duplicado na mesma versão: {', '.join(duplicados)} — "
                "duplicata torna o fundamento da avaliação ambíguo"
            )

        return [
            {
                "rule_id": regra.rule_id,
                "scope_kind": regra.scope_kind.value,
                "domain_ids": sorted(str(d) for d in regra.domain_ids),
                "anchor": regra.anchor.value,
                "minimum_age_days": regra.minimum_age_days,
                "on_expiry_action": regra.on_expiry_action.value,
            }
            for regra in sorted(rules, key=lambda r: r.sort_key())
        ]

    @staticmethod
    def deserialize_rules(payload: list[dict[str, Any]]) -> "tuple[RetentionRule, ...]":
        """Reconstrói regras tipadas a partir do JSON.

        Reconstrói **pelo construtor**, que reaplica todos os
        invariantes. Um valor fora do vocabulário fechado levanta erro
        em vez de virar regra silenciosamente inerte — que seria o pior
        desfecho: uma policy que parece reter e não retém.
        """
        import uuid as _uuid

        from app.memory.models.retention_enums import (
            RetentionAnchor,
            RetentionExpiryAction,
            RetentionScopeKind,
        )
        from app.memory.schemas.retention import RetentionRule

        if not payload:
            raise ValueError("payload de regras vazio — versão inválida")

        vistos: set[str] = set()
        for item in payload:
            if item["rule_id"] in vistos:
                raise ValueError(
                    f"rule_id duplicado na mesma versão: '{item['rule_id']}' — "
                    "duplicata torna o fundamento da avaliação ambíguo"
                )
            vistos.add(item["rule_id"])

        return tuple(
            RetentionRule(
                rule_id=item["rule_id"],
                scope_kind=RetentionScopeKind(item["scope_kind"]),
                domain_ids=frozenset(_uuid.UUID(d) for d in item["domain_ids"]),
                anchor=RetentionAnchor(item["anchor"]),
                minimum_age_days=item["minimum_age_days"],
                on_expiry_action=RetentionExpiryAction(item["on_expiry_action"]),
            )
            for item in payload
        )

    @property
    def typed_rules(self) -> "tuple[RetentionRule, ...]":
        """Regras desta versão, já tipadas."""
        return RetentionPolicy.deserialize_rules(self.rules or [])


@event.listens_for(RetentionPolicy, "before_update")
def _reject_retention_policy_update(
    mapper: object, connection: object, target: RetentionPolicy
) -> None:
    """Rejeita qualquer `UPDATE` numa versão publicada.

    Camada 1 de 3. Pega a mutação feita **por fora** do repositório —
    carregar o objeto, mutar o atributo e chamar `commit()` contorna
    qualquer override de método, e a E4.3.1 reproduziu esse defeito de
    verdade.
    """
    from app.memory.errors.exceptions import RetentionPolicyImmutableError

    raise RetentionPolicyImmutableError(target.id, operation="update")


@event.listens_for(RetentionPolicy, "before_delete")
def _reject_retention_policy_delete(
    mapper: object, connection: object, target: RetentionPolicy
) -> None:
    """Rejeita qualquer `DELETE` numa versão publicada.

    Remover a policy que fundamentou avaliações passadas apagaria o
    fundamento sem apagar a consequência.
    """
    from app.memory.errors.exceptions import RetentionPolicyImmutableError

    raise RetentionPolicyImmutableError(target.id, operation="delete")
