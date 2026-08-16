"""
Testes unitários da E4.7 — Accessibility Policy.

Cobrem os value objects, a autoridade e as transições com dublês das
portas. A composição real com `ObjectRepository`,
`AccessibilityManager` e `CausalHistoryRepository`, o lock de linha e a
concorrência vivem em
`tests/integration/memory/test_accessibility_integration.py` — SQLite
compila `FOR UPDATE` como no-op, então afirmar atomicidade aqui seria
overclaim.
"""

import ast
import dataclasses
import pathlib
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime

import pytest

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
)
from app.memory.schemas.accessibility import (
    ACCESSIBILITY_STATE_TOKENS,
    CAUSALLY_EXTINCT_TOKEN,
    AccessibilityDecision,
    AccessibilityRule,
    AccessibilityTransitionResult,
)
from app.memory.schemas.governance import GovernanceResolution
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.accessibility_policy_manager import AccessibilityPolicyManager
from app.memory.services.platform_safety_boundary import (
    PLATFORM_SAFETY_BOUNDARY_VERSION,
    CapabilityDescriptor,
)

_GK = "gov-teste"
_AK = "acc-teste"
_MOMENTO = datetime(2024, 6, 1, tzinfo=UTC)


# --- Dublês -----------------------------------------------------------


@dataclasses.dataclass
class SujeitoFalso:
    """Sujeito opaco — a E4.7 nunca lê seus campos."""

    id: uuid.UUID
    estado: str = "active"


class SubjectPortFalso:
    def __init__(self, sujeito: SujeitoFalso | None) -> None:
        self.sujeito = sujeito
        self.buscas: list[dict] = []
        self.locks: list[uuid.UUID] = []

    def get_by_id(self, entity_id, *, include_deleted: bool = False):
        self.buscas.append({"id": entity_id, "include_deleted": include_deleted})
        return self.sujeito

    def refresh_for_update(self, entity):
        self.locks.append(entity.id)
        return entity


class TransitionPortFalso:
    def __init__(self, *, estado_devolvido: object | None = None) -> None:
        self.escritas: list[tuple[uuid.UUID, str, str | None]] = []
        self.estado_devolvido = estado_devolvido

    def get_state(self, obj):
        if self.estado_devolvido is not None:
            return self.estado_devolvido
        return obj.estado

    def transition(self, obj, target_state, *, reason=None):
        self.escritas.append((obj.id, target_state, reason))
        obj.estado = target_state
        return obj


@dataclasses.dataclass(frozen=True)
class EventoFalso:
    id: uuid.UUID
    history_id: uuid.UUID


@dataclasses.dataclass(frozen=True)
class HistoriaFalsa:
    id: uuid.UUID
    subject_coid: uuid.UUID


class EvidencePortFalso:
    def __init__(self, evento=None, historia=None) -> None:
        self.evento = evento
        self.historia = historia
        self.consultas = 0

    def get_event(self, event_id):
        self.consultas += 1
        return self.evento

    def get_by_subject(self, subject_coid):
        return self.historia


class PolicyRepoFalso:
    def __init__(self, policy=None) -> None:
        self.policy = policy
        self.consultas: list[tuple[str, datetime]] = []

    def effective_version_at(self, policy_key, moment):
        self.consultas.append((policy_key, moment))
        return self.policy


@dataclasses.dataclass
class PolicyFalsa:
    policy_key: str
    version: int
    rules: list[dict]


class GovernanceFalso:
    def __init__(self, resolution, *, eco_policy: bool = True) -> None:
        self.resolution = resolution
        self.eco_policy = eco_policy
        self.chamadas: list[dict] = []

    def resolve(self, *, descriptor, context, policy_key=None, moment=None):
        self.chamadas.append({"descriptor": descriptor, "policy_key": policy_key})
        if self.eco_policy and self.resolution.policy_key is not None:
            return dataclasses.replace(self.resolution, policy_key=policy_key)
        return self.resolution


class ContextoFalso:
    def __init__(self, substituto=None) -> None:
        self.substituto = substituto

    def validate(self, context):
        return self.substituto if self.substituto is not None else context


# --- Construtores -----------------------------------------------------


def _resolucao(*, outcome=GovernanceOutcome.ADMISSIBLE, operation=None):
    operacao = operation or CognitiveOperation.ACCESSIBILITY_TRANSITION
    if outcome in (GovernanceOutcome.NOT_APPLICABLE, GovernanceOutcome.PROHIBITED):
        extras: dict = {}
        if outcome is GovernanceOutcome.PROHIBITED:
            from app.memory.services.platform_safety_boundary import CriticalCapability

            extras = {
                "blocked_capabilities": (CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT,),
                "safety_rationale": "proibido",
            }
        return GovernanceResolution(
            operation=operacao,
            outcome=outcome,
            safety_boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
            **extras,
        )
    return GovernanceResolution(
        operation=operacao,
        outcome=outcome,
        policy_key=_GK,
        policy_version=1,
        policy_id=uuid.uuid4(),
        matched_rule_id="r",
        safety_boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
    )


def _regra(rule_id="r1", effect=GovernanceEffect.ADMIT, fontes=("active",), alvos=("latent",)):
    return AccessibilityRule(
        rule_id=rule_id,
        effect=effect,
        source_states=frozenset(fontes),
        target_states=frozenset(alvos),
    )


def _policy(*regras, version=1):
    from app.memory.models.accessibility_policy import AccessibilityPolicy

    return PolicyFalsa(
        policy_key=_AK,
        version=version,
        rules=AccessibilityPolicy.serialize_rules(tuple(regras)),
    )


def _descritor(operation=None):
    return CapabilityDescriptor(operation=operation or CognitiveOperation.ACCESSIBILITY_TRANSITION)


def _manager(
    *,
    sujeito=None,
    policy=None,
    resolution=None,
    evidencia=None,
    contexto_substituto=None,
    estado_devolvido=None,
    eco_policy=True,
):
    subject_port = SubjectPortFalso(sujeito)
    transition_port = TransitionPortFalso(estado_devolvido=estado_devolvido)
    evidence_port = evidencia or EvidencePortFalso()
    policy_repo = PolicyRepoFalso(policy)
    governanca = GovernanceFalso(resolution or _resolucao(), eco_policy=eco_policy)
    contexto = ContextoFalso(contexto_substituto)
    manager = AccessibilityPolicyManager(
        subject_port, transition_port, evidence_port, policy_repo, governanca, contexto
    )
    return manager, subject_port, transition_port, evidence_port, policy_repo, governanca


def _transicionar(manager, *, coid=None, alvo="latent", **kw):
    kw.setdefault("context", MemoryContext())
    kw.setdefault("descriptor", _descritor())
    kw.setdefault("governance_policy_key", _GK)
    kw.setdefault("accessibility_policy_key", _AK)
    kw.setdefault("moment", _MOMENTO)
    return manager.transition(coid=coid or uuid.uuid4(), target_state=alvo, **kw)


# ======================================================================
# Value objects
# ======================================================================


def test_ap1_rule_requires_both_dimensions_non_empty():
    """Dimensão vazia seria curinga silencioso — a E4.3.3 mostrou o
    custo disso quando o vocabulário cresce."""
    with pytest.raises(ValueError, match="não pode ser vazio"):
        _regra(fontes=())
    with pytest.raises(ValueError, match="não pode ser vazio"):
        _regra(alvos=())


@pytest.mark.parametrize("token", ["ACTIVE", "Active", "quantum", " active"])
def test_ap2_rule_refuses_tokens_outside_the_e3_vocabulary(token):
    """Igualdade exata, sem normalização."""
    with pytest.raises(ValueError, match="fora do vocabulário"):
        _regra(fontes=(token,))


def test_ap3_rule_is_frozen_hashable_and_canonical():
    regra = _regra()
    assert isinstance(hash(regra), int)
    with pytest.raises(dataclasses.FrozenInstanceError):
        regra.rule_id = "outro"
    assert regra.sort_key() == ("admit", "r1")


def test_ap4_rule_matches_by_exact_conjunction():
    regra = _regra(fontes=("active", "latent"), alvos=("inaccessible",))
    assert regra.matches(source_state="active", target_state="inaccessible")
    assert regra.matches(source_state="latent", target_state="inaccessible")
    assert not regra.matches(source_state="active", target_state="latent")


def test_ap5_external_collection_does_not_stay_shared():
    fontes = {"active"}
    regra = AccessibilityRule(
        rule_id="r",
        effect=GovernanceEffect.ADMIT,
        source_states=fontes,  # type: ignore[arg-type]
        target_states={"latent"},  # type: ignore[arg-type]
    )
    fontes.add("latent")
    assert regra.source_states == frozenset({"active"})


def test_ap6_decision_requires_a_rule_unless_not_applicable():
    with pytest.raises(ValueError, match="sem regra citada"):
        AccessibilityDecision(
            outcome=GovernanceOutcome.ADMISSIBLE,
            source_state="active",
            target_state="latent",
            policy_key=_AK,
            policy_version=1,
        )


def test_ap7_decision_not_applicable_cannot_cite_a_rule():
    with pytest.raises(ValueError, match="contradiz o desfecho"):
        AccessibilityDecision(
            outcome=GovernanceOutcome.NOT_APPLICABLE,
            source_state="active",
            target_state="latent",
            policy_key=_AK,
            policy_version=1,
            matched_rule_id="r1",
        )


def test_ap8_decision_policy_identity_is_all_or_nothing():
    """Proveniência parcial parece proveniência — lição da E4.3.2."""
    with pytest.raises(ValueError, match="tudo-ou-nada"):
        AccessibilityDecision(
            outcome=GovernanceOutcome.NOT_APPLICABLE,
            source_state="active",
            target_state="latent",
            policy_key=_AK,
        )


def test_ap9_decision_never_carries_prohibited():
    """`PROHIBITED` pertence à fronteira de segurança da plataforma."""
    with pytest.raises(ValueError, match="fronteira de segurança"):
        AccessibilityDecision(
            outcome=GovernanceOutcome.PROHIBITED,
            source_state="active",
            target_state="latent",
        )


def test_ap10_only_admissible_admits():
    admissivel = AccessibilityDecision(
        outcome=GovernanceOutcome.ADMISSIBLE,
        source_state="active",
        target_state="latent",
        policy_key=_AK,
        policy_version=1,
        matched_rule_id="r1",
    )
    nao_aplicavel = AccessibilityDecision(
        outcome=GovernanceOutcome.NOT_APPLICABLE, source_state="active", target_state="latent"
    )
    assert admissivel.is_admissible is True
    assert nao_aplicavel.is_admissible is False


def _resultado(**overrides):
    campos = {
        "coid": uuid.uuid4(),
        "context": MemoryContext(),
        "governance_resolution": _resolucao(),
        "decision": AccessibilityDecision(
            outcome=GovernanceOutcome.ADMISSIBLE,
            source_state="active",
            target_state="latent",
            policy_key=_AK,
            policy_version=1,
            matched_rule_id="r1",
        ),
        "observed_state": "latent",
        "state_changed": True,
    }
    campos.update(overrides)
    return AccessibilityTransitionResult(**campos)


def test_ap11_result_is_frozen_and_hashable():
    resultado = _resultado()
    assert isinstance(hash(resultado), int)
    with pytest.raises(dataclasses.FrozenInstanceError):
        resultado.state_changed = False


def test_ap12_result_change_requires_admissible_decision():
    with pytest.raises(ValueError, match="escrita sem autoridade"):
        _resultado(
            decision=AccessibilityDecision(
                outcome=GovernanceOutcome.INADMISSIBLE,
                source_state="active",
                target_state="latent",
                policy_key=_AK,
                policy_version=1,
                matched_rule_id="r1",
            )
        )


def test_ap13_result_postcondition_must_confirm_the_target():
    with pytest.raises(ValueError, match="pós-condição não confirma"):
        _resultado(observed_state="active")


def test_ap14_result_extinction_requires_causal_evidence():
    decisao = AccessibilityDecision(
        outcome=GovernanceOutcome.ADMISSIBLE,
        source_state="active",
        target_state=CAUSALLY_EXTINCT_TOKEN,
        policy_key=_AK,
        policy_version=1,
        matched_rule_id="r1",
    )
    with pytest.raises(ValueError, match="evidência causal"):
        _resultado(decision=decisao, observed_state=CAUSALLY_EXTINCT_TOKEN)


def test_ap15_denied_result_cannot_carry_a_decision():
    with pytest.raises(ValueError, match="avaliação que não ocorreu"):
        _resultado(
            governance_resolution=_resolucao(outcome=GovernanceOutcome.INADMISSIBLE),
            observed_state="active",
            state_changed=False,
        )


def test_ap16_no_change_never_fabricates_decision_or_evidence():
    with pytest.raises(ValueError, match="não fabrica decisão"):
        _resultado(observed_state="active", state_changed=False, no_change=True)
    with pytest.raises(ValueError, match="não fabrica evidência"):
        _resultado(
            decision=None,
            observed_state="active",
            state_changed=False,
            no_change=True,
            causal_event_id=uuid.uuid4(),
        )


def test_ap17_state_changed_and_no_change_are_mutually_exclusive():
    with pytest.raises(ValueError, match="mutuamente exclusivos"):
        _resultado(decision=None, no_change=True)


def test_ap18_three_outcomes_stay_distinct():
    """`governança recusou` ≠ `no-op` ≠ `policy avaliou`."""
    negado = _resultado(
        governance_resolution=_resolucao(outcome=GovernanceOutcome.NOT_APPLICABLE),
        decision=None,
        observed_state="active",
        state_changed=False,
    )
    noop = _resultado(decision=None, observed_state="active", state_changed=False, no_change=True)
    avaliado = _resultado()
    assert (negado.no_change, negado.policy_evaluated) == (False, False)
    assert (noop.no_change, noop.policy_evaluated) == (True, False)
    assert (avaliado.no_change, avaliado.policy_evaluated) == (False, True)


# ======================================================================
# Autoridade
# ======================================================================


@pytest.mark.parametrize(
    "operacao",
    [CognitiveOperation.READ, CognitiveOperation.TRANSFORM, CognitiveOperation.CONSOLIDATE],
)
def test_ap19_only_accessibility_transition_operation_is_accepted(operacao):
    """`AUTHORIZATION TO TRANSFORM != AUTHORIZATION TO CHANGE ACCESSIBILITY`."""
    manager, subject_port, transition_port, _, _, governanca = _manager(
        sujeito=SujeitoFalso(uuid.uuid4())
    )
    with pytest.raises(ValueError, match="ACCESSIBILITY_TRANSITION"):
        _transicionar(manager, descriptor=_descritor(operacao))
    assert subject_port.buscas == []
    assert transition_port.escritas == []
    assert governanca.chamadas == []


@pytest.mark.parametrize(
    "outcome",
    [
        GovernanceOutcome.PROHIBITED,
        GovernanceOutcome.INADMISSIBLE,
        GovernanceOutcome.NOT_APPLICABLE,
    ],
)
def test_ap20_denied_governance_never_reads_the_subject(outcome):
    """Ler o sujeito sob recusa já revelaria se ele existe e em que
    estado está."""
    manager, subject_port, transition_port, _, policy_repo, _ = _manager(
        sujeito=SujeitoFalso(uuid.uuid4()), resolution=_resolucao(outcome=outcome)
    )
    resultado = _transicionar(manager)
    assert subject_port.buscas == []
    assert subject_port.locks == []
    assert transition_port.escritas == []
    assert policy_repo.consultas == []
    assert resultado.state_changed is False
    assert resultado.decision is None
    assert resultado.no_change is False


def test_ap21_actor_presence_does_not_authorize():
    """`ACTOR PRESENCE != AUTHORIZATION`."""
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=SujeitoFalso(uuid.uuid4()),
        resolution=_resolucao(outcome=GovernanceOutcome.NOT_APPLICABLE),
    )
    resultado = _transicionar(manager, context=MemoryContext(actor_ref="ana", purpose="curadoria"))
    assert resultado.governance_resolution.execution_authorized is False
    assert transition_port.escritas == []


def test_ap22_resolution_about_another_operation_is_refused():
    manager, subject_port, _, _, _, _ = _manager(
        sujeito=SujeitoFalso(uuid.uuid4()),
        resolution=_resolucao(operation=CognitiveOperation.TRANSFORM),
        eco_policy=False,
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager)
    assert exc.value.code == "PIA-8037"
    assert subject_port.buscas == []


def test_ap23_resolution_about_another_policy_is_refused():
    manager, subject_port, _, _, _, _ = _manager(
        sujeito=SujeitoFalso(uuid.uuid4()), eco_policy=False
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager, governance_policy_key="outra-policy")
    assert any("policy de governança resolvida" in m for m in exc.value.reasons)
    assert subject_port.buscas == []


def test_ap24_context_substitution_is_refused_before_governance():
    """`CONTEXT VALIDATION != CONTEXT SUBSTITUTION`."""
    manager, subject_port, _, _, _, governanca = _manager(
        sujeito=SujeitoFalso(uuid.uuid4()),
        contexto_substituto=MemoryContext(actor_ref="outro"),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager, context=MemoryContext(actor_ref="user"))
    assert any("contexto diferente" in m for m in exc.value.reasons)
    assert governanca.chamadas == []
    assert subject_port.buscas == []


@pytest.mark.parametrize("invalido", ["nao-e-contexto", 123, None])
def test_ap25_invalid_context_is_a_type_error(invalido):
    manager, _, _, _, _, governanca = _manager(sujeito=SujeitoFalso(uuid.uuid4()))
    with pytest.raises(TypeError, match="MemoryContext"):
        manager.transition(
            coid=uuid.uuid4(),
            target_state="latent",
            context=invalido,
            descriptor=_descritor(),
            governance_policy_key=_GK,
            accessibility_policy_key=_AK,
        )
    assert governanca.chamadas == []


# ======================================================================
# Sujeito, lock e transições
# ======================================================================


def test_ap26_missing_subject_has_its_own_diagnostic():
    """Objeto ausente não é transição negada."""
    manager, _, transition_port, _, _, _ = _manager(sujeito=None)
    with pytest.raises(AccessibilitySubjectNotFoundError) as exc:
        _transicionar(manager)
    assert exc.value.code == "PIA-8038"
    assert transition_port.escritas == []


def test_ap27_subject_is_read_with_include_deleted():
    """`SOFT_DELETED != NEVER EXISTED` — objeto apagado é sujeito
    legítimo, e a E4.7 nunca toca `deleted_at`."""
    manager, subject_port, _, _, _, _ = _manager(
        sujeito=SujeitoFalso(uuid.uuid4()), policy=_policy(_regra())
    )
    _transicionar(manager)
    assert subject_port.buscas[0]["include_deleted"] is True


def test_ap28_lock_is_acquired_before_the_policy_is_consulted():
    """A ordem é a garantia de atomicidade: o estado avaliado é o estado
    sob lock."""
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, subject_port, _, _, policy_repo, _ = _manager(
        sujeito=sujeito, policy=_policy(_regra())
    )
    _transicionar(manager, coid=sujeito.id)
    assert subject_port.locks == [sujeito.id]
    assert policy_repo.consultas, "a policy precisa ter sido consultada"


def test_ap29_admitted_transition_writes_through_the_e3_port():
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, transition_port, _, _, _ = _manager(sujeito=sujeito, policy=_policy(_regra()))
    resultado = _transicionar(manager, coid=sujeito.id)
    assert transition_port.escritas == [(sujeito.id, "latent", None)]
    assert resultado.state_changed is True
    assert resultado.observed_state == "latent"
    assert resultado.decision is not None
    assert resultado.decision.matched_rule_id == "r1"


def test_ap30_no_rule_means_not_applicable_and_no_write():
    """`POLICY ABSENCE != ADMISSION`."""
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito, policy=_policy(_regra(alvos=("inaccessible",)))
    )
    resultado = _transicionar(manager, coid=sujeito.id, alvo="latent")
    assert resultado.decision is not None
    assert resultado.decision.outcome is GovernanceOutcome.NOT_APPLICABLE
    assert resultado.state_changed is False
    assert transition_port.escritas == []


def test_ap31_absent_policy_version_is_not_applicable():
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, transition_port, _, _, _ = _manager(sujeito=sujeito, policy=None)
    resultado = _transicionar(manager, coid=sujeito.id)
    assert resultado.decision is not None
    assert resultado.decision.outcome is GovernanceOutcome.NOT_APPLICABLE
    assert transition_port.escritas == []


def test_ap32_deny_blocks_and_writes_nothing():
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito, policy=_policy(_regra(effect=GovernanceEffect.DENY))
    )
    resultado = _transicionar(manager, coid=sujeito.id)
    assert resultado.decision is not None
    assert resultado.decision.outcome is GovernanceOutcome.INADMISSIBLE
    assert transition_port.escritas == []


def test_ap33_deny_overrides_admit():
    """Restrição que some porque outra regra permite não é restrição."""
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito,
        policy=_policy(
            _regra("r-admit", GovernanceEffect.ADMIT),
            _regra("r-deny", GovernanceEffect.DENY),
        ),
    )
    resultado = _transicionar(manager, coid=sujeito.id)
    assert resultado.decision is not None
    assert resultado.decision.outcome is GovernanceOutcome.INADMISSIBLE
    assert resultado.decision.matched_rule_id == "r-deny"
    assert transition_port.escritas == []


def test_ap34_no_op_does_not_consult_the_policy_or_write():
    """`NO_CHANGE != POLICY ADMISSION`."""
    sujeito = SujeitoFalso(uuid.uuid4(), estado="latent")
    manager, subject_port, transition_port, evidence, policy_repo, _ = _manager(
        sujeito=sujeito, policy=_policy(_regra())
    )
    resultado = _transicionar(manager, coid=sujeito.id, alvo="latent")
    assert resultado.no_change is True
    assert resultado.decision is None
    assert resultado.policy_evaluated is False
    assert policy_repo.consultas == []
    assert transition_port.escritas == []
    assert evidence.consultas == 0
    # o lock ainda é adquirido: o no-op só é conhecido sob lock
    assert subject_port.locks == [sujeito.id]


def test_ap35_no_op_on_an_already_extinct_object_fabricates_nothing():
    sujeito = SujeitoFalso(uuid.uuid4(), estado=CAUSALLY_EXTINCT_TOKEN)
    manager, _, transition_port, evidence, policy_repo, _ = _manager(sujeito=sujeito)
    resultado = _transicionar(
        manager, coid=sujeito.id, alvo=CAUSALLY_EXTINCT_TOKEN, reason="já extinto"
    )
    assert resultado.no_change is True
    assert resultado.causal_event_id is None
    assert evidence.consultas == 0
    assert policy_repo.consultas == []
    assert transition_port.escritas == []


# ======================================================================
# CAUSALLY_EXTINCT
# ======================================================================


def test_ap36_extinction_without_reason_is_refused_before_anything():
    manager, subject_port, _, _, _, governanca = _manager(sujeito=SujeitoFalso(uuid.uuid4()))
    with pytest.raises(ValueError, match="reason não-vazio"):
        _transicionar(manager, alvo=CAUSALLY_EXTINCT_TOKEN)
    assert governanca.chamadas == []
    assert subject_port.buscas == []


def test_ap37_extinction_without_causal_event_is_refused():
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito, policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,)))
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager, coid=sujeito.id, alvo=CAUSALLY_EXTINCT_TOKEN, reason="fim")
    assert exc.value.code == "PIA-8037"
    assert transition_port.escritas == []


def test_ap38_nonexistent_causal_event_is_refused():
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito,
        policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,))),
        evidencia=EvidencePortFalso(evento=None),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(
            manager,
            coid=sujeito.id,
            alvo=CAUSALLY_EXTINCT_TOKEN,
            reason="fim",
            causal_event_id=uuid.uuid4(),
        )
    assert any("não existe" in m for m in exc.value.reasons)
    assert transition_port.escritas == []


def test_ap39_causal_event_of_another_subject_is_refused():
    """`CAUSAL EVENT ID != CAUSAL EVIDENCE UNTIL SUBJECT MEMBERSHIP IS
    VERIFIED`."""
    sujeito = SujeitoFalso(uuid.uuid4())
    evento = EventoFalso(id=uuid.uuid4(), history_id=uuid.uuid4())
    historia = HistoriaFalsa(id=uuid.uuid4(), subject_coid=sujeito.id)
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito,
        policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,))),
        evidencia=EvidencePortFalso(evento=evento, historia=historia),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(
            manager,
            coid=sujeito.id,
            alvo=CAUSALLY_EXTINCT_TOKEN,
            reason="fim",
            causal_event_id=evento.id,
        )
    assert any("outra história causal" in m for m in exc.value.reasons)
    assert transition_port.escritas == []


def test_ap40_subject_without_causal_history_is_refused():
    sujeito = SujeitoFalso(uuid.uuid4())
    evento = EventoFalso(id=uuid.uuid4(), history_id=uuid.uuid4())
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito,
        policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,))),
        evidencia=EvidencePortFalso(evento=evento, historia=None),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError):
        _transicionar(
            manager,
            coid=sujeito.id,
            alvo=CAUSALLY_EXTINCT_TOKEN,
            reason="fim",
            causal_event_id=evento.id,
        )
    assert transition_port.escritas == []


def test_ap41_verified_causal_event_allows_extinction():
    sujeito = SujeitoFalso(uuid.uuid4())
    historia = HistoriaFalsa(id=uuid.uuid4(), subject_coid=sujeito.id)
    evento = EventoFalso(id=uuid.uuid4(), history_id=historia.id)
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito,
        policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,))),
        evidencia=EvidencePortFalso(evento=evento, historia=historia),
    )
    resultado = _transicionar(
        manager,
        coid=sujeito.id,
        alvo=CAUSALLY_EXTINCT_TOKEN,
        reason="fim",
        causal_event_id=evento.id,
    )
    assert resultado.state_changed is True
    assert resultado.causal_event_id == evento.id
    assert transition_port.escritas == [(sujeito.id, CAUSALLY_EXTINCT_TOKEN, "fim")]


def test_ap42_e47_never_creates_a_causal_event():
    executavel = _codigo_executavel()
    for proibido in ("record(", "add_event(", "ensure_history(", "CausalHistoryManager"):
        assert proibido not in executavel, f"criação de causalidade: {proibido}"


# ======================================================================
# Pós-condição e fronteiras
# ======================================================================


def test_ap43_postcondition_divergence_is_diagnosed_never_repaired():
    class PortaInfiel(TransitionPortFalso):
        def transition(self, obj, target_state, *, reason=None):
            self.escritas.append((obj.id, target_state, reason))
            return obj  # não escreve

    sujeito = SujeitoFalso(uuid.uuid4())
    porta = PortaInfiel()
    manager = AccessibilityPolicyManager(
        SubjectPortFalso(sujeito),
        porta,
        EvidencePortFalso(),
        PolicyRepoFalso(_policy(_regra())),
        GovernanceFalso(_resolucao()),
        ContextoFalso(),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager, coid=sujeito.id)
    assert any("pós-condição não confirma" in m for m in exc.value.reasons)


def test_ap44_unknown_state_token_from_the_port_is_a_violation():
    manager, _, _, _, _, _ = _manager(
        sujeito=SujeitoFalso(uuid.uuid4()), estado_devolvido="quantum"
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager)
    assert any("fora do vocabulário" in m for m in exc.value.reasons)


def test_ap45_invalid_target_state_is_refused():
    manager, _, _, _, _, governanca = _manager(sujeito=SujeitoFalso(uuid.uuid4()))
    with pytest.raises(ValueError, match="fora do vocabulário"):
        _transicionar(manager, alvo="quantum")
    assert governanca.chamadas == []


def test_ap46_no_internal_commit_session_or_raw_sql():
    executavel = _codigo_executavel()
    for proibido in ("commit(", "rollback(", "Session", "UnitOfWork", "text(", "execute("):
        assert proibido not in executavel, f"encontrado: {proibido}"


def test_ap47_no_score_ranking_or_learning():
    executavel = _codigo_executavel()
    for proibido in ("score", "rank", "relevance", "embedding", "vector", "learn"):
        assert proibido not in executavel.lower(), f"capacidade proibida: {proibido}"


def test_ap48_never_touches_deleted_at_or_identity():
    executavel = _codigo_executavel()
    for proibido in ("deleted_at", "soft_delete", "clid", "revision_status", "lineage"):
        assert proibido not in executavel.lower(), f"campo indevido: {proibido}"


def test_ap49_no_app_cognitive_import_in_memory_production_code():
    padrao = re.compile(r"^\s*(from|import)\s+app\.cognitive", re.MULTILINE)
    raiz = pathlib.Path(__file__).resolve().parents[3] / "app"
    ofensores = [
        str(caminho)
        for caminho in raiz.rglob("*.py")
        if "cognitive" not in caminho.parts and padrao.search(caminho.read_text(encoding="utf-8"))
    ]
    assert ofensores == []


def test_ap50_no_reflection_as_escape():
    executavel = _codigo_executavel()
    for proibido in ("getattr(", "hasattr(", "vars(", "__dict__", "importlib", "sys.modules"):
        assert proibido not in executavel, f"reflexão encontrada: {proibido}"


def test_ap51_real_e3_objects_satisfy_the_ports():
    """Conformidade estrutural verificada, não presumida.

    Importa `app.cognitive` **no teste** — o que a fronteira veda é o
    import no código de produção de `app/memory`.
    """
    from app.cognitive.models.causal_history import CausalHistory, CausalHistoryEvent
    from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
    from app.cognitive.repositories.object_repository import ObjectRepository
    from app.cognitive.services.accessibility_manager import AccessibilityManager

    assert isinstance(ObjectRepository.__new__(ObjectRepository), CognitiveSubjectPort)
    assert isinstance(
        AccessibilityManager.__new__(AccessibilityManager), AccessibilityTransitionPort
    )
    assert isinstance(CausalHistoryRepository.__new__(CausalHistoryRepository), CausalEvidencePort)
    assert isinstance(CausalHistoryEvent(), CausalEventView)
    assert isinstance(CausalHistory(), CausalHistoryView)


def test_ap52_state_vocabulary_matches_the_e3_enum():
    from app.cognitive.models.enums import AccessibilityState

    assert {e.value for e in AccessibilityState} == ACCESSIBILITY_STATE_TOKENS
    assert AccessibilityState.CAUSALLY_EXTINCT.value == CAUSALLY_EXTINCT_TOKEN


@pytest.mark.parametrize(
    "primeiro_import",
    [
        "app.memory.ports.accessibility",
        "app.memory.schemas.accessibility",
        "app.memory.models.accessibility_policy",
        "app.memory.services.accessibility_policy_manager",
    ],
)
def test_ap53_public_imports_work_in_any_order_in_a_clean_interpreter(primeiro_import):
    """Guarda contra ciclo de import — o sétimo defeito da E4.3.1."""
    resultado = subprocess.run(
        [sys.executable, "-c", f"import {primeiro_import}; print('ok')"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "ok" in resultado.stdout


def _codigo_executavel() -> str:
    """Fonte da E4.7 sem docstrings nem literais soltos.

    As docstrings citam nominalmente o que o módulo não faz; comparar o
    texto bruto produziria falso positivo — o mesmo erro que a E4.3.1
    corrigiu em `gv16` e a E4.6.2 refinou para literais de atributo.
    """
    import app.memory.ports.accessibility as porta_mod
    import app.memory.schemas.accessibility as schema_mod
    import app.memory.services.accessibility_policy_manager as manager_mod

    partes = []
    for modulo in (manager_mod, schema_mod, porta_mod):
        arvore = ast.parse(pathlib.Path(modulo.__file__).read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            corpo = getattr(no, "body", None)
            if not isinstance(corpo, list):
                continue
            no.body = [
                filho
                for filho in corpo
                if not (
                    isinstance(filho, ast.Expr)
                    and isinstance(filho.value, ast.Constant)
                    and isinstance(filho.value.value, str)
                )
            ] or [ast.Pass()]
        partes.append(ast.unparse(arvore))
    return "\n".join(partes)


# ======================================================================
# Ramos descobertos pela exigência de 100%
# ======================================================================


@pytest.mark.parametrize("invalido", ["active", b"active", 123, None])
def test_ap54_rule_refuses_non_collection_state_arguments(invalido):
    """`str` e `bytes` são iteráveis; aceitá-los transformaria `"active"`
    num conjunto de caracteres em vez de erro.

    Constrói a regra **diretamente**: o helper `_regra` embrulha em
    `frozenset(...)`, o que já converteria a string em caracteres antes
    de o value object ser chamado — e o teste então provaria outra coisa.
    """
    with pytest.raises(TypeError, match="coleção de tokens"):
        AccessibilityRule(
            rule_id="r",
            effect=GovernanceEffect.ADMIT,
            source_states=invalido,
            target_states=frozenset({"latent"}),
        )


def test_ap55_rule_refuses_non_string_items():
    with pytest.raises(TypeError, match="apenas str"):
        _regra(fontes=(123,))


@pytest.mark.parametrize(
    ("campo", "valor", "excecao"),
    [
        ("rule_id", 123, TypeError),
        ("rule_id", "   ", ValueError),
        ("effect", "admit", TypeError),
    ],
)
def test_ap56_rule_separates_type_from_value_errors(campo, valor, excecao):
    campos = {
        "rule_id": "r",
        "effect": GovernanceEffect.ADMIT,
        "source_states": frozenset({"active"}),
        "target_states": frozenset({"latent"}),
    }
    campos[campo] = valor
    with pytest.raises(excecao):
        AccessibilityRule(**campos)


@pytest.mark.parametrize(
    ("campo", "valor", "excecao"),
    [
        ("outcome", "admissible", TypeError),
        ("source_state", 123, TypeError),
        ("target_state", "quantum", ValueError),
    ],
)
def test_ap57_decision_separates_type_from_value_errors(campo, valor, excecao):
    campos = {
        "outcome": GovernanceOutcome.NOT_APPLICABLE,
        "source_state": "active",
        "target_state": "latent",
    }
    campos[campo] = valor
    with pytest.raises(excecao):
        AccessibilityDecision(**campos)


def test_ap58_decision_cannot_cite_a_rule_without_a_policy():
    with pytest.raises(ValueError, match="citar uma regra exige"):
        AccessibilityDecision(
            outcome=GovernanceOutcome.ADMISSIBLE,
            source_state="active",
            target_state="latent",
            matched_rule_id="r1",
        )


@pytest.mark.parametrize(
    ("campo", "valor", "excecao"),
    [
        ("coid", "nao-e-uuid", TypeError),
        ("context", "nao-e-contexto", TypeError),
        ("governance_resolution", "nao-e-resolucao", TypeError),
        ("decision", "nao-e-decisao", TypeError),
        ("observed_state", 123, TypeError),
        ("observed_state", "quantum", ValueError),
        ("state_changed", "sim", TypeError),
        ("no_change", "sim", TypeError),
        ("causal_event_id", "nao-e-uuid", TypeError),
    ],
)
def test_ap59_result_separates_type_from_value_errors(campo, valor, excecao):
    with pytest.raises(excecao):
        _resultado(**{campo: valor})


def test_ap60_denied_result_cannot_claim_a_no_op():
    """A recusa é anterior a olhar o sujeito, então nem no-op houve."""
    with pytest.raises(ValueError, match="nem escrita nem no-op"):
        _resultado(
            governance_resolution=_resolucao(outcome=GovernanceOutcome.NOT_APPLICABLE),
            decision=None,
            observed_state="active",
            state_changed=False,
            no_change=True,
        )


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("coid", "nao-e-uuid"),
        ("target_state", 123),
        ("descriptor", "nao-e-descritor"),
        ("reason", 123),
        ("causal_event_id", "nao-e-uuid"),
    ],
)
def test_ap61_manager_refuses_invalid_argument_types(campo, valor):
    manager, subject_port, _, _, _, governanca = _manager(sujeito=SujeitoFalso(uuid.uuid4()))
    argumentos: dict = {
        "coid": uuid.uuid4(),
        "target_state": "latent",
        "context": MemoryContext(),
        "descriptor": _descritor(),
        "governance_policy_key": _GK,
        "accessibility_policy_key": _AK,
    }
    argumentos[campo] = valor
    with pytest.raises(TypeError):
        manager.transition(**argumentos)
    assert subject_port.buscas == []
    assert governanca.chamadas == []


def test_ap62_non_context_from_validator_is_a_contract_violation():
    class ContextoQuebrado:
        def validate(self, context):
            return "nao-e-contexto"

    manager = AccessibilityPolicyManager(
        SubjectPortFalso(SujeitoFalso(uuid.uuid4())),
        TransitionPortFalso(),
        EvidencePortFalso(),
        PolicyRepoFalso(None),
        GovernanceFalso(_resolucao()),
        ContextoQuebrado(),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager)
    assert any("não MemoryContext" in m for m in exc.value.reasons)


def test_ap63_non_resolution_from_governance_is_a_contract_violation():
    manager = AccessibilityPolicyManager(
        SubjectPortFalso(SujeitoFalso(uuid.uuid4())),
        TransitionPortFalso(),
        EvidencePortFalso(),
        PolicyRepoFalso(None),
        GovernanceFalso("nao-e-resolucao", eco_policy=False),
        ContextoFalso(),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager)
    assert any("não GovernanceResolution" in m for m in exc.value.reasons)


def test_ap64_non_string_state_from_the_port_is_a_contract_violation():
    manager, _, _, _, _, _ = _manager(sujeito=SujeitoFalso(uuid.uuid4()), estado_devolvido=123)
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager)
    assert any("não str" in m for m in exc.value.reasons)


def test_ap65_default_moment_is_used_when_none_is_given():
    """Sem `moment`, a vigência é avaliada em UTC — não no fuso da
    máquina."""
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, _, _, policy_repo, _ = _manager(sujeito=sujeito, policy=_policy(_regra()))
    _transicionar(manager, coid=sujeito.id, moment=None)
    assert policy_repo.consultas
    instante = policy_repo.consultas[0][1]
    assert instante.tzinfo is UTC


def test_ap66_duplicate_rule_id_in_the_same_version_is_refused():
    """Duplicata torna o fundamento da decisão ambíguo."""
    from app.memory.models.accessibility_policy import AccessibilityPolicy

    with pytest.raises(ValueError, match="rule_id duplicado"):
        AccessibilityPolicy.serialize_rules((_regra("r"), _regra("r", alvos=("inaccessible",))))


def test_ap67_sqlite_unique_violation_is_recognized_by_driver_signal():
    """Classificação por **sinal do driver**, nunca por texto da
    mensagem — lição da E3.2.1.

    O ramo SQLite não é alcançável nos testes de integração (que rodam
    em PostgreSQL), então é exercitado aqui com o sinal que o driver
    emite.
    """
    from app.memory.repositories.accessibility_policy_repository import (
        _is_unique_violation,
    )

    class _OrigSqlite:
        sqlite_errorname = "SQLITE_CONSTRAINT_UNIQUE"

    class _OrigOutro:
        sqlite_errorname = "SQLITE_CONSTRAINT_NOTNULL"

    class _Erro(Exception):
        def __init__(self, orig):
            self.orig = orig

    unico = Exception()
    unico.__cause__ = _Erro(_OrigSqlite())
    outro = Exception()
    outro.__cause__ = _Erro(_OrigOutro())

    assert _is_unique_violation(unico) is True  # type: ignore[arg-type]
    assert _is_unique_violation(outro) is False  # type: ignore[arg-type]


def test_ap68_non_unique_persistence_error_is_reraised_unchanged():
    """Um erro de persistência que não é violação de unicidade não vira
    diagnóstico de versão duplicada — ele sobe como veio."""
    from app.repositories.exceptions import PersistenceError

    class RepoQuebrado:
        def add(self, entity):
            raise PersistenceError("falha genérica")

    from app.memory.repositories.accessibility_policy_repository import (
        AccessibilityPolicyRepository,
    )

    repo = AccessibilityPolicyRepository.__new__(AccessibilityPolicyRepository)
    repo.add = RepoQuebrado().add  # type: ignore[method-assign]
    with pytest.raises(PersistenceError, match="falha genérica"):
        AccessibilityPolicyRepository.add_policy(
            repo, policy_key="k", version=1, governance_policy_key="g"
        )


def test_ap69_orm_delete_of_a_published_version_is_refused_by_the_mapper():
    """Segunda camada: o evento de mapper pega o `DELETE` que contorna o
    repositório."""
    from app.memory.errors.exceptions import AccessibilityPolicyImmutableError
    from app.memory.models.accessibility_policy import (
        AccessibilityPolicy,
        _reject_published_accessibility_policy_delete,
    )

    alvo = AccessibilityPolicy(policy_key="k", version=1, governance_policy_key="g")
    alvo.id = uuid.uuid4()
    with pytest.raises(AccessibilityPolicyImmutableError):
        _reject_published_accessibility_policy_delete(None, None, alvo)
