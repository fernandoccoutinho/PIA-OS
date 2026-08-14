"""
`GovernanceManager` — avaliação de admissibilidade cognitiva (E4.3).

```
MemoryContext + CognitiveOperation + GovernancePolicy
                        ↓
                GovernanceDecision
```

```
GOVERNANCE MAY RESTRICT ACCESS
GOVERNANCE MUST NOT REWRITE EXISTENCE
```

**A avaliação é estritamente read-only.** Publicar uma versão de
policy escreve — na tabela da própria policy, nunca em patrimônio.
Avaliar não escreve em lugar nenhum, e isso é provado por listener de
cursor, não afirmado.

O que este serviço **não** faz, e a lista importa tanto quanto a
anterior:

- não autentica nem afirma identidade
  (`ACTOR_REF != AUTHENTICATED IDENTITY`);
- não decide autorização de aplicação, endpoint, papel ou ACL;
- não executa Search nem Retrieval (E4.6);
- não avalia nem transiciona `AccessibilityState` (E4.7);
- não cria, altera ou remove `CognitiveObject`, COID, CLID,
  membership, `MemoryDomain`, proveniência ou história causal;
- não repara, não aprende, não pontua;
- não fabrica "não encontrado" a partir de uma negativa.

```
GOVERNANCE != TRUTH ENGINE
GOVERNANCE != LEARNING ENGINE
GOVERNANCE != REPAIR ENGINE
GOVERNANCE != COUT DECISION ENGINE
```
"""

from datetime import datetime

from app.memory.models.governance_enums import (
    CognitiveOperation,
    GovernanceEffect,
    GovernanceOutcome,
)
from app.memory.models.governance_policy import GovernancePolicy
from app.memory.repositories.governance_policy_repository import GovernancePolicyRepository
from app.memory.schemas.governance import GovernanceDecision, GovernanceRule
from app.memory.schemas.memory_context import MemoryContext


class GovernanceManager:
    """Publicação de versões e avaliação de admissibilidade."""

    def __init__(self, policy_repository: GovernancePolicyRepository) -> None:
        self._policies = policy_repository

    # --- publicação (escreve apenas na tabela de policies) -------------

    def publish_version(
        self,
        *,
        policy_key: str,
        rules: tuple[GovernanceRule, ...] = (),
        version: int | None = None,
        effective_from: datetime | None = None,
        effective_until: datetime | None = None,
    ) -> GovernancePolicy:
        """Publica uma versão. `version=None` sugere a próxima.

        A sugestão é conveniência, não reserva: entre calcular
        `max_version() + 1` e gravar, outra sessão pode publicar a
        mesma versão — e aí a constraint do banco recusa, que é o
        desfecho correto. Inventar um lock para fechar essa janela
        seria custo sem invariante novo, mesma decisão de E3.4.1 e da
        E4.1.
        """
        alvo = self._policies.max_version(policy_key) + 1 if version is None else version
        return self._policies.add_policy(
            policy_key=policy_key,
            version=alvo,
            rules=rules,
            effective_from=effective_from,
            effective_until=effective_until,
        )

    def get_version(self, policy_key: str, version: int) -> GovernancePolicy | None:
        return self._policies.get_version(policy_key, version)

    def list_versions(self, policy_key: str) -> list[GovernancePolicy]:
        return self._policies.list_versions(policy_key)

    def effective_version_at(self, policy_key: str, moment: datetime) -> GovernancePolicy | None:
        """Versão vigente num instante — `[from, until)`."""
        return self._policies.effective_version_at(policy_key, moment)

    # --- avaliação (read-only) ----------------------------------------

    def evaluate(
        self,
        *,
        policy: GovernancePolicy,
        operation: CognitiveOperation,
        context: MemoryContext,
    ) -> GovernanceDecision:
        """Avalia uma operação sob uma versão de policy e um contexto.

        **Precedência: `DENY_OVERRIDES`.** Havendo qualquer regra
        aplicável com `DENY`, o resultado é `INADMISSIBLE`, por mais
        regras que admitam. É a única precedência defensável para um
        sistema cujo princípio é "governança pode restringir": uma
        restrição que desaparece porque outra regra permite não é
        restrição.

        **Nenhuma regra aplicável ⇒ `NOT_APPLICABLE`**, nunca
        `INADMISSIBLE` e nunca `ADMISSIBLE`. Colapsar ausência de
        regra em negação apagaria a diferença entre "ninguém decidiu
        sobre isto" e "alguém proibiu" — providências diferentes para
        quem administra. E colapsar em admissão seria pior ainda:
        transformaria silêncio em permissão.

        Determinístico: as regras são avaliadas em ordem canônica
        (`effect`, depois `rule_id`), então a regra citada como
        fundamento é reproduzível entre execuções e instâncias.

        Não escreve absolutamente nada.
        """
        dominios = frozenset(context.domain_ids)
        aplicaveis = [
            rule
            for rule in sorted(policy.typed_rules, key=lambda r: r.sort_key())
            if rule.matches(
                operation=operation,
                domain_ids=dominios,
                actor_ref=context.actor_ref,
                purpose=context.purpose,
            )
        ]

        if not aplicaveis:
            return self._decision(
                policy=policy,
                operation=operation,
                context=context,
                outcome=GovernanceOutcome.NOT_APPLICABLE,
                rule=None,
                reason=(
                    "nenhuma regra desta versão se aplica ao contexto — "
                    "ausência de regra não concede admissibilidade"
                ),
            )

        negacoes = [rule for rule in aplicaveis if rule.effect is GovernanceEffect.DENY]
        if negacoes:
            return self._decision(
                policy=policy,
                operation=operation,
                context=context,
                outcome=GovernanceOutcome.INADMISSIBLE,
                rule=negacoes[0],
                reason=f"regra '{negacoes[0].rule_id}' nega a operação (DENY_OVERRIDES)",
            )

        return self._decision(
            policy=policy,
            operation=operation,
            context=context,
            outcome=GovernanceOutcome.ADMISSIBLE,
            rule=aplicaveis[0],
            reason=f"regra '{aplicaveis[0].rule_id}' admite a operação",
        )

    @staticmethod
    def _decision(
        *,
        policy: GovernancePolicy,
        operation: CognitiveOperation,
        context: MemoryContext,
        outcome: GovernanceOutcome,
        rule: GovernanceRule | None,
        reason: str,
    ) -> GovernanceDecision:
        """Monta a decisão explicável.

        Carrega policy, versão, operação e as dimensões do contexto
        que participaram — é o que permite auditar depois **sob qual
        configuração** algo foi decidido. Não é persistida: uma
        decisão é resultado datado contra uma versão, sempre derivável
        de novo.
        """
        return GovernanceDecision(
            outcome=outcome,
            operation=operation,
            policy_key=policy.policy_key,
            policy_version=policy.version,
            policy_id=policy.id,
            context_domain_ids=context.domain_ids,
            context_actor_ref=context.actor_ref,
            context_purpose=context.purpose,
            matched_rule_id=rule.rule_id if rule is not None else None,
            reason=reason,
        )
