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

from app.memory.errors.exceptions import RetrievalDuplicateCoidError
from app.memory.models.governance_enums import (
    CognitiveOperation,
    GovernanceEffect,
    GovernanceOutcome,
)
from app.memory.ports.retrieval import CognitiveObjectView, CognitiveSearchPort
from app.memory.schemas.governance import GovernanceResolution
from app.memory.schemas.memory_context import MemoryContext
from app.memory.schemas.retrieval import (
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
    MAX_LIMIT,
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

    def __init__(self, resolution: GovernanceResolution) -> None:
        self.resolution = resolution
        self.chamadas: list[dict] = []

    def resolve(self, *, descriptor, context, policy_key=None, moment=None):
        self.chamadas.append(
            {
                "descriptor": descriptor,
                "context": context,
                "policy_key": policy_key,
                "moment": moment,
            }
        )
        return self.resolution


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


def _resolucao(
    *,
    outcome: GovernanceOutcome = GovernanceOutcome.ADMISSIBLE,
    alternativas: tuple[str, ...] = (),
    capacidades: tuple[CriticalCapability, ...] = (),
) -> GovernanceResolution:
    """Resolução coerente com os invariantes congelados na E4.3.2."""
    if outcome is GovernanceOutcome.PROHIBITED:
        return GovernanceResolution(
            operation=CognitiveOperation.READ,
            outcome=outcome,
            blocked_capabilities=capacidades or (CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT,),
            admissible_alternatives=alternativas,
            safety_boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
            safety_rationale="proibido pela fronteira",
        )
    if outcome is GovernanceOutcome.NOT_APPLICABLE:
        return GovernanceResolution(
            operation=CognitiveOperation.READ,
            outcome=outcome,
            safety_boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
        )
    return GovernanceResolution(
        operation=CognitiveOperation.READ,
        outcome=outcome,
        policy_key="pk",
        policy_version=1,
        # `policy_id` faz parte da identidade tudo-ou-nada congelada na
        # E4.3.2: proveniência parcial parece proveniência.
        policy_id=uuid.uuid4(),
        matched_rule_id="r1",
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
    resultado = manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
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
        manager.retrieve(context=_contexto(), descriptor=_descritor(operacao), criteria=object())
    assert porta.chamadas == []
    assert governanca.chamadas == []


def test_r7_governance_manager_is_called_internally():
    manager, _, governanca, _, _ = _manager()
    contexto = _contexto()
    momento = datetime(2024, 6, 1, tzinfo=UTC)
    manager.retrieve(
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
    resultado = manager.retrieve(
        context=_contexto(dominio), descriptor=_descritor(), criteria=object()
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
    resultado = manager.retrieve(context=contexto, descriptor=_descritor(), criteria=object())
    assert resultado.execution_authorized is False
    assert porta.chamadas == []


def test_r13_denied_result_is_distinguishable_from_empty_search():
    """`DENIED != EMPTY RESULT` — e não há campo de contagem para vazar
    que o patrimônio está vazio sob os critérios recusados."""
    negado, _, _, _, _ = _manager(resolution=_resolucao(outcome=GovernanceOutcome.INADMISSIBLE))
    r_negado = negado.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
    vazio, _, _, _, _ = _manager(objetos=[])
    r_vazio = vazio.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())

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
    resultado = manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
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
    resultado = manager.retrieve(
        context=_contexto(d1, d2), descriptor=_descritor(), criteria=object()
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
    resultado = manager.retrieve(
        context=_contexto(d1, d2), descriptor=_descritor(), criteria=object()
    )
    assert resultado.coids == (objetos[0].id,)


def test_r17_context_without_domains_applies_no_domain_filter():
    objetos = _objetos(3)
    manager, _, _, _, associacoes = _manager(objetos=objetos)
    resultado = manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.coids == tuple(o.id for o in objetos)
    assert associacoes.chamadas == []


def test_r18_zero_domain_object_remains_valid_without_domain_filter():
    """`ZERO DOMAIN MEMBERSHIP != NONEXISTENCE` (E4.1)."""
    objetos = _objetos(2)
    manager, _, _, _, _ = _manager(objetos=objetos)
    sem_recorte = manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
    assert len(sem_recorte.items) == 2

    dominio = uuid.uuid4()
    manager2, _, _, _, _ = _manager(objetos=objetos, memberships={dominio: []})
    com_recorte = manager2.retrieve(
        context=_contexto(dominio), descriptor=_descritor(), criteria=object()
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
        manager.retrieve(
            context=_contexto(desconhecido), descriptor=_descritor(), criteria=object()
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
    resultado = manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.coids == (objetos[0].id,)
    assert resultado.items[0].accessibility == token


@pytest.mark.parametrize("token", ["inaccessible", "causally_extinct"])
def test_r22_r23_inaccessible_and_extinct_are_excluded(token):
    """`INACCESSIBLE != NONEXISTENT`; `CAUSALLY_EXTINCT != HISTORICALLY
    ERASED` — filtrados da vista, íntegros no patrimônio."""
    visivel = _objetos(1)[0]
    oculto = ObjetoFalso(id=uuid.uuid4(), accessibility=token, created_at=_BASE)
    manager, _, _, _, _ = _manager(objetos=[visivel, oculto])
    resultado = manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.coids == (visivel.id,)


def test_r24_soft_deleted_is_excluded_even_if_criteria_widen_include_deleted():
    """Filtro defensivo: auditoria histórica pertence à E3/E4.4."""
    visivel = _objetos(1)[0]
    apagado = ObjetoFalso(
        id=uuid.uuid4(), created_at=_BASE, deleted_at=datetime(2024, 5, 1, tzinfo=UTC)
    )
    manager, _, _, _, _ = _manager(objetos=[visivel, apagado])
    resultado = manager.retrieve(
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
    resultado = manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.coids == (atual.id, anterior.id)
    assert {i.revision_status for i in resultado.items} == {"current", "superseded"}


def test_r26_objects_sharing_a_clid_remain_distinct():
    clid = uuid.uuid4()
    objetos = [
        ObjetoFalso(id=uuid.uuid4(), clid=clid, created_at=_BASE + timedelta(minutes=i))
        for i in range(3)
    ]
    manager, _, _, _, _ = _manager(objetos=objetos)
    resultado = manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
    assert len(resultado.items) == 3
    assert len({i.clid for i in resultado.items}) == 1


def test_r27_consolidation_and_its_sources_remain_distinct():
    """`CONSOLIDATION != SOURCE REPLACEMENT` — a síntese não substitui
    nem esconde as fontes na vista."""
    fontes = _objetos(2)
    alvo = ObjetoFalso(id=uuid.uuid4(), created_at=_BASE + timedelta(minutes=5))
    manager, _, _, _, _ = _manager(objetos=[*fontes, alvo])
    resultado = manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.coids == (fontes[0].id, fontes[1].id, alvo.id)


def test_r27b_object_without_continuity_evidence_is_not_inadmissible():
    """`MISSING CONTINUITY EVIDENCE != RETRIEVAL INADMISSIBILITY` — a
    E4.6 nem consulta a E4.4 para compor a vista."""
    import inspect

    assinatura = set(inspect.signature(MemoryRetrievalManager.__init__).parameters)
    assert "persistence_manager" not in assinatura
    sem_clid = ObjetoFalso(id=uuid.uuid4(), clid=None, created_at=_BASE)
    manager, _, _, _, _ = _manager(objetos=[sem_clid])
    resultado = manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.coids == (sem_clid.id,)


# ======================================================================
# 28 a 32 — ordenação, paginação e erros
# ======================================================================


def test_r28_deterministic_order_is_preserved_and_never_reordered():
    objetos = _objetos(6)
    manager, _, _, _, _ = _manager(objetos=objetos)
    for _ in range(5):
        resultado = manager.retrieve(
            context=_contexto(), descriptor=_descritor(), criteria=object()
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

    pagina1 = manager.retrieve(
        context=_contexto(), descriptor=_descritor(), criteria=object(), limit=2, offset=0
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
        pagina = manager.retrieve(
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
    resultado = manager.retrieve(
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
            manager.retrieve(
                context=_contexto(), descriptor=_descritor(), criteria=object(), **kwargs
            )
    assert porta.chamadas == []


def test_r31c_default_limit_is_applied():
    manager, _, _, _, _ = _manager(objetos=_objetos(3))
    resultado = manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
    assert resultado.limit == DEFAULT_LIMIT


def test_r32_search_error_is_propagated_never_turned_into_an_empty_list():
    """Erro de busca não é resultado vazio, e não é aprendizado."""
    manager, _, _, _, _ = _manager(erro_busca=RuntimeError("falha na Search"))
    with pytest.raises(RuntimeError, match="falha na Search"):
        manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())


def test_r32b_duplicate_coid_from_the_port_raises_an_explicit_diagnostic():
    """Não escolher em silêncio qual ocorrência apresentar."""
    objeto = _objetos(1)[0]
    manager, _, _, _, _ = _manager(objetos=[objeto, objeto])
    with pytest.raises(RetrievalDuplicateCoidError) as exc:
        manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
    assert exc.value.code == "PIA-8033"
    assert exc.value.coid == objeto.id


def test_r32c_criteria_travel_opaque_to_the_port():
    """A E4.6 não inspeciona nem reconstrói os critérios da E3.8."""
    sentinela = object()
    manager, porta, _, _, _ = _manager(objetos=_objetos(2))
    manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=sentinela)
    assert porta.chamadas
    assert all(c["criteria"] is sentinela for c in porta.chamadas)


# ======================================================================
# 33 a 38 — fronteiras estruturais
# ======================================================================


def test_r33_no_orm_instance_escapes_in_the_result():
    objetos = _objetos(2)
    manager, _, _, _, _ = _manager(objetos=objetos)
    resultado = manager.retrieve(context=_contexto(), descriptor=_descritor(), criteria=object())
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
    manager.retrieve(
        context=_contexto(), descriptor=_descritor(), criteria=object(), limit=MAX_LIMIT
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
    with pytest.raises(ValueError, match="limit >= 1"):
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
        manager.retrieve(context=_contexto(), descriptor="nao-e-descritor", criteria=object())
    assert porta.chamadas == []
    assert governanca.chamadas == []
