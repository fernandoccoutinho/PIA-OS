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

from datetime import UTC, datetime

from app.memory.models.governance_enums import (
    CognitiveOperation,
    GovernanceEffect,
    GovernanceOutcome,
)
from app.memory.models.governance_policy import GovernancePolicy
from app.memory.repositories.governance_policy_repository import GovernancePolicyRepository
from app.memory.schemas.governance import (
    GovernanceDecision,
    GovernanceResolution,
    GovernanceRule,
)
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.platform_safety_boundary import (
    CapabilityDescriptor,
    SafetyAssessment,
    assess_capability,
)


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

        **Esta função não é autoridade ativa.** Ela avalia a policy que
        lhe derem — inclusive uma nunca publicada ou fora de vigência —
        e existe como função pura reutilizável. O caminho público
        canônico é `resolve()`, que busca a versão vigente por
        `policy_key` e passa pela fronteira de segurança antes.
        Corretivo `E4.3.1`, defeito 5.
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

    # --- caminho canônico: fronteira → policy → resolução -------------

    def resolve(
        self,
        *,
        descriptor: CapabilityDescriptor,
        context: MemoryContext,
        policy_key: str | None = None,
        moment: datetime | None = None,
    ) -> GovernanceResolution:
        """Caminho público canônico (E4.3.1).

        ```
        PLATFORM SAFETY BOUNDARY   → não sobreponível
                ↓
        LOCAL GOVERNANCE POLICY    → versão vigente, buscada aqui
                ↓
        GOVERNANCE RESOLUTION
        ```

        Não aceita objeto `GovernancePolicy` do chamador: recebe
        `policy_key` e busca a **versão vigente** no instante dado.
        Era esse o defeito 5 — o caminho público avaliava qualquer
        policy fornecida como se fosse autoridade ativa.

        Quando a fronteira proíbe, **a policy local sequer é
        consultada**. Não é otimização: consultá-la sugeriria que o
        resultado poderia depender dela, e não pode.

        Uma leitura de banco no máximo (a versão vigente). Nenhuma
        escrita, nenhuma consulta por `CognitiveObject`, nenhuma
        `Search`/`Retrieval`, nenhuma chamada de ferramenta ou
        provider, nenhum score.
        """
        agora = moment if moment is not None else datetime.now(UTC)
        avaliacao = assess_capability(descriptor)

        if avaliacao.prohibits:
            return self._prohibited_resolution(descriptor, avaliacao, context)

        if policy_key is None:
            return self._no_policy_resolution(descriptor, avaliacao, context)

        policy = self._policies.effective_version_at(policy_key, agora)
        if policy is None:
            return self._no_policy_resolution(
                descriptor,
                avaliacao,
                context,
                nota=(
                    f"nenhuma versão de '{policy_key}' vigente em {agora.isoformat()} — "
                    "ausência de policy não concede admissibilidade"
                ),
            )

        decisao = self.evaluate(policy=policy, operation=descriptor.operation, context=context)
        return GovernanceResolution(
            outcome=decisao.outcome,
            operation=descriptor.operation,
            # Propagado da DECISÃO, não recomposto do contexto: é a
            # decisão que registra o que a policy de fato consumiu
            # (corretivo E4.3.4).
            context_domain_ids=decisao.context_domain_ids,
            context_actor_ref=decisao.context_actor_ref,
            context_purpose=decisao.context_purpose,
            safety_boundary_version=avaliacao.boundary_version,
            safety_rationale=avaliacao.rationale,
            preserved_intent=avaliacao.preserved_intent,
            policy_key=decisao.policy_key,
            policy_version=decisao.policy_version,
            policy_id=decisao.policy_id,
            matched_rule_id=decisao.matched_rule_id,
            policy_rationale=decisao.reason,
        )

    @staticmethod
    def _prohibited_resolution(
        descriptor: CapabilityDescriptor,
        avaliacao: SafetyAssessment,
        context: MemoryContext,
    ) -> GovernanceResolution:
        """Resolução de um pedido recusado pela fronteira.

        Bloqueia a capacidade, preserva **apenas** intenção legítima
        demonstrável, oferece alternativas como proposta e declara o
        que foi preservado e o que foi perdido.

        Nenhum campo da policy local é preenchido — ela não foi
        consultada, e fingir que foi seria proveniência falsa.

        O **contexto**, ao contrário, é vinculado (corretivo E4.3.4):
        a fronteira não consultou policy, mas recebeu uma pergunta.

            NO LOCAL POLICY CONSULTED != NO CONTEXT RECEIVED
            CONTEXT BINDING != LOCAL POLICY PROVENANCE
        """
        preservou: list[str] = []
        perdeu: list[str] = ["a capacidade operacional solicitada"]
        if avaliacao.preserved_intent:
            preservou.append(f"finalidade declarada: {avaliacao.preserved_intent}")
        if avaliacao.admissible_alternatives:
            preservou.append("caminhos legítimos de trabalho sobre o assunto")
        else:  # pragma: no cover - toda capacidade do catálogo tem alternativas
            perdeu.append("nenhuma alternativa catalogada para esta capacidade")

        return GovernanceResolution(
            outcome=GovernanceOutcome.PROHIBITED,
            operation=descriptor.operation,
            context_domain_ids=context.domain_ids,
            context_actor_ref=context.actor_ref,
            context_purpose=context.purpose,
            safety_boundary_version=avaliacao.boundary_version,
            safety_rationale=avaliacao.rationale,
            blocked_capabilities=avaliacao.blocked_capabilities,
            preserved_intent=avaliacao.preserved_intent,
            admissible_alternatives=avaliacao.admissible_alternatives,
            constraints=(
                "a fronteira da plataforma não é sobreponível por policy local, "
                "ator, propósito ou domínio",
                "alternativas são propostas; nenhuma é executada automaticamente",
            ),
            declared_preservations=tuple(preservou),
            declared_losses=tuple(perdeu),
        )

    @staticmethod
    def _no_policy_resolution(
        descriptor: CapabilityDescriptor,
        avaliacao: SafetyAssessment,
        context: MemoryContext,
        *,
        nota: str = "nenhuma policy local informada",
    ) -> GovernanceResolution:
        """A fronteira não se opõe, mas não há policy local vigente.

        `NOT_APPLICABLE`, nunca `ADMISSIBLE`: a fronteira **não
        admite** — ela proíbe ou se cala. Silêncio da plataforma somado
        a ausência de policy continua sendo ausência de autorização.
        """
        return GovernanceResolution(
            outcome=GovernanceOutcome.NOT_APPLICABLE,
            operation=descriptor.operation,
            context_domain_ids=context.domain_ids,
            context_actor_ref=context.actor_ref,
            context_purpose=context.purpose,
            safety_boundary_version=avaliacao.boundary_version,
            safety_rationale=avaliacao.rationale,
            preserved_intent=avaliacao.preserved_intent,
            policy_rationale=nota,
        )
