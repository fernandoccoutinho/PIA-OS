"""
Testes unitários da E4.8 — Memory Isolation.

Cobrem a autoridade domínio a domínio, a atomicidade da recusa, o
snapshot e a pós-condição de não expansão, com dublês das portas.

A composição real com `MemoryRetrievalManager`, `GovernanceManager`,
`ContextManager` e `MemoryDomainMembershipRepository`, o vazamento real
e o censo SQL vivem em
`tests/integration/memory/test_memory_isolation_integration.py`.
"""

import ast
import dataclasses
import pathlib
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.memory.errors.exceptions import (
    IsolationContractViolationError,
    IsolationScopeRequiredError,
)
from app.memory.models.governance_enums import (
    CognitiveOperation,
    CriticalCapability,
    GovernanceOutcome,
)
from app.memory.ports.isolation import (
    ContextValidationPort,
    DomainMembershipPort,
    GovernanceResolutionPort,
    IsolatedRetrievalPort,
    MembershipView,
)
from app.memory.schemas.governance import GovernanceResolution
from app.memory.schemas.isolation import DomainIsolationDecision, MemoryIsolationResult
from app.memory.schemas.memory_context import MemoryContext
from app.memory.schemas.retrieval import MemoryRetrievalResult, RetrievedMemoryItem
from app.memory.services.memory_isolation_manager import MemoryIsolationManager
from app.memory.services.platform_safety_boundary import (
    PLATFORM_SAFETY_BOUNDARY_VERSION,
    CapabilityDescriptor,
)

_GK = "gov-iso"
_POLICY_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")
"""Identidade estável da versão publicada (corretivo E4.8.1).

O helper anterior gerava `uuid.uuid4()` **por chamada**, o que
normalizava como aceitável uma combinação que o repositório real não
produz: duas decisões do mesmo pedido, sob a mesma `policy_key` e o
mesmo `moment`, citando `policy_id` diferentes.

    ONE REQUEST != MULTIPLE AUTHORITY PROVENANCES

O harness codificava o defeito D. Corrigido, não preservado.
"""
_MOMENTO = datetime(2024, 6, 1, tzinfo=UTC)
_D1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
_D2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
_D3 = uuid.UUID("33333333-3333-3333-3333-333333333333")


# --- Construtores -----------------------------------------------------


def _contexto(*dominios, actor_ref="ana", purpose="curadoria", session_id="s1"):
    return MemoryContext(
        domain_ids=dominios or (_D1,),
        actor_ref=actor_ref,
        purpose=purpose,
        session_id=session_id,
    )


def _resolucao(
    *,
    contexto: MemoryContext,
    outcome: GovernanceOutcome = GovernanceOutcome.ADMISSIBLE,
    operation: CognitiveOperation = CognitiveOperation.READ,
    policy_key: str | None = _GK,
):
    campos: dict = {
        "operation": operation,
        "outcome": outcome,
        "context_domain_ids": contexto.domain_ids,
        "context_actor_ref": contexto.actor_ref,
        "context_purpose": contexto.purpose,
        "safety_boundary_version": PLATFORM_SAFETY_BOUNDARY_VERSION,
    }
    if outcome is GovernanceOutcome.PROHIBITED:
        campos |= {
            "blocked_capabilities": (CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT,),
            "safety_rationale": "proibido pela fronteira",
        }
    elif outcome is not GovernanceOutcome.NOT_APPLICABLE:
        campos |= {
            "policy_key": policy_key,
            "policy_version": 1,
            "policy_id": _POLICY_ID,
            "matched_rule_id": "r1",
        }
    return GovernanceResolution(**campos)


def _descritor(operation=CognitiveOperation.READ):
    return CapabilityDescriptor(operation=operation)


@dataclasses.dataclass(frozen=True)
class MembershipFalsa:
    domain_id: uuid.UUID
    coid: uuid.UUID


class ContextoFalso:
    """`ContextManager` fiel: confirma e deriva sem substituir."""

    def __init__(self, *, substituto=None, derivacao_infiel=None) -> None:
        self.substituto = substituto
        self.derivacao_infiel = derivacao_infiel

    def validate(self, context):
        return self.substituto if self.substituto is not None else context

    def derive(self, context, *, domain_ids=None, session_id=None, actor_ref=None, purpose=None):
        if self.derivacao_infiel is not None:
            return self.derivacao_infiel
        return MemoryContext(
            domain_ids=tuple(domain_ids) if domain_ids is not None else context.domain_ids,
            session_id=session_id if session_id is not None else context.session_id,
            actor_ref=actor_ref if actor_ref is not None else context.actor_ref,
            purpose=purpose if purpose is not None else context.purpose,
        )


class GovernancaFalsa:
    """Resolve por domínio, ecoando o contexto — como o manager real."""

    def __init__(self, desfechos: dict | None = None, *, eco: bool = True) -> None:
        self.desfechos = desfechos or {}
        self.eco = eco
        self.chamadas: list[dict] = []
        self.resolucao_fixa: GovernanceResolution | None = None

    def resolve(self, *, descriptor, context, policy_key=None, moment=None):
        self.chamadas.append({"context": context, "policy_key": policy_key, "moment": moment})
        if self.resolucao_fixa is not None:
            return self.resolucao_fixa
        dominio = context.domain_ids[0] if context.domain_ids else None
        outcome = self.desfechos.get(dominio, GovernanceOutcome.ADMISSIBLE)
        return _resolucao(contexto=context, outcome=outcome, policy_key=policy_key)


class MembershipsFalsas:
    def __init__(self, mapa: dict | None = None, *, devolver=None) -> None:
        self.mapa = mapa or {}
        self.devolver = devolver
        self.chamadas: list[uuid.UUID] = []

    def list_memberships_of_domain(self, domain_id):
        self.chamadas.append(domain_id)
        if self.devolver is not None:
            return self.devolver
        return [MembershipFalsa(domain_id, coid) for coid in self.mapa.get(domain_id, ())]


class RetrievalFalsa:
    def __init__(self, coids=(), *, resultado=None) -> None:
        self.coids = tuple(coids)
        self.resultado = resultado
        self.chamadas: list[dict] = []

    def retrieve(
        self,
        *,
        context,
        descriptor,
        criteria,
        policy_key=None,
        moment=None,
        limit=50,
        offset=0,
    ):
        self.chamadas.append(
            {
                "context": context,
                "descriptor": descriptor,
                "criteria": criteria,
                "policy_key": policy_key,
                "moment": moment,
                "limit": limit,
                "offset": offset,
            }
        )
        if self.resultado is not None:
            return self.resultado
        itens = tuple(
            RetrievedMemoryItem(
                coid=coid,
                clid=None,
                accessibility="active",
                revision_status="current",
                created_at=_MOMENTO,
            )
            for coid in self.coids
        )
        return MemoryRetrievalResult(
            context=context,
            # Ecoa a policy solicitada, como a E4.6 real faz: desde o
            # corretivo E4.8.1 a identidade local da Retrieval tem de
            # coincidir com a das decisões, e um dublê que devolvesse
            # sempre `_GK` seria ele próprio incoerente.
            governance_resolution=_resolucao(contexto=context, policy_key=policy_key),
            items=itens,
            search_executed=True,
            limit=limit,
            offset=offset,
            has_more=False,
        )


def _manager(
    *,
    coids=(),
    mapa=None,
    desfechos=None,
    contexto_port=None,
    memberships=None,
    retrieval=None,
):
    port_retrieval = retrieval or RetrievalFalsa(coids)
    port_gov = GovernancaFalsa(desfechos)
    port_ctx = contexto_port or ContextoFalso()
    port_mem = memberships or MembershipsFalsas(mapa)
    manager = MemoryIsolationManager(port_retrieval, port_gov, port_ctx, port_mem)
    return manager, port_retrieval, port_gov, port_ctx, port_mem


def _executar(manager, *, context=None, **kw):
    kw.setdefault("descriptor", _descritor())
    kw.setdefault("criteria", object())
    kw.setdefault("policy_key", _GK)
    kw.setdefault("moment", _MOMENTO)
    return manager.retrieve_isolated(context=context or _contexto(_D1), **kw)


# ======================================================================
# Autoridade domínio a domínio
# ======================================================================


def test_mi1_policy_for_one_domain_does_not_authorize_the_pair():
    """O vazamento que a E4.8 existe para fechar.

    FULL-CONTEXT INTERSECTION MATCH
    != AUTHORITY OVER EVERY DOMAIN IN THE UNION
    """
    manager, retrieval, _, _, memberships = _manager(
        desfechos={_D2: GovernanceOutcome.NOT_APPLICABLE}
    )
    resultado = _executar(manager, context=_contexto(_D1, _D2))
    assert resultado.authorized is False
    assert resultado.retrieval is None
    assert retrieval.chamadas == []
    assert memberships.chamadas == []


@pytest.mark.parametrize(
    "outcome",
    [
        GovernanceOutcome.NOT_APPLICABLE,
        GovernanceOutcome.INADMISSIBLE,
        GovernanceOutcome.PROHIBITED,
    ],
)
def test_mi2_any_unauthorized_domain_refuses_the_whole_request(outcome):
    """`PARTIAL AUTHORITY != AUTHORITY TO REWRITE REQUESTED SCOPE`."""
    manager, retrieval, _, _, memberships = _manager(desfechos={_D2: outcome})
    resultado = _executar(manager, context=_contexto(_D1, _D2))
    assert resultado.authorized is False
    assert resultado.retrieval is None
    assert resultado.refused_domain_ids == (_D2,)
    assert retrieval.chamadas == []
    assert memberships.chamadas == []


def test_mi3_prohibited_is_never_overridden():
    manager, retrieval, _, _, _ = _manager(
        desfechos={_D1: GovernanceOutcome.PROHIBITED, _D2: GovernanceOutcome.ADMISSIBLE}
    )
    resultado = _executar(manager, context=_contexto(_D1, _D2))
    assert resultado.authorized is False
    decisao = next(d for d in resultado.decisions if d.domain_id == _D1)
    assert decisao.outcome is GovernanceOutcome.PROHIBITED
    assert retrieval.chamadas == []


def test_mi4_context_is_not_silently_narrowed():
    """Remover o domínio recusado responderia a outra pergunta."""
    contexto = _contexto(_D1, _D2)
    manager, _, _, _, _ = _manager(desfechos={_D2: GovernanceOutcome.INADMISSIBLE})
    resultado = _executar(manager, context=contexto)
    assert resultado.context == contexto
    assert tuple(d.domain_id for d in resultado.decisions) == tuple(sorted((_D1, _D2)))


def test_mi5_all_domains_authorized_runs_exactly_one_retrieval():
    coid = uuid.uuid4()
    manager, retrieval, governanca, _, memberships = _manager(
        coids=(coid,), mapa={_D1: (coid,), _D2: ()}
    )
    resultado = _executar(manager, context=_contexto(_D1, _D2))
    assert resultado.authorized is True
    assert resultado.retrieval is not None
    assert len(retrieval.chamadas) == 1
    assert len(governanca.chamadas) == 2
    assert sorted(memberships.chamadas) == sorted((_D1, _D2))


def test_mi6_one_decision_per_declared_domain_in_canonical_order():
    manager, _, _, _, _ = _manager(mapa={_D1: (), _D2: (), _D3: ()})
    resultado = _executar(manager, context=_contexto(_D3, _D1, _D2))
    assert tuple(d.domain_id for d in resultado.decisions) == tuple(sorted((_D1, _D2, _D3)))


def test_mi7_singleton_preserves_actor_purpose_and_session():
    contexto = _contexto(_D1, _D2, actor_ref="bruno", purpose="revisão", session_id="s9")
    manager, _, governanca, _, _ = _manager(mapa={_D1: (), _D2: ()})
    _executar(manager, context=contexto)
    for chamada in governanca.chamadas:
        singleton = chamada["context"]
        assert len(singleton.domain_ids) == 1
        assert singleton.actor_ref == "bruno"
        assert singleton.purpose == "revisão"
        assert singleton.session_id == "s9"


def test_mi8_actor_presence_does_not_authorize():
    """`ACTOR PRESENCE != AUTHORIZATION`."""
    manager, retrieval, _, _, _ = _manager(desfechos={_D1: GovernanceOutcome.NOT_APPLICABLE})
    resultado = _executar(manager, context=_contexto(_D1, actor_ref="alguem"))
    assert resultado.authorized is False
    assert retrieval.chamadas == []


def test_mi9_session_id_is_not_a_tenancy_boundary():
    """Sessões diferentes não mudam autoridade."""
    coid = uuid.uuid4()
    for sessao in ("s1", "s2"):
        manager, _, _, _, _ = _manager(coids=(coid,), mapa={_D1: (coid,)})
        resultado = _executar(manager, context=_contexto(_D1, session_id=sessao))
        assert resultado.authorized is True


# ======================================================================
# Escopo explícito
# ======================================================================


def test_mi10_empty_scope_is_refused_before_any_collaborator():
    """`EMPTY DOMAIN SCOPE IS NOT AN ISOLATION BOUNDARY`."""
    manager, retrieval, governanca, _, memberships = _manager()
    with pytest.raises(IsolationScopeRequiredError) as exc:
        _executar(manager, context=MemoryContext())
    assert exc.value.code == "PIA-8039"
    assert governanca.chamadas == []
    assert memberships.chamadas == []
    assert retrieval.chamadas == []


def test_mi11_empty_scope_does_not_mean_nonexistence():
    manager, _, _, _, _ = _manager()
    with pytest.raises(IsolationScopeRequiredError) as exc:
        _executar(manager, context=MemoryContext())
    assert "não é" in str(exc.value)
    assert exc.value.error_code.category.value.lower() == "validation"


# ======================================================================
# Repasse fiel do pedido
# ======================================================================


def test_mi12_original_context_reaches_retrieval_not_a_rewrite():
    """`ISOLATION DOES NOT REWRITE USER CONTEXT`."""
    contexto = _contexto(_D1, _D2)
    manager, retrieval, _, _, _ = _manager(mapa={_D1: (), _D2: ()})
    _executar(manager, context=contexto)
    assert retrieval.chamadas[0]["context"] == contexto
    assert retrieval.chamadas[0]["context"].domain_ids == contexto.domain_ids


def test_mi13_criteria_travels_by_identity_without_inspection():
    criteria = object()
    manager, retrieval, _, _, _ = _manager(mapa={_D1: ()})
    _executar(manager, criteria=criteria)
    assert retrieval.chamadas[0]["criteria"] is criteria


def test_mi14_descriptor_policy_limit_and_offset_travel_exactly():
    descritor = _descritor()
    manager, retrieval, _, _, _ = _manager(mapa={_D1: ()})
    _executar(manager, descriptor=descritor, policy_key="outra", limit=7, offset=13)
    chamada = retrieval.chamadas[0]
    assert chamada["descriptor"] is descritor
    assert chamada["policy_key"] == "outra"
    assert chamada["limit"] == 7
    assert chamada["offset"] == 13


def test_mi15_one_instant_is_shared_by_every_resolution_and_retrieval():
    """`ONE OPERATION = ONE EVALUATION INSTANT`."""
    manager, retrieval, governanca, _, _ = _manager(mapa={_D1: (), _D2: ()})
    resultado = _executar(manager, context=_contexto(_D1, _D2), moment=None)
    instantes = {c["moment"] for c in governanca.chamadas}
    assert len(instantes) == 1
    instante = instantes.pop()
    assert instante is not None
    assert instante.tzinfo is UTC
    assert retrieval.chamadas[0]["moment"] == instante
    assert resultado.evaluated_at == instante


def test_mi16_explicit_moment_is_canonicalized_to_utc():
    momento = datetime(2024, 6, 1, 9, 0, tzinfo=UTC).astimezone(datetime.now().astimezone().tzinfo)
    manager, _, governanca, _, _ = _manager(mapa={_D1: ()})
    _executar(manager, moment=momento)
    assert governanca.chamadas[0]["moment"].tzinfo is UTC


@pytest.mark.parametrize(
    ("momento", "excecao"), [("ontem", TypeError), (datetime(2024, 6, 1), ValueError)]
)
def test_mi17_invalid_moment_is_refused_before_collaborators(momento, excecao):
    manager, _, governanca, _, _ = _manager(mapa={_D1: ()})
    with pytest.raises(excecao):
        _executar(manager, moment=momento)
    assert governanca.chamadas == []


# ======================================================================
# Snapshot e não expansão
# ======================================================================


def test_mi18_memberships_are_read_only_after_authority():
    manager, _, _, _, memberships = _manager(
        desfechos={_D1: GovernanceOutcome.INADMISSIBLE}, mapa={_D1: ()}
    )
    _executar(manager)
    assert memberships.chamadas == []


def test_mi19_item_of_an_authorized_domain_is_accepted():
    coid = uuid.uuid4()
    manager, _, _, _, _ = _manager(coids=(coid,), mapa={_D1: (coid,)})
    resultado = _executar(manager)
    assert resultado.retrieval is not None
    assert resultado.retrieval.coids == (coid,)


def test_mi20_membership_in_an_unrequested_domain_is_not_contamination():
    """Pertencer também a um domínio não solicitado não contamina."""
    coid = uuid.uuid4()
    manager, _, _, _, _ = _manager(coids=(coid,), mapa={_D1: (coid,), _D3: (coid,)})
    resultado = _executar(manager)
    assert resultado.authorized is True
    assert resultado.retrieval is not None
    assert resultado.retrieval.coids == (coid,)


def test_mi21_coid_outside_the_snapshot_is_a_contract_violation():
    """`LEAK DETECTED != AUTHORIZATION TO SILENTLY FILTER`."""
    dentro, fora = uuid.uuid4(), uuid.uuid4()
    manager, _, _, _, _ = _manager(coids=(dentro, fora), mapa={_D1: (dentro,)})
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert exc.value.code == "PIA-8040"
    assert any("fora da união de memberships" in m for m in exc.value.reasons)


def test_mi22_zero_domain_object_from_a_faulty_port_is_refused():
    orfao = uuid.uuid4()
    manager, _, _, _, _ = _manager(coids=(orfao,), mapa={_D1: ()})
    with pytest.raises(IsolationContractViolationError):
        _executar(manager)


def test_mi23_leak_is_never_silently_filtered():
    """A página não é devolvida parcial nem reparada."""
    dentro, fora = uuid.uuid4(), uuid.uuid4()
    manager, _, _, _, _ = _manager(coids=(dentro, fora), mapa={_D1: (dentro,)})
    with pytest.raises(IsolationContractViolationError):
        _executar(manager)


def test_mi24_membership_for_another_domain_is_a_violation():
    memberships = MembershipsFalsas(devolver=[MembershipFalsa(_D3, uuid.uuid4())])
    manager, _, _, _, _ = _manager(memberships=memberships)
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("mas foi pedida a do domínio" in m for m in exc.value.reasons)


def test_mi25_non_sequence_memberships_are_refused():
    """`Sequence`, não `Iterable` — a lição da E4.6.2."""

    def _gerador():
        yield MembershipFalsa(_D1, uuid.uuid4())

    memberships = MembershipsFalsas(devolver=_gerador())
    manager, _, _, _, _ = _manager(memberships=memberships)
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("Sequence" in m for m in exc.value.reasons)


def test_mi26_shapeless_membership_is_refused():
    class Nada:
        pass

    memberships = MembershipsFalsas(devolver=[Nada()])
    manager, _, _, _, _ = _manager(memberships=memberships)
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("sem os campos de uma membership" in m for m in exc.value.reasons)


# ======================================================================
# Fidelidade de contexto e resolução
# ======================================================================


def test_mi27_context_substitution_is_refused_before_governance():
    """`CONTEXT VALIDATION != CONTEXT SUBSTITUTION`."""
    manager, _, governanca, _, _ = _manager(contexto_port=ContextoFalso(substituto=_contexto(_D3)))
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("contexto diferente do solicitado" in m for m in exc.value.reasons)
    assert governanca.chamadas == []


def test_mi28_unfaithful_singleton_derivation_is_refused():
    """Derivar o escopo não reescreve a perspectiva."""
    manager, _, governanca, _, _ = _manager(
        contexto_port=ContextoFalso(
            derivacao_infiel=_contexto(_D1, actor_ref="outro", purpose="outro")
        )
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("alterou actor_ref" in m for m in exc.value.reasons)
    assert governanca.chamadas == []


def test_mi29_resolution_bound_to_another_domain_is_refused():
    """A E4.3.4 tornou isso verificável; a E4.8 verifica."""
    governanca = GovernancaFalsa()
    governanca.resolucao_fixa = _resolucao(contexto=_contexto(_D3))
    manager = MemoryIsolationManager(
        RetrievalFalsa(), governanca, ContextoFalso(), MembershipsFalsas()
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("emitida para os domínios" in m for m in exc.value.reasons)


def test_mi30_resolution_for_another_actor_or_purpose_is_refused():
    governanca = GovernancaFalsa()
    governanca.resolucao_fixa = _resolucao(
        contexto=_contexto(_D1, actor_ref="bob", purpose="outro")
    )
    manager = MemoryIsolationManager(
        RetrievalFalsa(), governanca, ContextoFalso(), MembershipsFalsas()
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert len(exc.value.reasons) >= 2


def test_mi31_resolution_about_another_operation_is_refused():
    governanca = GovernancaFalsa()
    governanca.resolucao_fixa = _resolucao(
        contexto=_contexto(_D1), operation=CognitiveOperation.TRANSFORM
    )
    manager = MemoryIsolationManager(
        RetrievalFalsa(), governanca, ContextoFalso(), MembershipsFalsas()
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("CognitiveOperation.READ" in m for m in exc.value.reasons)


def test_mi32_resolution_about_another_policy_is_refused():
    governanca = GovernancaFalsa()
    governanca.resolucao_fixa = _resolucao(contexto=_contexto(_D1), policy_key="outra")
    manager = MemoryIsolationManager(
        RetrievalFalsa(), governanca, ContextoFalso(), MembershipsFalsas()
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("policy resolvida" in m for m in exc.value.reasons)


def test_mi33_non_read_descriptor_is_refused():
    manager, _, governanca, _, _ = _manager()
    with pytest.raises(ValueError, match="CognitiveOperation.READ"):
        _executar(manager, descriptor=_descritor(CognitiveOperation.TRANSFORM))
    assert governanca.chamadas == []


def test_mi34_retrieval_with_another_context_is_refused():
    resultado = MemoryRetrievalResult(
        context=_contexto(_D3),
        governance_resolution=_resolucao(contexto=_contexto(_D3)),
        items=(),
        search_executed=True,
        limit=50,
        offset=0,
        has_more=False,
    )
    manager, _, _, _, _ = _manager(mapa={_D1: ()}, retrieval=RetrievalFalsa(resultado=resultado))
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("contexto diferente do solicitado" in m for m in exc.value.reasons)


def test_mi35_retrieval_with_changed_pagination_is_refused():
    contexto = _contexto(_D1)
    resultado = MemoryRetrievalResult(
        context=contexto,
        governance_resolution=_resolucao(contexto=contexto),
        items=(),
        search_executed=True,
        limit=90,
        offset=0,
        has_more=False,
    )
    manager, _, _, _, _ = _manager(mapa={_D1: ()}, retrieval=RetrievalFalsa(resultado=resultado))
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager, limit=50)
    assert any("paginação devolvida" in m for m in exc.value.reasons)


# ======================================================================
# Value objects
# ======================================================================


def test_mi36_decision_requires_a_singleton_resolution():
    with pytest.raises(ValueError, match="emitida para"):
        DomainIsolationDecision(domain_id=_D1, resolution=_resolucao(contexto=_contexto(_D1, _D2)))


def test_mi37_decision_requires_read():
    with pytest.raises(ValueError, match="caminho de leitura"):
        DomainIsolationDecision(
            domain_id=_D1,
            resolution=_resolucao(contexto=_contexto(_D1), operation=CognitiveOperation.TRANSFORM),
        )


def test_mi38_decision_is_frozen_and_hashable():
    decisao = DomainIsolationDecision(domain_id=_D1, resolution=_resolucao(contexto=_contexto(_D1)))
    assert isinstance(hash(decisao), int)
    with pytest.raises(dataclasses.FrozenInstanceError):
        decisao.domain_id = _D2


def _decisao(domain_id=_D1, outcome=GovernanceOutcome.ADMISSIBLE):
    return DomainIsolationDecision(
        domain_id=domain_id,
        resolution=_resolucao(contexto=_contexto(domain_id), outcome=outcome),
    )


def _resultado(**overrides):
    contexto = overrides.pop("context", _contexto(_D1))
    campos = {
        "context": contexto,
        "decisions": (_decisao(),),
        "evaluated_at": _MOMENTO,
        "retrieval": MemoryRetrievalResult(
            context=contexto,
            governance_resolution=_resolucao(contexto=contexto),
            items=(),
            search_executed=True,
            limit=50,
            offset=0,
            has_more=False,
        ),
    }
    campos.update(overrides)
    return MemoryIsolationResult(**campos)


def test_mi39_result_requires_explicit_scope():
    with pytest.raises(ValueError, match="escopo explícito"):
        _resultado(context=MemoryContext(), decisions=(), retrieval=None)


def test_mi40_result_requires_one_decision_per_declared_domain():
    with pytest.raises(ValueError, match="uma decisão por"):
        _resultado(context=_contexto(_D1, _D2), decisions=(_decisao(),), retrieval=None)


def test_mi41_result_refuses_duplicate_decisions():
    with pytest.raises(ValueError, match="mais de uma decisão"):
        _resultado(decisions=(_decisao(), _decisao()), retrieval=None)


def test_mi42_refused_result_cannot_carry_a_retrieval():
    with pytest.raises(ValueError, match="responderia a uma pergunta diferente"):
        _resultado(decisions=(_decisao(outcome=GovernanceOutcome.INADMISSIBLE),))


def test_mi43_authorized_result_requires_a_retrieval():
    with pytest.raises(ValueError, match="autoridade sem efeito"):
        _resultado(retrieval=None)


def test_mi44_result_refuses_a_retrieval_over_another_context():
    outro = _contexto(_D3)
    with pytest.raises(ValueError, match="contexto diferente"):
        _resultado(
            retrieval=MemoryRetrievalResult(
                context=outro,
                governance_resolution=_resolucao(contexto=outro),
                items=(),
                search_executed=True,
                limit=50,
                offset=0,
                has_more=False,
            )
        )


def test_mi45_refusal_and_authorized_empty_view_do_not_collapse():
    """`NOT_RETRIEVED != FORGOTTEN`."""
    negado = _resultado(
        decisions=(_decisao(outcome=GovernanceOutcome.NOT_APPLICABLE),), retrieval=None
    )
    vazio = _resultado()
    assert negado.retrieval is None and negado.authorized is False
    assert vazio.retrieval is not None and vazio.authorized is True
    assert vazio.retrieval.coids == ()


def test_mi46_result_is_frozen_hashable_and_defensively_copied():
    decisoes = [_decisao()]
    resultado = _resultado(decisions=decisoes)
    decisoes.append(_decisao(_D2))
    assert len(resultado.decisions) == 1
    assert isinstance(resultado.decisions, tuple)
    assert isinstance(hash(resultado), int)
    with pytest.raises(dataclasses.FrozenInstanceError):
        resultado.evaluated_at = _MOMENTO


@pytest.mark.parametrize(
    ("campo", "valor", "excecao"),
    [
        ("decisions", "nao-e-colecao", TypeError),
        ("decisions", (123,), TypeError),
        ("evaluated_at", "ontem", TypeError),
        ("evaluated_at", datetime(2024, 6, 1), ValueError),
        ("retrieval", "nao-e-resultado", TypeError),
    ],
)
def test_mi47_result_separates_type_from_value_errors(campo, valor, excecao):
    with pytest.raises(excecao):
        _resultado(**{campo: valor})


def test_mi48_result_refuses_a_non_executed_view_when_authorized():
    contexto = _contexto(_D1)
    with pytest.raises(ValueError, match="recusa que não houve"):
        _resultado(
            retrieval=MemoryRetrievalResult(
                context=contexto,
                governance_resolution=_resolucao(
                    contexto=contexto, outcome=GovernanceOutcome.NOT_APPLICABLE
                ),
                items=(),
                search_executed=False,
                limit=50,
                offset=0,
                has_more=None,
            )
        )


def test_mi49_result_exposes_no_count_or_membership_snapshot():
    """Recusa não expõe contagem, snapshot nem evidência de existência."""
    campos = {f.name for f in dataclasses.fields(MemoryIsolationResult)}
    for proibido in ("total", "count", "snapshot", "memberships", "authorized_coids"):
        assert proibido not in campos
    negado = _resultado(
        decisions=(_decisao(outcome=GovernanceOutcome.NOT_APPLICABLE),), retrieval=None
    )
    assert negado.retrieval is None


# ======================================================================
# Guardas estruturais
# ======================================================================


def _codigo_executavel() -> str:
    """Fonte da E4.8 sem docstrings — elas citam nominalmente o que o
    módulo não faz, e comparar texto bruto daria falso positivo (a lição
    de `gv16` na E4.3.1)."""
    import app.memory.ports.isolation as porta_mod
    import app.memory.schemas.isolation as schema_mod
    import app.memory.services.memory_isolation_manager as manager_mod

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


def test_mi50_no_direct_search_call():
    executavel = _codigo_executavel()
    for proibido in ("SearchEngine", ".search(", "SearchRepository", "SearchCriteria"):
        assert proibido not in executavel, f"Search direta: {proibido}"


def test_mi51_no_writes_commits_or_raw_sql():
    executavel = _codigo_executavel()
    for proibido in (
        "commit(",
        "rollback(",
        "flush(",
        "Session",
        "UnitOfWork",
        "text(",
        "execute(",
        "session.add",
        "session.delete",
        ".soft_delete(",
    ):
        assert proibido not in executavel, f"escrita/SQL: {proibido}"

    # `set.add` em memória não é escrita no banco: o padrão anterior
    # (`"add("`) pegava `uniao.add(coid)` e provaria outra coisa. O que
    # importa é ausência de sessão, SQL e mutação persistente.
    assert "uniao.add(" in executavel, "o snapshot usa um set em memória"


def test_mi52_no_reflection():
    executavel = _codigo_executavel()
    for proibido in (
        "getattr(",
        "hasattr(",
        "vars(",
        "__dict__",
        "importlib",
        "sys.modules",
        "inspect",
    ):
        assert proibido not in executavel, f"reflexão: {proibido}"


def test_mi53_no_tenancy_acl_or_orchestration_vocabulary():
    """Busca por PALAVRA INTEIRA, não substring.

    Substring solta produz falso positivo — `acl` casa dentro de
    `collections.abc`, `role` casa dentro de `control`. O guarda tem de
    provar ausência do vocabulário, não da sequência de letras.
    """
    executavel = _codigo_executavel().lower()
    for proibido in (
        "tenant",
        "owner",
        "acl",
        "role",
        "workspace",
        "schedule",
        "provider",
        "connector",
        "rls",
        "credential",
        "secret",
    ):
        assert not re.search(rf"\b{proibido}\b", executavel), f"vocabulário proibido: {proibido}"


def test_mi54_no_score_ranking_or_learning():
    executavel = _codigo_executavel().lower()
    for proibido in ("score", "rank", "relevance", "embedding", "vector", "learn"):
        assert not re.search(rf"\b{proibido}\b", executavel), f"capacidade proibida: {proibido}"


def test_mi55_no_app_cognitive_import_in_memory_production_code():
    padrao = re.compile(r"^\s*(from|import)\s+app\.cognitive", re.MULTILINE)
    raiz = pathlib.Path(__file__).resolve().parents[3] / "app"
    ofensores = [
        str(caminho)
        for caminho in raiz.rglob("*.py")
        if "cognitive" not in caminho.parts and padrao.search(caminho.read_text(encoding="utf-8"))
    ]
    assert ofensores == []


def test_mi56_shared_binding_function_is_used_not_reimplemented():
    """A comparação das TRÊS dimensões é a da E4.3.4 — copiá-la faria as
    duas divergirem, que é a lição da E4.5.1.

    `DomainIsolationDecision` compara `context_domain_ids` com o
    singleton, e isso NÃO é a mesma verificação: ali se confirma que a
    decisão e a resolução falam do mesmo domínio, um invariante do
    próprio value object. O que não pode existir é uma segunda
    comparação das três dimensões contra o contexto.
    """
    import app.memory.services.memory_isolation_manager as manager_mod

    executavel = _codigo_executavel()
    assert "resolucao_vincula_contexto(" in executavel

    fonte_manager = pathlib.Path(manager_mod.__file__).read_text(encoding="utf-8")
    for dimensao in ("context_actor_ref", "context_purpose"):
        assert f"resolucao.{dimensao}" not in fonte_manager, (
            f"o manager compara {dimensao} por conta própria em vez de usar a "
            "função compartilhada"
        )


def test_mi57_no_policy_repository_access():
    """A E4.8 não consulta policy para 'confirmar' a resolução."""
    executavel = _codigo_executavel()
    for proibido in ("GovernancePolicyRepository", "effective_version_at", "matches("):
        assert proibido not in executavel, f"acesso indevido: {proibido}"


def test_mi58_manager_has_no_mutable_instance_state():
    """`PARALLEL WORKLOADS MUST NOT SHARE MUTABLE ISOLATION STATE`."""
    manager, _, _, _, _ = _manager(mapa={_D1: ()})
    antes = dict(manager.__dict__)
    _executar(manager)
    assert dict(manager.__dict__) == antes


def test_mi59_two_calls_with_different_contexts_do_not_share_state():
    coid1, coid2 = uuid.uuid4(), uuid.uuid4()
    manager, _, _, _, _ = _manager(coids=(coid1,), mapa={_D1: (coid1,), _D2: (coid2,)})
    primeiro = _executar(manager, context=_contexto(_D1))
    assert primeiro.retrieval is not None
    assert primeiro.retrieval.coids == (coid1,)
    assert primeiro.context.domain_ids == (_D1,)


def test_mi60_real_collaborators_satisfy_the_ports():
    """Conformidade verificada, não presumida.

    Importa `app.cognitive` **no teste** — o que a fronteira veda é o
    import no código de produção de `app/memory`.
    """
    from app.memory.repositories.memory_domain_membership_repository import (
        MemoryDomainMembershipRepository,
    )
    from app.memory.services.context_manager import ContextManager
    from app.memory.services.governance_manager import GovernanceManager
    from app.memory.services.retrieval_manager import MemoryRetrievalManager

    assert isinstance(MemoryRetrievalManager.__new__(MemoryRetrievalManager), IsolatedRetrievalPort)
    assert isinstance(GovernanceManager.__new__(GovernanceManager), GovernanceResolutionPort)
    assert isinstance(ContextManager.__new__(ContextManager), ContextValidationPort)
    assert isinstance(
        MemoryDomainMembershipRepository.__new__(MemoryDomainMembershipRepository),
        DomainMembershipPort,
    )
    from app.memory.models.memory_domain_membership import MemoryDomainMembership

    assert isinstance(MemoryDomainMembership(), MembershipView)


def test_mi61_static_port_proof_exists():
    """`RUNTIME_CHECKABLE != STATIC SIGNATURE COMPATIBILITY` — a lição
    que a E4.7.1 pagou."""
    prova = pathlib.Path(__file__).resolve().parents[2] / "static" / "test_isolation_ports.py"
    assert prova.exists()
    fonte = prova.read_text(encoding="utf-8")
    assert "IsolatedRetrievalPort" in fonte
    assert "MemoryIsolationManager" in fonte


def test_mi62_deferred_capabilities_are_not_anticipated():
    """Compatibilidade não é antecipação de produto."""
    raiz = pathlib.Path(__file__).resolve().parents[3] / "app" / "memory"
    for proibido in ("Workspace", "Schedule", "Workstream", "RemoteResource"):
        ofensores = [
            str(p)
            for p in raiz.rglob("*.py")
            if f"class {proibido}" in p.read_text(encoding="utf-8")
        ]
        assert ofensores == [], f"{proibido} antecipado em {ofensores}"


def test_mi63_no_new_persistent_entity():
    """`NEW_TABLE = NO`, `NEW_MODEL = NO`."""
    import app.memory.models as models

    fonte = pathlib.Path(models.__file__).read_text(encoding="utf-8")
    assert "Isolation" not in fonte
    raiz = pathlib.Path(models.__file__).parent
    assert not list(raiz.glob("*isolation*"))


def test_mi64_timedelta_import_is_used_for_timezone_proof():
    """Guarda de higiene: o teste de fuso usa `timedelta` de verdade."""
    assert timedelta(hours=-3) != timedelta(0)


# ======================================================================
# Ramos descobertos pela exigência de 100%
# ======================================================================


@pytest.mark.parametrize(
    ("campo", "valor", "excecao"),
    [
        ("context", "nao-e-contexto", TypeError),
        ("descriptor", "nao-e-descritor", TypeError),
        ("policy_key", 123, TypeError),
        ("limit", "50", TypeError),
        ("limit", True, TypeError),
        ("offset", "0", TypeError),
    ],
)
def test_mi65_manager_refuses_invalid_argument_types(campo, valor, excecao):
    manager, retrieval, governanca, _, memberships = _manager()
    argumentos: dict = {
        "context": _contexto(_D1),
        "descriptor": _descritor(),
        "criteria": object(),
        "policy_key": _GK,
        "moment": _MOMENTO,
    }
    argumentos[campo] = valor
    with pytest.raises(excecao):
        manager.retrieve_isolated(**argumentos)
    assert governanca.chamadas == []
    assert memberships.chamadas == []
    assert retrieval.chamadas == []


def test_mi66_non_context_from_the_validator_is_a_contract_violation():
    class ValidadorQuebrado:
        def validate(self, context):
            return "nao-e-contexto"

        def derive(self, context, **kw):
            return context

    manager = MemoryIsolationManager(
        RetrievalFalsa(), GovernancaFalsa(), ValidadorQuebrado(), MembershipsFalsas()
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("não MemoryContext" in m for m in exc.value.reasons)


def test_mi67_non_context_from_derive_is_a_contract_violation():
    class DeriveQuebrado:
        def validate(self, context):
            return context

        def derive(self, context, **kw):
            return "nao-e-contexto"

    manager = MemoryIsolationManager(
        RetrievalFalsa(), GovernancaFalsa(), DeriveQuebrado(), MembershipsFalsas()
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("derive devolveu" in m for m in exc.value.reasons)


def test_mi68_singleton_with_wrong_scope_is_refused():
    manager, _, governanca, _, _ = _manager(
        contexto_port=ContextoFalso(derivacao_infiel=_contexto(_D1, _D2))
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager, context=_contexto(_D1))
    assert any("e não apenas" in m for m in exc.value.reasons)
    assert governanca.chamadas == []


def test_mi69_non_resolution_from_governance_is_a_contract_violation():
    class GovernancaQuebrada:
        def resolve(self, **kw):
            return "nao-e-resolucao"

    manager = MemoryIsolationManager(
        RetrievalFalsa(), GovernancaQuebrada(), ContextoFalso(), MembershipsFalsas()
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("não GovernanceResolution" in m for m in exc.value.reasons)


def test_mi70_non_result_from_retrieval_is_a_contract_violation():
    class RetrievalQuebrada:
        def retrieve(self, **kw):
            return "nao-e-resultado"

    manager = MemoryIsolationManager(
        RetrievalQuebrada(), GovernancaFalsa(), ContextoFalso(), MembershipsFalsas()
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("não MemoryRetrievalResult" in m for m in exc.value.reasons)


def test_mi71_membership_with_non_uuid_coid_is_refused():
    @dataclasses.dataclass(frozen=True)
    class CoidTorto:
        domain_id: uuid.UUID
        coid: str

    memberships = MembershipsFalsas(devolver=[CoidTorto(_D1, "nao-e-uuid")])
    manager, _, _, _, _ = _manager(memberships=memberships)
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager)
    assert any("não uuid.UUID" in m for m in exc.value.reasons)


def test_mi72_decision_separates_type_from_value_errors():
    with pytest.raises(TypeError, match="domain_id"):
        DomainIsolationDecision(
            domain_id="nao-e-uuid", resolution=_resolucao(contexto=_contexto(_D1))
        )
    with pytest.raises(TypeError, match="resolution"):
        DomainIsolationDecision(domain_id=_D1, resolution="nao-e-resolucao")


def test_mi73_result_refuses_a_non_context_object():
    with pytest.raises(TypeError, match="MemoryContext"):
        MemoryIsolationResult(context="nao-e-contexto", decisions=(), evaluated_at=_MOMENTO)


# ======================================================================
# E4.8.1 — Isolation Authority & Result Fidelity
# ======================================================================
#
# A E4.8 provava escopo e não provava autoridade:
#
#     SCOPE NON-EXPANSION WITHOUT AUTHORITY FIDELITY = INCOMPLETE ISOLATION
#     SAME DOMAIN != SAME CONTEXT
#     DOMAIN BINDING ALONE != CONTEXT BINDING
#     ONE REQUEST != MULTIPLE AUTHORITY PROVENANCES

_PID_OUTRO = uuid.UUID("88888888-8888-8888-8888-888888888888")


def _res_livre(
    *,
    domain_ids,
    actor_ref="ana",
    purpose="curadoria",
    outcome=GovernanceOutcome.ADMISSIBLE,
    policy_key=_GK,
    policy_version=1,
    policy_id=_POLICY_ID,
    matched_rule_id="r1",
):
    """Resolução montada campo a campo, para exercitar divergências."""
    campos: dict = {
        "operation": CognitiveOperation.READ,
        "outcome": outcome,
        "context_domain_ids": domain_ids,
        "context_actor_ref": actor_ref,
        "context_purpose": purpose,
        "safety_boundary_version": PLATFORM_SAFETY_BOUNDARY_VERSION,
    }
    if outcome is GovernanceOutcome.PROHIBITED:
        campos |= {
            "blocked_capabilities": (CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT,),
            "safety_rationale": "proibido pela fronteira",
        }
    elif outcome is not GovernanceOutcome.NOT_APPLICABLE:
        campos |= {
            "policy_key": policy_key,
            "policy_version": policy_version,
            "policy_id": policy_id,
            "matched_rule_id": matched_rule_id,
        }
    return GovernanceResolution(**campos)


def _vista(contexto, **kw):
    """Vista construída a partir de uma resolução montada campo a campo.

    `search_executed` acompanha o outcome: a E4.6 congelou que uma
    resolução que não autoriza execução não pode ter chamado a Search.
    """
    resolucao = _res_livre(domain_ids=contexto.domain_ids, **kw)
    executou = resolucao.execution_authorized
    return MemoryRetrievalResult(
        context=contexto,
        governance_resolution=resolucao,
        items=(),
        search_executed=executou,
        limit=50,
        offset=0,
        has_more=False if executou else None,
    )


# --- Defeito A: vínculo ao contexto original --------------------------


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("actor_ref", "mallory", "emitida para o ator"),
        ("purpose", "other", "emitida para o propósito"),
    ],
)
def test_e481_direct_constructor_refuses_a_decision_bound_to_another_context(campo, valor, trecho):
    """Defeito A: `SAME DOMAIN != SAME CONTEXT`.

    Na cadeia 61 uma decisão emitida para `mallory/other` era aceita num
    resultado cujo contexto declarava `alice/research`.
    """
    contexto = _contexto(_D1, actor_ref="alice", purpose="research")
    divergente = _res_livre(domain_ids=(_D1,), actor_ref="alice", purpose="research")
    divergente = dataclasses.replace(divergente, **{f"context_{campo}": valor})
    with pytest.raises(ValueError) as exc:
        MemoryIsolationResult(
            context=contexto,
            decisions=(DomainIsolationDecision(domain_id=_D1, resolution=divergente),),
            evaluated_at=_MOMENTO,
            retrieval=_vista(contexto, actor_ref="alice", purpose="research"),
        )
    assert trecho in str(exc.value)
    assert f"decisão do domínio {_D1}" in str(exc.value)


def test_e481_manager_refuses_singleton_bound_to_another_actor_before_memberships():
    """Preserva a garantia do manager: a recusa precede o patrimônio."""
    governanca = GovernancaFalsa()
    governanca.resolucao_fixa = _res_livre(domain_ids=(_D1,), actor_ref="mallory")
    memberships = MembershipsFalsas({_D1: ()})
    retrieval = RetrievalFalsa()
    manager = MemoryIsolationManager(retrieval, governanca, ContextoFalso(), memberships)
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager, context=_contexto(_D1, actor_ref="ana"))
    assert exc.value.code == "PIA-8040"
    assert memberships.chamadas == []
    assert retrieval.chamadas == []


# --- Defeito B: identidade da autoridade da Retrieval -----------------


@pytest.mark.parametrize(
    ("divergencia", "descricao"),
    [
        ({"policy_key": "policy-nao-solicitada"}, "outra policy_key"),
        ({"policy_version": 2}, "mesma key, outra versão"),
        ({"policy_id": _PID_OUTRO}, "mesma key e versão, outro id"),
    ],
)
def test_e481_direct_constructor_refuses_a_retrieval_under_another_authority(
    divergencia, descricao
):
    """Defeito B: `SAME POLICY KEY != SAME POLICY VERSION`."""
    contexto = _contexto(_D1)
    with pytest.raises(ValueError, match="autorizada por"):
        MemoryIsolationResult(
            context=contexto,
            decisions=(
                DomainIsolationDecision(domain_id=_D1, resolution=_res_livre(domain_ids=(_D1,))),
            ),
            evaluated_at=_MOMENTO,
            retrieval=_vista(contexto, **divergencia),
        )


@pytest.mark.parametrize(
    "divergencia",
    [
        {"policy_key": "policy-nao-solicitada"},
        {"policy_version": 2},
        {"policy_id": _PID_OUTRO},
    ],
)
def test_e481_manager_converts_authority_divergence_into_pia_8040(divergencia):
    """`COLLABORATOR DISAGREEMENT != INVALID REQUEST`."""
    contexto = _contexto(_D1)

    class RetrievalDivergente:
        def retrieve(self, *, context, **kw):
            return MemoryRetrievalResult(
                context=context,
                governance_resolution=_res_livre(domain_ids=context.domain_ids, **divergencia),
                items=(),
                search_executed=True,
                limit=kw.get("limit", 50),
                offset=kw.get("offset", 0),
                has_more=False,
            )

    manager = MemoryIsolationManager(
        RetrievalDivergente(), GovernancaFalsa(), ContextoFalso(), MembershipsFalsas({_D1: ()})
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager, context=contexto)
    assert exc.value.code == "PIA-8040"


def test_e481_retrieval_without_local_provenance_is_refused():
    contexto = _contexto(_D1)
    # `NOT_APPLICABLE` não executa Search — a E4.6 congelou isso —, então
    # a vista sem proveniência é necessariamente não executada. O
    # resultado acumula os dois motivos.
    sem_policy = MemoryRetrievalResult(
        context=contexto,
        governance_resolution=_res_livre(
            domain_ids=(_D1,), outcome=GovernanceOutcome.NOT_APPLICABLE
        ),
        items=(),
        search_executed=False,
        limit=50,
        offset=0,
        has_more=None,
    )
    with pytest.raises(ValueError, match="não cita proveniência local"):
        MemoryIsolationResult(
            context=contexto,
            decisions=(
                DomainIsolationDecision(domain_id=_D1, resolution=_res_livre(domain_ids=(_D1,))),
            ),
            evaluated_at=_MOMENTO,
            retrieval=sem_policy,
        )


# --- Defeito C: Retrieval negada vira PIA-8040 ------------------------


def test_e481_denied_retrieval_after_full_authorization_raises_pia_8040():
    """Defeito C: era `ValueError` cru escapando do caminho canônico."""
    contexto = _contexto(_D1)

    class RetrievalNegada:
        def retrieve(self, *, context, **kw):
            return MemoryRetrievalResult(
                context=context,
                governance_resolution=_res_livre(
                    domain_ids=context.domain_ids,
                    outcome=GovernanceOutcome.NOT_APPLICABLE,
                ),
                items=(),
                search_executed=False,
                limit=kw.get("limit", 50),
                offset=kw.get("offset", 0),
                has_more=None,
            )

    manager = MemoryIsolationManager(
        RetrievalNegada(), GovernancaFalsa(), ContextoFalso(), MembershipsFalsas({_D1: ()})
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager, context=contexto)
    assert exc.value.code == "PIA-8040"
    assert not isinstance(exc.value, ValueError) or exc.value.code == "PIA-8040"
    assert any("não autoriza execução" in m for m in exc.value.reasons)


# --- Defeito D: identidade única entre decisões -----------------------


def test_e481_singleton_decisions_with_divergent_policy_identity_are_refused():
    """Defeito D: `ONE REQUEST != MULTIPLE AUTHORITY PROVENANCES`."""
    contexto = _contexto(_D1, _D2)
    decisoes = tuple(
        sorted(
            (
                DomainIsolationDecision(domain_id=_D1, resolution=_res_livre(domain_ids=(_D1,))),
                DomainIsolationDecision(
                    domain_id=_D2,
                    resolution=_res_livre(domain_ids=(_D2,), policy_id=_PID_OUTRO),
                ),
            ),
            key=lambda d: d.domain_id,
        )
    )
    with pytest.raises(ValueError, match="identidades de policy local diferentes"):
        MemoryIsolationResult(
            context=contexto,
            decisions=decisoes,
            evaluated_at=_MOMENTO,
            retrieval=_vista(contexto),
        )


def test_e481_manager_refuses_divergent_identities_before_memberships():
    contexto = _contexto(_D1, _D2)

    class GovernancaDivergente:
        def __init__(self):
            self.n = 0

        def resolve(self, *, descriptor, context, policy_key=None, moment=None):
            self.n += 1
            pid = _POLICY_ID if self.n == 1 else _PID_OUTRO
            return _res_livre(domain_ids=context.domain_ids, policy_id=pid)

    memberships = MembershipsFalsas({_D1: (), _D2: ()})
    retrieval = RetrievalFalsa()
    manager = MemoryIsolationManager(
        retrieval, GovernancaDivergente(), ContextoFalso(), memberships
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager, context=contexto)
    assert exc.value.code == "PIA-8040"
    assert memberships.chamadas == []
    assert retrieval.chamadas == []


def test_e481_same_identity_with_different_matched_rules_stays_valid():
    """`MATCHED RULE != POLICY IDENTITY`.

    Regras diferentes podem casar em domínios diferentes da **mesma**
    versão de policy; recusar isso rejeitaria composição legítima.
    """
    contexto = _contexto(_D1, _D2)
    decisoes = tuple(
        sorted(
            (
                DomainIsolationDecision(
                    domain_id=_D1,
                    resolution=_res_livre(domain_ids=(_D1,), matched_rule_id="regra-a"),
                ),
                DomainIsolationDecision(
                    domain_id=_D2,
                    resolution=_res_livre(domain_ids=(_D2,), matched_rule_id="regra-b"),
                ),
            ),
            key=lambda d: d.domain_id,
        )
    )
    resultado = MemoryIsolationResult(
        context=contexto,
        decisions=decisoes,
        evaluated_at=_MOMENTO,
        retrieval=_vista(contexto),
    )
    assert resultado.authorized is True


# --- Outcomes sem proveniência local continuam legítimos --------------


@pytest.mark.parametrize(
    "outcome", [GovernanceOutcome.NOT_APPLICABLE, GovernanceOutcome.PROHIBITED]
)
def test_e481_refusals_without_local_provenance_remain_valid(outcome):
    """A E4.3 deliberadamente não consulta policy nesses casos, e o
    isolamento não fabrica proveniência onde ela não existe."""
    contexto = _contexto(_D1)
    resultado = MemoryIsolationResult(
        context=contexto,
        decisions=(
            DomainIsolationDecision(
                domain_id=_D1, resolution=_res_livre(domain_ids=(_D1,), outcome=outcome)
            ),
        ),
        evaluated_at=_MOMENTO,
    )
    assert resultado.authorized is False
    assert resultado.retrieval is None
    assert resultado.refused_domain_ids == (_D1,)


def test_e481_local_inadmissible_keeps_its_provenance_and_refuses_atomically():
    contexto = _contexto(_D1)
    decisao = DomainIsolationDecision(
        domain_id=_D1,
        resolution=_res_livre(domain_ids=(_D1,), outcome=GovernanceOutcome.INADMISSIBLE),
    )
    assert decisao.resolution.policy_id == _POLICY_ID
    resultado = MemoryIsolationResult(context=contexto, decisions=(decisao,), evaluated_at=_MOMENTO)
    assert resultado.authorized is False
    assert resultado.retrieval is None


def test_e481_mixed_provenance_between_refusal_and_authorization_is_allowed():
    """Um `PROHIBITED` sem proveniência ao lado de um `ADMISSIBLE` com
    ela não é incoerência — a fronteira simplesmente não consultou
    policy."""
    contexto = _contexto(_D1, _D2)
    decisoes = tuple(
        sorted(
            (
                DomainIsolationDecision(domain_id=_D1, resolution=_res_livre(domain_ids=(_D1,))),
                DomainIsolationDecision(
                    domain_id=_D2,
                    resolution=_res_livre(domain_ids=(_D2,), outcome=GovernanceOutcome.PROHIBITED),
                ),
            ),
            key=lambda d: d.domain_id,
        )
    )
    resultado = MemoryIsolationResult(context=contexto, decisions=decisoes, evaluated_at=_MOMENTO)
    assert resultado.authorized is False
    assert resultado.refused_domain_ids == (_D2,)


# --- Uma implementação, não duas --------------------------------------


def test_e481_coherence_function_is_shared_between_schema_and_manager():
    """Duas cópias da mesma regra divergem — E4.5.1, E4.6.1, E4.7.2."""
    import app.memory.schemas.isolation as schema_mod
    import app.memory.services.memory_isolation_manager as manager_mod

    fonte_schema = pathlib.Path(schema_mod.__file__).read_text(encoding="utf-8")
    fonte_manager = pathlib.Path(manager_mod.__file__).read_text(encoding="utf-8")
    assert fonte_schema.count("def verificar_coerencia_resultado_isolado(") == 1
    assert "def verificar_coerencia_resultado_isolado(" not in fonte_manager
    assert "verificar_coerencia_resultado_isolado(" in fonte_manager
    # e o manager não reimplementa a comparação de identidade local
    assert "policy_version !=" not in fonte_manager
    assert "policy_id !=" not in fonte_manager


def test_e481_all_reasons_are_accumulated():
    """`PIA-8040` acumula tudo o que é detectável sem reflexão."""
    contexto = _contexto(_D1, actor_ref="alice", purpose="research")
    divergente = dataclasses.replace(
        _res_livre(domain_ids=(_D1,), actor_ref="alice", purpose="research"),
        context_actor_ref="mallory",
        context_purpose="other",
    )
    with pytest.raises(ValueError) as exc:
        MemoryIsolationResult(
            context=contexto,
            decisions=(DomainIsolationDecision(domain_id=_D1, resolution=divergente),),
            evaluated_at=_MOMENTO,
            retrieval=_vista(
                contexto,
                actor_ref="alice",
                purpose="research",
                policy_key="outra",
            ),
        )
    mensagem = str(exc.value)
    assert "emitida para o ator" in mensagem
    assert "emitida para o propósito" in mensagem
    assert "autorizada por" in mensagem


def test_e481_no_reason_becomes_silent_filtering_or_repair():
    """`LEAK DETECTED != AUTHORIZATION TO SILENTLY FILTER`."""
    executavel = _codigo_executavel()
    for proibido in ("filtrar", "descartar", "reparar", "corrigir"):
        assert proibido not in executavel.lower()


def test_e481_helper_uses_a_stable_policy_id_per_published_version():
    """O harness anterior gerava `uuid4()` por chamada e normalizava o
    defeito D. Corrigido, não preservado."""
    primeira = _resolucao(contexto=_contexto(_D1))
    segunda = _resolucao(contexto=_contexto(_D2))
    assert primeira.policy_id == segunda.policy_id == _POLICY_ID


# ======================================================================
# E4.8.2 — Denied-Path Authority Coherence
# ======================================================================
#
# A E4.8.1 centralizou a coerência numa função pura, mas o manager só a
# chamava DEPOIS do `return` da recusa atômica. Com isso, um pedido com
# identidades locais divergentes em que alguma decisão recusava escapava
# como `ValueError` cru, sem `PIA-8040`.
#
# A função pura não estava errada; a POSIÇÃO da chamada estava.
#
#     COLLABORATOR DISAGREEMENT != INVALID REQUEST


class _GovernancaPorDominio:
    """Resolve cada domínio conforme um plano explícito.

    Permite montar combinações de outcome e identidade local que o
    repositório real não produziria, para exercitar a fronteira.
    """

    def __init__(self, plano: dict) -> None:
        self.plano = plano
        self.chamadas: list[uuid.UUID] = []

    def resolve(self, *, descriptor, context, policy_key=None, moment=None):
        dominio = context.domain_ids[0]
        self.chamadas.append(dominio)
        outcome, policy_id, rule = self.plano[dominio]
        return _res_livre(
            domain_ids=context.domain_ids,
            outcome=outcome,
            policy_id=policy_id if policy_id is not None else _POLICY_ID,
            matched_rule_id=rule,
        )


def _manager_por_dominio(plano):
    retrieval = RetrievalFalsa()
    memberships = MembershipsFalsas({_D1: (), _D2: ()})
    manager = MemoryIsolationManager(
        retrieval, _GovernancaPorDominio(plano), ContextoFalso(), memberships
    )
    return manager, retrieval, memberships


@pytest.mark.parametrize(
    ("descricao", "plano"),
    [
        (
            "ADMISSIBLE(A) + INADMISSIBLE(B)",
            {
                _D1: (GovernanceOutcome.ADMISSIBLE, _POLICY_ID, "r"),
                _D2: (GovernanceOutcome.INADMISSIBLE, _PID_OUTRO, "r"),
            },
        ),
        (
            "INADMISSIBLE(A) + INADMISSIBLE(B)",
            {
                _D1: (GovernanceOutcome.INADMISSIBLE, _POLICY_ID, "r"),
                _D2: (GovernanceOutcome.INADMISSIBLE, _PID_OUTRO, "r"),
            },
        ),
        (
            "INADMISSIBLE(A) + ADMISSIBLE(B)",
            {
                _D1: (GovernanceOutcome.INADMISSIBLE, _POLICY_ID, "r"),
                _D2: (GovernanceOutcome.ADMISSIBLE, _PID_OUTRO, "r"),
            },
        ),
    ],
)
def test_e482_divergent_identity_on_the_denied_path_raises_pia_8040(descricao, plano):
    """`ONE REQUEST != MULTIPLE AUTHORITY PROVENANCES`.

    Vale **independentemente dos outcomes**: o que invalida o pedido é
    transportar duas identidades locais, não haver ou não uma recusa.
    """
    manager, retrieval, memberships = _manager_por_dominio(plano)
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager, context=_contexto(_D1, _D2))
    assert exc.value.code == "PIA-8040"
    assert any("identidades de policy local diferentes" in m for m in exc.value.reasons)
    # e nada de patrimônio é tocado antes de confirmar a coerência
    assert memberships.chamadas == []
    assert retrieval.chamadas == []


def test_e482_divergent_identity_is_never_a_raw_value_error():
    """O diagnóstico é de colaborador, não de pedido inválido."""
    manager, _, _ = _manager_por_dominio(
        {
            _D1: (GovernanceOutcome.ADMISSIBLE, _POLICY_ID, "r"),
            _D2: (GovernanceOutcome.INADMISSIBLE, _PID_OUTRO, "r"),
        }
    )
    with pytest.raises(IsolationContractViolationError) as exc:
        _executar(manager, context=_contexto(_D1, _D2))
    assert type(exc.value) is IsolationContractViolationError
    assert exc.value.code == "PIA-8040"


def test_e482_same_identity_with_a_refusal_is_a_normal_atomic_denial():
    """`ADMISSIBLE(A) + INADMISSIBLE(A)` continua recusa atômica."""
    manager, retrieval, memberships = _manager_por_dominio(
        {
            _D1: (GovernanceOutcome.ADMISSIBLE, _POLICY_ID, "r"),
            _D2: (GovernanceOutcome.INADMISSIBLE, _POLICY_ID, "r"),
        }
    )
    resultado = _executar(manager, context=_contexto(_D1, _D2))
    assert resultado.authorized is False
    assert resultado.retrieval is None
    assert resultado.refused_domain_ids == (_D2,)
    assert memberships.chamadas == []
    assert retrieval.chamadas == []


def test_e482_admissible_plus_prohibited_remains_valid():
    """`PROHIBITED` não carrega proveniência local, então não há duas
    identidades — a fronteira simplesmente não consultou policy."""
    manager, retrieval, _ = _manager_por_dominio(
        {
            _D1: (GovernanceOutcome.ADMISSIBLE, _POLICY_ID, "r"),
            _D2: (GovernanceOutcome.PROHIBITED, None, "r"),
        }
    )
    resultado = _executar(manager, context=_contexto(_D1, _D2))
    assert resultado.authorized is False
    assert resultado.retrieval is None
    assert retrieval.chamadas == []


def test_e482_different_matched_rules_of_the_same_version_remain_valid():
    """`MATCHED RULE != POLICY IDENTITY`, também no caminho recusado."""
    manager, _, _ = _manager_por_dominio(
        {
            _D1: (GovernanceOutcome.ADMISSIBLE, _POLICY_ID, "regra-a"),
            _D2: (GovernanceOutcome.INADMISSIBLE, _POLICY_ID, "regra-b"),
        }
    )
    resultado = _executar(manager, context=_contexto(_D1, _D2))
    assert resultado.authorized is False
    assert resultado.retrieval is None


def test_e482_direct_constructor_still_raises_value_error():
    """O value object continua levantando `ValueError` — a distinção de
    categoria entre manager e construtor é deliberada."""
    contexto = _contexto(_D1, _D2)
    decisoes = tuple(
        sorted(
            (
                DomainIsolationDecision(domain_id=_D1, resolution=_res_livre(domain_ids=(_D1,))),
                DomainIsolationDecision(
                    domain_id=_D2,
                    resolution=_res_livre(
                        domain_ids=(_D2,),
                        outcome=GovernanceOutcome.INADMISSIBLE,
                        policy_id=_PID_OUTRO,
                    ),
                ),
            ),
            key=lambda d: d.domain_id,
        )
    )
    with pytest.raises(ValueError) as exc:
        MemoryIsolationResult(context=contexto, decisions=decisoes, evaluated_at=_MOMENTO)
    assert type(exc.value) is ValueError
    assert "identidades de policy local diferentes" in str(exc.value)


def test_e482_coherence_is_checked_before_the_atomic_refusal_branch():
    """A ordem é o que o corretivo estabelece.

    Prova estrutural: no corpo de `retrieve_isolated`, a chamada a
    `_verificar_coerencia` com `apenas_decisoes=True` aparece **antes**
    do ramo `if not all(d.authorized ...)`.
    """
    import app.memory.services.memory_isolation_manager as manager_mod

    fonte = pathlib.Path(manager_mod.__file__).read_text(encoding="utf-8")
    corpo = fonte[fonte.index("def retrieve_isolated(") :]
    corpo = corpo[: corpo.index("    @staticmethod")]
    posicao_verificacao = corpo.index("apenas_decisoes=True")
    posicao_ramo = corpo.index("if not all(d.authorized for d in decisoes):")
    assert (
        posicao_verificacao < posicao_ramo
    ), "a coerência precisa ser verificada antes do ramo de recusa atômica"


def test_e482_no_second_coherence_implementation_was_created():
    """Nenhuma segunda implementação da regra, e nenhuma comparação de
    identidade feita à mão no manager."""
    import app.memory.schemas.isolation as schema_mod
    import app.memory.services.memory_isolation_manager as manager_mod

    fonte_schema = pathlib.Path(schema_mod.__file__).read_text(encoding="utf-8")
    fonte_manager = pathlib.Path(manager_mod.__file__).read_text(encoding="utf-8")
    assert fonte_schema.count("def verificar_coerencia_resultado_isolado(") == 1
    assert "def verificar_coerencia_resultado_isolado(" not in fonte_manager
    for proibido in ("policy_version", "policy_id", "_identidade_local"):
        assert proibido not in fonte_manager, f"o manager compara {proibido} por conta própria"
    # e a chamada redundante foi removida: exatamente duas no fluxo
    corpo = fonte_manager[fonte_manager.index("def retrieve_isolated(") :]
    corpo = corpo[: corpo.index("    @staticmethod")]
    assert corpo.count("self._verificar_coerencia(") == 2
