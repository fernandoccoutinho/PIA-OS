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


# ======================================================================
# E4.2.1 — invariantes do value object em QUALQUER construção pública
#
# Defeito corrigido: `frozen=True` protege a *referência*, não o
# *conteúdo*. Antes de E4.2.1 os invariantes viviam apenas em
# `build()`, e o construtor direto — API pública de qualquer dataclass
# — os contornava por completo.
# ======================================================================


def test_e421_direct_construction_with_a_list_stores_a_tuple():
    """(1) Construção direta com lista guarda `tuple`, não a lista.

    Este era o defeito de origem: `MemoryContext(domain_ids=[...])`
    guardava a própria lista.
    """
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    contexto = MemoryContext(domain_ids=[d1, d2])

    assert isinstance(contexto.domain_ids, tuple)
    assert set(contexto.domain_ids) == {d1, d2}


def test_e421_original_list_is_isolated_from_the_context():
    """(2) Mutar a lista original não altera o contexto.

    O sintoma mais grave do defeito: um objeto que o contrato declara
    imutável mudava de conteúdo depois de construído, pelas costas de
    quem o segurava.
    """
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    origem = [d1, d2]

    contexto = MemoryContext(domain_ids=origem)
    origem.append(uuid.uuid4())
    origem.clear()

    assert len(contexto.domain_ids) == 2
    assert set(contexto.domain_ids) == {d1, d2}


def test_e421_direct_construction_canonicalizes_and_deduplicates():
    """(3) Ordenação determinística e desduplicação no construtor."""
    d1, d2, d3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    contexto = MemoryContext(domain_ids=[d3, d1, d2, d1, d3])

    assert contexto.domain_ids == tuple(sorted({d1, d2, d3}, key=str))
    assert len(contexto.domain_ids) == 3


def test_e421_direct_construction_equals_build():
    """(4) Construtor direto e `build()` produzem o mesmo objeto.

    Comparação feita com uma ordem de entrada **garantidamente**
    diferente da canônica, para que a igualdade não passe por acaso.
    """
    ids = [uuid.uuid4() for _ in range(4)]
    canonico = sorted(ids, key=str)
    desordenado = list(reversed(canonico))
    assert desordenado != canonico, "a entrada precisa diferir da ordem canônica"

    direto = MemoryContext(domain_ids=desordenado, purpose="p", session_id="s")
    construido = MemoryContext.build(domain_ids=desordenado, purpose="p", session_id="s")

    assert direto == construido
    assert direto.domain_ids == tuple(canonico)


def test_e421_context_is_hashable_in_every_construction():
    """(5) `hash()` funciona — inclusive vindo de lista.

    Com uma lista dentro, `hash()` levantava `TypeError`, quebrando a
    igualdade estrutural de que o módulo depende para comparar
    perspectivas.
    """
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    a = MemoryContext(domain_ids=[d1, d2])
    b = MemoryContext.build(domain_ids=[d2, d1])

    assert isinstance(hash(a), int)
    assert hash(a) == hash(b)
    assert len({a, b}) == 1, "contextos equivalentes colapsam num conjunto"
    assert {a: "vista"}[b] == "vista", "utilizável como chave de dicionário"


def test_e421_non_uuid_domain_is_rejected():
    """(6) Só `uuid.UUID` entra em `domain_ids`."""
    with pytest.raises(TypeError, match="uuid.UUID"):
        MemoryContext(domain_ids=["nao-e-uuid"])
    with pytest.raises(TypeError, match="uuid.UUID"):
        MemoryContext(domain_ids=[uuid.uuid4(), 42])
    with pytest.raises(TypeError, match="uuid.UUID"):
        MemoryContext.build(domain_ids=[str(uuid.uuid4())])

    # Uma string é iterável, mas iterar caractere a caractere é sempre
    # engano do chamador — rejeitada como tipo, não silenciosamente
    # expandida.
    with pytest.raises(TypeError, match="iterável"):
        MemoryContext(domain_ids=str(uuid.uuid4()))
    with pytest.raises(TypeError, match="iterável"):
        MemoryContext(domain_ids=123)


@pytest.mark.parametrize("campo", ["session_id", "actor_ref", "purpose"])
def test_e421_blank_and_wrong_typed_text_fields_are_rejected(campo):
    """(7) `None` ou `str` não vazia — nada além disso.

    Ausência é válida e silenciosa (`ValueError` nunca é levantado por
    campo omitido); presença vazia é engano de valor; tipo errado é
    engano de tipo. Os dois diagnósticos permanecem distintos.
    """
    for branco in ("", "   ", "\t\n"):
        with pytest.raises(ValueError, match=campo):
            MemoryContext(**{campo: branco})
        with pytest.raises(ValueError, match=campo):
            MemoryContext.build(**{campo: branco})

    for tipo_errado in (123, 1.5, uuid.uuid4(), ["x"], True):
        with pytest.raises(TypeError, match=campo):
            MemoryContext(**{campo: tipo_errado})

    assert getattr(MemoryContext(**{campo: None}), campo) is None
    assert getattr(MemoryContext(**{campo: "válido"}), campo) == "válido"


def test_e421_invariants_survive_derive_and_without_domains():
    """(8) `derive()` e `without_domains()` preservam os invariantes.

    `without_domains()` usa `dataclasses.replace`, que reexecuta
    `__post_init__` — é por isso que impor a regra ali, e não em
    `build()`, fecha todos os caminhos de uma vez.
    """
    d1, d2, d3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    base = MemoryContext(domain_ids=[d2, d1], session_id="s1")

    # derive com lista mutável e desordenada
    origem = [d3, d1, d3]
    derivado = base.derive(domain_ids=origem)
    origem.append(uuid.uuid4())

    assert isinstance(derivado.domain_ids, tuple)
    assert derivado.domain_ids == tuple(sorted({d1, d3}, key=str))
    assert isinstance(hash(derivado), int)
    assert base.domain_ids == tuple(sorted({d1, d2}, key=str)), "base intacta"

    # derive rejeita entrada inválida em vez de aceitá-la em silêncio
    with pytest.raises(TypeError, match="uuid.UUID"):
        base.derive(domain_ids=["x"])
    with pytest.raises(ValueError, match="purpose"):
        base.derive(purpose="   ")

    # without_domains preserva tipo, hashabilidade e demais campos
    vazio = base.without_domains()
    assert vazio.domain_ids == ()
    assert isinstance(vazio.domain_ids, tuple)
    assert isinstance(hash(vazio), int)
    assert vazio.session_id == "s1"
    assert base.domain_ids != ()


def test_e421_replace_cannot_reintroduce_a_mutable_container():
    """`dataclasses.replace` também passa por `__post_init__`.

    Fecha a última porta pública: não existe caminho que devolva um
    `MemoryContext` com lista dentro.
    """
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    base = MemoryContext(domain_ids=[d1])

    reposto = dataclasses.replace(base, domain_ids=[d2, d1, d2])

    assert isinstance(reposto.domain_ids, tuple)
    assert reposto.domain_ids == tuple(sorted({d1, d2}, key=str))
    assert isinstance(hash(reposto), int)

    with pytest.raises(TypeError, match="uuid.UUID"):
        dataclasses.replace(base, domain_ids=["x"])


def test_e421_explicit_none_domain_ids_is_rejected():
    """`domain_ids=None` explícito é engano do chamador.

    O default do campo é `()` e `build()` normaliza ausência, então um
    `None` explícito contradiz a anotação `tuple[uuid.UUID, ...]`.
    Aceitá-lo como "vazio" seria a mesma leniência que produziu o
    defeito de E4.2.1.
    """
    with pytest.raises(TypeError, match="iterável"):
        MemoryContext(domain_ids=None)

    # Ausência continua sendo expressa das duas formas legítimas.
    assert MemoryContext().domain_ids == ()
    assert MemoryContext.build(domain_ids=None).domain_ids == ()
