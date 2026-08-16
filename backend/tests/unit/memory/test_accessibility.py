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
    governance_policy_key: str = _GK
    """O vínculo de autoridade é **verificado** desde o corretivo
    E4.7.1: uma AccessibilityPolicy subordinada a G2 não pode operar sob
    autoridade G1."""


class GovernanceFalso:
    def __init__(self, resolution, *, eco_policy: bool = True) -> None:
        self.resolution = resolution
        self.eco_policy = eco_policy
        self.chamadas: list[dict] = []

    def resolve(self, *, descriptor, context, policy_key=None, moment=None):
        self.chamadas.append({"descriptor": descriptor, "policy_key": policy_key, "moment": moment})
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


def _policy(*regras, version=1, policy_key=_AK, governance_policy_key=_GK):
    from app.memory.models.accessibility_policy import AccessibilityPolicy

    return PolicyFalsa(
        policy_key=policy_key,
        version=version,
        rules=AccessibilityPolicy.serialize_rules(tuple(regras)),
        governance_policy_key=governance_policy_key,
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
    # O COID padrão das chamadas passa a ser o do sujeito montado: desde
    # o corretivo E4.7.1 a identidade é verificada, e um UUID aleatório
    # produziria `PIA-8037` — corretamente, mas mascarando o caso sob
    # teste.
    manager._coid_de_teste = sujeito.id if sujeito is not None else None  # type: ignore[attr-defined]
    return manager, subject_port, transition_port, evidence_port, policy_repo, governanca


def _transicionar(manager, *, coid=None, alvo="latent", sujeito=None, **kw):
    """Executa a transição.

    A partir do corretivo E4.7.1 a identidade do sujeito é verificada em
    três pontos, então o COID pedido precisa ser o do sujeito montado —
    um UUID aleatório agora produz `PIA-8037`, corretamente.
    """
    if coid is None:
        coid = sujeito.id if sujeito is not None else getattr(manager, "_coid_de_teste", None)
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
    with pytest.raises(ValueError, match="exatamente um token"):
        _regra(fontes=())
    with pytest.raises(ValueError, match="exatamente um token"):
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


def test_ap4_rule_matches_exactly_one_edge():
    """Uma regra descreve UMA aresta (corretivo E4.7.1).

    A versão anterior deste teste usava `{active, latent} → {inaccessible}`
    — ela própria uma regra cartesiana, isto é, o defeito G escrito no
    harness. Duas arestas exigem duas regras.
    """
    regra = _regra(fontes=("active",), alvos=("inaccessible",))
    assert regra.matches(source_state="active", target_state="inaccessible")
    assert not regra.matches(source_state="latent", target_state="inaccessible")
    assert not regra.matches(source_state="active", target_state="latent")


@pytest.mark.parametrize(
    ("fontes", "alvos"),
    [
        (("active", "latent"), ("inaccessible",)),
        (("active",), ("inaccessible", CAUSALLY_EXTINCT_TOKEN)),
        (("active", "latent"), ("inaccessible", CAUSALLY_EXTINCT_TOKEN)),
    ],
)
def test_ap4b_cartesian_rule_is_refused(fontes, alvos):
    """`ONE TRANSITION RULE = ONE EXACT EDGE`.

    `{ACTIVE, LATENT} × {INACCESSIBLE, CAUSALLY_EXTINCT}` autorizava
    quatro transições a partir de uma única regra declarada.
    """
    with pytest.raises(ValueError, match="exatamente um token"):
        _regra(fontes=fontes, alvos=alvos)


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
        _decisao(matched_rule_id=None)


def test_ap7_decision_not_applicable_cannot_cite_a_rule():
    with pytest.raises(ValueError, match="contradiz o desfecho"):
        _decisao(outcome=GovernanceOutcome.NOT_APPLICABLE)


def test_ap8_decision_policy_identity_is_all_or_nothing():
    """Proveniência parcial parece proveniência — lição da E4.3.2."""
    with pytest.raises(ValueError, match="tudo-ou-nada"):
        _decisao(
            outcome=GovernanceOutcome.NOT_APPLICABLE,
            policy_version=None,
            governance_policy_key=None,
            matched_rule_id=None,
        )


def test_ap9_decision_never_carries_prohibited():
    """`PROHIBITED` pertence à fronteira de segurança da plataforma."""
    with pytest.raises(ValueError, match="fronteira de segurança"):
        _decisao(outcome=GovernanceOutcome.PROHIBITED)


def test_ap10_only_admissible_admits():
    admissivel = _decisao()
    nao_aplicavel = _decisao(
        outcome=GovernanceOutcome.NOT_APPLICABLE,
        policy_key=None,
        policy_version=None,
        governance_policy_key=None,
        matched_rule_id=None,
    )
    assert admissivel.is_admissible is True
    assert nao_aplicavel.is_admissible is False


def _decisao(**overrides):
    campos = {
        "outcome": GovernanceOutcome.ADMISSIBLE,
        "source_state": "active",
        "target_state": "latent",
        "evaluated_at": _MOMENTO,
        "policy_key": _AK,
        "policy_version": 1,
        "governance_policy_key": _GK,
        "matched_rule_id": "r1",
    }
    campos.update(overrides)
    return AccessibilityDecision(**campos)


def _resultado(**overrides):
    campos = {
        "coid": uuid.uuid4(),
        "context": MemoryContext(),
        "governance_resolution": _resolucao(),
        "decision": _decisao(),
        "requested_target_state": "latent",
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
        _resultado(decision=_decisao(outcome=GovernanceOutcome.INADMISSIBLE))


def test_ap13_result_postcondition_must_confirm_the_target():
    with pytest.raises(ValueError, match="pós-condição não confirma"):
        _resultado(observed_state="active")


def test_ap14_result_extinction_requires_causal_evidence():
    decisao = _decisao(target_state=CAUSALLY_EXTINCT_TOKEN)
    with pytest.raises(ValueError, match="evidência causal"):
        _resultado(
            decision=decisao,
            requested_target_state=CAUSALLY_EXTINCT_TOKEN,
            observed_state=CAUSALLY_EXTINCT_TOKEN,
        )


def test_ap15_denied_result_cannot_carry_a_decision():
    with pytest.raises(ValueError, match="avaliação que não ocorreu"):
        _resultado(
            governance_resolution=_resolucao(outcome=GovernanceOutcome.INADMISSIBLE),
            observed_state=None,
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
        observed_state=None,
        state_changed=False,
    )
    noop = _resultado(decision=None, observed_state="active", state_changed=False, no_change=True)
    avaliado = _resultado()
    assert (negado.no_change, negado.policy_evaluated) == (False, False)
    assert negado.observed_state is None, "recusa não fabrica observação"
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


def test_ap36_extinction_without_reason_is_refused_only_for_a_real_change():
    """**Corrigido em E4.7.1.** A versão anterior deste teste codificava
    o defeito F: exigia `reason` **antes** de Governance e do lock, o que
    impedia o no-op prometido para um objeto já `causally_extinct`.

    A exigência é real, mas pertence ao ponto em que a mudança é real —
    depois de observar o estado atual sob lock.

        NO-OP REQUIRES NO FABRICATED CAUSE
    """
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, subject_port, transition_port, _, _, governanca = _manager(
        sujeito=sujeito, policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,)))
    )
    with pytest.raises(ValueError, match="reason não-vazio"):
        _transicionar(manager, coid=sujeito.id, alvo=CAUSALLY_EXTINCT_TOKEN)
    # governança e lock JÁ ocorreram; a escrita não
    assert governanca.chamadas != []
    assert subject_port.locks == [sujeito.id]
    assert transition_port.escritas == []


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
    # evento existe e é o pedido, mas pertence a OUTRA história
    evento_id = uuid.uuid4()
    evento = EventoFalso(id=evento_id, history_id=uuid.uuid4())
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
            causal_event_id=evento_id,
        )
    assert any("história" in m for m in exc.value.reasons)
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
    assert porta.escritas, "a porta precisa ter sido chamada"
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


@pytest.mark.parametrize("invalido", [b"active", 123, None])
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


def test_ap54b_string_state_argument_is_refused_as_a_character_set():
    """`"active"` é iterável; aceitá-lo daria um conjunto de caracteres.

    Com uma aresta por regra, a mensagem que aparece é a de
    cardinalidade — `"active"` vira seis caracteres — e é igualmente
    correta: o argumento não descreve uma aresta.
    """
    with pytest.raises((TypeError, ValueError)):
        AccessibilityRule(
            rule_id="r",
            effect=GovernanceEffect.ADMIT,
            source_states="active",  # type: ignore[arg-type]
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
        ("evaluated_at", "ontem", TypeError),
        ("evaluated_at", datetime(2024, 6, 1), ValueError),
    ],
)
def test_ap57_decision_separates_type_from_value_errors(campo, valor, excecao):
    with pytest.raises(excecao):
        _decisao(
            **{
                "outcome": GovernanceOutcome.NOT_APPLICABLE,
                "policy_key": None,
                "policy_version": None,
                "governance_policy_key": None,
                "matched_rule_id": None,
                campo: valor,
            }
        )


def test_ap58_decision_cannot_cite_a_rule_without_a_policy():
    with pytest.raises(ValueError, match="citar uma regra exige"):
        _decisao(policy_key=None, policy_version=None, governance_policy_key=None)


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
            observed_state=None,
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

    sujeito = SujeitoFalso(uuid.uuid4())
    manager = AccessibilityPolicyManager(
        SubjectPortFalso(sujeito),
        TransitionPortFalso(),
        EvidencePortFalso(),
        PolicyRepoFalso(None),
        GovernanceFalso(_resolucao()),
        ContextoQuebrado(),
    )
    manager._coid_de_teste = sujeito.id  # type: ignore[attr-defined]
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager)
    assert any("não MemoryContext" in m for m in exc.value.reasons)


def test_ap63_non_resolution_from_governance_is_a_contract_violation():
    sujeito = SujeitoFalso(uuid.uuid4())
    manager = AccessibilityPolicyManager(
        SubjectPortFalso(sujeito),
        TransitionPortFalso(),
        EvidencePortFalso(),
        PolicyRepoFalso(None),
        GovernanceFalso("nao-e-resolucao", eco_policy=False),
        ContextoFalso(),
    )
    manager._coid_de_teste = sujeito.id  # type: ignore[attr-defined]
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


# ======================================================================
# E4.7.1 — Authority, Subject, Evidence & Temporal Fidelity
# ======================================================================
#
# Oito defeitos da auditoria, quatro causas-raiz, um hábito:
#
#     PORT RETURN != TRUSTED FACT UNTIL FIDELITY IS VERIFIED


def _sujeito_e_manager(**kw):
    sujeito = kw.pop("sujeito", None) or SujeitoFalso(uuid.uuid4())
    manager, sp, tp, ep, pr, gm = _manager(sujeito=sujeito, **kw)
    return sujeito, manager, sp, tp, ep, pr, gm


# --- A: identidade do sujeito ----------------------------------------


def test_e471_get_by_id_returning_another_subject_is_refused():
    """`REQUESTED SUBJECT MUST BE THE WRITTEN SUBJECT`.

    Na cadeia 55 o pedido sobre A escrevia em B e devolvia um resultado
    citando A.
    """
    pedido = uuid.uuid4()
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=SujeitoFalso(uuid.uuid4()), policy=_policy(_regra())
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager, coid=pedido)
    assert exc.value.code == "PIA-8037"
    assert any("get_by_id devolveu o sujeito" in m for m in exc.value.reasons)
    assert transition_port.escritas == []


def test_e471_lock_returning_another_subject_is_refused():
    """A substituição pode acontecer no lock, não só no lookup."""

    class LockInfiel(SubjectPortFalso):
        def refresh_for_update(self, entity):
            self.locks.append(entity.id)
            return SujeitoFalso(uuid.uuid4())

    sujeito = SujeitoFalso(uuid.uuid4())
    porta = LockInfiel(sujeito)
    transition_port = TransitionPortFalso()
    manager = AccessibilityPolicyManager(
        porta,
        transition_port,
        EvidencePortFalso(),
        PolicyRepoFalso(_policy(_regra())),
        GovernanceFalso(_resolucao()),
        ContextoFalso(),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager, coid=sujeito.id)
    assert any("refresh_for_update devolveu o sujeito" in m for m in exc.value.reasons)
    assert transition_port.escritas == []


def test_e471_transition_returning_another_subject_is_refused_after_the_write():
    """Divergência **depois** da escrita sobe para rollback externo, sem
    reparo.

        AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN
    """

    class EscritaInfiel(TransitionPortFalso):
        def transition(self, obj, target_state, *, reason=None):
            self.escritas.append((obj.id, target_state, reason))
            obj.estado = target_state
            return SujeitoFalso(uuid.uuid4(), estado=target_state)

    sujeito = SujeitoFalso(uuid.uuid4())
    porta = EscritaInfiel()
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
    assert any("transition devolveu o sujeito" in m for m in exc.value.reasons)
    assert porta.escritas, "a escrita ocorreu e o rollback é do chamador"


def test_e471_subject_without_observable_identity_is_refused():
    class SemId:
        estado = "active"

    class PortaSemId(SubjectPortFalso):
        def get_by_id(self, entity_id, *, include_deleted=False):
            return SemId()

    manager = AccessibilityPolicyManager(
        PortaSemId(None),
        TransitionPortFalso(),
        EvidencePortFalso(),
        PolicyRepoFalso(_policy(_regra())),
        GovernanceFalso(_resolucao()),
        ContextoFalso(),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager, coid=uuid.uuid4())
    assert any("sem identidade observável" in m for m in exc.value.reasons)


def test_e471_subject_with_non_uuid_id_is_refused():
    @dataclasses.dataclass
    class IdErrado:
        id: str = "nao-e-uuid"
        estado: str = "active"

    class PortaIdErrado(SubjectPortFalso):
        def get_by_id(self, entity_id, *, include_deleted=False):
            return IdErrado()

    manager = AccessibilityPolicyManager(
        PortaIdErrado(None),
        TransitionPortFalso(),
        EvidencePortFalso(),
        PolicyRepoFalso(_policy(_regra())),
        GovernanceFalso(_resolucao()),
        ContextoFalso(),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager, coid=uuid.uuid4())
    assert any("não uuid.UUID" in m for m in exc.value.reasons)


# --- B: vínculo de autoridade ----------------------------------------


def test_e471_policy_bound_to_another_governance_authority_is_refused():
    """`REQUESTED AUTHORITY MUST BE THE POLICY'S AUTHORITY`.

    `governance_policy_key` era persistido e documentado, mas nunca
    lido: `PERSISTED BINDING != ENFORCED BINDING`.
    """
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito, policy=_policy(_regra(), governance_policy_key="G2")
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager, coid=sujeito.id)
    assert exc.value.code == "PIA-8037"
    assert any("subordinada" in m for m in exc.value.reasons)
    assert transition_port.escritas == []


def test_e471_repository_returning_another_policy_key_is_refused():
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito, policy=_policy(_regra(), policy_key="OUTRA")
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _transicionar(manager, coid=sujeito.id)
    assert any("o repositório devolveu a policy" in m for m in exc.value.reasons)
    assert transition_port.escritas == []


def test_e471_binding_mismatch_is_never_merely_not_applicable():
    """Mismatch de autoridade é violação de contrato — nunca um desfecho
    de policy, e nunca admissão."""
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, _, _, _, _ = _manager(
        sujeito=sujeito, policy=_policy(_regra(), governance_policy_key="G2")
    )
    with pytest.raises(AccessibilityTransitionContractViolationError):
        _transicionar(manager, coid=sujeito.id)


def test_e471_decision_carries_the_verified_governance_key():
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, _, _, _, _ = _manager(sujeito=sujeito, policy=_policy(_regra()))
    resultado = _transicionar(manager, coid=sujeito.id)
    assert resultado.decision is not None
    assert resultado.decision.governance_policy_key == _GK
    assert resultado.decision.policy_key == _AK


# --- C: fidelidade da evidência causal -------------------------------


def _extincao(manager, sujeito, **kw):
    return _transicionar(
        manager,
        coid=sujeito.id,
        alvo=CAUSALLY_EXTINCT_TOKEN,
        reason="fim",
        **kw,
    )


def test_e471_port_returning_another_event_is_refused():
    """`REQUESTED EVENT MUST BE THE VERIFIED EVENT`."""
    sujeito = SujeitoFalso(uuid.uuid4())
    historia = HistoriaFalsa(id=uuid.uuid4(), subject_coid=sujeito.id)
    devolvido = EventoFalso(id=uuid.uuid4(), history_id=historia.id)
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito,
        policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,))),
        evidencia=EvidencePortFalso(evento=devolvido, historia=historia),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _extincao(manager, sujeito, causal_event_id=uuid.uuid4())
    assert any("mas o solicitado foi" in m for m in exc.value.reasons)
    assert transition_port.escritas == []


def test_e471_history_of_another_subject_is_refused():
    sujeito = SujeitoFalso(uuid.uuid4())
    pedido = uuid.uuid4()
    historia = HistoriaFalsa(id=uuid.uuid4(), subject_coid=uuid.uuid4())
    evento = EventoFalso(id=pedido, history_id=historia.id)
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito,
        policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,))),
        evidencia=EvidencePortFalso(evento=evento, historia=historia),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _extincao(manager, sujeito, causal_event_id=pedido)
    assert any("história devolvida pertence a" in m for m in exc.value.reasons)
    assert transition_port.escritas == []


def test_e471_all_three_causal_mismatches_are_reported_together():
    """Uma porta infiel raramente diverge num só ponto."""
    sujeito = SujeitoFalso(uuid.uuid4())
    historia = HistoriaFalsa(id=uuid.uuid4(), subject_coid=uuid.uuid4())
    evento = EventoFalso(id=uuid.uuid4(), history_id=uuid.uuid4())
    manager, _, _, _, _, _ = _manager(
        sujeito=sujeito,
        policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,))),
        evidencia=EvidencePortFalso(evento=evento, historia=historia),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _extincao(manager, sujeito, causal_event_id=uuid.uuid4())
    assert len(exc.value.reasons) == 3


def test_e471_non_uuid_identifiers_in_causal_evidence_are_refused():
    @dataclasses.dataclass(frozen=True)
    class EventoTorto:
        id: str = "nao-e-uuid"
        history_id: str = "tambem-nao"

    sujeito = SujeitoFalso(uuid.uuid4())
    historia = HistoriaFalsa(id=uuid.uuid4(), subject_coid=sujeito.id)
    manager, _, _, _, _, _ = _manager(
        sujeito=sujeito,
        policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,))),
        evidencia=EvidencePortFalso(evento=EventoTorto(), historia=historia),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _extincao(manager, sujeito, causal_event_id=uuid.uuid4())
    assert any("não uuid.UUID" in m for m in exc.value.reasons)


def test_e471_only_the_confirmed_event_id_is_cited():
    sujeito = SujeitoFalso(uuid.uuid4())
    historia = HistoriaFalsa(id=uuid.uuid4(), subject_coid=sujeito.id)
    evento = EventoFalso(id=uuid.uuid4(), history_id=historia.id)
    manager, _, _, _, _, _ = _manager(
        sujeito=sujeito,
        policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,))),
        evidencia=EvidencePortFalso(evento=evento, historia=historia),
    )
    resultado = _extincao(manager, sujeito, causal_event_id=evento.id)
    assert resultado.causal_event_id == evento.id


# --- E: observação não fabricada -------------------------------------


def test_e471_governance_denial_yields_no_observed_state():
    """`OBSERVED STATE REQUIRES AN OBSERVATION`."""
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, subject_port, _, _, _, _ = _manager(
        sujeito=sujeito, resolution=_resolucao(outcome=GovernanceOutcome.NOT_APPLICABLE)
    )
    resultado = _transicionar(manager, coid=sujeito.id)
    assert subject_port.buscas == []
    assert resultado.observed_state is None
    assert resultado.requested_target_state == "latent"


def test_e471_authorized_paths_always_carry_an_observation():
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, _, _, _, _ = _manager(sujeito=sujeito, policy=_policy(_regra()))
    resultado = _transicionar(manager, coid=sujeito.id)
    assert resultado.observed_state == "latent"


# --- H: instante único -----------------------------------------------


def test_e471_one_instant_reaches_governance_policy_and_decision():
    """`ONE OPERATION = ONE EVALUATION INSTANT`."""
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, _, _, policy_repo, governanca = _manager(sujeito=sujeito, policy=_policy(_regra()))
    resultado = _transicionar(manager, coid=sujeito.id, moment=None)
    instante_governanca = governanca.chamadas[0]["moment"]
    instante_policy = policy_repo.consultas[0][1]
    assert instante_governanca is not None
    assert instante_governanca == instante_policy
    assert resultado.decision is not None
    assert resultado.decision.evaluated_at == instante_governanca
    assert instante_governanca.tzinfo is UTC


def test_e471_explicit_moment_is_canonicalized_to_utc():
    from datetime import timedelta, timezone

    outro_fuso = timezone(timedelta(hours=-3))
    momento = datetime(2024, 6, 1, 9, 0, tzinfo=outro_fuso)
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, _, _, _, policy_repo, governanca = _manager(sujeito=sujeito, policy=_policy(_regra()))
    _transicionar(manager, coid=sujeito.id, moment=momento)
    recebido = governanca.chamadas[0]["moment"]
    assert recebido.tzinfo is UTC
    assert recebido == momento
    assert policy_repo.consultas[0][1] == recebido


@pytest.mark.parametrize(
    ("momento", "excecao"),
    [("ontem", TypeError), (datetime(2024, 6, 1), ValueError)],
)
def test_e471_invalid_moment_is_refused_before_collaborators(momento, excecao):
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, subject_port, _, _, _, governanca = _manager(sujeito=sujeito)
    with pytest.raises(excecao):
        _transicionar(manager, coid=sujeito.id, moment=momento)
    assert governanca.chamadas == []
    assert subject_port.buscas == []


# --- Argumentos básicos e G ------------------------------------------


@pytest.mark.parametrize("campo", ["governance_policy_key", "accessibility_policy_key"])
@pytest.mark.parametrize(("valor", "excecao"), [(123, TypeError), ("  ", ValueError)])
def test_e471_policy_keys_are_validated_before_collaborators(campo, valor, excecao):
    sujeito = SujeitoFalso(uuid.uuid4())
    manager, subject_port, _, _, _, governanca = _manager(sujeito=sujeito)
    with pytest.raises(excecao):
        _transicionar(manager, coid=sujeito.id, **{campo: valor})
    assert governanca.chamadas == []
    assert subject_port.buscas == []


def test_e471_serialization_refuses_cartesian_rules():
    """O payload plural é preservado, mas a cardinalidade é 1."""
    from app.memory.models.accessibility_policy import AccessibilityPolicy

    historico = [
        {
            "rule_id": "r",
            "effect": "admit",
            "source_states": ["active", "latent"],
            "target_states": ["inaccessible"],
        }
    ]
    with pytest.raises(ValueError, match="exatamente um token"):
        AccessibilityPolicy.deserialize_rules(historico)


def test_e471_singleton_rule_round_trips():
    from app.memory.models.accessibility_policy import AccessibilityPolicy

    original = (_regra(),)
    ida = AccessibilityPolicy.serialize_rules(original)
    assert ida[0]["source_states"] == ["active"]
    assert ida[0]["target_states"] == ["latent"]
    assert AccessibilityPolicy.deserialize_rules(ida) == original


def test_e471_static_port_assignment_is_the_real_proof():
    """`RUNTIME_CHECKABLE != STATIC SIGNATURE COMPATIBILITY`.

    `isinstance` num `Protocol` `runtime_checkable` confere **nomes de
    membros**, não assinaturas — foi por isso que a candidata 55 passou
    nos próprios testes com uma porta que o mypy recusa. A prova real
    vive em `tests/static/test_port_assignment.py`, verificada pelo
    mypy; este teste apenas registra que ela existe.
    """
    prova = pathlib.Path(__file__).resolve().parents[2] / "static" / "test_port_assignment.py"
    assert prova.exists(), "a prova estática da porta precisa existir"
    fonte = prova.read_text(encoding="utf-8")
    assert "AccessibilityTransitionPort" in fonte
    assert "AccessibilityManager" in fonte


# --- Ramos descobertos pela exigência de 100% ------------------------


@pytest.mark.parametrize(
    ("valor", "excecao"), [(123, TypeError), ("quantum", ValueError)]
)
def test_e471_requested_target_state_is_validated(valor, excecao):
    with pytest.raises(excecao):
        _resultado(requested_target_state=valor)


def test_e471_denied_result_cannot_carry_an_observed_state():
    """A recusa é anterior a olhar o sujeito."""
    with pytest.raises(ValueError, match="observação que não ocorreu"):
        _resultado(
            governance_resolution=_resolucao(outcome=GovernanceOutcome.NOT_APPLICABLE),
            decision=None,
            observed_state="active",
            state_changed=False,
        )


def test_e471_authorized_result_requires_an_observed_state():
    """Com governança autorizada o sujeito é lido sob lock — `None`
    descreveria uma operação que não aconteceu."""
    with pytest.raises(ValueError, match="não pode ser None"):
        _resultado(decision=None, observed_state=None, state_changed=False, no_change=True)


def test_e471_causal_port_returning_a_shapeless_event_is_refused():
    class Nada:
        pass

    sujeito = SujeitoFalso(uuid.uuid4())
    historia = HistoriaFalsa(id=uuid.uuid4(), subject_coid=sujeito.id)
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito,
        policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,))),
        evidencia=EvidencePortFalso(evento=Nada(), historia=historia),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _extincao(manager, sujeito, causal_event_id=uuid.uuid4())
    assert any("sem os campos de um evento causal" in m for m in exc.value.reasons)
    assert transition_port.escritas == []


def test_e471_causal_port_returning_a_shapeless_history_is_refused():
    class Nada:
        pass

    sujeito = SujeitoFalso(uuid.uuid4())
    evento_id = uuid.uuid4()
    manager, _, transition_port, _, _, _ = _manager(
        sujeito=sujeito,
        policy=_policy(_regra(alvos=(CAUSALLY_EXTINCT_TOKEN,))),
        evidencia=EvidencePortFalso(
            evento=EventoFalso(id=evento_id, history_id=uuid.uuid4()), historia=Nada()
        ),
    )
    with pytest.raises(AccessibilityTransitionContractViolationError) as exc:
        _extincao(manager, sujeito, causal_event_id=evento_id)
    assert any("sem os campos de uma história" in m for m in exc.value.reasons)
    assert transition_port.escritas == []
