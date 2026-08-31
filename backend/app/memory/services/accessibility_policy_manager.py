"""
`AccessibilityPolicyManager` — E4.7.

Aplica política local de admissibilidade e transição de
`AccessibilityState`, **sempre subordinada** à autoridade da E4.3.

```text
GOVERNANCE DECIDES AUTHORITY
ACCESSIBILITY POLICY APPLIES UNDER GOVERNANCE AUTHORITY
ACCESSIBILITY POLICY DOES NOT INVENT AUTHORITY
```

## Caminho canônico

```text
1. validar argumentos e o MemoryContext
2. ContextManager.validate + fidelidade pedido↔contexto
3. GovernanceManager.resolve(ACCESSIBILITY_TRANSITION)
4. fidelidade pedido↔resolução
5. se não autorizado: resultado explícito, SEM tocar no sujeito
6. resolver o sujeito e ADQUIRIR O LOCK
7. ler o estado de origem SOB LOCK
8. resolver a versão vigente da AccessibilityPolicy
9. avaliar source_state → target_state
10. no-op se target == current
11. se causally_extinct: VERIFICAR evidência causal real
12. transição pela porta E3, mesma Session e mesmo lock
13. verificar a pós-condição
14. resultado imutável
```

## Atomicidade — por que o lock vem antes da avaliação

A autorização depende do **estado de origem**. Avaliar a policy sobre um
estado lido sem lock permitiria que outra transação o mudasse antes da
escrita; o manager da E3 recarregaria o novo valor e escreveria o
destino sem que a regra fosse reavaliada.

```text
PRE-LOCK SOURCE STATE != AUTHORIZED WRITE PRECONDITION
POLICY(ACTIVE → TARGET) != POLICY(ANY CURRENT STATE → TARGET)
LAST-WRITE-WINS != VALID TRANSITION
```

`refresh_for_update()` emite `SELECT ... FOR UPDATE` e mantém a linha
bloqueada **até o fim da transação**. Adquirindo o lock no passo 6, o
estado do passo 7 é o mesmo que o manager da E3 verá no passo 12 — desde
que tudo ocorra na **mesma `Session`**, que é o que o compositor precisa
garantir.

## Fronteiras

Não cria `Session` nem `UnitOfWork`, não commita, não faz rollback, não
captura erro para continuar, não repara. Escreve **apenas**
`CognitiveObject.accessibility`, e por meio do manager sancionado da E3 —
nunca por SQL paralelo, nunca por um segundo writer.

Não toca `deleted_at`, identidade, CLID, `revision_status`, proveniência,
linhagem, história ou memberships. Não cria evento causal, não infere
extinção, não reativa soft delete, não executa Search ou Retrieval, não
calcula score.

```text
ACCESSIBILITY CHANGES ADMISSIBILITY/STATE
ACCESSIBILITY DOES NOT REWRITE EXISTENCE
CAUSAL EXTINCTION REQUIRES EVIDENCE
EVIDENCE IS NEVER FABRICATED
```
"""

import uuid
from datetime import UTC, datetime
from typing import Generic

from app.memory.errors.exceptions import (
    AccessibilitySubjectNotFoundError,
    AccessibilityTransitionContractViolationError,
)
from app.memory.models.governance_enums import (
    CognitiveOperation,
    GovernanceEffect,
    GovernanceOutcome,
)
from app.memory.ports.accessibility import (
    AccessibilityTransitionPort,
    CausalEventView,
    CausalEvidencePort,
    CausalHistoryView,
    CognitiveSubjectPort,
    StateT,
    SubjectIdentityView,
    SubjectT,
)
from app.memory.repositories.accessibility_policy_repository import (
    AccessibilityPolicyRepository,
)
from app.memory.schemas.accessibility import (
    ACCESSIBILITY_STATE_TOKENS,
    CAUSALLY_EXTINCT_TOKEN,
    AccessibilityDecision,
    AccessibilityTransitionResult,
)
from app.memory.schemas.governance import (
    GovernanceResolution,
    resolucao_vincula_contexto,
)
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.context_manager import ContextManager
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.platform_safety_boundary import CapabilityDescriptor
from app.utils.logger import get_logger

logger = get_logger("app.memory.services.accessibility_policy_manager")


class AccessibilityPolicyManager(Generic[SubjectT, StateT]):
    """Avalia e executa transições de acessibilidade sob autoridade.

    Genérico sobre o sujeito: o `CognitiveObject` atravessa este módulo
    **opaco**, sem nunca ser inspecionado. O estado vem da porta, e o
    mesmo objeto volta para a porta.
    """

    def __init__(
        self,
        subject_port: CognitiveSubjectPort[SubjectT],
        transition_port: AccessibilityTransitionPort[SubjectT, StateT],
        causal_evidence_port: CausalEvidencePort[object, object],
        policy_repository: AccessibilityPolicyRepository,
        governance_manager: GovernanceManager,
        context_manager: ContextManager,
    ) -> None:
        self._subjects = subject_port
        self._transitions = transition_port
        # `CausalEvidencePort[object, object]`, não `[CausalEventView,
        # CausalHistoryView]`: os modelos da E3 declaram campos como
        # `Mapped[...]`, e não são subtipos nominais das views. Como os
        # parâmetros da porta são **covariantes**, qualquer
        # `CausalEvidencePort[X, Y]` satisfaz esta assinatura — inclusive
        # o `CausalHistoryRepository` real.
        #
        # `object` é o tipo **topo**, não `Any`: o mypy recusa ler
        # qualquer atributo dele, o que torna o estreitamento por
        # `isinstance` contra as views obrigatório em vez de opcional.
        # É exatamente a garantia que se quer aqui.
        self._causal = causal_evidence_port
        self._policies = policy_repository
        self._governance = governance_manager
        self._context = context_manager

    def transition(
        self,
        *,
        coid: uuid.UUID,
        target_state: StateT,
        context: MemoryContext,
        descriptor: CapabilityDescriptor,
        governance_policy_key: str,
        accessibility_policy_key: str,
        reason: str | None = None,
        causal_event_id: uuid.UUID | None = None,
        moment: datetime | None = None,
    ) -> AccessibilityTransitionResult:
        """Solicita uma transição de acessibilidade.

        **Governança precede qualquer leitura do sujeito**, inclusive
        para same-state: consultar o patrimônio sob recusa já revelaria
        se o objeto existe e em que estado está.

            POLICY ABSENCE != ADMISSION
            NOT_APPLICABLE != ADMISSIBLE
            ACTOR PRESENCE != AUTHORIZATION
        """
        instante = self._instante_unico(moment)
        self._validar_argumentos(
            coid=coid,
            target_state=target_state,
            context=context,
            descriptor=descriptor,
            governance_policy_key=governance_policy_key,
            accessibility_policy_key=accessibility_policy_key,
            reason=reason,
            causal_event_id=causal_event_id,
        )

        confirmado = self._context.validate(context)
        self._verificar_fidelidade_do_contexto(context, confirmado)

        resolution = self._governance.resolve(
            descriptor=descriptor,
            context=context,
            policy_key=governance_policy_key,
            moment=instante,
        )
        self._verificar_fidelidade_da_resolucao(
            resolution,
            descriptor=descriptor,
            policy_key=governance_policy_key,
            context=context,
        )

        if not resolution.execution_authorized:
            logger.info(
                "accessibility_transition_denied_by_governance",
                extra={
                    "coid": str(coid),
                    "outcome": str(resolution.outcome),
                    "target_state": target_state,
                },
            )
            # Sem autorização não se lê o sujeito. `observed_state` seria
            # informação sobre patrimônio que a recusa deveria proteger,
            # então o resultado carrega o alvo pedido como referência do
            # que se pediu — nunca um estado observado.
            return AccessibilityTransitionResult(
                coid=coid,
                context=context,
                governance_resolution=resolution,
                decision=None,
                requested_target_state=str(target_state),
                observed_state=None,
                state_changed=False,
                evaluated_at=instante,
            )

        sujeito = self._subjects.get_by_id(coid, include_deleted=True)
        if sujeito is None:
            raise AccessibilitySubjectNotFoundError(coid)
        self._verificar_identidade(sujeito, coid, origem="get_by_id")

        # LOCK antes de observar. A partir daqui o estado não muda até
        # commit/rollback do chamador.
        bloqueado = self._subjects.refresh_for_update(sujeito)
        self._verificar_identidade(
            bloqueado, coid, origem="refresh_for_update", mesma_instancia_que=sujeito
        )
        estado_atual = self._ler_estado(bloqueado)

        if estado_atual == target_state:
            # No-op detectado SOB LOCK e ANTES de avaliar a policy: não
            # há transição a admitir, e consultá-la produziria uma
            # admissão (ou recusa) sobre algo que não vai acontecer.
            # Nenhuma escrita, nenhum evento causal, nenhuma história.
            #
            #     NO_CHANGE != POLICY ADMISSION
            #     NO_CHANGE != POLICY REFUSAL
            logger.info(
                "accessibility_transition_no_change",
                extra={"coid": str(coid), "state": estado_atual},
            )
            return AccessibilityTransitionResult(
                coid=coid,
                context=context,
                governance_resolution=resolution,
                decision=None,
                requested_target_state=str(target_state),
                observed_state=str(estado_atual),
                state_changed=False,
                no_change=True,
                evaluated_at=instante,
            )

        # `reason` só é exigido para uma mudança REAL para extinção
        # causal — depois do lock, portanto. Validá-lo antes impedia o
        # no-op prometido para um objeto já `causally_extinct`, embora o
        # manager E3 seja idempotente e não exija reason em same-state.
        if str(target_state) == CAUSALLY_EXTINCT_TOKEN and not (reason or "").strip():
            raise ValueError(
                "extinção causal exige reason não-vazio — exigência do manager "
                "sancionado da E3 (E3.6), que a E4.7 complementa sem substituir"
            )

        decisao = self._avaliar(
            policy_key=accessibility_policy_key,
            governance_policy_key=governance_policy_key,
            resolution=resolution,
            source_state=str(estado_atual),
            target_state=str(target_state),
            moment=instante,
        )

        if not decisao.is_admissible:
            # Recusa da policy não escreve e não fabrica evidência.
            return AccessibilityTransitionResult(
                coid=coid,
                context=context,
                governance_resolution=resolution,
                decision=decisao,
                requested_target_state=str(target_state),
                observed_state=str(estado_atual),
                state_changed=False,
                evaluated_at=instante,
            )

        evidencia = None
        if str(target_state) == CAUSALLY_EXTINCT_TOKEN:
            evidencia = self._verificar_evidencia_causal(coid, causal_event_id)

        escrito = self._transitions.transition(bloqueado, target_state, reason=reason)
        self._verificar_identidade(
            escrito, coid, origem="transition", mesma_instancia_que=bloqueado
        )
        # O estado confirmado é lido da instância BLOQUEADA, não da
        # devolvida: é a linha sob lock que precisa ter mudado.
        observado = self._ler_estado(bloqueado)
        self._verificar_poscondicao(str(observado), str(target_state))

        logger.info(
            "accessibility_transition_executed",
            extra={
                "coid": str(coid),
                "source_state": str(estado_atual),
                "target_state": str(target_state),
                "policy_key": accessibility_policy_key,
                "policy_version": decisao.policy_version,
                "matched_rule_id": decisao.matched_rule_id,
            },
        )

        return AccessibilityTransitionResult(
            coid=coid,
            context=context,
            governance_resolution=resolution,
            decision=decisao,
            requested_target_state=str(target_state),
            observed_state=str(observado),
            state_changed=True,
            causal_event_id=evidencia,
            evaluated_at=instante,
        )

    # --- Validação do pedido -------------------------------------------

    @staticmethod
    def _validar_argumentos(
        *,
        coid: object,
        target_state: object,
        context: object,
        descriptor: object,
        governance_policy_key: object,
        accessibility_policy_key: object,
        reason: object,
        causal_event_id: object,
    ) -> None:
        """Tipos e vocabulário, antes de tocar em qualquer colaborador."""
        if not isinstance(coid, uuid.UUID):
            raise TypeError(f"coid deve ser uuid.UUID, recebido {type(coid).__name__}")
        if not isinstance(target_state, str):
            raise TypeError(f"target_state deve ser str, recebido {type(target_state).__name__}")
        if target_state not in ACCESSIBILITY_STATE_TOKENS:
            raise ValueError(
                f"target_state {target_state!r} está fora do vocabulário da E3 "
                f"{sorted(ACCESSIBILITY_STATE_TOKENS)}"
            )
        if not isinstance(context, MemoryContext):
            raise TypeError(f"context deve ser MemoryContext, recebido {type(context).__name__}")
        if not isinstance(descriptor, CapabilityDescriptor):
            raise TypeError(
                f"descriptor deve ser CapabilityDescriptor, recebido "
                f"{type(descriptor).__name__}"
            )
        if descriptor.operation is not CognitiveOperation.ACCESSIBILITY_TRANSITION:
            raise ValueError(
                "a E4.7 executa apenas CognitiveOperation.ACCESSIBILITY_TRANSITION; "
                f"recebido {descriptor.operation}"
            )
        if reason is not None and not isinstance(reason, str):
            raise TypeError(f"reason deve ser str ou None, recebido {type(reason).__name__}")
        if causal_event_id is not None and not isinstance(causal_event_id, uuid.UUID):
            raise TypeError(
                "causal_event_id deve ser uuid.UUID ou None, recebido "
                f"{type(causal_event_id).__name__}"
            )
        for nome, chave in (
            ("governance_policy_key", governance_policy_key),
            ("accessibility_policy_key", accessibility_policy_key),
        ):
            if not isinstance(chave, str):
                raise TypeError(f"{nome} deve ser str, recebido {type(chave).__name__}")
            if not chave.strip():
                raise ValueError(f"{nome} não pode ser vazio")
        # `reason` NÃO é validado aqui: exigi-lo antes do lock impedia o
        # no-op de um objeto já `causally_extinct`. A exigência vale
        # apenas para uma mudança real, e é aplicada depois de observar
        # o estado atual (corretivo E4.7.1).
        #
        #     NO-OP REQUIRES NO FABRICATED CAUSE

    @staticmethod
    def _instante_unico(moment: datetime | None) -> datetime:
        """Um instante de decisão para a operação inteira.

        A versão anterior repassava `moment=None` à Governança — que
        capturava o próprio `now()` — e depois capturava outro `now()`
        para a AccessibilityPolicy. Uma operação na fronteira de vigência
        podia ser governada por instantes diferentes:

            TWO NOW() CALLS != ONE DECISION INSTANT
            ONE OPERATION = ONE EVALUATION INSTANT

        Exige `datetime` **aware** e canonicaliza para UTC: comparar
        vigência com um instante ingênuo daria resultado dependente do
        fuso da máquina onde o processo roda.
        """
        if moment is None:
            return datetime.now(UTC)
        if not isinstance(moment, datetime):
            raise TypeError(f"moment deve ser datetime ou None, recebido {type(moment).__name__}")
        if moment.tzinfo is None:
            raise ValueError(
                "moment deve ser timezone-aware — um instante ingênuo tornaria a "
                "vigência dependente do fuso da máquina"
            )
        return moment.astimezone(UTC)

    def _verificar_identidade(
        self,
        sujeito: SubjectT,
        coid: uuid.UUID,
        *,
        origem: str,
        mesma_instancia_que: SubjectT | None = None,
    ) -> None:
        """O objeto devolvido pela porta é o sujeito pedido?

        Verificado após `get_by_id`, após `refresh_for_update` e após
        `transition` — os três pontos em que uma porta infiel poderia
        substituir o sujeito:

            REQUESTED ID != RETURNED ID
            REQUESTED SUBJECT MUST BE THE WRITTEN SUBJECT

        Sem isto, um pedido sobre A escrevia em B e devolvia um resultado
        citando A. Acesso tipado direto pela `SubjectIdentityView`, sem
        reflexão.
        """
        if not isinstance(sujeito, SubjectIdentityView):
            raise AccessibilityTransitionContractViolationError(
                (
                    f"{origem} devolveu um objeto sem identidade observável "
                    f"({type(sujeito).__name__})",
                )
            )
        identidade = sujeito.id
        if not isinstance(identidade, uuid.UUID):
            raise AccessibilityTransitionContractViolationError(
                (f"{origem} devolveu id do tipo {type(identidade).__name__}, não uuid.UUID",)
            )
        if identidade != coid:
            raise AccessibilityTransitionContractViolationError(
                (
                    f"{origem} devolveu o sujeito {identidade}, mas o pedido é sobre "
                    f"{coid} — escrever nele alteraria patrimônio que ninguém pediu",
                )
            )
        # Igualdade de COID não é identidade de instância (corretivo
        # E4.7.2). Uma porta podia devolver OUTRA instância com o mesmo
        # COID e o estado-alvo, deixando a instância bloqueada intacta —
        # e a E4.7 certificava a aparência devolvida, não a linha que o
        # lock protege.
        #
        #     SAME COID != SAME LOCKED INSTANCE
        #     RETURNED REPLACEMENT != VERIFIED WRITE
        #     REQUESTED SUBJECT MUST BE THE LOCKED AND WRITTEN SUBJECT
        if mesma_instancia_que is not None and sujeito is not mesma_instancia_que:
            raise AccessibilityTransitionContractViolationError(
                (
                    f"{origem} devolveu outra instância do sujeito {coid} — a "
                    "identidade do COID coincide, mas a instância bloqueada não foi "
                    "a alterada, e confirmar a substituta certificaria uma escrita "
                    "que não ocorreu na linha protegida pelo lock",
                )
            )

    @staticmethod
    def _verificar_fidelidade_do_contexto(solicitado: MemoryContext, confirmado: object) -> None:
        """O validador confirma a perspectiva; não a reescreve.

        CONTEXT VALIDATION != CONTEXT SUBSTITUTION
        """
        if not isinstance(confirmado, MemoryContext):
            raise AccessibilityTransitionContractViolationError(
                (
                    "ContextManager.validate devolveu "
                    f"{type(confirmado).__name__}, não MemoryContext",
                )
            )
        if confirmado != solicitado:
            raise AccessibilityTransitionContractViolationError(
                (
                    "ContextManager.validate devolveu contexto diferente do solicitado — "
                    "validação não substitui a perspectiva pedida",
                )
            )

    @staticmethod
    def _verificar_fidelidade_da_resolucao(
        resolution: object,
        *,
        descriptor: CapabilityDescriptor,
        policy_key: str,
        context: MemoryContext,
    ) -> None:
        """A autorização tem de ser sobre **este** pedido.

        `execution_authorized` sozinho não diz qual operação nem qual
        policy produziram a autorização — lição da E4.6.1.

            AUTHORIZATION TO TRANSFORM != AUTHORIZATION TO CHANGE ACCESSIBILITY
            REQUESTED POLICY != RESOLVED POLICY
        """
        if not isinstance(resolution, GovernanceResolution):
            raise AccessibilityTransitionContractViolationError(
                (
                    "GovernanceManager.resolve devolveu "
                    f"{type(resolution).__name__}, não GovernanceResolution",
                )
            )
        motivos: list[str] = []
        if resolution.operation is not CognitiveOperation.ACCESSIBILITY_TRANSITION:
            motivos.append(
                f"a resolução é sobre {resolution.operation}, e a E4.7 executa apenas "
                "CognitiveOperation.ACCESSIBILITY_TRANSITION"
            )
        if resolution.operation is not descriptor.operation:
            motivos.append(
                f"operação resolvida ({resolution.operation}) difere da solicitada "
                f"({descriptor.operation})"
            )
        if resolution.policy_key is not None and resolution.policy_key != policy_key:
            motivos.append(
                f"policy de governança resolvida {resolution.policy_key!r} difere da "
                f"solicitada {policy_key!r}"
            )
        # Vínculo com o contexto avaliado (corretivo E4.3.4), antes de
        # qualquer leitura do sujeito, lock, estado, AccessibilityPolicy
        # ou evidência causal.
        motivos.extend(
            resolucao_vincula_contexto(
                resolution,
                domain_ids=context.domain_ids,
                actor_ref=context.actor_ref,
                purpose=context.purpose,
            )
        )
        if motivos:
            raise AccessibilityTransitionContractViolationError(tuple(motivos))

    # --- Estado e avaliação --------------------------------------------

    def _ler_estado(self, sujeito: SubjectT) -> str:
        """Token de estado pela porta, validado contra o vocabulário.

        Um token fora do vocabulário é violação da porta, não um estado
        a tratar em silêncio — mesma disciplina da E4.6.1.
        """
        estado = self._transitions.get_state(sujeito)
        if not isinstance(estado, str):
            raise AccessibilityTransitionContractViolationError(
                (f"get_state devolveu {type(estado).__name__}, não str",)
            )
        if estado not in ACCESSIBILITY_STATE_TOKENS:
            raise AccessibilityTransitionContractViolationError(
                (
                    f"get_state devolveu {estado!r}, fora do vocabulário da E3 "
                    f"{sorted(ACCESSIBILITY_STATE_TOKENS)}",
                )
            )
        return estado

    def _avaliar(
        self,
        *,
        policy_key: str,
        governance_policy_key: str,
        resolution: GovernanceResolution,
        source_state: str,
        target_state: str,
        moment: datetime,
    ) -> AccessibilityDecision:
        """Aplica a versão vigente da policy à transição pedida.

        Precedência idêntica à da E4.3, e pelo mesmo motivo: restrição
        que some porque outra regra permite não é restrição.

        ```text
        DENY_OVERRIDES
        NO_MATCH = NOT_APPLICABLE
        NOT_APPLICABLE DOES NOT AUTHORIZE
        ```

        Sem policy vigente, o desfecho é `NOT_APPLICABLE` — nunca
        `ADMISSIBLE`, nunca `INADMISSIBLE`. Ausência de regra é distinta
        de negação explícita, e nenhuma das duas autoriza.
        """
        # O instante já vem resolvido do início da operação: nenhuma
        # chamada a `now()` acontece aqui (corretivo E4.7.1).
        policy = self._policies.effective_version_at(policy_key, moment)
        if policy is None:
            return AccessibilityDecision(
                outcome=GovernanceOutcome.NOT_APPLICABLE,
                source_state=source_state,
                target_state=target_state,
                evaluated_at=moment,
            )

        # Vínculo de autoridade, verificado — não apenas persistido
        # (corretivo E4.7.1).
        #
        #     PERSISTED BINDING != ENFORCED BINDING
        #     REQUESTED AUTHORITY MUST BE THE POLICY'S AUTHORITY
        #
        # Mismatch é violação de contrato, nunca `NOT_APPLICABLE` e
        # nunca admissão: uma policy subordinada a G2 não pode operar
        # sob autoridade G1.
        motivos: list[str] = []
        if policy.policy_key != policy_key:
            motivos.append(
                f"o repositório devolveu a policy {policy.policy_key!r}, não a "
                f"solicitada {policy_key!r}"
            )
        if policy.governance_policy_key != governance_policy_key:
            motivos.append(
                f"a AccessibilityPolicy é subordinada a {policy.governance_policy_key!r}, "
                f"mas a autoridade solicitada é {governance_policy_key!r}"
            )
        if policy.governance_policy_key != resolution.policy_key:
            motivos.append(
                f"a AccessibilityPolicy é subordinada a {policy.governance_policy_key!r}, "
                f"mas a autoridade resolvida é {resolution.policy_key!r}"
            )
        if motivos:
            raise AccessibilityTransitionContractViolationError(tuple(motivos))

        from app.memory.models.accessibility_policy import AccessibilityPolicy

        regras = AccessibilityPolicy.deserialize_rules(policy.rules)
        aplicaveis = [
            regra
            for regra in regras
            if regra.matches(source_state=source_state, target_state=target_state)
        ]
        if not aplicaveis:
            return AccessibilityDecision(
                outcome=GovernanceOutcome.NOT_APPLICABLE,
                source_state=source_state,
                target_state=target_state,
                evaluated_at=moment,
            )

        # Ordem canônica antes de decidir: `DENY` vem antes de `ADMIT`
        # em `sort_key`, então a primeira negativa aplicável vence.
        aplicaveis.sort(key=lambda r: r.sort_key())
        negativas = [r for r in aplicaveis if r.effect is GovernanceEffect.DENY]
        escolhida = negativas[0] if negativas else aplicaveis[0]
        outcome = (
            GovernanceOutcome.INADMISSIBLE
            if escolhida.effect is GovernanceEffect.DENY
            else GovernanceOutcome.ADMISSIBLE
        )
        return AccessibilityDecision(
            outcome=outcome,
            source_state=source_state,
            target_state=target_state,
            evaluated_at=moment,
            policy_key=policy.policy_key,
            policy_version=policy.version,
            governance_policy_key=policy.governance_policy_key,
            matched_rule_id=escolhida.rule_id,
        )

    # --- Evidência causal e pós-condição --------------------------------

    def _verificar_evidencia_causal(
        self, coid: uuid.UUID, causal_event_id: uuid.UUID | None
    ) -> uuid.UUID:
        """Confirma que o evento existe e pertence ao **mesmo** sujeito.

        A E3.6 exige hoje apenas `reason` não-vazio, porque a E3.9 não
        existia quando o manager foi escrito. A E4.7 eleva a garantia no
        seu caminho canônico — e **apenas nele**: qualquer outro chamador
        do `AccessibilityManager` continua podendo extinguir com um
        `reason` qualquer. Não afirmo que o invariante global da E3 foi
        fechado.

            CAUSAL EVENT ID != CAUSAL EVIDENCE UNTIL SUBJECT MEMBERSHIP IS VERIFIED
            MISSING EVIDENCE != AUTHORIZATION TO FABRICATE HISTORY

        Nada é criado aqui: o evento é verificado, nunca produzido,
        alterado ou inferido.
        """
        if causal_event_id is None:
            raise AccessibilityTransitionContractViolationError(
                (
                    "transição para causally_extinct exige causal_event_id — extinção "
                    "sem evidência seria causalidade fabricada",
                )
            )
        bruto_evento = self._causal.get_event(causal_event_id)
        if bruto_evento is None:
            raise AccessibilityTransitionContractViolationError(
                (f"evento causal {causal_event_id} não existe",)
            )
        # `isinstance` contra um `Protocol` `runtime_checkable` **tipa** o
        # objeto para o mypy: a leitura dos campos abaixo é verificada
        # estaticamente, sem `Any`, `cast` ou reflexão.
        if not isinstance(bruto_evento, CausalEventView):
            raise AccessibilityTransitionContractViolationError(
                (
                    "get_event devolveu um objeto sem os campos de um evento causal "
                    f"({type(bruto_evento).__name__})",
                )
            )
        evento = bruto_evento
        bruto_historia = self._causal.get_by_subject(coid)
        if bruto_historia is None:
            raise AccessibilityTransitionContractViolationError(
                (
                    f"o sujeito {coid} não possui história causal; o evento informado "
                    "não pode pertencer a ele",
                )
            )
        if not isinstance(bruto_historia, CausalHistoryView):
            raise AccessibilityTransitionContractViolationError(
                (
                    "get_by_subject devolveu um objeto sem os campos de uma história "
                    f"causal ({type(bruto_historia).__name__})",
                )
            )
        historia = bruto_historia

        # Três igualdades, todas necessárias (corretivo E4.7.1). A
        # versão anterior comparava apenas `event.history_id ==
        # history.id`, então uma porta podia devolver OUTRO evento e a
        # história de OUTRO sujeito — internamente consistentes entre si
        # — e a extinção era executada citando o ID pedido como se ele
        # tivesse sido verificado.
        #
        #     REQUESTED EVENT MUST BE THE VERIFIED EVENT
        #     PORT RETURN != TRUSTED FACT UNTIL FIDELITY IS VERIFIED
        motivos: list[str] = []
        identificadores = (
            ("evento.id", evento.id),
            ("evento.history_id", evento.history_id),
            ("historia.id", historia.id),
            ("historia.subject_coid", historia.subject_coid),
        )
        for nome, valor in identificadores:
            if not isinstance(valor, uuid.UUID):
                motivos.append(f"{nome} é {type(valor).__name__}, não uuid.UUID")
        if motivos:
            raise AccessibilityTransitionContractViolationError(tuple(motivos))

        if evento.id != causal_event_id:
            motivos.append(
                f"a porta devolveu o evento {evento.id}, mas o solicitado foi " f"{causal_event_id}"
            )
        if historia.subject_coid != coid:
            motivos.append(
                f"a história devolvida pertence a {historia.subject_coid}, não ao "
                f"sujeito {coid}"
            )
        if evento.history_id != historia.id:
            motivos.append(
                f"o evento {evento.id} pertence à história {evento.history_id}, não à "
                f"história {historia.id} do sujeito"
            )
        if motivos:
            raise AccessibilityTransitionContractViolationError(tuple(motivos))

        # Só o ID efetivamente confirmado é devolvido.
        return evento.id

    @staticmethod
    def _verificar_poscondicao(observado: str, alvo: str) -> None:
        """Confirma que o estado escrito é o autorizado.

        Divergência produz diagnóstico e deixa o rollback para o
        chamador. Nada é reparado:

            AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN
        """
        if observado != alvo:
            raise AccessibilityTransitionContractViolationError(
                (
                    f"pós-condição não confirma a transição: estado observado "
                    f"{observado!r}, alvo autorizado {alvo!r}",
                )
            )
