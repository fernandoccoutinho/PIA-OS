"""
E4.3 — testes unitários de governança.

Cobrem o vocabulário fechado, os invariantes das regras tipadas, a
precedência `DENY_OVERRIDES` e a explicabilidade da decisão. Os
requisitos que exigem banco (versionamento, vigência, concorrência,
zero escritas na avaliação) vivem em `tests/integration/memory/`.
"""

import dataclasses
import inspect
import uuid

import pytest

from app.memory.models.governance_enums import (
    CognitiveOperation,
    GovernanceEffect,
    GovernanceOutcome,
)
from app.memory.models.governance_policy import GovernancePolicy
from app.memory.schemas.governance import GovernanceDecision, GovernanceRule
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.governance_manager import GovernanceManager


def _executable_source(alvo) -> str:
    """Código-fonte sem docstrings — ver `test_gv16` (E4.3.1)."""
    import ast

    arvore = ast.parse(inspect.getsource(alvo))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant):
            no.value = ast.Constant(value="")
    return ast.unparse(arvore)


def _policy(rules: tuple[GovernanceRule, ...], *, key: str = "p", version: int = 1):
    """Policy em memória — não persistida; basta para avaliar."""
    policy = GovernancePolicy(
        policy_key=key,
        version=version,
        rules=GovernancePolicy.serialize_rules(rules),
    )
    policy.id = uuid.uuid4()
    return policy


def _evaluate(rules, operation, context, **kw):
    manager = GovernanceManager(policy_repository=None)  # type: ignore[arg-type]
    return manager.evaluate(policy=_policy(rules, **kw), operation=operation, context=context)


# ======================================================================
# Vocabulário e invariantes das regras
# ======================================================================


def test_gv1_cognitive_operation_vocabulary_is_closed():
    """O vocabulário de operações é fechado e não foi inventado.

    São as sete que `E4_GOVERNANCE_BOUNDARIES.md` §9 lista como o que
    governança pode controlar. Ampliar exige EDR.
    """
    assert {op.value for op in CognitiveOperation} == {
        "read",
        "reference",
        "derive",
        "transform",
        "expose",
        "synchronize",
        "consolidate",
    }


def test_gv2_rule_invariants_hold_in_direct_construction():
    """Invariantes valem no construtor direto — lição de E4.2.1.

    Conjuntos viram `frozenset`, listas mutáveis não sobrevivem, e a
    regra é hashable.
    """
    d1 = uuid.uuid4()
    origem_dom = [d1, d1]
    origem_ops = [CognitiveOperation.READ, CognitiveOperation.READ]

    regra = GovernanceRule(
        rule_id="r1",
        effect=GovernanceEffect.ADMIT,
        operations=origem_ops,  # type: ignore[arg-type]
        domain_ids=origem_dom,  # type: ignore[arg-type]
    )
    origem_dom.append(uuid.uuid4())
    origem_ops.append(CognitiveOperation.EXPOSE)

    assert isinstance(regra.operations, frozenset)
    assert isinstance(regra.domain_ids, frozenset)
    assert regra.domain_ids == frozenset({d1})
    assert regra.operations == frozenset({CognitiveOperation.READ})
    assert isinstance(hash(regra), int)


@pytest.mark.parametrize(
    "kwargs,exc",
    [
        ({"rule_id": ""}, ValueError),
        ({"rule_id": "   "}, ValueError),
        ({"rule_id": 123}, TypeError),
        ({"effect": "admit"}, TypeError),
        ({"operations": ["read"]}, TypeError),
        ({"operations": "read"}, TypeError),
        ({"domain_ids": ["x"]}, TypeError),
        ({"actor_refs": [""]}, ValueError),
        ({"actor_refs": [1]}, TypeError),
        ({"actor_refs": "ana"}, TypeError),
        ({"purposes": ["  "]}, ValueError),
    ],
)
def test_gv3_malformed_rules_are_rejected(kwargs, exc):
    """Valor inválido → `ValueError`; tipo inválido → `TypeError`.

    Diagnósticos distintos, como em E4.2.1 — não se mascaram.
    """
    base = {"rule_id": "r1", "effect": GovernanceEffect.ADMIT}
    base.update(kwargs)
    with pytest.raises(exc):
        GovernanceRule(**base)


def test_gv4_empty_dimension_means_unrestricted_not_unmatchable():
    """Dimensão vazia é curinga, não "não casa com nada".

    Sem isso seria impossível escrever "qualquer ator, neste domínio,
    para leitura" sem enumerar todos os atores.
    """
    d1 = uuid.uuid4()
    regra = GovernanceRule(rule_id="r", effect=GovernanceEffect.ADMIT)

    assert regra.matches(
        operation=CognitiveOperation.READ,
        domain_ids=frozenset({d1}),
        actor_ref="ana",
        purpose="p",
    )
    assert regra.matches(
        operation=CognitiveOperation.EXPOSE,
        domain_ids=frozenset(),
        actor_ref=None,
        purpose=None,
    )


def test_gv5_domains_match_by_intersection():
    """Domínios casam por interseção, não por igualdade.

    Um contexto multi-domínio `{D1, D2}` casa com uma regra sobre
    `{D1}` — exigir igualdade tornaria as regras inúteis para qualquer
    contexto com mais de um domínio, e a E4.2 congelou que contexto
    apenas *declara* o conjunto.
    """
    d1, d2, d3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    regra = GovernanceRule(rule_id="r", effect=GovernanceEffect.ADMIT, domain_ids=frozenset({d1}))

    assert regra.matches(
        operation=CognitiveOperation.READ,
        domain_ids=frozenset({d1, d2}),
        actor_ref=None,
        purpose=None,
    )
    assert not regra.matches(
        operation=CognitiveOperation.READ,
        domain_ids=frozenset({d2, d3}),
        actor_ref=None,
        purpose=None,
    )


def test_gv6_absent_context_dimension_does_not_match_a_restricting_rule():
    """Ausência de informação não vale como informação.

    Uma regra sobre `actor_refs={"ana"}` não se aplica a um contexto
    **sem** ator. O contrário faria o silêncio casar com qualquer
    restrição — e ausência de ator é precisamente o caso em que não se
    deve concluir nada.
    """
    regra = GovernanceRule(
        rule_id="r", effect=GovernanceEffect.ADMIT, actor_refs=frozenset({"ana"})
    )
    assert not regra.matches(
        operation=CognitiveOperation.READ,
        domain_ids=frozenset(),
        actor_ref=None,
        purpose=None,
    )
    assert regra.matches(
        operation=CognitiveOperation.READ,
        domain_ids=frozenset(),
        actor_ref="ana",
        purpose=None,
    )


# ======================================================================
# Avaliação
# ======================================================================


def test_gv7_three_outcomes_are_distinguishable():
    """(7) Admissível, inadmissível e não aplicável são distintos.

    Sem `NOT_APPLICABLE`, "ninguém decidiu sobre isto" seria
    indistinguível de "alguém proibiu" — o mesmo colapso diagnóstico
    que a E3.12 provou não cometer.
    """
    ctx = MemoryContext.build(actor_ref="ana")
    admite = GovernanceRule(
        rule_id="ok", effect=GovernanceEffect.ADMIT, operations=frozenset({CognitiveOperation.READ})
    )
    nega = GovernanceRule(
        rule_id="no", effect=GovernanceEffect.DENY, operations=frozenset({CognitiveOperation.READ})
    )

    assert _evaluate((admite,), CognitiveOperation.READ, ctx).outcome is (
        GovernanceOutcome.ADMISSIBLE
    )
    assert _evaluate((nega,), CognitiveOperation.READ, ctx).outcome is (
        GovernanceOutcome.INADMISSIBLE
    )
    assert _evaluate((admite,), CognitiveOperation.EXPOSE, ctx).outcome is (
        GovernanceOutcome.NOT_APPLICABLE
    )


def test_gv8_actor_present_without_applicable_rule_grants_nothing():
    """(6) `actor_ref` presente, sem regra aplicável, não concede.

    ```
    ACTOR PRESENCE != AUTHORIZATION
    ```

    O resultado é `NOT_APPLICABLE`, e `is_admissible` é `False` —
    ausência de regra jamais vira permissão.
    """
    ctx = MemoryContext.build(actor_ref="ana", purpose="qualquer", domain_ids=[uuid.uuid4()])
    decisao = _evaluate((), CognitiveOperation.READ, ctx)

    assert decisao.outcome is GovernanceOutcome.NOT_APPLICABLE
    assert decisao.is_admissible is False
    assert decisao.matched_rule_id is None
    assert decisao.context_actor_ref == "ana"


def test_gv9_deny_overrides_admit():
    """Precedência `DENY_OVERRIDES`, por mais regras que admitam.

    Uma restrição que desaparece porque outra regra permite não é
    restrição.
    """
    ctx = MemoryContext.build(actor_ref="ana")
    regras = (
        GovernanceRule(rule_id="a1", effect=GovernanceEffect.ADMIT),
        GovernanceRule(rule_id="a2", effect=GovernanceEffect.ADMIT),
        GovernanceRule(rule_id="d1", effect=GovernanceEffect.DENY),
        GovernanceRule(rule_id="a3", effect=GovernanceEffect.ADMIT),
    )

    decisao = _evaluate(regras, CognitiveOperation.READ, ctx)
    assert decisao.outcome is GovernanceOutcome.INADMISSIBLE
    assert decisao.matched_rule_id == "d1"
    assert "DENY_OVERRIDES" in decisao.reason


def test_gv10_decision_carries_policy_version_and_rationale():
    """(8) A decisão registra policy, versão e fundamento."""
    ctx = MemoryContext.build(domain_ids=[uuid.uuid4()], actor_ref="ana", purpose="revisão")
    regra = GovernanceRule(rule_id="r-fundante", effect=GovernanceEffect.ADMIT)

    decisao = _evaluate((regra,), CognitiveOperation.DERIVE, ctx, key="minha-policy", version=7)

    assert decisao.policy_key == "minha-policy"
    assert decisao.policy_version == 7
    assert isinstance(decisao.policy_id, uuid.UUID)
    assert decisao.operation is CognitiveOperation.DERIVE
    assert decisao.matched_rule_id == "r-fundante"
    assert decisao.context_domain_ids == ctx.domain_ids
    assert decisao.context_actor_ref == "ana"
    assert decisao.context_purpose == "revisão"
    assert decisao.reason


def test_gv11_same_input_yields_structurally_equivalent_decision():
    """(9) Mesma entrada, decisão estruturalmente equivalente.

    A ordem em que as regras são declaradas não pode mudar o resultado
    nem o fundamento citado — a avaliação ordena canonicamente.
    """
    ctx = MemoryContext.build(actor_ref="ana")
    a = GovernanceRule(rule_id="a", effect=GovernanceEffect.ADMIT)
    b = GovernanceRule(rule_id="b", effect=GovernanceEffect.ADMIT)

    primeira = _evaluate((a, b), CognitiveOperation.READ, ctx)
    segunda = _evaluate((b, a), CognitiveOperation.READ, ctx)

    assert primeira.outcome == segunda.outcome
    assert primeira.matched_rule_id == segunda.matched_rule_id == "a"
    assert dataclasses.replace(primeira, policy_id=segunda.policy_id) == segunda


def test_gv12_different_contexts_can_yield_different_decisions():
    """(10) Contextos diferentes podem decidir diferente.

    É o ponto inteiro da governança contextual — e a contrapartida do
    `COUT1` da E4.2: contexto muda a vista, não o patrimônio.
    """
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    regra = GovernanceRule(
        rule_id="so-d1", effect=GovernanceEffect.ADMIT, domain_ids=frozenset({d1})
    )

    em_d1 = _evaluate((regra,), CognitiveOperation.READ, MemoryContext.build(domain_ids=[d1]))
    em_d2 = _evaluate((regra,), CognitiveOperation.READ, MemoryContext.build(domain_ids=[d2]))

    assert em_d1.outcome is GovernanceOutcome.ADMISSIBLE
    assert em_d2.outcome is GovernanceOutcome.NOT_APPLICABLE


def test_gv13_denied_never_implies_nonexistence():
    """(12) `DENIED != NONEXISTENT`.

    A decisão diz explicitamente que não implica inexistência, em vez
    de deixar isso para a inferência de cada consumidor futuro.
    """
    ctx = MemoryContext.build(actor_ref="ana")
    nega = GovernanceRule(rule_id="d", effect=GovernanceEffect.DENY)

    decisao = _evaluate((nega,), CognitiveOperation.READ, ctx)

    assert decisao.outcome is GovernanceOutcome.INADMISSIBLE
    assert decisao.implies_nonexistence is False
    assert _evaluate((), CognitiveOperation.READ, ctx).implies_nonexistence is False
    for proibido in ("not_found", "missing", "nonexistent", "deleted"):
        assert proibido not in decisao.reason.lower()


def test_gv14_rules_round_trip_deterministically():
    """Serialização canônica: mesmo conjunto, mesmos bytes.

    `frozenset` não tem ordem estável entre execuções; sem
    canonicalização, comparar duas versões viraria loteria.
    """
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    regras = (
        GovernanceRule(
            rule_id="b",
            effect=GovernanceEffect.DENY,
            operations=frozenset({CognitiveOperation.EXPOSE, CognitiveOperation.READ}),
            domain_ids=frozenset({d2, d1}),
            actor_refs=frozenset({"zoe", "ana"}),
        ),
        GovernanceRule(rule_id="a", effect=GovernanceEffect.ADMIT),
    )

    primeiro = GovernancePolicy.serialize_rules(regras)
    segundo = GovernancePolicy.serialize_rules(tuple(reversed(regras)))
    assert primeiro == segundo

    reconstruidas = GovernancePolicy.deserialize_rules(primeiro)
    assert set(reconstruidas) == set(regras)


def test_gv15_unknown_vocabulary_in_stored_rules_is_rejected():
    """Regra gravada fora do vocabulário levanta erro, não vira inerte.

    O pior desfecho seria uma policy que **parece** restringir e não
    restringe.
    """
    with pytest.raises(ValueError):
        GovernancePolicy.deserialize_rules(
            [
                {
                    "rule_id": "r",
                    "effect": "talvez",
                    "operations": [],
                    "domain_ids": [],
                    "actor_refs": [],
                    "purposes": [],
                }
            ]
        )
    with pytest.raises(ValueError):
        GovernancePolicy.deserialize_rules(
            [
                {
                    "rule_id": "r",
                    "effect": "admit",
                    "operations": ["orquestrar"],
                    "domain_ids": [],
                    "actor_refs": [],
                    "purposes": [],
                }
            ]
        )


def test_gv16_governance_is_not_an_authorization_or_search_engine():
    """Fronteiras verificadas por **ausência estrutural**.

    Um teste de comportamento passaria igual se a capacidade proibida
    existisse mas não fosse chamada naquele caminho.
    """
    expostos = {
        nome for nome, _ in inspect.getmembers(GovernanceManager) if not nome.startswith("_")
    }
    for proibido in (
        "authenticate",
        "login",
        "has_role",
        "check_permission",
        "search",
        "retrieve",
        "rank",
        "score",
        "repair",
        "learn",
        "transition",
        "set_accessibility",
        "add_membership",
    ):
        assert proibido not in expostos, f"GovernanceManager expõe {proibido}"

    # Compara apenas o **código executável**: as docstrings do módulo
    # citam nominalmente o que ele não faz, e uma varredura ingênua no
    # texto acusaria exatamente as frases que negam o uso. Ajuste do
    # verificador em E4.3.1 — a asserção continua a mesma.
    codigo = _executable_source(GovernanceManager) + _executable_source(GovernanceDecision)
    for proibido in (
        "SearchEngine",
        "SearchCriteria",
        "AccessibilityState",
        "MemoryDomainMembership",
        "CognitiveObject",
    ):
        assert proibido not in codigo, f"governança não deve conhecer {proibido}"


def test_gv17_permission_does_not_implement_the_operation():
    """`PERMISSION != OPERATION IMPLEMENTATION`.

    Admitir `CONSOLIDATE` não consolida nada — E4.5 sequer existe. A
    policy nomeia; quem executa é outro módulo, quando houver.
    """
    ctx = MemoryContext.build(actor_ref="ana")
    regra = GovernanceRule(
        rule_id="c",
        effect=GovernanceEffect.ADMIT,
        operations=frozenset({CognitiveOperation.CONSOLIDATE}),
    )

    decisao = _evaluate((regra,), CognitiveOperation.CONSOLIDATE, ctx)

    assert decisao.outcome is GovernanceOutcome.ADMISSIBLE
    expostos = {
        nome for nome, _ in inspect.getmembers(GovernanceManager) if not nome.startswith("_")
    }
    for operacao in CognitiveOperation:
        assert (
            operacao.value not in expostos
        ), f"o manager não deve expor um executor de {operacao.value}"


def test_gv18_decision_is_a_frozen_value_object():
    """A decisão é value object imutável e não persistido."""
    ctx = MemoryContext.build(actor_ref="ana")
    decisao = _evaluate(
        (GovernanceRule(rule_id="r", effect=GovernanceEffect.ADMIT),),
        CognitiveOperation.READ,
        ctx,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        decisao.outcome = GovernanceOutcome.INADMISSIBLE  # type: ignore[misc]
    assert not hasattr(decisao, "__tablename__")
    assert "governance_decisions" not in {
        t for t in GovernancePolicy.metadata.tables
    }, "GovernanceDecision não é persistida"


# ======================================================================
# Repositório — precondições e classificação de violação
# ======================================================================


def _repo(session):
    from app.memory.repositories.governance_policy_repository import (
        GovernancePolicyRepository,
    )

    return GovernancePolicyRepository(session)


def test_gv19_repository_rejects_malformed_publication(memory_session):
    """Precondições do chamador são recusadas antes de tocar o banco."""
    repo = _repo(memory_session)

    for chave in ("", "   "):
        with pytest.raises(ValueError, match="policy_key"):
            repo.add_policy(policy_key=chave, version=1)
    for versao in (0, -1):
        with pytest.raises(ValueError, match="version"):
            repo.add_policy(policy_key="p", version=versao)

    from datetime import UTC, datetime

    with pytest.raises(ValueError, match="effective_until"):
        repo.add_policy(
            policy_key="p",
            version=1,
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            effective_until=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_gv20_duplicate_version_is_rejected_on_sqlite_signal_too(memory_session):
    """A classificação de unicidade também reconhece o sinal do SQLite.

    O caminho de produção é PostgreSQL, mas o ramo existe e precisa
    ser exercitado — deixá-lo sem teste foi exatamente o defeito que a
    E4.1 teve de fechar com `DB5`.
    """
    from app.memory.errors.exceptions import GovernancePolicyVersionExistsError

    repo = _repo(memory_session)
    repo.add_policy(policy_key="p", version=1)
    memory_session.flush()

    with pytest.raises(GovernancePolicyVersionExistsError) as exc:
        repo.add_policy(policy_key="p", version=1)
    assert exc.value.error_code.code == "PIA-8027"
    assert exc.value.policy_key == "p"
    assert exc.value.version == 1


def test_gv21_unclassified_persistence_error_is_reraised(memory_session):
    """Causa desconhecida é relançada sem reinterpretação.

    Lição de E3.2.1: não classificar por eliminação.
    """
    from app.repositories.exceptions import PersistenceError

    repo = _repo(memory_session)

    def _explode(_entity):
        raise PersistenceError("falha sem sqlstate conhecido")

    repo.add = _explode  # type: ignore[method-assign]
    with pytest.raises(PersistenceError):
        repo.add_policy(policy_key="p", version=1)


def test_gv22_max_version_suggests_the_next_one(memory_session):
    """`max_version` é sugestão, não reserva — devolve 0 se não há nada."""
    repo = _repo(memory_session)
    assert repo.max_version("inexistente") == 0

    repo.add_policy(policy_key="p", version=1)
    repo.add_policy(policy_key="p", version=2)
    memory_session.flush()
    assert repo.max_version("p") == 2


def test_gv23_non_iterable_domain_ids_in_a_rule_is_rejected():
    """`domain_ids` não iterável é erro de tipo, não iteração acidental."""
    with pytest.raises(TypeError, match="iterável"):
        GovernanceRule(rule_id="r", effect=GovernanceEffect.ADMIT, domain_ids=123)
    with pytest.raises(TypeError, match="iterável"):
        GovernanceRule(rule_id="r", effect=GovernanceEffect.ADMIT, domain_ids="abc")
