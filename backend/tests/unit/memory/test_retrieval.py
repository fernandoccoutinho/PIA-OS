"""
Testes unitários da E4.6 — Memory Retrieval.

Cobrem os 38 itens do §17 do prompt canônico. Usam dublês da porta de
Search e do `GovernanceManager`: aqui o objeto sob teste é a
**disciplina** da E4.6 — governança antes de qualquer toque no
patrimônio, filtros de admissibilidade, união de domínios, paginação
depois dos filtros e recusa distinguível de vista vazia.

A composição real com o `SearchEngine` da E3.8 e o banco vive em
`tests/integration/memory/test_retrieval_integration.py`.
"""

import ast
import dataclasses
import pathlib
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.memory.errors.exceptions import (
    RetrievalContractViolationError,
    RetrievalDuplicateCoidError,
)
from app.memory.models.governance_enums import (
    CognitiveOperation,
    GovernanceEffect,
    GovernanceOutcome,
)
from app.memory.ports.retrieval import CognitiveObjectView, CognitiveSearchPort
from app.memory.schemas.governance import GovernanceResolution
from app.memory.schemas.memory_context import MemoryContext
from app.memory.schemas.retrieval import (
    KNOWN_ACCESSIBILITY_TOKENS,
    KNOWN_REVISION_TOKENS,
    MAX_LIMIT,
    RETRIEVABLE_ACCESSIBILITY_TOKENS,
    MemoryRetrievalResult,
    RetrievedMemoryItem,
)
from app.memory.services.platform_safety_boundary import (
    PLATFORM_SAFETY_BOUNDARY_VERSION,
    CapabilityDescriptor,
    CriticalCapability,
)
from app.memory.services.retrieval_manager import (
    DEFAULT_LIMIT,
    SEARCH_BATCH_SIZE,
    MemoryRetrievalManager,
)

_BASE = datetime(2024, 1, 1, tzinfo=UTC)


# --- Dublês -----------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ObjetoFalso:
    """Dublê estrutural de `CognitiveObject` — mesma forma da porta."""

    id: uuid.UUID
    clid: uuid.UUID | None = None
    accessibility: str = "active"
    revision_status: str | None = None
    created_at: datetime = _BASE
    deleted_at: datetime | None = None


class PortaFalsa:
    """Devolve objetos em ordem canônica, respeitando limit/offset."""

    def __init__(self, objetos=(), erro: Exception | None = None) -> None:
        self.objetos = list(objetos)
        self.erro = erro
        self.chamadas: list[dict] = []

    def search(self, criteria, *, limit=None, offset=None):
        self.chamadas.append({"criteria": criteria, "limit": limit, "offset": offset})
        if self.erro is not None:
            raise self.erro
        inicio = offset or 0
        fim = None if limit is None else inicio + limit
        return self.objetos[inicio:fim]


class GovernanceFalso:
    """Devolve uma resolução fixa e registra as chamadas."""

    def __init__(
        self,
        resolution: GovernanceResolution,
        *,
        eco_policy: bool = True,
        eco_contexto: bool = True,
    ) -> None:
        self.resolution = resolution
        self.eco_policy = eco_policy
        self.eco_contexto = eco_contexto
        self.chamadas: list[dict] = []

    def _com_contexto(self, resolution, context):
        """Reescreve o vínculo de contexto, como o manager REAL faz.

        Sem isto, qualquer teste com domínios falharia a fidelidade
        introduzida pelo corretivo E4.3.4 — e falharia com razão, porque
        o dublê estaria devolvendo uma resolução emitida para outro
        contexto. Testes que QUEREM essa divergência desligam o eco.
        """
        # Só ecoa sobre uma resolução REAL: alguns testes injetam
        # propositalmente um objeto que não é `GovernanceResolution`
        # para provar o diagnóstico de tipo, e o eco não pode
        # atrapalhar essa prova.
        if not self.eco_contexto or not isinstance(resolution, GovernanceResolution):
            return resolution
        return dataclasses.replace(
            resolution,
            context_domain_ids=context.domain_ids,
            context_actor_ref=context.actor_ref,
            context_purpose=context.purpose,
        )

    def resolve(self, *, descriptor, context, policy_key=None, moment=None):
        self.chamadas.append(
            {
                "descriptor": descriptor,
                "context": context,
                "policy_key": policy_key,
                "moment": moment,
            }
        )
        if self.eco_policy and self.resolution.policy_key is not None:
            # O `GovernanceManager` real resolve a versão vigente da
            # policy **solicitada**; o dublê ecoa o mesmo `policy_key`
            # para não produzir a divergência que o corretivo E4.6.1
            # (corretamente) recusa. Testes que querem a divergência
            # desligam o eco.
            #
            # Sem policy no pedido, a resolução não pode carregar
            # proveniência parcial: `policy_key`, `policy_version` e
            # `policy_id` são tudo-ou-nada desde a E4.3.2.
            if policy_key is None:
                return self._com_contexto(_resolucao_sem_policy(self.resolution.outcome), context)
            return self._com_contexto(
                dataclasses.replace(self.resolution, policy_key=policy_key), context
            )
        return self._com_contexto(self.resolution, context)


class ContextoFalso:
    """`ContextManager` de teste: devolve o contexto, ou levanta."""

    def __init__(self, erro: Exception | None = None) -> None:
        self.erro = erro
        self.chamadas: list[MemoryContext] = []

    def validate(self, context: MemoryContext) -> MemoryContext:
        self.chamadas.append(context)
        if self.erro is not None:
            raise self.erro
        return context


@dataclasses.dataclass(frozen=True)
class MembershipFalsa:
    domain_id: uuid.UUID
    coid: uuid.UUID


class MembershipsFalsas:
    def __init__(self, por_dominio: dict[uuid.UUID, list[uuid.UUID]] | None = None) -> None:
        self.por_dominio = por_dominio or {}
        self.chamadas: list[uuid.UUID] = []

    def list_memberships_of_domain(self, domain_id: uuid.UUID):
        self.chamadas.append(domain_id)
        return [MembershipFalsa(domain_id, coid) for coid in self.por_dominio.get(domain_id, [])]


# --- Construtores de apoio --------------------------------------------


_POLICY_KEY = "pol-teste"
"""Policy usada pelos dublês.

A partir do corretivo E4.6.1 o manager exige `resolution.policy_key ==
policy_key solicitado`. Os dublês da E4.6 fixavam `"pk"` enquanto o
pedido ia sem policy — combinação que o corretivo (corretamente) recusa,
porque é exatamente o defeito B. Os testes passam a declarar a mesma
policy nos dois lados.
"""


_CONTEXTO_VAZIO: dict = {
    "context_domain_ids": (),
    "context_actor_ref": None,
    "context_purpose": None,
}
"""Vínculo de contexto para os dublês (corretivo E4.3.4).

As três dimensões passaram a ser **obrigatórias** em
`GovernanceResolution`: omissão não é mais indistinguível de contexto
explicitamente vazio. Os dublês declaram o vazio explicitamente, e o
`GovernanceFalso` reescreve o vínculo com o contexto recebido — como o
`GovernanceManager` real faz.
"""


def _resolucao(
    *,
    outcome: GovernanceOutcome = GovernanceOutcome.ADMISSIBLE,
    alternativas: tuple[str, ...] = (),
    capacidades: tuple[CriticalCapability, ...] = (),
) -> GovernanceResolution:
    """Resolução coerente com os invariantes congelados na E4.3.2."""
    if outcome is GovernanceOutcome.PROHIBITED:
        return GovernanceResolution(
            **_CONTEXTO_VAZIO,
            operation=CognitiveOperation.READ,
            outcome=outcome,
            blocked_capabilities=capacidades or (CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT,),
            admissible_alternatives=alternativas,
            safety_boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
            safety_rationale="proibido pela fronteira",
        )
    if outcome is GovernanceOutcome.NOT_APPLICABLE:
        return GovernanceResolution(
            **_CONTEXTO_VAZIO,
            operation=CognitiveOperation.READ,
            outcome=outcome,
            safety_boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
        )
    return GovernanceResolution(
        **_CONTEXTO_VAZIO,
        operation=CognitiveOperation.READ,
        outcome=outcome,
        policy_key=_POLICY_KEY,
        policy_version=1,
        # `policy_id` faz parte da identidade tudo-ou-nada congelada na
        # E4.3.2: proveniência parcial parece proveniência.
        policy_id=uuid.uuid4(),
        matched_rule_id="r1",
        safety_boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
    )


def _resolucao_sem_policy(outcome: GovernanceOutcome) -> GovernanceResolution:
    """Resolução admissível sem proveniência local.

    Usada quando o pedido não informa `policy_key`. `ADMISSIBLE` exige
    proveniência completa (E4.3.2), então este caso vira
    `NOT_APPLICABLE` — que é justamente o que o `GovernanceManager` real
    devolve quando nenhuma policy foi informada, e que **não** autoriza.
    """
    return GovernanceResolution(
        **_CONTEXTO_VAZIO,
        operation=CognitiveOperation.READ,
        outcome=GovernanceOutcome.NOT_APPLICABLE,
        safety_boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
    )


def _descritor(operation: CognitiveOperation = CognitiveOperation.READ) -> CapabilityDescriptor:
    return CapabilityDescriptor(operation=operation)


def _objetos(quantidade: int, **overrides) -> list[ObjetoFalso]:
    """Objetos com `created_at` crescente — ordem canônica estável.

    Os COIDs são aleatórios, mas a ordem NÃO depende deles: depende da
    posição na lista devolvida pela porta, que reproduz a ordenação
    canônica da E3.
    """
    return [
        ObjetoFalso(id=uuid.uuid4(), created_at=_BASE + timedelta(minutes=i), **overrides)
        for i in range(quantidade)
    ]


def _manager(
    *,
    objetos=(),
    resolution: GovernanceResolution | None = None,
    memberships=None,
    erro_busca: Exception | None = None,
    erro_contexto: Exception | None = None,
):
    porta = PortaFalsa(objetos, erro=erro_busca)
    governanca = GovernanceFalso(resolution or _resolucao())
    contexto = ContextoFalso(erro=erro_contexto)
    associacoes = MembershipsFalsas(memberships)
    manager = MemoryRetrievalManager(porta, governanca, contexto, associacoes)
    return manager, porta, governanca, contexto, associacoes


_AUSENTE = object()


def _executar(manager, *, context=None, descriptor=None, criteria=None, **kwargs):
    """Executa `retrieve()` informando a policy padrão.

    A partir do corretivo E4.6.1 o manager exige que a policy resolvida
    seja a solicitada. Concentrar isso aqui evita repetir o argumento em
    dezenas de chamadas — e um teste que queira pedido sem policy passa
    `policy_key=None` explicitamente.
    """
    if "policy_key" not in kwargs:
        kwargs["policy_key"] = _POLICY_KEY
    return manager.retrieve(
        context=_contexto() if context is None else context,
        descriptor=_descritor() if descriptor is None else descriptor,
        criteria=object() if criteria is None else criteria,
        **kwargs,
    )


def _contexto(*domain_ids: uuid.UUID) -> MemoryContext:
    return MemoryContext(domain_ids=tuple(domain_ids))


def _item(**overrides) -> RetrievedMemoryItem:
    campos = {
        "coid": uuid.uuid4(),
        "clid": None,
        "accessibility": "active",
        "revision_status": None,
        "created_at": _BASE,
    }
    campos.update(overrides)
    return RetrievedMemoryItem(**campos)


def _resultado(**overrides) -> MemoryRetrievalResult:
    campos = {
        "context": _contexto(),
        "governance_resolution": _resolucao(),
        "items": (_item(),),
        "search_executed": True,
        "limit": 50,
        "offset": 0,
        "has_more": False,
    }
    campos.update(overrides)
    return MemoryRetrievalResult(**campos)


# ======================================================================
# 1 a 4 — value objects
# ======================================================================


def test_r1_value_objects_are_frozen_and_hashable():
    item = _item()
    resultado = _resultado()
    assert isinstance(hash(item), int)
    assert isinstance(hash(resultado), int)
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.coid = uuid.uuid4()
    with pytest.raises(dataclasses.FrozenInstanceError):
        resultado.search_executed = False


def test_r1b_structural_equality():
    coid = uuid.uuid4()
    a = _item(coid=coid)
    b = _item(coid=coid)
    assert a == b
    assert hash(a) == hash(b)


def test_r2_external_list_does_not_mutate_the_result():
    """`frozen=True` protege a referência, não o conteúdo — quinta vez
    que o projeto aplica essa lição."""
    itens = [_item()]
    resultado = _resultado(items=itens)
    antes = resultado.items
    itens.append(_item())
    assert resultado.items == antes
    assert isinstance(resultado.items, tuple)


def test_r3_direct_constructor_and_replace_preserve_invariants():
    resultado = _resultado()
    with pytest.raises(ValueError, match="has_more"):
        dataclasses.replace(resultado, has_more=None)
    with pytest.raises(ValueError, match="não pertence à vista admissível"):
        dataclasses.replace(_item(), accessibility="inaccessible")


@pytest.mark.parametrize(
    ("campo", "valor", "excecao"),
    [
        ("coid", "nao-e-uuid", TypeError),
        ("clid", "nao-e-uuid", TypeError),
        ("accessibility", 123, TypeError),
        ("accessibility", "   ", ValueError),
        ("revision_status", 123, TypeError),
        ("revision_status", "  ", ValueError),
        ("created_at", "ontem", TypeError),
        ("accessibility", "inaccessible", ValueError),
    ],
)
def test_r4_item_separates_type_errors_from_value_errors(campo, valor, excecao):
    with pytest.raises(excecao):
        _item(**{campo: valor})


@pytest.mark.parametrize(
    ("campo", "valor", "excecao"),
    [
        ("context", "nao-e-contexto", TypeError),
        ("governance_resolution", "nao-e-resolucao", TypeError),
        ("items", "abc", TypeError),
        ("items", [1], TypeError),
        ("search_executed", "sim", TypeError),
        ("limit", True, TypeError),
        ("offset", True, TypeError),
        ("has_more", "sim", TypeError),
        ("limit", -1, ValueError),
        ("offset", -1, ValueError),
    ],
)
def test_r4b_result_separates_type_errors_from_value_errors(campo, valor, excecao):
    with pytest.raises(excecao):
        _resultado(**{campo: valor})


def test_r4c_duplicate_coid_in_items_is_rejected():
    coid = uuid.uuid4()
    with pytest.raises(ValueError, match="mais de uma vez"):
        _resultado(items=(_item(coid=coid), _item(coid=coid)))


def test_r4d_admissible_tokens_are_exactly_active_and_latent():
    assert frozenset({"active", "latent"}) == RETRIEVABLE_ACCESSIBILITY_TOKENS


# ======================================================================
# 5 a 14 — governança
# ======================================================================


def test_r5_only_read_operation_is_accepted():
    manager, _, governanca, _, _ = _manager()
    resultado = _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.search_executed is True
    assert governanca.chamadas[0]["descriptor"].operation is CognitiveOperation.READ


@pytest.mark.parametrize(
    "operacao",
    [
        CognitiveOperation.TRANSFORM,
        CognitiveOperation.CONSOLIDATE,
        CognitiveOperation.EXPOSE,
        CognitiveOperation.SYNCHRONIZE,
    ],
)
def test_r6_other_operations_are_refused_before_search(operacao):
    """Um descritor de outra operação não é pedido de leitura que a
    governança deva julgar — é pedido endereçado ao módulo errado."""
    manager, porta, governanca, _, _ = _manager(objetos=_objetos(3))
    with pytest.raises(ValueError, match="apenas CognitiveOperation.READ"):
        _executar(manager, context=_contexto(), descriptor=_descritor(operacao), criteria=object())
    assert porta.chamadas == []
    assert governanca.chamadas == []


def test_r7_governance_manager_is_called_internally():
    manager, _, governanca, _, _ = _manager()
    contexto = _contexto()
    momento = datetime(2024, 6, 1, tzinfo=UTC)
    _executar(
        manager,
        context=contexto,
        descriptor=_descritor(),
        criteria=object(),
        policy_key="pk",
        moment=momento,
    )
    assert len(governanca.chamadas) == 1
    assert governanca.chamadas[0]["policy_key"] == "pk"
    assert governanca.chamadas[0]["moment"] == momento
    assert governanca.chamadas[0]["context"] is contexto


def test_r8_external_policy_or_resolution_cannot_be_injected_as_authority():
    """A assinatura pública não oferece por onde: só `policy_key`."""
    import inspect

    parametros = set(inspect.signature(MemoryRetrievalManager.retrieve).parameters)
    for proibido in ("policy", "governance_policy", "resolution", "authorized", "rules"):
        assert proibido not in parametros
    assert "policy_key" in parametros

    construtor = set(inspect.signature(MemoryRetrievalManager.__init__).parameters)
    assert construtor == {
        "self",
        "search_port",
        "governance_manager",
        "context_manager",
        "membership_repository",
    }


@pytest.mark.parametrize(
    "outcome",
    [
        GovernanceOutcome.PROHIBITED,
        GovernanceOutcome.INADMISSIBLE,
        GovernanceOutcome.NOT_APPLICABLE,
    ],
)
def test_r9_r10_r11_denied_outcomes_never_touch_search_or_memberships(outcome):
    """Sob recusa nem a Search corre nem memberships são carregadas: a
    quantidade de objetos já seria informação vazada."""
    dominio = uuid.uuid4()
    manager, porta, _, _, associacoes = _manager(
        objetos=_objetos(5),
        resolution=_resolucao(outcome=outcome),
        memberships={dominio: [uuid.uuid4()]},
    )
    resultado = _executar(
        manager, context=_contexto(dominio), descriptor=_descritor(), criteria=object()
    )
    assert porta.chamadas == []
    assert associacoes.chamadas == []
    assert resultado.search_executed is False
    assert resultado.execution_authorized is False
    assert resultado.items == ()
    assert resultado.has_more is None


def test_r12_actor_presence_without_rule_does_not_authorize():
    """`ACTOR PRESENCE != AUTHORIZATION`; `NOT_APPLICABLE != ADMISSIBLE`."""
    manager, porta, _, _, _ = _manager(
        objetos=_objetos(3), resolution=_resolucao(outcome=GovernanceOutcome.NOT_APPLICABLE)
    )
    contexto = MemoryContext(actor_ref="ator", purpose="auditoria")
    resultado = _executar(manager, context=contexto, descriptor=_descritor(), criteria=object())
    assert resultado.execution_authorized is False
    assert porta.chamadas == []


def test_r13_denied_result_is_distinguishable_from_empty_search():
    """`DENIED != EMPTY RESULT` — e não há campo de contagem para vazar
    que o patrimônio está vazio sob os critérios recusados."""
    negado, _, _, _, _ = _manager(resolution=_resolucao(outcome=GovernanceOutcome.INADMISSIBLE))
    r_negado = _executar(negado, context=_contexto(), descriptor=_descritor(), criteria=object())
    vazio, _, _, _, _ = _manager(objetos=[])
    r_vazio = _executar(
        vazio,
        policy_key=_POLICY_KEY,
        context=_contexto(),
        descriptor=_descritor(),
        criteria=object(),
    )

    assert r_negado.items == r_vazio.items == ()
    assert r_negado.search_executed is False
    assert r_vazio.search_executed is True
    assert r_negado.has_more is None
    assert r_vazio.has_more is False
    assert r_negado != r_vazio
    assert not hasattr(r_negado, "matched_count")


def test_r14_safety_boundary_alternatives_are_preserved_untouched():
    alternativas = ("consultar sumário público", "solicitar autorização formal")
    manager, _, _, _, _ = _manager(
        resolution=_resolucao(outcome=GovernanceOutcome.PROHIBITED, alternativas=alternativas)
    )
    resultado = _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.governance_resolution.admissible_alternatives == alternativas


# ======================================================================
# 15 a 19 — domínios
# ======================================================================


def test_r15_multi_domain_context_is_a_union():
    """`scope(D1, D2) = members(D1) ∪ members(D2)`."""
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    objetos = _objetos(3)
    manager, _, _, _, associacoes = _manager(
        objetos=objetos,
        memberships={d1: [objetos[0].id], d2: [objetos[2].id]},
    )
    resultado = _executar(
        manager, context=_contexto(d1, d2), descriptor=_descritor(), criteria=object()
    )
    assert resultado.coids == (objetos[0].id, objetos[2].id)
    assert set(associacoes.chamadas) == {d1, d2}


def test_r16_coid_in_two_domains_appears_once():
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    objetos = _objetos(2)
    manager, _, _, _, _ = _manager(
        objetos=objetos,
        memberships={d1: [objetos[0].id], d2: [objetos[0].id]},
    )
    resultado = _executar(
        manager, context=_contexto(d1, d2), descriptor=_descritor(), criteria=object()
    )
    assert resultado.coids == (objetos[0].id,)


def test_r17_context_without_domains_applies_no_domain_filter():
    objetos = _objetos(3)
    manager, _, _, _, associacoes = _manager(objetos=objetos)
    resultado = _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.coids == tuple(o.id for o in objetos)
    assert associacoes.chamadas == []


def test_r18_zero_domain_object_remains_valid_without_domain_filter():
    """`ZERO DOMAIN MEMBERSHIP != NONEXISTENCE` (E4.1)."""
    objetos = _objetos(2)
    manager, _, _, _, _ = _manager(objetos=objetos)
    sem_recorte = _executar(
        manager, context=_contexto(), descriptor=_descritor(), criteria=object()
    )
    assert len(sem_recorte.items) == 2

    dominio = uuid.uuid4()
    manager2, _, _, _, _ = _manager(objetos=objetos, memberships={dominio: []})
    com_recorte = _executar(
        manager2, context=_contexto(dominio), descriptor=_descritor(), criteria=object()
    )
    assert com_recorte.items == ()
    assert com_recorte.search_executed is True


def test_r19_unknown_domain_raises_the_e42_diagnostic_not_an_empty_view():
    """Domínio desconhecido é erro do pedido, não vista vazia."""
    from app.memory.errors.exceptions import ContextUnknownDomainReferenceError

    desconhecido = uuid.uuid4()
    manager, porta, governanca, _, _ = _manager(
        objetos=_objetos(3),
        erro_contexto=ContextUnknownDomainReferenceError((desconhecido,)),
    )
    with pytest.raises(ContextUnknownDomainReferenceError):
        _executar(
            manager, context=_contexto(desconhecido), descriptor=_descritor(), criteria=object()
        )
    assert porta.chamadas == []
    assert governanca.chamadas == []


# ======================================================================
# 20 a 27 — admissibilidade e preservação de distinções
# ======================================================================


@pytest.mark.parametrize("token", ["active", "latent"])
def test_r20_r21_active_and_latent_are_admitted(token):
    objetos = _objetos(1, accessibility=token)
    manager, _, _, _, _ = _manager(objetos=objetos)
    resultado = _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.coids == (objetos[0].id,)
    assert resultado.items[0].accessibility == token


@pytest.mark.parametrize("token", ["inaccessible", "causally_extinct"])
def test_r22_r23_inaccessible_and_extinct_are_excluded(token):
    """`INACCESSIBLE != NONEXISTENT`; `CAUSALLY_EXTINCT != HISTORICALLY
    ERASED` — filtrados da vista, íntegros no patrimônio."""
    visivel = _objetos(1)[0]
    oculto = ObjetoFalso(id=uuid.uuid4(), accessibility=token, created_at=_BASE)
    manager, _, _, _, _ = _manager(objetos=[visivel, oculto])
    resultado = _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.coids == (visivel.id,)


def test_r24_soft_deleted_is_excluded_even_if_criteria_widen_include_deleted():
    """Filtro defensivo: auditoria histórica pertence à E3/E4.4."""
    visivel = _objetos(1)[0]
    apagado = ObjetoFalso(
        id=uuid.uuid4(), created_at=_BASE, deleted_at=datetime(2024, 5, 1, tzinfo=UTC)
    )
    manager, _, _, _, _ = _manager(objetos=[visivel, apagado])
    resultado = _executar(
        manager,
        context=_contexto(),
        descriptor=_descritor(),
        criteria={"include_deleted": True},
    )
    assert resultado.coids == (visivel.id,)


def test_r25_current_and_superseded_are_not_collapsed():
    """Nada privilegia `CURRENT` em silêncio."""
    clid = uuid.uuid4()
    atual = ObjetoFalso(id=uuid.uuid4(), clid=clid, revision_status="current", created_at=_BASE)
    anterior = ObjetoFalso(
        id=uuid.uuid4(),
        clid=clid,
        revision_status="superseded",
        created_at=_BASE + timedelta(minutes=1),
    )
    manager, _, _, _, _ = _manager(objetos=[atual, anterior])
    resultado = _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.coids == (atual.id, anterior.id)
    assert {i.revision_status for i in resultado.items} == {"current", "superseded"}


def test_r26_objects_sharing_a_clid_remain_distinct():
    clid = uuid.uuid4()
    objetos = [
        ObjetoFalso(id=uuid.uuid4(), clid=clid, created_at=_BASE + timedelta(minutes=i))
        for i in range(3)
    ]
    manager, _, _, _, _ = _manager(objetos=objetos)
    resultado = _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())
    assert len(resultado.items) == 3
    assert len({i.clid for i in resultado.items}) == 1


def test_r27_consolidation_and_its_sources_remain_distinct():
    """`CONSOLIDATION != SOURCE REPLACEMENT` — a síntese não substitui
    nem esconde as fontes na vista."""
    fontes = _objetos(2)
    alvo = ObjetoFalso(id=uuid.uuid4(), created_at=_BASE + timedelta(minutes=5))
    manager, _, _, _, _ = _manager(objetos=[*fontes, alvo])
    resultado = _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.coids == (fontes[0].id, fontes[1].id, alvo.id)


def test_r27b_object_without_continuity_evidence_is_not_inadmissible():
    """`MISSING CONTINUITY EVIDENCE != RETRIEVAL INADMISSIBILITY` — a
    E4.6 nem consulta a E4.4 para compor a vista."""
    import inspect

    assinatura = set(inspect.signature(MemoryRetrievalManager.__init__).parameters)
    assert "persistence_manager" not in assinatura
    sem_clid = ObjetoFalso(id=uuid.uuid4(), clid=None, created_at=_BASE)
    manager, _, _, _, _ = _manager(objetos=[sem_clid])
    resultado = _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.coids == (sem_clid.id,)


# ======================================================================
# 28 a 32 — ordenação, paginação e erros
# ======================================================================


def test_r28_deterministic_order_is_preserved_and_never_reordered():
    objetos = _objetos(6)
    manager, _, _, _, _ = _manager(objetos=objetos)
    for _ in range(5):
        resultado = _executar(
            manager, context=_contexto(), descriptor=_descritor(), criteria=object()
        )
        assert resultado.coids == tuple(o.id for o in objetos)


def test_r29_pagination_happens_after_the_filters():
    """O caso que uma paginação "filtrar depois do limit" erra.

    Entre os candidatos brutos há inadmissíveis intercalados; se
    `limit=2` fosse aplicado ao conjunto bruto, a primeira página viria
    com 1 item em vez de 2.
    """
    admissivel = _objetos(4)
    inadmissivel = [
        ObjetoFalso(
            id=uuid.uuid4(),
            accessibility="inaccessible",
            created_at=_BASE + timedelta(seconds=30 * i),
        )
        for i in range(4)
    ]
    intercalado = [
        admissivel[0],
        inadmissivel[0],
        admissivel[1],
        inadmissivel[1],
        admissivel[2],
        inadmissivel[2],
        admissivel[3],
        inadmissivel[3],
    ]
    manager, _, _, _, _ = _manager(objetos=intercalado)

    pagina1 = _executar(
        manager, context=_contexto(), descriptor=_descritor(), criteria=object(), limit=2, offset=0
    )
    assert pagina1.coids == (admissivel[0].id, admissivel[1].id)
    assert pagina1.has_more is True


def test_r30_pages_have_no_gaps_or_duplicates():
    admissivel = _objetos(5)
    inadmissivel = [
        ObjetoFalso(id=uuid.uuid4(), accessibility="causally_extinct", created_at=_BASE)
        for _ in range(5)
    ]
    intercalado = [x for par in zip(admissivel, inadmissivel, strict=True) for x in par]
    manager, _, _, _, _ = _manager(objetos=intercalado)

    coletados: list[uuid.UUID] = []
    for offset in range(0, 6, 2):
        pagina = _executar(
            manager,
            context=_contexto(),
            descriptor=_descritor(),
            criteria=object(),
            limit=2,
            offset=offset,
        )
        coletados.extend(pagina.coids)

    assert coletados == [o.id for o in admissivel]
    assert len(set(coletados)) == len(coletados)


@pytest.mark.parametrize(
    ("quantidade", "limit", "offset", "esperado_has_more"),
    [(5, 2, 0, True), (5, 2, 4, False), (5, 5, 0, False), (5, 10, 0, False), (0, 5, 0, False)],
)
def test_r31_has_more_is_correct(quantidade, limit, offset, esperado_has_more):
    manager, _, _, _, _ = _manager(objetos=_objetos(quantidade))
    resultado = _executar(
        manager,
        context=_contexto(),
        descriptor=_descritor(),
        criteria=object(),
        limit=limit,
        offset=offset,
    )
    assert resultado.has_more is esperado_has_more


def test_r31b_pagination_arguments_are_validated():
    manager, porta, _, _, _ = _manager(objetos=_objetos(3))
    for kwargs, excecao in (
        ({"limit": 0}, ValueError),
        ({"limit": MAX_LIMIT + 1}, ValueError),
        ({"offset": -1}, ValueError),
        ({"limit": True}, TypeError),
        ({"limit": "10"}, TypeError),
        ({"offset": 1.5}, TypeError),
    ):
        with pytest.raises(excecao):
            _executar(
                manager, context=_contexto(), descriptor=_descritor(), criteria=object(), **kwargs
            )
    assert porta.chamadas == []


def test_r31c_default_limit_is_applied():
    manager, _, _, _, _ = _manager(objetos=_objetos(3))
    resultado = _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.limit == DEFAULT_LIMIT


def test_r32_search_error_is_propagated_never_turned_into_an_empty_list():
    """Erro de busca não é resultado vazio, e não é aprendizado."""
    manager, _, _, _, _ = _manager(erro_busca=RuntimeError("falha na Search"))
    with pytest.raises(RuntimeError, match="falha na Search"):
        _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())


def test_r32b_duplicate_coid_from_the_port_raises_an_explicit_diagnostic():
    """Não escolher em silêncio qual ocorrência apresentar."""
    objeto = _objetos(1)[0]
    manager, _, _, _, _ = _manager(objetos=[objeto, objeto])
    with pytest.raises(RetrievalDuplicateCoidError) as exc:
        _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())
    assert exc.value.code == "PIA-8033"
    assert exc.value.coid == objeto.id


def test_r32c_criteria_travel_opaque_to_the_port():
    """A E4.6 não inspeciona nem reconstrói os critérios da E3.8."""
    sentinela = object()
    manager, porta, _, _, _ = _manager(objetos=_objetos(2))
    _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=sentinela)
    assert porta.chamadas
    assert all(c["criteria"] is sentinela for c in porta.chamadas)


# ======================================================================
# 33 a 38 — fronteiras estruturais
# ======================================================================


def test_r33_no_orm_instance_escapes_in_the_result():
    objetos = _objetos(2)
    manager, _, _, _, _ = _manager(objetos=objetos)
    resultado = _executar(manager, context=_contexto(), descriptor=_descritor(), criteria=object())
    for item in resultado.items:
        assert isinstance(item, RetrievedMemoryItem)
        assert not hasattr(item, "_sa_instance_state")
        assert not isinstance(item, ObjetoFalso)


def test_r34_no_score_ranking_or_relevance_anywhere():
    executavel = _codigo_executavel()
    for proibido in (
        "score",
        "rank",
        "relevance",
        "relevancia",
        "top_k",
        "embedding",
        "vector",
        "similarity",
        "popularity",
        "recency",
        "trust",
        "weight",
    ):
        assert proibido not in executavel.lower(), f"capacidade proibida: {proibido}"


def test_r35_no_write_capability_in_production_code():
    executavel = _codigo_executavel()
    for proibido in ("commit(", "flush(", "session.add", "INSERT", "UPDATE", "DELETE"):
        assert proibido not in executavel, f"escrita encontrada: {proibido}"


def test_r36_no_dependency_on_e47_or_e48():
    """A E4.6 lê estados; não decide transições nem isolamento."""
    executavel = _codigo_executavel()
    for proibido in (
        "AccessibilityPolicy",
        "accessibility_policy",
        "transition",
        "MemoryIsolation",
        "row_level_security",
    ):
        assert proibido not in executavel, f"dependência antecipada: {proibido}"


def test_r37_g17_import_guard_is_preserved():
    """Nenhum import de `app.cognitive` no código de produção da E4."""
    padrao = re.compile(r"^\s*(from|import)\s+app\.cognitive", re.MULTILINE)
    raiz = pathlib.Path(__file__).resolve().parents[3] / "app"
    ofensores = [
        str(caminho)
        for caminho in raiz.rglob("*.py")
        if "cognitive" not in caminho.parts and padrao.search(caminho.read_text(encoding="utf-8"))
    ]
    assert ofensores == []


@pytest.mark.parametrize(
    "primeiro_import",
    [
        "app.memory.ports.retrieval",
        "app.memory.schemas.retrieval",
        "app.memory.services.retrieval_manager",
        "app.memory.ports",
    ],
)
def test_r38_public_imports_work_in_any_order_in_a_clean_interpreter(primeiro_import):
    """Guarda contra ciclo de import — o sétimo defeito da E4.3.1, que só
    apareceu porque a suíte sempre importava outro módulo antes."""
    resultado = subprocess.run(
        [sys.executable, "-c", f"import {primeiro_import}; print('ok')"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "ok" in resultado.stdout


def test_r38b_batch_size_is_independent_of_the_public_limit():
    """Os lotes existem para filtrar antes de paginar; se o lote fosse o
    `limit`, a paginação voltaria a incidir sobre o conjunto bruto."""
    assert SEARCH_BATCH_SIZE >= MAX_LIMIT

    objetos = _objetos(SEARCH_BATCH_SIZE + 10)
    manager, porta, _, _, _ = _manager(objetos=objetos)
    _executar(
        manager, context=_contexto(), descriptor=_descritor(), criteria=object(), limit=MAX_LIMIT
    )
    assert all(c["limit"] == SEARCH_BATCH_SIZE for c in porta.chamadas)


def test_r38c_the_real_search_engine_satisfies_the_port():
    """Conformidade estrutural verificada, não presumida.

    Importa `app.cognitive` **no teste** — permitido; o que a fronteira
    veda é o import no código de produção de `app/memory`.
    """
    from app.cognitive.models.cognitive_object import CognitiveObject
    from app.cognitive.services.search_engine import SearchEngine

    assert isinstance(SearchEngine.__new__(SearchEngine), CognitiveSearchPort)
    assert isinstance(CognitiveObject(), CognitiveObjectView)


def _codigo_executavel() -> str:
    """Fonte da E4.6 sem docstrings.

    As docstrings citam nominalmente o que o módulo não faz, então
    comparar o texto bruto produziria falso positivo — o mesmo erro que a
    E4.3.1 corrigiu em `gv16`. A comparação usa o **código executável**.

    Remove **toda** expressão que seja apenas um literal de string, não
    só a primeira de cada bloco: as "docstrings de atributo" — string
    solta logo após uma constante de módulo — documentam sem executar
    nada, e mantê-las reintroduziria exatamente o falso positivo que
    esta função existe para evitar.
    """
    import app.memory.ports.retrieval as porta_mod
    import app.memory.schemas.retrieval as schema_mod
    import app.memory.services.retrieval_manager as manager_mod

    partes = []
    for modulo in (manager_mod, schema_mod, porta_mod):
        arvore = ast.parse(pathlib.Path(modulo.__file__).read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            corpo = getattr(no, "body", None)
            if not isinstance(corpo, list):
                continue
            restante = [
                filho
                for filho in corpo
                if not (
                    isinstance(filho, ast.Expr)
                    and isinstance(filho.value, ast.Constant)
                    and isinstance(filho.value.value, str)
                )
            ]
            no.body = restante or [ast.Pass()]
        partes.append(ast.unparse(arvore))
    return "\n".join(partes)


def test_r38d_governance_effect_vocabulary_is_untouched():
    """A E4.6 não amplia nem reinterpreta o vocabulário da E4.3."""
    assert {e.name for e in GovernanceEffect} == {"ADMIT", "DENY"}
    assert CognitiveOperation.READ in set(CognitiveOperation)


# ======================================================================
# Ramos descobertos pela exigência de 100%
# ======================================================================
#
# Todos são invariantes do construtor direto, que é API pública de
# qualquer dataclass. Um resultado montado à mão que afirmasse ter
# executado uma busca sob recusa — ou o contrário — mentiria sobre a
# própria operação.


def test_r39_authorized_result_requires_search_executed():
    with pytest.raises(ValueError, match="search_executed é False"):
        _resultado(search_executed=False, has_more=False)


def test_r39b_authorized_result_requires_boolean_has_more():
    with pytest.raises(ValueError, match="has_more booleano"):
        _resultado(has_more=None)


def test_r39c_authorized_result_requires_limit_at_least_one():
    """Com página vazia, quem dispara é o `limit >= 1`; com página
    preenchida, o invariante `len(items) <= limit` do corretivo E4.6.1
    dispara antes. Ambos recusam o estado, por razões distintas."""
    with pytest.raises(ValueError, match="limit >= 1"):
        _resultado(items=(), limit=0)
    with pytest.raises(ValueError, match="itens para limit"):
        _resultado(limit=0)


def test_r40_denied_result_cannot_claim_search_was_executed():
    with pytest.raises(ValueError, match="Search não pode ter sido chamada"):
        _resultado(
            governance_resolution=_resolucao(outcome=GovernanceOutcome.INADMISSIBLE),
            items=(),
            search_executed=True,
            has_more=False,
        )


def test_r40b_denied_result_cannot_carry_items():
    """Expor patrimônio sob recusa anularia a própria recusa."""
    with pytest.raises(ValueError, match="não carrega itens"):
        _resultado(
            governance_resolution=_resolucao(outcome=GovernanceOutcome.PROHIBITED),
            items=(_item(),),
            search_executed=False,
            has_more=None,
        )


def test_r40c_denied_result_cannot_assert_has_more():
    """Afirmar True ou False vazaria se existe mais patrimônio sob os
    critérios recusados."""
    with pytest.raises(ValueError, match="vazaria"):
        _resultado(
            governance_resolution=_resolucao(outcome=GovernanceOutcome.NOT_APPLICABLE),
            items=(),
            search_executed=False,
            has_more=False,
        )


def test_r41_item_count_is_the_page_not_a_contextual_total():
    itens = (_item(), _item(), _item())
    resultado = _resultado(items=itens, limit=3, has_more=True)
    assert resultado.item_count == 3
    assert resultado.item_count == len(resultado.coids)


def test_r42_non_descriptor_argument_is_a_type_error():
    manager, porta, governanca, _, _ = _manager(objetos=_objetos(2))
    with pytest.raises(TypeError, match="CapabilityDescriptor"):
        _executar(manager, context=_contexto(), descriptor="nao-e-descritor", criteria=object())
    assert porta.chamadas == []
    assert governanca.chamadas == []


# ======================================================================
# E4.6.1 — Retrieval Authority & Contract Fidelity
# ======================================================================
#
# Quatro fronteiras que a E4.6 deixara sem pós-condição:
#
#     REQUEST ↔ VALIDATED CONTEXT
#     REQUEST ↔ GOVERNANCE RESOLUTION
#     SEARCH PORT ↔ COGNITIVE OBJECT VIEW
#     RESULT PAGE ↔ PAGINATION CONTRACT
#
# Verificar só `execution_authorized` não diz QUAL operação nem QUAL
# policy produziram a autorização; e filtrar um hit antes de validar sua
# forma transforma dado malformado em ausência legítima.


def _manager_infiel(*, resolution=None, ctx_sub=None, objetos=(), nao_iteravel=False):
    """Manager cujos colaboradores devolvem respostas incoerentes."""
    porta = PortaFalsa(objetos)
    if nao_iteravel:
        porta.search = lambda c, *, limit=None, offset=None: 42  # type: ignore[assignment]
    governanca = GovernanceFalso(resolution or _resolucao(), eco_policy=False)
    contexto = ContextoFalso()
    if ctx_sub is not None:
        contexto.substituto = ctx_sub
        contexto.validate = lambda c: ctx_sub  # type: ignore[assignment]
    associacoes = MembershipsFalsas()
    manager = MemoryRetrievalManager(porta, governanca, contexto, associacoes)
    return manager, porta, governanca, associacoes


# --- Defeito A: operação resolvida diferente da solicitada -----------


def test_e461_transform_resolution_never_authorizes_a_read():
    """`AUTHORIZATION TO TRANSFORM != AUTHORIZATION TO READ`."""
    resolucao = dataclasses.replace(_resolucao(), operation=CognitiveOperation.TRANSFORM)
    manager, porta, _, associacoes = _manager_infiel(resolution=resolucao, objetos=_objetos(3))
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager)
    assert exc.value.code == "PIA-8034"
    assert any("apenas CognitiveOperation.READ" in m for m in exc.value.reasons)
    # Search e memberships intocadas.
    assert porta.chamadas == []
    assert associacoes.chamadas == []


def test_e461_resolution_operation_must_match_the_descriptor():
    resolucao = dataclasses.replace(_resolucao(), operation=CognitiveOperation.TRANSFORM)
    manager, _, _, _ = _manager_infiel(resolution=resolucao)
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager)
    assert any("difere da solicitada" in m for m in exc.value.reasons)


# --- Defeito B: policy resolvida diferente da solicitada -------------


def test_e461_resolved_policy_must_be_the_requested_one():
    """`REQUESTED POLICY != RESOLVED POLICY`."""
    resolucao = dataclasses.replace(_resolucao(), policy_key="other-policy")
    manager, porta, _, associacoes = _manager_infiel(resolution=resolucao, objetos=_objetos(3))
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager, policy_key="requested-policy")
    assert exc.value.code == "PIA-8034"
    assert any("policy resolvida" in m for m in exc.value.reasons)
    assert porta.chamadas == []
    assert associacoes.chamadas == []


def test_e461_policy_names_are_not_normalized():
    """Sem `lower()`/`strip()`: nomes de policy são comparados exatos."""
    resolucao = dataclasses.replace(_resolucao(), policy_key="Pol-Teste")
    manager, porta, _, _ = _manager_infiel(resolution=resolucao)
    with pytest.raises(RetrievalContractViolationError):
        _executar(manager, policy_key="pol-teste")
    assert porta.chamadas == []


def test_e461_absent_policy_does_not_become_admission():
    """`POLICY ABSENCE != ADMISSION` — sem policy, o desfecho real é
    `NOT_APPLICABLE`, que não autoriza e não chama Search."""
    manager, porta, _, _, _ = _manager(
        objetos=_objetos(3), resolution=_resolucao(outcome=GovernanceOutcome.NOT_APPLICABLE)
    )
    resultado = _executar(manager, policy_key=None)
    assert resultado.execution_authorized is False
    assert resultado.search_executed is False
    assert porta.chamadas == []


@pytest.mark.parametrize(
    "outcome", [GovernanceOutcome.PROHIBITED, GovernanceOutcome.NOT_APPLICABLE]
)
def test_e461_outcomes_without_local_provenance_are_not_rejected(outcome):
    """`PROHIBITED` nunca carrega proveniência local — a fronteira decide
    antes de a policy ser consultada — e `NOT_APPLICABLE` pode não
    carregá-la. Exigir identidade nesses casos recusaria recusas
    legítimas."""
    manager, porta, _, _, _ = _manager(resolution=_resolucao(outcome=outcome))
    resultado = _executar(manager, policy_key="qualquer-policy")
    assert resultado.execution_authorized is False
    assert resultado.search_executed is False
    assert porta.chamadas == []


def test_e461_non_resolution_object_is_an_explicit_diagnostic():
    manager, porta, _, _ = _manager_infiel(resolution="nao-e-resolucao")
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager)
    assert any("não GovernanceResolution" in m for m in exc.value.reasons)
    assert porta.chamadas == []


def test_e461_multiple_divergences_produce_multiple_reasons():
    resolucao = dataclasses.replace(
        _resolucao(), operation=CognitiveOperation.TRANSFORM, policy_key="other"
    )
    manager, _, _, _ = _manager_infiel(resolution=resolucao)
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager, policy_key="pol-teste")
    assert len(exc.value.reasons) >= 3


# --- Defeito C: substituição de contexto -----------------------------


def test_e461_context_manager_cannot_substitute_the_requested_perspective():
    """`CONTEXT VALIDATION != CONTEXT SUBSTITUTION`."""
    pedido = MemoryContext(actor_ref="user", purpose="requested")
    substituto = MemoryContext(actor_ref="other", purpose="substituted")
    manager, porta, governanca, associacoes = _manager_infiel(
        ctx_sub=substituto, objetos=_objetos(3)
    )
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager, context=pedido)
    assert exc.value.code == "PIA-8034"
    assert any("contexto diferente do solicitado" in m for m in exc.value.reasons)
    assert porta.chamadas == []
    assert associacoes.chamadas == []
    assert governanca.chamadas == []


def test_e461_original_context_is_the_one_preserved_in_the_result():
    """`VALIDATOR CONFIRMS / VALIDATOR DOES NOT REWRITE` — mesmo quando o
    validador devolve objeto estruturalmente igual, quem segue é o
    original do pedido."""
    pedido = MemoryContext(actor_ref="user", purpose="requested")
    igual = MemoryContext(actor_ref="user", purpose="requested")
    assert pedido == igual and pedido is not igual

    porta = PortaFalsa(_objetos(2))
    contexto = ContextoFalso()
    contexto.validate = lambda c: igual  # type: ignore[assignment]
    manager = MemoryRetrievalManager(
        porta, GovernanceFalso(_resolucao()), contexto, MembershipsFalsas()
    )
    resultado = _executar(manager, context=pedido)
    assert resultado.context is pedido


def test_e461_validator_returning_a_non_context_is_a_contract_violation():
    porta = PortaFalsa(_objetos(2))
    contexto = ContextoFalso()
    contexto.validate = lambda c: "nao-e-contexto"  # type: ignore[assignment]
    manager = MemoryRetrievalManager(
        porta, GovernanceFalso(_resolucao()), contexto, MembershipsFalsas()
    )
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager)
    assert any("não MemoryContext" in m for m in exc.value.reasons)
    assert porta.chamadas == []


@pytest.mark.parametrize("invalido", ["nao-e-contexto", 123, None, uuid.uuid4()])
def test_e461_invalid_context_argument_is_a_type_error(invalido):
    """`TypeError`, não `AttributeError` lá adiante.

    Chama `retrieve()` direto: `_executar` substitui `context=None` pelo
    default, e o caso `None` precisa alcançar o manager.
    """
    manager, porta, governanca, _ = _manager_infiel()
    with pytest.raises(TypeError, match="MemoryContext"):
        manager.retrieve(
            context=invalido,
            descriptor=_descritor(),
            criteria=object(),
            policy_key=_POLICY_KEY,
        )
    assert porta.chamadas == []
    assert governanca.chamadas == []


# --- Defeito D: hits malformados -------------------------------------


@pytest.mark.parametrize(
    ("descricao", "objeto"),
    [
        ("id não-UUID", ObjetoFalso(id="nao-uuid")),
        ("clid inválido", ObjetoFalso(id=uuid.uuid4(), clid="nao-uuid")),
        ("accessibility com tipo inválido", ObjetoFalso(id=uuid.uuid4(), accessibility=123)),
        (
            "token de acessibilidade desconhecido",
            ObjetoFalso(id=uuid.uuid4(), accessibility="quantum"),
        ),
        ("revision_status com tipo inválido", ObjetoFalso(id=uuid.uuid4(), revision_status=7)),
        ("token de revisão desconhecido", ObjetoFalso(id=uuid.uuid4(), revision_status="garbage")),
        ("created_at inválido", ObjetoFalso(id=uuid.uuid4(), created_at="ontem")),
        ("deleted_at inválido", ObjetoFalso(id=uuid.uuid4(), deleted_at="yesterday")),
    ],
)
def test_e461_malformed_hit_is_a_contract_violation_not_an_empty_view(descricao, objeto):
    """`PORT CONTRACT VIOLATION != EMPTY VIEW`;
    `MALFORMED EVIDENCE != NO MATCH`."""
    manager, _, _, _ = _manager_infiel(objetos=[objeto])
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager)
    assert exc.value.code == "PIA-8034"


def test_e461_hit_missing_a_required_attribute_is_a_contract_violation():
    class Incompleto:
        id = uuid.uuid4()
        clid = None
        accessibility = "active"
        # sem revision_status, created_at e deleted_at

    manager, _, _, _ = _manager_infiel(objetos=[Incompleto()])
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager)
    # A partir do corretivo E4.6.2 o acesso é tipado direto, sem
    # `hasattr`: o `AttributeError` interrompe na PRIMEIRA ausência, e o
    # diagnóstico reporta um motivo, não todos. É o custo declarado de
    # abandonar a reflexão que o contrato da porta proíbe.
    assert len(exc.value.reasons) == 1
    assert "não satisfaz CognitiveObjectView" in exc.value.reasons[0]


def test_e461_non_iterable_search_result_is_a_contract_violation():
    manager, _, _, _ = _manager_infiel(nao_iteravel=True)
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager)
    # Mensagem passou a falar em `Sequence` no corretivo E4.6.2: o
    # contrato da porta é mais estrito que "iterável".
    assert any("não é uma Sequence" in m for m in exc.value.reasons)


def test_e461_malformed_hit_is_detected_even_when_it_would_be_filtered_out():
    """A validação vem ANTES do filtro: um hit inadmissível **e**
    malformado ainda é violação, não exclusão silenciosa."""
    manager, _, _, _ = _manager_infiel(
        objetos=[ObjetoFalso(id=uuid.uuid4(), accessibility="inaccessible", created_at="ontem")]
    )
    with pytest.raises(RetrievalContractViolationError):
        _executar(manager)


def test_e461_valid_hits_still_produce_a_normal_view():
    """O endurecimento não recusa o caminho legítimo."""
    objetos = _objetos(3)
    manager, _, _, _, _ = _manager(objetos=objetos)
    resultado = _executar(manager)
    assert resultado.coids == tuple(o.id for o in objetos)


# --- Defeito E: invariantes do value object --------------------------


def test_e461_result_refuses_a_resolution_about_another_operation():
    with pytest.raises(ValueError, match="apenas CognitiveOperation.READ"):
        _resultado(
            governance_resolution=dataclasses.replace(
                _resolucao(), operation=CognitiveOperation.TRANSFORM
            )
        )


def test_e461_result_refuses_more_items_than_limit():
    with pytest.raises(ValueError, match="itens para limit"):
        _resultado(items=(_item(), _item()), limit=1, has_more=False)


def test_e461_result_refuses_limit_above_max():
    with pytest.raises(ValueError, match="MAX_LIMIT"):
        _resultado(limit=MAX_LIMIT + 1)


def test_e461_result_refuses_has_more_with_a_partial_page():
    """Página parcial não pode afirmar que há mais: o coletor canônico
    preencheria a página antes de declarar `has_more`."""
    with pytest.raises(ValueError, match="página parcial"):
        _resultado(items=(_item(),), limit=5, has_more=True)


def test_e461_full_page_with_has_more_is_accepted():
    itens = (_item(), _item())
    resultado = _resultado(items=itens, limit=2, has_more=True)
    assert resultado.has_more is True
    assert resultado.item_count == 2


@pytest.mark.parametrize("token", ["garbage", "CURRENT", "Superseded", "  current"])
def test_e461_item_refuses_unknown_revision_tokens(token):
    with pytest.raises(ValueError):
        _item(revision_status=token)


@pytest.mark.parametrize("token", [None, "current", "superseded"])
def test_e461_item_accepts_the_frozen_revision_vocabulary(token):
    assert _item(revision_status=token).revision_status == token


def test_e461_dataclasses_replace_cannot_bypass_the_new_invariants():
    resultado = _resultado(items=(_item(), _item()), limit=2, has_more=True)
    with pytest.raises(ValueError, match="itens para limit"):
        dataclasses.replace(resultado, limit=1)


# --- Centralização e regressão ---------------------------------------


def test_e461_pagination_contract_lives_in_one_place():
    """Constantes duplicadas entre schema e manager divergiriam — a
    lição da E4.5.1 sobre duas implementações da mesma regra."""
    from app.memory.schemas import retrieval as schema_mod
    from app.memory.services import retrieval_manager as manager_mod

    assert manager_mod.MAX_LIMIT is schema_mod.MAX_LIMIT
    assert manager_mod.DEFAULT_LIMIT is schema_mod.DEFAULT_LIMIT


def test_e461_known_vocabularies_match_the_e3_enums():
    """Verificado contra os enums reais da E3 — importar no teste é
    permitido; o que a fronteira veda é o import em produção."""
    from app.cognitive.models.enums import AccessibilityState, RevisionStatus

    assert {e.value for e in AccessibilityState} == KNOWN_ACCESSIBILITY_TOKENS
    assert {e.value for e in RevisionStatus} == KNOWN_REVISION_TOKENS
    assert RETRIEVABLE_ACCESSIBILITY_TOKENS < KNOWN_ACCESSIBILITY_TOKENS


def test_e461_pia_8033_still_means_only_duplicate_coid():
    objeto = _objetos(1)[0]
    manager, _, _, _, _ = _manager(objetos=[objeto, objeto])
    with pytest.raises(RetrievalDuplicateCoidError) as exc:
        _executar(manager)
    assert exc.value.code == "PIA-8033"


# ======================================================================
# E4.6.2 — Search Sequence & No-Reflection Contract
# ======================================================================
#
# Duas lacunas da E4.6.1:
#
#   F — o manager aceitava qualquer iterável, embora a porta declare
#       `Sequence`; generator, set e dict passavam, e a ordem podia
#       divergir da oficial da Search.
#   G — a validação defensiva usava `hasattr`/`getattr`, contrariando o
#       contrato que a própria porta declara.
#
#     SEQUENCE != ARBITRARY ITERABLE
#     UNORDERED COLLECTION != DETERMINISTIC SEARCH RESULT


class _PortaComRetorno:
    """Devolve o lote no tipo pedido, respeitando limit/offset."""

    def __init__(self, objetos, tipo: str) -> None:
        self.objetos = list(objetos)
        self.tipo = tipo
        self.chamadas: list[dict] = []

    def search(self, criteria, *, limit=None, offset=None):
        self.chamadas.append({"limit": limit, "offset": offset})
        inicio = offset or 0
        fatia = self.objetos[inicio : inicio + (limit or len(self.objetos))]
        if self.tipo == "generator":
            return (o for o in fatia)
        if self.tipo == "set":
            return set(fatia)
        if self.tipo == "dict":
            return {o: 1 for o in fatia}
        if self.tipo == "str":
            return "abc"
        if self.tipo == "bytes":
            return b"abc"
        if self.tipo == "tuple":
            return tuple(fatia)
        return fatia


def _manager_com_retorno(objetos, tipo: str):
    porta = _PortaComRetorno(objetos, tipo)
    manager = MemoryRetrievalManager(
        porta,
        GovernanceFalso(_resolucao(), eco_policy=False),
        ContextoFalso(),
        MembershipsFalsas(),
    )
    return manager, porta


# --- Defeito F: contrato de retorno ----------------------------------


@pytest.mark.parametrize("tipo", ["generator", "set", "dict"])
def test_e462_non_sequence_return_is_a_contract_violation(tipo):
    """Uma `Sequence` tem **ordem**, e a ordem da Search da E3 é o
    contrato determinístico do qual a paginação depende."""
    manager, _ = _manager_com_retorno(_objetos(5), tipo)
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager)
    assert exc.value.code == "PIA-8034"
    assert any("não é uma Sequence" in m for m in exc.value.reasons)


@pytest.mark.parametrize("tipo", ["str", "bytes"])
def test_e462_str_and_bytes_remain_invalid_even_being_sequences(tipo):
    """`str` e `bytes` implementam `Sequence`, mas são sequências de
    caracteres, não de objetos cognitivos."""
    manager, _ = _manager_com_retorno(_objetos(3), tipo)
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager)
    assert exc.value.code == "PIA-8034"


@pytest.mark.parametrize("tipo", ["list", "tuple"])
def test_e462_list_and_tuple_remain_accepted(tipo):
    objetos = _objetos(5)
    manager, _ = _manager_com_retorno(objetos, tipo)
    resultado = _executar(manager)
    assert resultado.coids == tuple(o.id for o in objetos)


def test_e462_official_search_order_is_preserved_exactly():
    """A E4.6 preserva a ordem oficial; não fabrica outra."""
    objetos = _objetos(12)
    manager, _ = _manager_com_retorno(objetos, "list")
    resultado = _executar(manager, limit=MAX_LIMIT)
    assert resultado.coids == tuple(o.id for o in objetos)


def test_e462_correction_does_not_materialize_or_sort_the_violation():
    """Converter um generator em `list`, ou ordenar um `set`, esconderia
    a violação e fabricaria uma ordem que a Search não produziu.

    Prova por ausência estrutural sobre o código executável: o coletor
    não constrói `list(...)` a partir do retorno nem o ordena.
    """
    executavel = _coletar_executavel()
    for proibido in ("list(bruto)", "sorted(bruto)", "sorted(lote)", ".sort("):
        assert proibido not in executavel, f"conversão/ordenação encontrada: {proibido}"


def test_e462_violation_is_detected_before_any_item_is_collected():
    """O retorno inválido é recusado antes de qualquer filtro ou coleta —
    não vira vista vazia."""
    manager, porta = _manager_com_retorno(_objetos(5), "set")
    with pytest.raises(RetrievalContractViolationError):
        _executar(manager)
    assert len(porta.chamadas) == 1


# --- Defeito G: ausência de reflexão ---------------------------------


def _coletar_executavel() -> str:
    """Código executável de `_coletar` e `_validar_hit`, sem docstrings.

    As docstrings desses métodos citam nominalmente `hasattr` e `getattr`
    ao explicar o que **não** fazem; comparar o texto bruto produziria
    falso positivo, o mesmo erro que a E4.3.1 corrigiu em `gv16`.
    """
    import app.memory.services.retrieval_manager as manager_mod

    arvore = ast.parse(pathlib.Path(manager_mod.__file__).read_text(encoding="utf-8"))
    partes = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name in {"_coletar", "_validar_hit"}:
            corpo = [
                filho
                for filho in no.body
                if not (
                    isinstance(filho, ast.Expr)
                    and isinstance(filho.value, ast.Constant)
                    and isinstance(filho.value.value, str)
                )
            ]
            no.body = corpo or [ast.Pass()]
            partes.append(ast.unparse(no))
    assert len(partes) == 2, "os dois métodos precisam existir para a inspeção valer"
    return "\n".join(partes)


@pytest.mark.parametrize(
    "proibido",
    ["hasattr(", "getattr(", "vars(", "__dict__", "inspect.", "cast(", "type: ignore"],
)
def test_e462_no_reflection_in_the_collector_or_the_hit_validator(proibido):
    """O contrato que a própria porta declara — e que a E4.6.1 violava
    enquanto o documentava."""
    assert proibido not in _coletar_executavel()


def test_e462_port_contract_and_executable_code_no_longer_contradict():
    """A porta declara "nenhum getattr, nenhuma reflexão". Agora o código
    executável cumpre o que a documentação afirma."""
    import app.memory.ports.retrieval as porta_mod

    fonte_da_porta = pathlib.Path(porta_mod.__file__).read_text(encoding="utf-8")
    assert "nenhuma reflexão" in fonte_da_porta
    executavel = _coletar_executavel()
    assert "getattr" not in executavel
    assert "hasattr" not in executavel


def test_e462_typed_field_access_still_diagnoses_invalid_types():
    """A validação continua defensiva, só que sem reflexão."""
    manager, _, _, _ = _manager_infiel(objetos=[ObjetoFalso(id=uuid.uuid4(), created_at="ontem")])
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager)
    assert any("created_at deve ser datetime" in m for m in exc.value.reasons)


def test_e462_typed_field_access_still_diagnoses_unknown_tokens():
    manager, _, _, _ = _manager_infiel(
        objetos=[ObjetoFalso(id=uuid.uuid4(), accessibility="quantum")]
    )
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager)
    assert any("não pertence ao vocabulário" in m for m in exc.value.reasons)


def test_e462_multiple_invalid_fields_still_accumulate_reasons():
    """Campos **presentes** e malformados continuam acumulando motivos;
    só a ausência de atributo é que passou a interromper na primeira."""
    manager, _, _, _ = _manager_infiel(
        objetos=[ObjetoFalso(id="nao-uuid", clid="nao-uuid", accessibility=123, created_at="ontem")]
    )
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager)
    assert len(exc.value.reasons) >= 4


def test_e462_hits_are_still_validated_before_the_filters():
    """Um hit inadmissível **e** malformado continua sendo violação, não
    exclusão silenciosa."""
    manager, _, _, _ = _manager_infiel(
        objetos=[ObjetoFalso(id=uuid.uuid4(), accessibility="inaccessible", created_at="ontem")]
    )
    with pytest.raises(RetrievalContractViolationError):
        _executar(manager)


def test_e462_pia_8033_remains_reserved_for_duplicate_coid():
    objeto = _objetos(1)[0]
    manager, _, _, _, _ = _manager(objetos=[objeto, objeto])
    with pytest.raises(RetrievalDuplicateCoidError) as exc:
        _executar(manager)
    assert exc.value.code == "PIA-8033"


def test_e462_real_search_engine_still_satisfies_the_port():
    """O `SearchEngine` da E3.8 devolve `list`, que é `Sequence` — a
    correção não o exclui."""
    from app.cognitive.services.search_engine import SearchEngine

    assert isinstance(SearchEngine.__new__(SearchEngine), CognitiveSearchPort)
    import inspect as _inspect
    from collections.abc import Sequence as _Sequence

    anotacao = _inspect.signature(SearchEngine.search).return_annotation
    assert anotacao.__origin__ is list
    assert issubclass(list, _Sequence)


# ======================================================================
# E4.3.4 — vínculo de contexto verificado no Retrieval
# ======================================================================
#
#     REQUESTED CONTEXT MUST EQUAL RESOLVED CONTEXT


def _manager_contexto_infiel(resolucao_infiel, objetos=()):
    """Governança que devolve resolução emitida sob OUTRO contexto."""
    porta = PortaFalsa(objetos)
    governanca = GovernanceFalso(resolucao_infiel, eco_policy=False, eco_contexto=False)
    associacoes = MembershipsFalsas()
    manager = MemoryRetrievalManager(porta, governanca, ContextoFalso(), associacoes)
    return manager, porta, associacoes


def _resolucao_para(
    *, domain_ids=(), actor_ref=None, purpose=None, outcome=GovernanceOutcome.ADMISSIBLE
):
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
            "safety_rationale": "proibido",
        }
    elif outcome is not GovernanceOutcome.NOT_APPLICABLE:
        campos |= {
            "policy_key": _POLICY_KEY,
            "policy_version": 1,
            "policy_id": uuid.uuid4(),
            "matched_rule_id": "r1",
        }
    return GovernanceResolution(**campos)


def test_e434r_resolution_for_another_domain_is_refused_before_search():
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    manager, porta, associacoes = _manager_contexto_infiel(
        _resolucao_para(domain_ids=(d2,)), objetos=_objetos(3)
    )
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager, context=_contexto(d1))
    assert exc.value.code == "PIA-8034"
    assert any("emitida para os domínios" in m for m in exc.value.reasons)
    assert porta.chamadas == []
    assert associacoes.chamadas == []


def test_e434r_resolution_for_another_actor_is_refused():
    manager, porta, _ = _manager_contexto_infiel(_resolucao_para(actor_ref="bob"))
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager, context=MemoryContext(actor_ref="ana"))
    assert any("emitida para o ator" in m for m in exc.value.reasons)
    assert porta.chamadas == []


def test_e434r_resolution_for_another_purpose_is_refused():
    manager, porta, _ = _manager_contexto_infiel(_resolucao_para(purpose="outro"))
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager, context=MemoryContext(purpose="curadoria"))
    assert any("emitida para o propósito" in m for m in exc.value.reasons)
    assert porta.chamadas == []


def test_e434r_every_divergence_is_accumulated():
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    manager, _, _ = _manager_contexto_infiel(
        _resolucao_para(domain_ids=(d2,), actor_ref="bob", purpose="outro")
    )
    with pytest.raises(RetrievalContractViolationError) as exc:
        _executar(manager, context=MemoryContext(domain_ids=(d1,), actor_ref="ana", purpose="p"))
    assert len(exc.value.reasons) >= 3


@pytest.mark.parametrize(
    "outcome",
    [
        GovernanceOutcome.ADMISSIBLE,
        GovernanceOutcome.INADMISSIBLE,
        GovernanceOutcome.NOT_APPLICABLE,
        GovernanceOutcome.PROHIBITED,
    ],
)
def test_e434r_mismatch_is_detected_in_every_outcome(outcome):
    """A recusa também recebeu uma pergunta — vincular vale para todos.

    NO LOCAL POLICY CONSULTED != NO CONTEXT RECEIVED
    """
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    manager, porta, associacoes = _manager_contexto_infiel(
        _resolucao_para(domain_ids=(d2,), outcome=outcome)
    )
    with pytest.raises(RetrievalContractViolationError):
        _executar(manager, context=_contexto(d1))
    assert porta.chamadas == []
    assert associacoes.chamadas == []


def test_e434r_matching_context_preserves_existing_behaviour():
    objetos = _objetos(3)
    manager, _, _, _, _ = _manager(objetos=objetos)
    resultado = _executar(manager)
    assert resultado.coids == tuple(o.id for o in objetos)


def test_e434r_result_constructor_refuses_a_mismatched_resolution():
    """O construtor público não contorna a garantia da fronteira."""
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ValueError, match="não foi emitida para este contexto"):
        MemoryRetrievalResult(
            context=_contexto(d1),
            governance_resolution=_resolucao_para(
                domain_ids=(d2,), outcome=GovernanceOutcome.NOT_APPLICABLE
            ),
            items=(),
            search_executed=False,
            limit=50,
            offset=0,
            has_more=None,
        )


def test_e434r_comparison_is_exact_without_normalization():
    """Ator `"Ana"` não é o mesmo que `"ana"`."""
    manager, porta, _ = _manager_contexto_infiel(_resolucao_para(actor_ref="Ana"))
    with pytest.raises(RetrievalContractViolationError):
        _executar(manager, context=MemoryContext(actor_ref="ana"))
    assert porta.chamadas == []
