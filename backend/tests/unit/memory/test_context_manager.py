"""
E4.2 — testes unitários de `MemoryContext` e `ContextManager`.

Cobrem CT1–CT12 e CT18–CT20 do §39 do prompt canônico. Os gates que
exigem banco real (zero escritas, patrimônio inalterado) vivem em
`tests/integration/memory/`.
"""

import dataclasses
import inspect
import uuid

import pytest

from app.memory.models.memory_domain import MemoryDomain
from app.memory.models.memory_domain_membership import MemoryDomainMembership
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.context_manager import ContextManager


def _ctx() -> ContextManager:
    return ContextManager()


# ======================================================================
# CT1–CT4 — o que contexto NÃO é
# ======================================================================


def test_ct1_context_is_not_a_memory_domain():
    """CT1 — `CONTEXT != DOMAIN`.

    Um domínio é entidade persistida com identidade; um contexto é
    perspectiva efêmera que apenas **declara** domínios. Declarar não
    é pertencer.
    """
    contexto = _ctx().build(domain_ids=[uuid.uuid4()])

    assert not isinstance(contexto, MemoryDomain)
    assert not hasattr(contexto, "__tablename__")
    assert not hasattr(contexto, "name")
    assert MemoryDomain.__table__ is not None  # domínio é persistido; contexto não


def test_ct2_context_is_not_a_cognitive_object():
    """CT2 — `CONTEXT != COGNITIVE OBJECT`.

    Sem COID, sem CLID, sem accessibility, sem revision_status: uma
    perspectiva não é patrimônio.
    """
    contexto = _ctx().build()
    for atributo in ("coid", "id", "clid", "accessibility", "revision_status"):
        assert not hasattr(contexto, atributo), f"contexto não deve ter {atributo}"


def test_ct3_context_is_not_a_session():
    """CT3 — `CONTEXT != SESSION`; `session_id != context identity`.

    O mesmo contexto semântico existe em sessões diferentes, e a mesma
    sessão produz contextos diferentes. Nenhuma das duas coisas seria
    possível se sessão fosse identidade.
    """
    manager = _ctx()
    d1 = uuid.uuid4()

    mesma_perspectiva_a = manager.build(domain_ids=[d1], session_id="s1")
    mesma_perspectiva_b = manager.build(domain_ids=[d1], session_id="s2")
    assert mesma_perspectiva_a != mesma_perspectiva_b

    outra_na_mesma_sessao = manager.build(domain_ids=[uuid.uuid4()], session_id="s1")
    assert outra_na_mesma_sessao != mesma_perspectiva_a

    # E contexto sem sessão nenhuma é perfeitamente válido.
    assert manager.build(domain_ids=[d1]).session_id is None


def test_ct4_context_is_not_a_policy():
    """CT4 — `CONTEXT != POLICY`.

    Contexto diz *de onde se olha*; policy diz *o que é permitido
    ver*. O contexto não carrega regra, permissão, efeito nem decisão.
    """
    contexto = _ctx().build(actor_ref="ana", purpose="revisão")
    campos = {f.name for f in dataclasses.fields(contexto)}

    assert campos == {"domain_ids", "session_id", "actor_ref", "purpose"}
    for proibido in ("rules", "effect", "permissions", "allow", "deny", "role", "acl"):
        assert proibido not in campos


# ======================================================================
# CT5–CT7 — determinismo, imutabilidade, variantes
# ======================================================================


def test_ct5_construction_is_deterministic_and_order_independent():
    """CT5 — mesma entrada, representação estrutural equivalente.

    A ordem em que os domínios são informados não é informação
    semântica; tratá-la como se fosse tornaria contextos idênticos
    artificialmente distintos. Duplicatas também colapsam.
    """
    manager = _ctx()
    d1, d2, d3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    a = manager.build(domain_ids=[d3, d1, d2], purpose="p")
    b = manager.build(domain_ids=[d1, d2, d3], purpose="p")
    c = manager.build(domain_ids=[d2, d3, d1, d1, d2], purpose="p")

    assert a == b == c
    assert manager.equivalent(a, c)
    assert len(a.domain_ids) == 3
    assert a.domain_ids == tuple(sorted({d1, d2, d3}, key=str))
    assert hash(a) == hash(b), "igualdade estrutural precisa valer para hash também"


def test_ct6_context_is_frozen():
    """CT6 — imutável. Perspectiva não se altera em silêncio."""
    contexto = _ctx().build(domain_ids=[uuid.uuid4()], purpose="p")

    with pytest.raises(dataclasses.FrozenInstanceError):
        contexto.purpose = "outro"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        contexto.domain_ids = ()  # type: ignore[misc]


def test_ct7_derive_does_not_mutate_the_base_context():
    """CT7 — variante explícita; base intacta.

    `C1 → C2`, nunca "mutar C1". É o que torna auditável sob qual
    perspectiva cada decisão futura terá sido tomada.
    """
    manager = _ctx()
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    base = manager.build(domain_ids=[d1], session_id="s1", purpose="original")

    variante = manager.derive(base, domain_ids=[d2], purpose="derivado")

    assert base.domain_ids == (d1,)
    assert base.purpose == "original"
    assert variante.domain_ids == (d2,)
    assert variante.purpose == "derivado"
    assert variante.session_id == "s1", "campos não informados são herdados"
    assert base != variante


def test_ct7b_without_domains_produces_an_empty_scope_variant():
    """`derive()` não expressa remoção (um `None` significa "não mexa"),
    então limpar domínios tem operação própria e explícita."""
    manager = _ctx()
    base = manager.build(domain_ids=[uuid.uuid4()], session_id="s1")

    vazio = base.without_domains()

    assert base.domain_ids != ()
    assert vazio.domain_ids == ()
    assert vazio.session_id == "s1"


# ======================================================================
# CT10 — contexto vazio
# ======================================================================


def test_ct10_empty_context_is_valid():
    """CT10 — contexto vazio é estado válido, não degenerado.

    ```
    empty context != no memory
    empty context != all authorized
    ```

    Ele não afirma nada sobre o patrimônio e não concede nada;
    governança futura continua decidindo.
    """
    contexto = _ctx().build()

    assert contexto.is_empty
    assert contexto.domain_ids == ()
    assert contexto.session_id is None
    assert contexto.actor_ref is None
    assert contexto.purpose is None
    assert contexto == MemoryContext()


def test_ct10b_a_context_with_any_dimension_is_not_empty():
    manager = _ctx()
    assert not manager.build(domain_ids=[uuid.uuid4()]).is_empty
    assert not manager.build(session_id="s").is_empty
    assert not manager.build(actor_ref="a").is_empty
    assert not manager.build(purpose="p").is_empty


# ======================================================================
# CT11–CT12 — sessão e domínio produzem contextos distintos
# ======================================================================


def test_ct11_same_domain_different_session_yields_distinct_contexts():
    """CT11 — mesmo domínio + sessões diferentes ⇒ contextos distintos."""
    manager = _ctx()
    d1 = uuid.uuid4()

    a = manager.build(domain_ids=[d1], session_id="s1")
    b = manager.build(domain_ids=[d1], session_id="s2")

    assert a != b
    assert a.domain_ids == b.domain_ids


def test_ct12_same_session_different_domain_yields_distinct_contexts():
    """CT12 — mesma sessão + domínios diferentes ⇒ contextos distintos."""
    manager = _ctx()

    a = manager.build(domain_ids=[uuid.uuid4()], session_id="s1")
    b = manager.build(domain_ids=[uuid.uuid4()], session_id="s1")

    assert a != b
    assert a.session_id == b.session_id


# ======================================================================
# CT18–CT20 — fronteiras: nenhuma autoridade, nenhum ranking, nenhuma busca
# ======================================================================


def test_ct18_actor_does_not_imply_authorization():
    """CT18 — `ACTOR PRESENCE != AUTHORIZATION`.

    Verificado por **ausência estrutural**: o módulo não expõe nenhuma
    API capaz de decidir acesso. Governança é E4.3.
    """
    manager = _ctx()
    contexto = manager.build(actor_ref="ana", domain_ids=[uuid.uuid4()], purpose="p")

    assert contexto.actor_ref == "ana"

    proibidos = {
        "allow",
        "deny",
        "can",
        "can_access",
        "authorize",
        "is_authorized",
        "permit",
        "check_permission",
        "resolve_policy",
        "has_role",
    }
    for alvo in (ContextManager, MemoryContext):
        expostos = {nome for nome, _ in inspect.getmembers(alvo) if not nome.startswith("_")}
        assert not (
            expostos & proibidos
        ), f"{alvo.__name__} expõe API de autorização: {expostos & proibidos}"


def test_ct19_purpose_does_not_imply_ranking():
    """CT19 — `purpose` não ranqueia nada.

    Nenhum score existe: nem no value object, nem no manager.
    """
    contexto = _ctx().build(purpose="urgente e muito importante")

    campos = {f.name for f in dataclasses.fields(contexto)}
    for proibido in ("relevance_score", "importance_score", "context_score", "weight", "rank"):
        assert proibido not in campos

    expostos = {nome for nome, _ in inspect.getmembers(ContextManager) if not nome.startswith("_")}
    for proibido in ("rank", "score", "sort_by_relevance", "top_k"):
        assert proibido not in expostos


def test_ct20_context_does_not_execute_search():
    """CT20 — E4.2 não é Memory Retrieval (E4.6).

    Nenhuma execução de consulta, `top_k`, busca semântica ou
    recuperação. O manager também não conhece `SearchEngine`.
    """
    expostos = {nome for nome, _ in inspect.getmembers(ContextManager) if not nome.startswith("_")}
    for proibido in ("search", "query", "retrieve", "execute", "fetch_objects", "resolve_view"):
        assert proibido not in expostos

    fonte = inspect.getsource(ContextManager)
    for proibido in ("SearchEngine", "SearchCriteria", "SearchRepository"):
        assert proibido not in fonte, f"ContextManager não deve conhecer {proibido}"


# ======================================================================
# Contrato mínimo e precondições
# ======================================================================


def test_ct21_blank_strings_are_a_caller_precondition_error():
    """String presente porém em branco é precondição violada.

    Ausência (`None`) é válida e silenciosa; presença vazia é engano
    do chamador. `ValueError`, mesma convenção de `CoidManager`
    (E3.2) e do `trace_id` em branco do `IndexManager` (E3.7).
    """
    manager = _ctx()
    for campo in ("session_id", "actor_ref", "purpose"):
        with pytest.raises(ValueError, match=campo):
            manager.build(**{campo: "   "})
        assert getattr(manager.build(**{campo: None}), campo) is None


def test_ct22_context_contract_is_minimal():
    """O contrato não cresceu por antecipação.

    `task_ref` e `scope` aparecem na lista ilustrativa da E4.0, mas
    nenhum consumidor os exige — ficam deferidos (E4.2 §3, Q12/Q13).
    """
    campos = {f.name for f in dataclasses.fields(MemoryContext)}
    assert campos == {"domain_ids", "session_id", "actor_ref", "purpose"}
    for proibido in (
        "task_ref",
        "task",
        "scope",
        "accessibility",
        "context_id",
        "metadata",
        "policy_ref",
        "openai_context",
        "anthropic_session",
        "model_context_window",
        "provider_id",
        "transcript",
    ):
        assert proibido not in campos, f"campo não autorizado: {proibido}"


def test_ct23_declaring_a_domain_is_not_membership():
    """`domain in context != object added to domain`.

    Contexto não conhece `MemoryDomainMembership` e não tem como
    criá-lo.
    """
    fonte = inspect.getsource(ContextManager) + inspect.getsource(MemoryContext)
    assert "MemoryDomainMembership" not in fonte
    assert MemoryDomainMembership.__tablename__ == "memory_domain_memberships"

    expostos = {nome for nome, _ in inspect.getmembers(ContextManager) if not nome.startswith("_")}
    for proibido in ("add_object", "add_membership", "classify"):
        assert proibido not in expostos


def test_ct24_validate_without_repository_is_a_caller_error_not_a_silent_pass():
    """Validar sem repositório não pode "passar" silenciosamente.

    Um contexto com domínios declarados e nenhuma forma de verificá-los
    é ambíguo — e o pior desfecho seria devolver "válido" por não ter
    como checar.
    """
    manager = _ctx()
    with pytest.raises(ValueError, match="MemoryDomainRepository"):
        manager.validate(manager.build(domain_ids=[uuid.uuid4()]))

    # Já um contexto sem domínios não tem o que validar — e isso é
    # ausência de trabalho, não ausência de verificação.
    vazio = manager.build(session_id="s1")
    assert manager.validate(vazio) is vazio
