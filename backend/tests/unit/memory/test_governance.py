"""
E4.3 — testes unitários de governança.

Cobrem o vocabulário fechado, os invariantes das regras tipadas, a
precedência `DENY_OVERRIDES` e a explicabilidade da decisão. Os
requisitos que exigem banco (versionamento, vigência, concorrência,
zero escritas na avaliação) vivem em `tests/integration/memory/`.
"""

import ast
import dataclasses
import inspect
import pathlib
import uuid

import pytest

from app.memory.models.governance_enums import (
    EMPTY_OPERATIONS_SCOPE_V1,
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

    Sete vieram da E4.3 — o que `E4_GOVERNANCE_BOUNDARIES.md` §9 lista
    como o que governança pode controlar. A oitava veio do corretivo
    E4.3.3, com EDR próprio, para fechar o `GOVERNANCE_OPERATION_GAP`
    que o preflight da E4.7 confirmou. As três últimas vieram do
    corretivo E4.3.5, também com EDR próprio, para fechar o
    `RETENTION_OPERATION_AUTHORITY_GAP` que o preflight da E4.9
    encontrou. Ampliar de novo exige novo EDR.

    **Nota do corretivo E4.3.5.** Este teste falhava na cadeia 63 depois
    da ampliação do enum, e a falha é o comportamento correto dele: ele
    existe justamente para que nenhuma operação entre no vocabulário sem
    que alguém edite este conjunto literal e explique por quê. Foi
    atualizado, não afrouxado — continua exaustivo, continua literal, e
    continua falhando diante de qualquer membro não declarado aqui.
    """
    assert {op.value for op in CognitiveOperation} == {
        "read",
        "reference",
        "derive",
        "transform",
        "expose",
        "synchronize",
        "consolidate",
        "accessibility_transition",
        "retention_assessment",
        "retention_disposition",
        "legal_erasure",
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


# ======================================================================
# E4.3.3 — Explicit Accessibility Transition Authority
# ======================================================================
#
# O preflight da E4.7 confirmou `GOVERNANCE_OPERATION_GAP`: nenhuma das
# sete operações representava a transição de acessibilidade, e o curinga
# `operations=()` alcançava qualquer membro que viesse a existir.
#
#     EMPTY OPERATIONS  != ALL FUTURE OPERATIONS
#     OLD AUTHORIZATION != CONSENT TO A NEW CAPABILITY
#     FUTURE OPERATION DEFAULT = EXPLICIT OPT-IN REQUIRED


_OPERACOES_HISTORICAS = (
    CognitiveOperation.READ,
    CognitiveOperation.REFERENCE,
    CognitiveOperation.DERIVE,
    CognitiveOperation.TRANSFORM,
    CognitiveOperation.EXPOSE,
    CognitiveOperation.SYNCHRONIZE,
    CognitiveOperation.CONSOLIDATE,
)
_TRANSICAO = CognitiveOperation.ACCESSIBILITY_TRANSITION
_SEM_DIMENSOES = {"domain_ids": frozenset(), "actor_ref": None, "purpose": None}


def _regra(rule_id: str, effect: GovernanceEffect, operations=frozenset(), **extra):
    return GovernanceRule(rule_id=rule_id, effect=effect, operations=operations, **extra)


# --- 12.1 Vocabulário -------------------------------------------------


def test_e433_new_operation_token_is_exact():
    assert _TRANSICAO.value == "accessibility_transition"


def test_e433_historic_scope_has_exactly_the_seven_previous_operations():
    assert frozenset(_OPERACOES_HISTORICAS) == EMPTY_OPERATIONS_SCOPE_V1
    assert len(EMPTY_OPERATIONS_SCOPE_V1) == 7


def test_e433_new_operation_is_outside_the_historic_scope():
    assert _TRANSICAO not in EMPTY_OPERATIONS_SCOPE_V1


def test_e433_historic_scope_is_really_immutable():
    assert isinstance(EMPTY_OPERATIONS_SCOPE_V1, frozenset)
    with pytest.raises(AttributeError):
        EMPTY_OPERATIONS_SCOPE_V1.add(_TRANSICAO)  # type: ignore[attr-defined]


def test_e433_scope_is_not_derived_from_the_enum():
    """`set(CognitiveOperation)` reintroduziria o defeito: o conjunto
    cresceria sozinho a cada operação nova."""
    assert frozenset(CognitiveOperation) != EMPTY_OPERATIONS_SCOPE_V1
    assert len(EMPTY_OPERATIONS_SCOPE_V1) < len(list(CognitiveOperation))


# --- 12.2 Compatibilidade do curinga ---------------------------------


@pytest.mark.parametrize("operacao", _OPERACOES_HISTORICAS)
def test_e433_wildcard_still_matches_every_historic_operation(operacao):
    """As sete continuam exatamente como antes do corretivo."""
    assert _regra("r", GovernanceEffect.ADMIT).matches(operation=operacao, **_SEM_DIMENSOES)


def test_e433_wildcard_does_not_match_the_new_operation():
    """O defeito reproduzido na cadeia 53, agora fechado."""
    assert not _regra("r", GovernanceEffect.ADMIT).matches(operation=_TRANSICAO, **_SEM_DIMENSOES)


@pytest.mark.parametrize("operacao", _OPERACOES_HISTORICAS)
def test_e433_rule_restricted_to_an_old_operation_never_matches_the_new(operacao):
    assert not _regra("r", GovernanceEffect.ADMIT, operations=frozenset({operacao})).matches(
        operation=_TRANSICAO, **_SEM_DIMENSOES
    )


def test_e433_explicit_opt_in_matches_only_the_new_operation():
    regra = _regra("r", GovernanceEffect.ADMIT, operations=frozenset({_TRANSICAO}))
    assert regra.matches(operation=_TRANSICAO, **_SEM_DIMENSOES)
    for operacao in _OPERACOES_HISTORICAS:
        assert not regra.matches(operation=operacao, **_SEM_DIMENSOES)


def test_e433_no_sensitive_operations_blacklist_exists():
    """Blacklist foi rejeitada: uma operação futura poderia ser
    acrescentada sem entrar nela e voltaria a receber autorização
    retroativa. O escopo positivo faz o default seguro ser automático.
    """
    import ast

    import app.memory.models.governance_enums as enums_mod
    import app.memory.schemas.governance as schema_mod

    # Compara o CÓDIGO EXECUTÁVEL, não o texto bruto: as docstrings
    # citam nominalmente `set(CognitiveOperation)` ao explicar por que
    # NÃO derivar o escopo do enum. Mesmo falso positivo que a E4.3.1
    # corrigiu em `gv16`.
    for modulo in (enums_mod, schema_mod):
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
        executavel = ast.unparse(arvore)
        for proibido in (
            "SENSITIVE_OPERATIONS",
            "EXPLICIT_OPT_IN_OPERATIONS",
            "BLACKLIST",
            "set(CognitiveOperation)",
            "frozenset(CognitiveOperation)",
        ):
            assert proibido not in executavel, f"encontrado: {proibido}"


# --- 12.3 Avaliação ---------------------------------------------------


@pytest.mark.parametrize("effect", [GovernanceEffect.ADMIT, GovernanceEffect.DENY])
def test_e433_wildcard_only_policy_is_not_applicable_to_the_new_operation(effect):
    """Ausência de opt-in nunca vira admissão — nem negação explícita.

    NOT_APPLICABLE != INADMISSIBLE
    NOT_APPLICABLE DOES NOT GRANT
    """
    decisao = _evaluate((_regra("r", effect),), _TRANSICAO, MemoryContext())
    assert decisao.outcome is GovernanceOutcome.NOT_APPLICABLE
    assert decisao.is_admissible is False
    assert decisao.matched_rule_id is None


def test_e433_explicit_admit_makes_the_new_operation_admissible():
    decisao = _evaluate(
        (_regra("r-at", GovernanceEffect.ADMIT, operations=frozenset({_TRANSICAO})),),
        _TRANSICAO,
        MemoryContext(),
    )
    assert decisao.outcome is GovernanceOutcome.ADMISSIBLE
    assert decisao.matched_rule_id == "r-at"


def test_e433_explicit_deny_makes_the_new_operation_inadmissible():
    decisao = _evaluate(
        (_regra("r-at", GovernanceEffect.DENY, operations=frozenset({_TRANSICAO})),),
        _TRANSICAO,
        MemoryContext(),
    )
    assert decisao.outcome is GovernanceOutcome.INADMISSIBLE
    assert decisao.matched_rule_id == "r-at"


def test_e433_deny_overrides_still_holds_for_the_new_operation():
    decisao = _evaluate(
        (
            _regra("r-admit", GovernanceEffect.ADMIT, operations=frozenset({_TRANSICAO})),
            _regra("r-deny", GovernanceEffect.DENY, operations=frozenset({_TRANSICAO})),
        ),
        _TRANSICAO,
        MemoryContext(),
    )
    assert decisao.outcome is GovernanceOutcome.INADMISSIBLE


def test_e433_other_dimensions_still_constrain_the_new_operation():
    """A nova operação continua sujeita a domínio, ator e propósito."""
    dominio = uuid.uuid4()
    regra = _regra(
        "r",
        GovernanceEffect.ADMIT,
        operations=frozenset({_TRANSICAO}),
        domain_ids=frozenset({dominio}),
        actor_refs=frozenset({"ana"}),
        purposes=frozenset({"curadoria"}),
    )
    assert regra.matches(
        operation=_TRANSICAO,
        domain_ids=frozenset({dominio}),
        actor_ref="ana",
        purpose="curadoria",
    )
    # domínio divergente
    assert not regra.matches(
        operation=_TRANSICAO,
        domain_ids=frozenset({uuid.uuid4()}),
        actor_ref="ana",
        purpose="curadoria",
    )
    # ator ausente não casa regra que restringe ator
    assert not regra.matches(
        operation=_TRANSICAO,
        domain_ids=frozenset({dominio}),
        actor_ref=None,
        purpose="curadoria",
    )
    # propósito divergente
    assert not regra.matches(
        operation=_TRANSICAO,
        domain_ids=frozenset({dominio}),
        actor_ref="ana",
        purpose="outro",
    )


# --- 12.4 Serialização ------------------------------------------------


def test_e433_serialization_writes_the_exact_token():
    from app.memory.models.governance_policy import GovernancePolicy

    payload = GovernancePolicy.serialize_rules(
        (_regra("r", GovernanceEffect.ADMIT, operations=frozenset({_TRANSICAO})),)
    )
    assert payload[0]["operations"] == ["accessibility_transition"]


def test_e433_round_trip_is_deterministic():
    from app.memory.models.governance_policy import GovernancePolicy

    original = (_regra("r", GovernanceEffect.ADMIT, operations=frozenset({_TRANSICAO})),)
    ida = GovernancePolicy.serialize_rules(original)
    volta = GovernancePolicy.deserialize_rules(ida)
    assert volta == original
    assert GovernancePolicy.serialize_rules(volta) == ida


def test_e433_historic_empty_payload_stays_empty_and_does_not_match():
    """Payload histórico continua vazio na leitura, e o vazio agora tem
    alcance definido."""
    from app.memory.models.governance_policy import GovernancePolicy

    historico = [
        {
            "rule_id": "r1",
            "effect": "admit",
            "operations": [],
            "domain_ids": [],
            "actor_refs": [],
            "purposes": [],
        }
    ]
    regras = GovernancePolicy.deserialize_rules(historico)
    assert regras[0].operations == frozenset()
    assert not regras[0].matches(operation=_TRANSICAO, **_SEM_DIMENSOES)
    assert regras[0].matches(operation=CognitiveOperation.READ, **_SEM_DIMENSOES)
    # e a releitura não reescreve o payload
    assert GovernancePolicy.serialize_rules(regras)[0]["operations"] == []


def test_e433_unknown_token_is_still_refused_by_the_closed_vocabulary():
    from app.memory.models.governance_policy import GovernancePolicy

    with pytest.raises((ValueError, TypeError, KeyError)):
        GovernancePolicy.deserialize_rules(
            [
                {
                    "rule_id": "r",
                    "effect": "admit",
                    "operations": ["teleport"],
                    "domain_ids": [],
                    "actor_refs": [],
                    "purposes": [],
                }
            ]
        )


# --- 12.7 Não-regressão de autoridade cruzada ------------------------


def test_e433_authority_for_the_new_operation_does_not_grant_read():
    regra = _regra("r", GovernanceEffect.ADMIT, operations=frozenset({_TRANSICAO}))
    assert not regra.matches(operation=CognitiveOperation.READ, **_SEM_DIMENSOES)


def test_e433_authority_for_read_does_not_grant_the_new_operation():
    regra = _regra("r", GovernanceEffect.ADMIT, operations=frozenset({CognitiveOperation.READ}))
    assert not regra.matches(operation=_TRANSICAO, **_SEM_DIMENSOES)


def test_e433_transform_is_not_used_as_an_alias():
    """`ACCESSIBILITY TRANSITION != COGNITIVE TRANSFORMATION`."""
    assert _TRANSICAO is not CognitiveOperation.TRANSFORM
    assert _TRANSICAO.value != CognitiveOperation.TRANSFORM.value
    regra = _regra(
        "r", GovernanceEffect.ADMIT, operations=frozenset({CognitiveOperation.TRANSFORM})
    )
    assert not regra.matches(operation=_TRANSICAO, **_SEM_DIMENSOES)


def test_e433_docs_no_longer_claim_empty_means_any_future_operation():
    import app.memory.schemas.governance as schema_mod

    fonte = pathlib.Path(schema_mod.__file__).read_text(encoding="utf-8")
    assert "EMPTY_OPERATIONS_SCOPE_V1" in fonte


# ======================================================================
# E4.3.5 — Retention Operation Authority
#
# O corretivo fecha a Stop Condition primária do preflight da E4.9:
# as três autoridades de retenção não eram representáveis. Ele cria
# VOCABULÁRIO, não capacidade:
#
#     AUTHORITY VOCABULARY != OPERATION IMPLEMENTATION
#     PERMISSION != EXECUTION
#     E4_3_5 != E4_9
# ======================================================================


def _fonte_executavel_de_metodo(metodo) -> str:
    """`_executable_source` sobre um **método**.

    O helper compartilhado (linha 29) foi escrito para alvos de nível de
    módulo; `inspect.getsource` de um método vem indentado e o `ast.parse`
    recusa. Desindentar antes é a única diferença — a remoção de
    docstrings continua sendo a do helper, pela mesma razão do `gv16`.
    """
    import textwrap

    fonte = textwrap.dedent(inspect.getsource(metodo))
    arvore = ast.parse(fonte)
    for no in ast.walk(arvore):
        if isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant):
            no.value = ast.Constant(value="")
    return ast.unparse(arvore)


_AVALIACAO = CognitiveOperation.RETENTION_ASSESSMENT
_DISPOSICAO = CognitiveOperation.RETENTION_DISPOSITION
_APAGAMENTO = CognitiveOperation.LEGAL_ERASURE
_OPERACOES_E435 = (_AVALIACAO, _DISPOSICAO, _APAGAMENTO)


# --- 13.1 Vocabulário -------------------------------------------------


def test_e435_new_operation_tokens_are_exact():
    assert _AVALIACAO.value == "retention_assessment"
    assert _DISPOSICAO.value == "retention_disposition"
    assert _APAGAMENTO.value == "legal_erasure"


def test_e435_the_three_authorities_are_distinct_members():
    """Nenhuma é alias da outra, e nenhuma colapsa em operação anterior.

    AUTHORITY TO ASSESS  != AUTHORITY TO DISPOSE
    AUTHORITY TO DISPOSE != AUTHORITY TO ERASE
    """
    assert len({op for op in _OPERACOES_E435}) == 3
    assert len({op.value for op in _OPERACOES_E435}) == 3
    for nova in _OPERACOES_E435:
        for antiga in (*_OPERACOES_HISTORICAS, _TRANSICAO):
            assert nova is not antiga
            assert nova.value != antiga.value


def test_e435_no_generic_collapsing_operation_was_created():
    """§4: proibido criar `RETENTION` ou `ERASURE` genérica que funda
    avaliação, decisão e efeito num membro só."""
    valores = {op.value for op in CognitiveOperation}
    assert "retention" not in valores
    assert "erasure" not in valores
    assert "retention_forgetting" not in valores


def test_e435_no_aliases_were_created():
    """`StrEnum` com dois nomes para o mesmo valor viraria alias
    silencioso. Cada membro tem valor próprio."""
    valores = [op.value for op in CognitiveOperation]
    assert len(valores) == len(set(valores))
    assert len(CognitiveOperation.__members__) == len(valores)


@pytest.mark.parametrize("token", ["retencao", "RETENTION_ASSESSMENT", "erase", "delete", ""])
def test_e435_unknown_tokens_are_still_rejected(token):
    """Vocabulário continua fechado: nenhum fallback para string
    desconhecida."""
    with pytest.raises(ValueError):
        CognitiveOperation(token)


# --- 13.2 O curinga histórico permanece fechado -----------------------


def test_e435_historic_scope_still_has_exactly_the_seven_previous_operations():
    assert frozenset(_OPERACOES_HISTORICAS) == EMPTY_OPERATIONS_SCOPE_V1
    assert len(EMPTY_OPERATIONS_SCOPE_V1) == 7


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_e435_new_operations_are_outside_the_historic_scope(operacao):
    """Guarda contra inclusão acidental futura (§9.4)."""
    assert operacao not in EMPTY_OPERATIONS_SCOPE_V1


def test_e435_historic_scope_did_not_grow_with_the_enum():
    """O conjunto é literal. Se alguém o derivasse do enum, ele teria
    passado de 7 para 11 sozinho — que é exatamente o defeito que a
    E4.3.3 corrigiu."""
    assert len(EMPTY_OPERATIONS_SCOPE_V1) == 7
    assert len(list(CognitiveOperation)) == 11
    assert len(EMPTY_OPERATIONS_SCOPE_V1) < len(list(CognitiveOperation))


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
@pytest.mark.parametrize("effect", [GovernanceEffect.ADMIT, GovernanceEffect.DENY])
def test_e435_wildcard_rule_does_not_reach_the_new_operations(operacao, effect):
    """Nem admite nem nega: a regra simplesmente não se aplica.

    OLD WILDCARD AUTHORITY != FUTURE RETENTION AUTHORITY
    """
    regra = _regra("curinga", effect, operations=frozenset())
    assert not regra.matches(operation=operacao, **_SEM_DIMENSOES)


def test_e435_wildcard_rule_still_reaches_every_historic_operation():
    """Controle positivo: o corretivo não estreitou o curinga."""
    regra = _regra("curinga", GovernanceEffect.ADMIT, operations=frozenset())
    for operacao in _OPERACOES_HISTORICAS:
        assert regra.matches(operation=operacao, **_SEM_DIMENSOES)


def test_e435_matching_has_no_special_branch_per_operation():
    """§8.2: as novas operações seguem o mecanismo positivo geral da
    E4.3.3, sem `if` dedicado a nenhuma delas."""
    fonte = _fonte_executavel_de_metodo(GovernanceRule.matches)
    for token in ("retention_assessment", "retention_disposition", "legal_erasure"):
        assert token not in fonte
    for nome in ("RETENTION_ASSESSMENT", "RETENTION_DISPOSITION", "LEGAL_ERASURE"):
        assert nome not in fonte


# --- 13.3 Autoridade explícita ---------------------------------------


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_e435_wildcard_only_policy_resolves_not_applicable(operacao):
    decisao = _evaluate(
        (_regra("curinga", GovernanceEffect.ADMIT, operations=frozenset()),),
        operacao,
        MemoryContext(),
    )
    assert decisao.outcome is GovernanceOutcome.NOT_APPLICABLE
    assert decisao.matched_rule_id is None


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_e435_explicit_opt_in_admits(operacao):
    decisao = _evaluate(
        (_regra("opt-in", GovernanceEffect.ADMIT, operations=frozenset({operacao})),),
        operacao,
        MemoryContext(),
    )
    assert decisao.outcome is GovernanceOutcome.ADMISSIBLE
    assert decisao.matched_rule_id == "opt-in"
    assert decisao.operation is operacao


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_e435_explicit_deny_is_inadmissible_not_merely_not_applicable(operacao):
    """`INADMISSIBLE` e `NOT_APPLICABLE` continuam diagnósticos
    diferentes — alguém proibiu × ninguém decidiu."""
    decisao = _evaluate(
        (_regra("nega", GovernanceEffect.DENY, operations=frozenset({operacao})),),
        operacao,
        MemoryContext(),
    )
    assert decisao.outcome is GovernanceOutcome.INADMISSIBLE
    assert decisao.matched_rule_id == "nega"


@pytest.mark.parametrize("pedida", _OPERACOES_E435)
def test_e435_authority_over_one_retention_operation_does_not_grant_the_others(pedida):
    """O ponto central da separação em três: quem pode avaliar não pode
    dispor, e quem pode dispor não pode apagar."""
    outras = [op for op in _OPERACOES_E435 if op is not pedida]
    for concedida in outras:
        decisao = _evaluate(
            (_regra("r", GovernanceEffect.ADMIT, operations=frozenset({concedida})),),
            pedida,
            MemoryContext(),
        )
        assert decisao.outcome is GovernanceOutcome.NOT_APPLICABLE


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_e435_read_authority_does_not_grant_retention_authority(operacao):
    """AUTHORITY TO READ != AUTHORITY TO FORGET"""
    decisao = _evaluate(
        (_regra("r", GovernanceEffect.ADMIT, operations=frozenset({CognitiveOperation.READ})),),
        operacao,
        MemoryContext(),
    )
    assert decisao.outcome is GovernanceOutcome.NOT_APPLICABLE


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_e435_transform_and_transition_authority_do_not_grant_erasure(operacao):
    """AUTHORITY TO TRANSFORM != AUTHORITY TO ERASE
    AUTHORITY TO CHANGE ACCESSIBILITY != AUTHORITY TO DELETE
    """
    for concedida in (CognitiveOperation.TRANSFORM, _TRANSICAO):
        decisao = _evaluate(
            (_regra("r", GovernanceEffect.ADMIT, operations=frozenset({concedida})),),
            operacao,
            MemoryContext(),
        )
        assert decisao.outcome is GovernanceOutcome.NOT_APPLICABLE


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_e435_deny_overrides_still_applies_to_the_new_operations(operacao):
    """A disciplina vigente não muda: uma restrição que some porque
    outra regra permite não é restrição."""
    decisao = _evaluate(
        (
            _regra("admite", GovernanceEffect.ADMIT, operations=frozenset({operacao})),
            _regra("nega", GovernanceEffect.DENY, operations=frozenset({operacao})),
        ),
        operacao,
        MemoryContext(),
    )
    assert decisao.outcome is GovernanceOutcome.INADMISSIBLE
    assert decisao.matched_rule_id == "nega"


def test_e435_one_rule_may_enumerate_the_three_without_fusing_them():
    """§8.3: combinar operações numa regra é permitido e **não** altera
    a independência semântica entre elas."""
    regra = _regra("tres", GovernanceEffect.ADMIT, operations=frozenset(_OPERACOES_E435))
    for operacao in _OPERACOES_E435:
        assert regra.matches(operation=operacao, **_SEM_DIMENSOES)
    for operacao in (*_OPERACOES_HISTORICAS, _TRANSICAO):
        assert not regra.matches(operation=operacao, **_SEM_DIMENSOES)


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_e435_context_dimensions_still_bind_for_the_new_operations(operacao):
    """Ator, propósito e domínio continuam vinculados normalmente —
    o corretivo não abriu exceção contextual para retenção."""
    dominio = uuid.uuid4()
    regra = _regra(
        "r",
        GovernanceEffect.ADMIT,
        operations=frozenset({operacao}),
        domain_ids=frozenset({dominio}),
        actor_refs=frozenset({"ana"}),
        purposes=frozenset({"auditoria"}),
    )
    assert regra.matches(
        operation=operacao,
        domain_ids=frozenset({dominio}),
        actor_ref="ana",
        purpose="auditoria",
    )
    # dimensão ausente no contexto não casa com regra que a restringe
    assert not regra.matches(
        operation=operacao,
        domain_ids=frozenset({dominio}),
        actor_ref=None,
        purpose="auditoria",
    )
    assert not regra.matches(
        operation=operacao,
        domain_ids=frozenset({uuid.uuid4()}),
        actor_ref="ana",
        purpose="auditoria",
    )


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_e435_decision_binds_the_evaluated_context(operacao):
    """A E4.3.4 vale para as operações novas como para as antigas."""
    dominio = uuid.uuid4()
    contexto = MemoryContext.build(domain_ids=[dominio], actor_ref="ana", purpose="retencao")
    decisao = _evaluate(
        (_regra("r", GovernanceEffect.ADMIT, operations=frozenset({operacao})),),
        operacao,
        contexto,
    )
    assert decisao.context_domain_ids == (dominio,)
    assert decisao.context_actor_ref == "ana"
    assert decisao.context_purpose == "retencao"


# --- 13.4 Serialização ------------------------------------------------


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_e435_new_operation_round_trips_deterministically(operacao):
    regra = _regra("r", GovernanceEffect.ADMIT, operations=frozenset({operacao}))
    payload = GovernancePolicy.serialize_rules((regra,))
    assert payload[0]["operations"] == [operacao.value]
    assert GovernancePolicy.serialize_rules((regra,)) == payload
    (reconstruida,) = GovernancePolicy.deserialize_rules(payload)
    assert reconstruida == regra
    assert reconstruida.operations == frozenset({operacao})


def test_e435_policy_with_all_three_round_trips():
    regra = _regra("tres", GovernanceEffect.ADMIT, operations=frozenset(_OPERACOES_E435))
    payload = GovernancePolicy.serialize_rules((regra,))
    assert payload[0]["operations"] == sorted(op.value for op in _OPERACOES_E435)
    (reconstruida,) = GovernancePolicy.deserialize_rules(payload)
    assert reconstruida.operations == frozenset(_OPERACOES_E435)


def test_e435_old_payloads_are_byte_identical_after_the_corrective():
    """Nenhum payload publicado antes do corretivo muda de forma.

    O payload é montado a partir de `op.value` ordenado, então
    acrescentar membros ao enum não pode alterar bytes de regra alguma
    que não os cite.
    """
    antiga = _regra(
        "historica",
        GovernanceEffect.ADMIT,
        operations=frozenset({CognitiveOperation.READ, CognitiveOperation.TRANSFORM}),
    )
    curinga = _regra("curinga", GovernanceEffect.DENY, operations=frozenset())
    payload = GovernancePolicy.serialize_rules((antiga, curinga))
    assert payload == [
        {
            "rule_id": "historica",
            "effect": "admit",
            "operations": ["read", "transform"],
            "domain_ids": [],
            "actor_refs": [],
            "purposes": [],
        },
        {
            "rule_id": "curinga",
            "effect": "deny",
            "operations": [],
            "domain_ids": [],
            "actor_refs": [],
            "purposes": [],
        },
    ]
    assert GovernancePolicy.deserialize_rules(payload) == (antiga, curinga)


def test_e435_unknown_operation_token_in_payload_still_raises():
    """Uma policy gravada com token fora do vocabulário continua
    falhando alto, em vez de virar regra silenciosamente inerte."""
    with pytest.raises(ValueError):
        GovernancePolicy.deserialize_rules(
            [
                {
                    "rule_id": "r",
                    "effect": "admit",
                    "operations": ["retention"],
                    "domain_ids": [],
                    "actor_refs": [],
                    "purposes": [],
                }
            ]
        )


# --- 13.5 Não capacidade ----------------------------------------------


def test_e435_corrective_created_no_retention_capability():
    """§9.5: o corretivo é vocabulário. Nada em `app/memory` ganhou
    mecanismo de retenção, disposição ou apagamento.

    Compara o **código executável** (AST sem docstrings), porque as
    docstrings citam nominalmente o que o corretivo não faz — mesmo
    falso positivo que a E4.3.1 corrigiu em `gv16` e que a E4.8 pagou
    com guardas por substring solta.
    """
    import ast
    import re

    base = pathlib.Path(__file__).parents[3] / "app" / "memory"
    assert base.is_dir(), f"caminho de app/memory não resolvido: {base}"

    proibidos = (
        "RetentionPolicy",
        "RetentionRule",
        "RetentionAssessment",
        "RetentionDecision",
        "ErasureRecord",
        "retention_policies",
    )
    metodos_proibidos = ("assess_retention", "dispose", "erase", "forget")

    # Atualizado pela E4.9.5: `ErasureRecord` deixou de ser ausência
    # e passou a ser primitiva persistente autorizada, em QUATRO
    # arquivos nomeados. A proibição continua valendo em todo o resto
    # de `app/memory` — e todas as proibições de RETENÇÃO seguem
    # intactas, porque a E4.9.5 não criou policy, avaliação nem
    # disposição.
    autorizados_e495 = {
        base / "models" / "erasure_record.py",
        base / "models" / "erasure_enums.py",
        base / "models" / "__init__.py",
        base / "schemas" / "erasure_record.py",
        base / "repositories" / "erasure_record_repository.py",
        base / "errors" / "codes.py",
        base / "errors" / "exceptions.py",
    }

    # Atualizado pela E4.9.6: `RetentionPolicy`, `RetentionRule` e
    # `retention_policies` deixaram de ser ausência e passaram a ser
    # primitiva persistente autorizada, em arquivos NOMEADOS. A
    # proibição continua valendo em todo o resto de `app/memory`, e as
    # proibições de AVALIAÇÃO e DISPOSIÇÃO (`RetentionAssessment`,
    # `RetentionDecision`, `assess_retention`, `dispose`, `erase`,
    # `forget`) seguem INTACTAS em todos os arquivos — inclusive
    # nestes: a E4.9.6 persiste a regra, não a executa.
    autorizados_e496 = {
        base / "models" / "retention_policy.py",
        base / "models" / "retention_enums.py",
        base / "models" / "__init__.py",
        base / "schemas" / "retention.py",
        base / "repositories" / "retention_policy_repository.py",
        base / "errors" / "codes.py",
        base / "errors" / "exceptions.py",
    }
    proibidos_e496 = {"RetentionPolicy", "RetentionRule", "retention_policies"}

    for arquivo in sorted(base.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            corpo = getattr(no, "body", None)
            if isinstance(corpo, list):
                no.body = [
                    filho
                    for filho in corpo
                    if not (
                        isinstance(filho, ast.Expr)
                        and isinstance(filho.value, ast.Constant)
                        and isinstance(filho.value.value, str)
                    )
                ] or [ast.Pass()]
        executavel = ast.unparse(arvore)
        for proibido in proibidos:
            if proibido == "ErasureRecord" and arquivo in autorizados_e495:
                continue
            if proibido in proibidos_e496 and arquivo in autorizados_e496:
                continue
            assert not re.search(rf"\b{proibido}\b", executavel), f"{arquivo}: {proibido}"
        for metodo in metodos_proibidos:
            assert not re.search(rf"\bdef {metodo}\b", executavel), f"{arquivo}: def {metodo}"


def test_e435_production_diff_is_confined_to_the_enum_module():
    """O corretivo não precisou tocar `matches()`, o manager, os
    schemas de resultado nem repositório algum: o mecanismo positivo da
    E4.3.3 já trata membro novo sem código novo."""
    fonte_matches = _fonte_executavel_de_metodo(GovernanceRule.matches)
    assert "EMPTY_OPERATIONS_SCOPE_V1" in fonte_matches
    fonte_manager = _executable_source(GovernanceManager)
    for token in ("retention", "erasure", "Retention", "Erasure"):
        assert token not in fonte_manager


def test_e435_governance_result_gained_no_execution_fields():
    """§8.4: `GovernanceDecision` continua descrevendo só o resultado da
    policy — sem approval, receipt ou efeito executado."""
    campos = {campo.name for campo in dataclasses.fields(GovernanceDecision)}
    for proibido in ("approval", "approved_by", "receipt", "executed", "effect_executed"):
        assert proibido not in campos
