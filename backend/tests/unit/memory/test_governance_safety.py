"""
E4.3.1 — testes do corretivo de Governance Safety & Resolution.

Cobrem os sete defeitos reproduzidos e a lista mínima do corretivo.

Nota sobre o método: cada teste desta suíte foi verificado contra o
código anterior. Um teste que passasse nos dois lados não provaria
correção alguma.
"""

import dataclasses
import inspect
import pathlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.memory.models.governance_enums import (
    CapabilityEngagement,
    CognitiveOperation,
    CriticalCapability,
    GovernanceEffect,
    GovernanceOutcome,
)
from app.memory.models.governance_policy import GovernancePolicy
from app.memory.repositories.governance_policy_repository import GovernancePolicyRepository
from app.memory.schemas.governance import (
    GovernanceDecision,
    GovernanceResolution,
    GovernanceRule,
    resolucao_vincula_contexto,
)
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.platform_safety_boundary import (
    PLATFORM_SAFETY_BOUNDARY_VERSION,
    CapabilityDescriptor,
    assess_capability,
)

_ADMIT_TUDO = (GovernanceRule(rule_id="admite-tudo", effect=GovernanceEffect.ADMIT),)


def _repo(session) -> GovernancePolicyRepository:
    return GovernancePolicyRepository(session)


def _manager(session) -> GovernanceManager:
    return GovernanceManager(_repo(session))


def _descriptor(**kw) -> CapabilityDescriptor:
    kw.setdefault("operation", CognitiveOperation.READ)
    return CapabilityDescriptor(**kw)


# ======================================================================
# Fronteira de segurança — pura, sem banco
# ======================================================================


def test_sb1_wmd_operational_request_is_prohibited():
    """Pedido operacional de arma de destruição em massa ⇒ `PROHIBITED`."""
    avaliacao = assess_capability(
        _descriptor(
            capabilities=frozenset({CriticalCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT}),
            engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        )
    )
    assert avaliacao.outcome is GovernanceOutcome.PROHIBITED
    assert avaliacao.blocked_capabilities == (
        CriticalCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT,
    )
    assert avaliacao.admissible_alternatives


def test_sb2_minor_targeting_for_exploitation_is_prohibited():
    """Perfilamento de crianças para exploração sexual ⇒ `PROHIBITED`.

    Inclusive quando apresentado como "segmentação" ou "análise de
    audiência": o que decide é a capacidade declarada, não o rótulo.
    """
    for engajamento in (
        CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        CapabilityEngagement.UNSPECIFIED,
    ):
        avaliacao = assess_capability(
            _descriptor(
                operation=CognitiveOperation.DERIVE,
                capabilities=frozenset(
                    {
                        CriticalCapability.MINOR_TARGETING_FOR_EXPLOITATION,
                        CriticalCapability.CHILD_SEXUAL_EXPLOITATION,
                    }
                ),
                engagement=engajamento,
                stated_intent="segmentação de audiência",
            )
        )
        assert avaliacao.outcome is GovernanceOutcome.PROHIBITED
        assert len(avaliacao.blocked_capabilities) == 2


def test_sb3_topic_alone_does_not_prohibit():
    """`TOPIC != CAPABILITY`.

    Discussão histórica, científica, preventiva ou defensiva dos
    mesmos assuntos **não** é proibida pelo tópico — bloquear por tema
    destruiria justamente o trabalho de prevenção e proteção.
    """
    for engajamento in (CapabilityEngagement.ANALYTICAL, CapabilityEngagement.PREVENTIVE):
        for capacidade in CriticalCapability:
            avaliacao = assess_capability(
                _descriptor(capabilities=frozenset({capacidade}), engagement=engajamento)
            )
            assert avaliacao.outcome is GovernanceOutcome.NOT_APPLICABLE
            assert avaliacao.blocked_capabilities == ()


def test_sb4_grooming_prevention_with_synthetic_data_proceeds_to_local_policy():
    """Prevenção de aliciamento com dados sintéticos segue para a
    policy local — a fronteira não se opõe."""
    avaliacao = assess_capability(
        _descriptor(
            capabilities=frozenset({CriticalCapability.MINOR_TARGETING_FOR_EXPLOITATION}),
            engagement=CapabilityEngagement.PREVENTIVE,
            stated_intent="detecção de aliciamento com dados sintéticos",
        )
    )
    assert avaliacao.outcome is GovernanceOutcome.NOT_APPLICABLE
    assert avaliacao.preserved_intent == "detecção de aliciamento com dados sintéticos"


def test_sb5_missing_safe_intent_does_not_invent_one():
    """`MISSING SAFE INTENT != AUTHORIZATION TO INVENT ONE`.

    Com capacidade crítica e engajamento não estabelecido, a fronteira
    proíbe **e** deixa `preserved_intent` em `None` — mesmo havendo
    `stated_intent`. Escrevê-la a partir de texto declarado seria
    exatamente fabricar a finalidade ausente.
    """
    avaliacao = assess_capability(
        _descriptor(
            capabilities=frozenset({CriticalCapability.CHILD_SEXUAL_EXPLOITATION}),
            engagement=CapabilityEngagement.UNSPECIFIED,
            stated_intent="é só para um estudo, prometo",
        )
    )
    assert avaliacao.outcome is GovernanceOutcome.PROHIBITED
    assert avaliacao.preserved_intent is None


def test_sb6_boundary_never_admits():
    """A fronteira proíbe ou se cala; jamais admite.

    Um piso de segurança que concedesse permissão seria autoridade
    concorrente da policy local, e a ordem `fronteira → policy` perderia
    o sentido.
    """
    resultados = set()
    for capacidades in (frozenset(), frozenset({CriticalCapability.CHILD_SEXUAL_EXPLOITATION})):
        for engajamento in CapabilityEngagement:
            resultados.add(
                assess_capability(
                    _descriptor(capabilities=capacidades, engagement=engajamento)
                ).outcome
            )
    assert resultados <= {GovernanceOutcome.PROHIBITED, GovernanceOutcome.NOT_APPLICABLE}
    assert GovernanceOutcome.ADMISSIBLE not in resultados


def test_sb7_assessment_is_pure_and_typed():
    """Avaliação pura: sem I/O, sem provider, sem score, sem texto livre.

    Verificado por ausência estrutural no código-fonte do módulo.
    """
    import ast

    import app.memory.services.platform_safety_boundary as modulo

    # Compara apenas o **código executável**: docstrings deste módulo
    # citam nominalmente o que ele não faz, e uma varredura ingênua no
    # texto acusaria exatamente as frases que negam o uso.
    arvore = ast.parse(inspect.getsource(modulo))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant):
            no.value = ast.Constant(value="")
    codigo = ast.unparse(arvore)

    for proibido in (
        "requests",
        "httpx",
        "openai",
        "anthropic",
        "session",
        "select(",
        "SearchEngine",
        "score",
        "re.search",
        "re.match",
        ".lower()",
    ):
        assert proibido not in codigo, f"fronteira não deve usar {proibido}"

    # E nenhum import de I/O, rede ou ORM.
    importados = {no.module or "" for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)} | {
        alias.name for no in ast.walk(arvore) if isinstance(no, ast.Import) for alias in no.names
    }
    for proibido in ("sqlalchemy", "requests", "httpx", "urllib", "socket", "subprocess"):
        assert not any(
            proibido in nome for nome in importados
        ), f"fronteira não deve importar {proibido}"

    with pytest.raises(TypeError):
        CapabilityDescriptor(operation=CognitiveOperation.READ, capabilities={"texto livre"})
    with pytest.raises(TypeError):
        CapabilityDescriptor(operation="read")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        CapabilityDescriptor(operation=CognitiveOperation.READ, stated_intent="   ")


# ======================================================================
# Ordem: fronteira → policy local → resolução
# ======================================================================


def test_sr1_prohibited_survives_a_local_admit(memory_session):
    """`PROHIBITED` nunca é revertido por `ADMIT` local.

    O teste central do corretivo: policy local admite tudo, e o
    resultado continua sendo recusa.
    """
    manager = _manager(memory_session)
    manager.publish_version(policy_key="permissiva", rules=_ADMIT_TUDO)
    memory_session.flush()

    resolucao = manager.resolve(
        descriptor=_descriptor(
            operation=CognitiveOperation.EXPOSE,
            capabilities=frozenset({CriticalCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT}),
            engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        ),
        context=MemoryContext.build(actor_ref="qualquer", purpose="qualquer"),
        policy_key="permissiva",
    )

    assert resolucao.outcome is GovernanceOutcome.PROHIBITED
    assert resolucao.prohibited_by_platform
    assert resolucao.execution_authorized is False
    # A policy local sequer foi consultada — fingir que foi seria
    # proveniência falsa.
    assert resolucao.policy_key is None
    assert resolucao.matched_rule_id is None
    assert resolucao.safety_boundary_version == PLATFORM_SAFETY_BOUNDARY_VERSION


def test_sr2_boundary_prevails_over_domain_actor_and_purpose(memory_session):
    """Domínio, ator e propósito não movem a fronteira."""
    manager = _manager(memory_session)
    manager.publish_version(policy_key="p", rules=_ADMIT_TUDO)
    memory_session.flush()

    descriptor = _descriptor(
        capabilities=frozenset({CriticalCapability.CHILD_SEXUAL_EXPLOITATION}),
        engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
    )
    for contexto in (
        MemoryContext.build(),
        MemoryContext.build(actor_ref="diretor"),
        MemoryContext.build(purpose="pesquisa aprovada"),
        MemoryContext.build(domain_ids=[uuid.uuid4()], actor_ref="a", purpose="p"),
    ):
        resolucao = manager.resolve(descriptor=descriptor, context=contexto, policy_key="p")
        assert resolucao.outcome is GovernanceOutcome.PROHIBITED
        assert resolucao.execution_authorized is False


def test_sr3_prohibited_resolution_preserves_declares_and_proposes(memory_session):
    """Em pedido proibido: bloqueia, preserva o legítimo, propõe
    alternativas e declara preservações e perdas."""
    manager = _manager(memory_session)
    resolucao = manager.resolve(
        descriptor=_descriptor(
            capabilities=frozenset({CriticalCapability.MINOR_TARGETING_FOR_EXPLOITATION}),
            engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        ),
        context=MemoryContext.build(),
    )

    assert resolucao.blocked_capabilities == (CriticalCapability.MINOR_TARGETING_FOR_EXPLOITATION,)
    assert resolucao.admissible_alternatives
    assert resolucao.declared_losses
    assert resolucao.declared_preservations
    assert resolucao.constraints
    assert resolucao.implies_nonexistence is False

    # A resolução não conserva detalhe operacional: só o vocabulário
    # fechado de capacidades e texto de orientação.
    texto = " ".join(
        resolucao.admissible_alternatives
        + resolucao.constraints
        + resolucao.declared_preservations
        + resolucao.declared_losses
        + (resolucao.safety_rationale,)
    )
    for proibido in ("como fazer", "passo a passo", "receita", "instruções", "tutorial"):
        assert proibido not in texto.lower()


def test_sr4_alternatives_do_not_authorize_the_original_operation(memory_session):
    """`REDIRECTION != AUTHORIZATION`.

    Oferecer caminho seguro não libera o caminho recusado, e nada é
    executado automaticamente.
    """
    manager = _manager(memory_session)
    resolucao = manager.resolve(
        descriptor=_descriptor(
            capabilities=frozenset({CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT}),
            engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        ),
        context=MemoryContext.build(),
    )

    assert resolucao.admissible_alternatives
    assert resolucao.execution_authorized is False
    assert resolucao.outcome is GovernanceOutcome.PROHIBITED

    expostos = {
        nome for nome, _ in inspect.getmembers(GovernanceResolution) if not nome.startswith("_")
    }
    for proibido in ("execute", "run", "apply", "perform", "search", "retrieve"):
        assert proibido not in expostos


def test_sr5_no_search_retrieval_tool_or_write_on_a_prohibited_request(memory_session):
    """Nenhuma pesquisa, recuperação, exposição ou ferramenta é
    executada num pedido proibido — e nenhuma escrita ocorre.

    Verificado por ausência estrutural no manager e por contagem de
    escritas na sessão.
    """
    fonte = inspect.getsource(GovernanceManager)
    for proibido in ("SearchEngine", "SearchCriteria", "requests", "httpx", "subprocess"):
        assert proibido not in fonte

    manager = _manager(memory_session)
    antes = memory_session.query(GovernancePolicy).count()
    manager.resolve(
        descriptor=_descriptor(
            capabilities=frozenset({CriticalCapability.CHILD_SEXUAL_EXPLOITATION}),
            engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        ),
        context=MemoryContext.build(),
    )
    assert memory_session.query(GovernancePolicy).count() == antes
    assert not memory_session.dirty
    assert not memory_session.new


def test_sr6_safe_engagement_reaches_the_local_policy(memory_session):
    """Engajamento preventivo chega à policy local e é decidido por ela."""
    manager = _manager(memory_session)
    manager.publish_version(
        policy_key="p",
        rules=(
            GovernanceRule(
                rule_id="pesquisa-preventiva",
                effect=GovernanceEffect.ADMIT,
                operations=frozenset({CognitiveOperation.READ}),
            ),
        ),
    )
    memory_session.flush()

    resolucao = manager.resolve(
        descriptor=_descriptor(
            capabilities=frozenset({CriticalCapability.MINOR_TARGETING_FOR_EXPLOITATION}),
            engagement=CapabilityEngagement.PREVENTIVE,
            stated_intent="detecção com dados sintéticos",
        ),
        context=MemoryContext.build(actor_ref="pesquisadora"),
        policy_key="p",
    )

    assert resolucao.outcome is GovernanceOutcome.ADMISSIBLE
    assert resolucao.execution_authorized is True
    assert resolucao.policy_key == "p"
    assert resolucao.matched_rule_id == "pesquisa-preventiva"
    assert resolucao.preserved_intent == "detecção com dados sintéticos"


def test_sr7_resolution_is_deterministic(memory_session):
    """Mesma entrada, resolução estruturalmente equivalente."""
    manager = _manager(memory_session)
    descriptor = _descriptor(
        capabilities=frozenset({CriticalCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT}),
        engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
    )
    contexto = MemoryContext.build(actor_ref="ana")

    primeira = manager.resolve(descriptor=descriptor, context=contexto)
    segunda = manager.resolve(descriptor=descriptor, context=contexto)
    assert primeira == segunda


# ======================================================================
# Defeito 4 — imutabilidade real
# ======================================================================


def test_sr8_published_policy_rejects_update_and_delete(memory_session):
    """Versão publicada recusa `update()` e `delete()` do repositório."""
    from app.memory.errors.exceptions import GovernancePolicyImmutableError

    repo = _repo(memory_session)
    policy = repo.add_policy(policy_key="p", version=1, rules=_ADMIT_TUDO)
    memory_session.flush()

    with pytest.raises(GovernancePolicyImmutableError) as exc:
        repo.update(policy)
    assert exc.value.error_code.code == "PIA-8028"
    with pytest.raises(GovernancePolicyImmutableError):
        repo.delete(policy)


def test_sr9_orm_mutation_bypassing_the_repository_is_also_rejected(memory_session):
    """O caminho pelo qual o defeito foi **reproduzido** também é fechado.

    Sobrescrever `update()` não bastava: bastava mutar o atributo do
    objeto carregado e dar `flush()`. O evento de mapper pega isso.

    Alcance declarado com honestidade: isto protege o caminho ORM, que
    é o caminho da aplicação. Um `UPDATE` SQL direto continua possível,
    como em toda a E3 — e o documento diz isso em vez de afirmar
    garantia de banco inexistente.
    """
    from app.memory.errors.exceptions import GovernancePolicyImmutableError

    repo = _repo(memory_session)
    repo.add_policy(policy_key="p", version=1, rules=_ADMIT_TUDO)
    memory_session.commit()

    policy = repo.get_version("p", 1)
    policy.rules = GovernancePolicy.serialize_rules(
        (GovernanceRule(rule_id="ADULTERADA", effect=GovernanceEffect.DENY),)
    )
    with pytest.raises(GovernancePolicyImmutableError):
        memory_session.flush()
    memory_session.rollback()

    intacta = _repo(memory_session).get_version("p", 1)
    assert intacta.typed_rules[0].rule_id == "admite-tudo"
    assert intacta.typed_rules[0].effect is GovernanceEffect.ADMIT


def test_sr10_orm_delete_bypassing_the_repository_is_rejected(memory_session):
    from app.memory.errors.exceptions import GovernancePolicyImmutableError

    repo = _repo(memory_session)
    repo.add_policy(policy_key="p", version=1)
    memory_session.commit()

    policy = repo.get_version("p", 1)
    memory_session.delete(policy)
    with pytest.raises(GovernancePolicyImmutableError):
        memory_session.flush()
    memory_session.rollback()
    assert _repo(memory_session).get_version("p", 1) is not None


# ======================================================================
# Defeito 5 — caminho canônico
# ======================================================================


def test_sr11_canonical_path_refuses_an_arbitrary_or_inactive_policy(memory_session):
    """O caminho canônico não avalia policy arbitrária nem fora de
    vigência como autoridade ativa.

    `resolve()` recebe `policy_key`, não um objeto — e uma versão fora
    de vigência simplesmente não é encontrada.
    """
    assinatura = inspect.signature(GovernanceManager.resolve)
    assert (
        "policy" not in assinatura.parameters
    ), "resolve() não pode aceitar um objeto GovernancePolicy do chamador"
    assert "policy_key" in assinatura.parameters

    manager = _manager(memory_session)
    passado = datetime(2020, 1, 1, tzinfo=UTC)
    manager.publish_version(
        policy_key="expirada",
        rules=_ADMIT_TUDO,
        effective_from=passado,
        effective_until=passado + timedelta(days=1),
    )
    memory_session.flush()

    resolucao = manager.resolve(
        descriptor=_descriptor(),
        context=MemoryContext.build(actor_ref="ana"),
        policy_key="expirada",
        moment=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert resolucao.outcome is GovernanceOutcome.NOT_APPLICABLE
    assert resolucao.execution_authorized is False
    assert resolucao.policy_key is None

    # E sem policy_key algum, também não concede.
    sem_policy = manager.resolve(
        descriptor=_descriptor(), context=MemoryContext.build(actor_ref="ana")
    )
    assert sem_policy.outcome is GovernanceOutcome.NOT_APPLICABLE
    assert sem_policy.execution_authorized is False


# ======================================================================
# Defeito 6 — rule_id duplicado
# ======================================================================


def test_sr12_duplicate_rule_id_is_rejected(memory_session):
    """Duplicata torna o fundamento da decisão ambíguo.

    Rejeitada na publicação **e** na desserialização — proveniência
    ambígua é pior que ausente, porque parece proveniência.
    """
    duplicadas = (
        GovernanceRule(rule_id="mesmo", effect=GovernanceEffect.ADMIT),
        GovernanceRule(rule_id="mesmo", effect=GovernanceEffect.DENY),
    )
    with pytest.raises(ValueError, match="duplicado"):
        GovernancePolicy.serialize_rules(duplicadas)

    with pytest.raises(ValueError, match="duplicado"):
        _manager(memory_session).publish_version(policy_key="p", rules=duplicadas)

    with pytest.raises(ValueError, match="duplicado"):
        GovernancePolicy.deserialize_rules(
            [
                {
                    "rule_id": "mesmo",
                    "effect": "admit",
                    "operations": [],
                    "domain_ids": [],
                    "actor_refs": [],
                    "purposes": [],
                },
                {
                    "rule_id": "mesmo",
                    "effect": "deny",
                    "operations": [],
                    "domain_ids": [],
                    "actor_refs": [],
                    "purposes": [],
                },
            ]
        )


# ======================================================================
# Defeito 7 (achado durante o corretivo) — ciclo de import
# ======================================================================


def test_sr13_governance_modules_import_in_any_order():
    """Ciclo de import da E4.3, achado durante este corretivo.

    `import app.memory.schemas.governance` como **primeiro** import
    falhava com `ImportError`: schemas → models.governance_enums →
    `models/__init__` → governance_policy → schemas. Passava
    despercebido porque a suíte sempre importava `app.memory.models`
    antes.

    O teste roda cada ordem num interpretador limpo, senão o módulo já
    estaria em `sys.modules` e o ciclo não seria exercitado.
    """
    import subprocess
    import sys

    for primeiro in (
        "app.memory.schemas.governance",
        "app.memory.models",
        "app.memory.services.platform_safety_boundary",
        "app.memory.services.governance_manager",
    ):
        resultado = subprocess.run(
            [sys.executable, "-c", f"import {primeiro}"],
            capture_output=True,
            text=True,
            cwd=str(__import__("pathlib").Path(__file__).resolve().parents[3]),
        )
        assert (
            resultado.returncode == 0
        ), f"importar {primeiro} primeiro falhou:\n{resultado.stderr}"


@pytest.mark.parametrize(
    "kwargs,exc",
    [
        ({"engagement": "analytical"}, TypeError),
        ({"capabilities": 123}, TypeError),
        ({"capabilities": b"bytes"}, TypeError),
        ({"stated_intent": 42}, TypeError),
    ],
)
def test_sb8_descriptor_rejects_wrong_types(kwargs, exc):
    """O descritor é tipado de ponta a ponta.

    Valor inválido é `ValueError`; tipo inválido é `TypeError` —
    diagnósticos distintos, como em E4.2.1.
    """
    base = {"operation": CognitiveOperation.READ}
    base.update(kwargs)
    with pytest.raises(exc):
        CapabilityDescriptor(**base)


def test_sb9_preserved_intent_appears_in_a_prohibited_resolution(memory_session):
    """Intenção legítima **demonstrável** é preservada mesmo quando a
    capacidade é bloqueada.

    Cobre o caso em que o engajamento é preservável e, ainda assim,
    outra capacidade do mesmo pedido é recusada — o pedido perde a
    capacidade destrutiva sem perder o que havia de legítimo.
    """
    from app.memory.services.platform_safety_boundary import SafetyAssessment

    avaliacao = SafetyAssessment(
        outcome=GovernanceOutcome.PROHIBITED,
        boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
        blocked_capabilities=(CriticalCapability.CHILD_SEXUAL_EXPLOITATION,),
        admissible_alternatives=("detecção e denúncia a canais competentes e a autoridades",),
        preserved_intent="proteção de vítimas",
        rationale="teste",
    )
    resolucao = GovernanceManager._prohibited_resolution(
        _descriptor(
            capabilities=frozenset({CriticalCapability.CHILD_SEXUAL_EXPLOITATION}),
            engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        ),
        avaliacao,
        # Corretivo E4.3.4: o helper passou a receber o contexto, porque
        # PROHIBITED não consulta policy local mas RECEBEU uma pergunta.
        MemoryContext(),
    )

    assert resolucao.preserved_intent == "proteção de vítimas"
    assert any("proteção de vítimas" in p for p in resolucao.declared_preservations)
    assert resolucao.declared_losses
    assert resolucao.execution_authorized is False


# ======================================================================
# E4.3.2 — invariantes de GovernanceResolution e SafetyAssessment
#
# Mesma classe de defeito que a E4.2.1 corrigiu em `MemoryContext`, e
# que eu repeti aqui: `frozen=True` protege a referência, não o
# conteúdo, e o construtor aceitava estados contraditórios.
# ======================================================================


_CONTEXTO_VAZIO: dict = {
    "context_domain_ids": (),
    "context_actor_ref": None,
    "context_purpose": None,
}
"""Vínculo de contexto explícito (corretivo E4.3.4).

As três dimensões passaram a ser obrigatórias, porque omissão não podia
seguir indistinguível de contexto explicitamente vazio:

    OMITTED CONTEXT != EXPLICITLY EMPTY CONTEXT
"""


def _valid_prohibited(**kw) -> GovernanceResolution:
    base = {
        "outcome": GovernanceOutcome.PROHIBITED,
        "operation": CognitiveOperation.READ,
        "safety_boundary_version": PLATFORM_SAFETY_BOUNDARY_VERSION,
        "blocked_capabilities": (CriticalCapability.CHILD_SEXUAL_EXPLOITATION,),
        **_CONTEXTO_VAZIO,
    }
    base.update(kw)
    return GovernanceResolution(**base)


def _valid_admissible(**kw) -> GovernanceResolution:
    base = {
        "outcome": GovernanceOutcome.ADMISSIBLE,
        "operation": CognitiveOperation.READ,
        "safety_boundary_version": PLATFORM_SAFETY_BOUNDARY_VERSION,
        "policy_key": "p",
        "policy_version": 1,
        "policy_id": uuid.uuid4(),
        "matched_rule_id": "r",
        **_CONTEXTO_VAZIO,
    }
    base.update(kw)
    return GovernanceResolution(**base)


def test_e432_mutating_the_original_list_does_not_alter_the_resolution():
    """O sintoma mais grave: um objeto declarado imutável mudava de
    conteúdo pelas costas de quem o segurava."""
    origem = [CriticalCapability.CHILD_SEXUAL_EXPLOITATION]
    resolucao = _valid_prohibited(blocked_capabilities=origem)

    origem.append(CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT)
    origem.clear()

    assert resolucao.blocked_capabilities == (CriticalCapability.CHILD_SEXUAL_EXPLOITATION,)
    assert isinstance(resolucao.blocked_capabilities, tuple)


def test_e432_resolution_is_hashable():
    """Com uma lista dentro, `hash()` levantava `TypeError` — e a
    igualdade estrutural é o que torna a resolução comparável."""
    a = _valid_prohibited(blocked_capabilities=[CriticalCapability.CHILD_SEXUAL_EXPLOITATION])
    b = _valid_prohibited(blocked_capabilities={CriticalCapability.CHILD_SEXUAL_EXPLOITATION})

    assert isinstance(hash(a), int)
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_e432_lists_and_sets_become_canonical_tuples():
    """Listas, conjuntos e geradores viram tuplas canônicas.

    Capacidades são ordenadas e desduplicadas; coleções textuais
    preservam a ordem (curada, carrega intenção) removendo repetição.
    """
    resolucao = _valid_prohibited(
        blocked_capabilities=[
            CriticalCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT,
            CriticalCapability.CHILD_SEXUAL_EXPLOITATION,
            CriticalCapability.CHILD_SEXUAL_EXPLOITATION,
        ],
        admissible_alternatives=["prevenção", "denúncia", "prevenção"],
        constraints={"única"},
        declared_preservations=(x for x in ("a", "b")),
        declared_losses=["a capacidade solicitada"],
    )

    assert resolucao.blocked_capabilities == (
        CriticalCapability.CHILD_SEXUAL_EXPLOITATION,
        CriticalCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT,
    )
    assert resolucao.admissible_alternatives == ("prevenção", "denúncia")
    for campo in (
        "blocked_capabilities",
        "admissible_alternatives",
        "constraints",
        "declared_preservations",
        "declared_losses",
    ):
        assert isinstance(getattr(resolucao, campo), tuple)
    assert isinstance(hash(resolucao), int)


@pytest.mark.parametrize(
    "kwargs,exc",
    [
        ({"outcome": "prohibited"}, TypeError),
        ({"operation": "read"}, TypeError),
        ({"safety_boundary_version": "um"}, TypeError),
        ({"safety_boundary_version": True}, TypeError),
        ({"safety_boundary_version": 0}, ValueError),
        ({"blocked_capabilities": ("texto",)}, TypeError),
        ({"blocked_capabilities": "csae"}, TypeError),
        ({"admissible_alternatives": ("",)}, ValueError),
        ({"admissible_alternatives": ("   ",)}, ValueError),
        ({"admissible_alternatives": (1,)}, TypeError),
        ({"constraints": None}, TypeError),
        ({"preserved_intent": "  "}, ValueError),
        ({"preserved_intent": 42}, TypeError),
        ({"safety_rationale": None}, TypeError),
        # `None` explícito numa coleção: o default é `()` e o campo é
        # anotado como tupla, então `None` ali contradiz a anotação.
        # Aceitá-lo como "vazio" repetiria a leniência que gerou o
        # defeito (mesma lição de E4.2.1).
        ({"blocked_capabilities": None}, TypeError),
        ({"declared_losses": None}, TypeError),
        ({"policy_id": "nao-e-uuid"}, TypeError),
        # Uma str é iterável, mas iterar caractere a caractere é
        # sempre engano do chamador — rejeitada como tipo, nunca
        # expandida em silêncio.
        ({"constraints": "restrição única"}, TypeError),
        ({"declared_preservations": 123}, TypeError),
    ],
)
def test_e432_invalid_types_and_values_are_rejected(kwargs, exc):
    """Tipo inválido é `TypeError`; valor inválido é `ValueError`.

    `StrEnum` compara igual à sua string, então aceitar `"prohibited"`
    passaria despercebido em quase todo teste de comportamento — o
    tipo é a garantia.
    """
    with pytest.raises(exc):
        _valid_prohibited(**kwargs)


def test_e432_admissible_cannot_carry_blocked_capabilities():
    """O estado mais alarmante do defeito: uma autorização que carrega
    a prova da própria recusa."""
    with pytest.raises(ValueError, match="capacidades bloqueadas"):
        _valid_admissible(blocked_capabilities=(CriticalCapability.CHILD_SEXUAL_EXPLOITATION,))


@pytest.mark.parametrize(
    "outcome",
    [GovernanceOutcome.INADMISSIBLE, GovernanceOutcome.NOT_APPLICABLE],
)
def test_e432_non_prohibited_outcomes_carry_no_blocked_capabilities(outcome):
    """Capacidade bloqueada é a marca da fronteira; num resultado de
    policy local seria proveniência falsa."""
    kw = {
        "outcome": outcome,
        "operation": CognitiveOperation.READ,
        "safety_boundary_version": 1,
        "blocked_capabilities": (CriticalCapability.CHILD_SEXUAL_EXPLOITATION,),
        **_CONTEXTO_VAZIO,
    }
    if outcome is GovernanceOutcome.INADMISSIBLE:
        kw |= {
            "policy_key": "p",
            "policy_version": 1,
            "policy_id": uuid.uuid4(),
            "matched_rule_id": "r",
        }
    with pytest.raises(ValueError, match="capacidades bloqueadas"):
        GovernanceResolution(**kw)


def test_e432_prohibited_requires_at_least_one_blocked_capability():
    """Uma recusa que não diz o que bloqueou é irrecorrível: não há
    como auditar nem propor alternativa."""
    with pytest.raises(ValueError, match="ao menos uma capacidade"):
        GovernanceResolution(
            **_CONTEXTO_VAZIO,
            outcome=GovernanceOutcome.PROHIBITED,
            operation=CognitiveOperation.READ,
            safety_boundary_version=1,
        )


@pytest.mark.parametrize(
    "faltando",
    ["policy_key", "policy_version", "policy_id", "matched_rule_id"],
)
def test_e432_admissible_requires_complete_local_provenance(faltando):
    """Sem proveniência completa não se pode dizer sob qual regra a
    decisão foi tomada — e proveniência incompleta é pior que ausente,
    porque parece proveniência."""
    with pytest.raises(ValueError):
        _valid_admissible(**{faltando: None})


def test_e432_prohibited_cannot_fabricate_local_provenance():
    """Quando a fronteira proíbe, a policy local **sequer é
    consultada** (E4.3.1) — citá-la seria fabricar consulta que não
    houve."""
    with pytest.raises(ValueError, match="não pode carregar proveniência"):
        _valid_prohibited(policy_key="p", policy_version=1, policy_id=uuid.uuid4())
    with pytest.raises(ValueError):
        _valid_prohibited(matched_rule_id="inventada")


def test_e432_partial_policy_identity_is_rejected():
    """Identidade de policy é tudo-ou-nada, e regra exige identidade."""
    with pytest.raises(ValueError, match="incompleta"):
        GovernanceResolution(
            **_CONTEXTO_VAZIO,
            outcome=GovernanceOutcome.NOT_APPLICABLE,
            operation=CognitiveOperation.READ,
            safety_boundary_version=1,
            policy_key="p",
        )
    with pytest.raises(ValueError, match="sem identidade de policy"):
        GovernanceResolution(
            **_CONTEXTO_VAZIO,
            outcome=GovernanceOutcome.NOT_APPLICABLE,
            operation=CognitiveOperation.READ,
            safety_boundary_version=1,
            matched_rule_id="r",
        )


def test_e432_not_applicable_cites_no_rule():
    """Se nenhuma regra se aplicou, não há regra a citar."""
    with pytest.raises(ValueError, match="não cita regra"):
        GovernanceResolution(
            **_CONTEXTO_VAZIO,
            outcome=GovernanceOutcome.NOT_APPLICABLE,
            operation=CognitiveOperation.READ,
            safety_boundary_version=1,
            policy_key="p",
            policy_version=1,
            policy_id=uuid.uuid4(),
            matched_rule_id="r",
        )


def test_e432_execution_authorized_only_over_a_structurally_valid_state():
    """`execution_authorized` continua derivada — e agora só pode ser
    `True` sobre um estado válido, porque o inválido não chega a
    existir."""
    assert _valid_admissible().execution_authorized is True
    assert _valid_prohibited().execution_authorized is False

    with pytest.raises(ValueError):
        _valid_admissible(blocked_capabilities=[CriticalCapability.CHILD_SEXUAL_EXPLOITATION])


def test_e432_safety_assessment_has_the_same_discipline():
    """`SafetyAssessment` tinha os mesmos defeitos.

    Corrigir só a resolução deixaria a metade errada exatamente no
    caminho pelo qual a outra é construída.
    """
    from app.memory.services.platform_safety_boundary import SafetyAssessment

    origem = [CriticalCapability.CHILD_SEXUAL_EXPLOITATION]
    avaliacao = SafetyAssessment(
        outcome=GovernanceOutcome.PROHIBITED, boundary_version=1, blocked_capabilities=origem
    )
    origem.append(CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT)

    assert avaliacao.blocked_capabilities == (CriticalCapability.CHILD_SEXUAL_EXPLOITATION,)
    assert isinstance(hash(avaliacao), int)

    with pytest.raises(ValueError, match="ao menos uma capacidade"):
        SafetyAssessment(outcome=GovernanceOutcome.PROHIBITED, boundary_version=1)
    with pytest.raises(ValueError, match="não bloqueia capacidade"):
        SafetyAssessment(
            outcome=GovernanceOutcome.NOT_APPLICABLE,
            boundary_version=1,
            blocked_capabilities=(CriticalCapability.CHILD_SEXUAL_EXPLOITATION,),
        )
    # E a fronteira segue não podendo admitir — agora impedido no tipo.
    with pytest.raises(ValueError, match="nunca produz"):
        SafetyAssessment(outcome=GovernanceOutcome.ADMISSIBLE, boundary_version=1)


def test_e432_resolutions_from_resolve_remain_valid(memory_session):
    """Toda resolução produzida pelo caminho canônico continua válida.

    Percorre os três desfechos que `resolve()` sabe produzir, e exige
    que cada um seja hashable e estruturalmente coerente — se algum
    caminho do manager montasse um estado inválido, `__post_init__` o
    recusaria aqui.
    """
    manager = _manager(memory_session)
    manager.publish_version(
        policy_key="p",
        rules=(
            GovernanceRule(
                rule_id="ok",
                effect=GovernanceEffect.ADMIT,
                operations=frozenset({CognitiveOperation.READ}),
            ),
        ),
    )
    memory_session.flush()

    proibida = manager.resolve(
        descriptor=_descriptor(
            capabilities=frozenset({CriticalCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT}),
            engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        ),
        context=MemoryContext.build(),
        policy_key="p",
    )
    admitida = manager.resolve(
        descriptor=_descriptor(), context=MemoryContext.build(), policy_key="p"
    )
    sem_policy = manager.resolve(descriptor=_descriptor(), context=MemoryContext.build())

    assert proibida.outcome is GovernanceOutcome.PROHIBITED
    assert proibida.blocked_capabilities and proibida.policy_key is None
    assert admitida.outcome is GovernanceOutcome.ADMISSIBLE
    assert admitida.matched_rule_id == "ok" and admitida.policy_id is not None
    assert sem_policy.outcome is GovernanceOutcome.NOT_APPLICABLE

    for resolucao in (proibida, admitida, sem_policy):
        assert isinstance(hash(resolucao), int)
        assert isinstance(resolucao.blocked_capabilities, tuple)


# ======================================================================
# E4.3.4 — Governance Resolution Context Binding
# ======================================================================
#
# O preflight da E4.8 provou que, na cadeia 58:
#
#     resolution(context=D1) == resolution(context=D2)
#
# sob policy curinga. Nada na resolução dizia sobre QUAL pergunta ela
# respondia:
#
#     MATCHED RULE ID      != EVALUATED CONTEXT
#     POLICY ID            != EVALUATED CONTEXT
#     EXECUTION_AUTHORIZED != PROOF OF THE QUESTION THAT WAS AUTHORIZED

_D1 = uuid.uuid4()
_D2 = uuid.uuid4()


def test_e434_resolutions_for_different_domains_are_no_longer_equal():
    """O defeito A, fechado."""
    a = _valid_admissible(context_domain_ids=(_D1,))
    b = _valid_admissible(context_domain_ids=(_D2,), policy_id=a.policy_id)
    assert a != b
    assert a.context_domain_ids != b.context_domain_ids


def test_e434_domain_order_is_canonicalized():
    """A mesma perspectiva declarada em ordens diferentes é a mesma
    pergunta — e precisa ter o mesmo hash."""
    identidade = uuid.uuid4()
    a = _valid_admissible(context_domain_ids=(_D1, _D2), policy_id=identidade)
    b = _valid_admissible(context_domain_ids=(_D2, _D1), policy_id=identidade)
    assert a.context_domain_ids == b.context_domain_ids == tuple(sorted((_D1, _D2)))
    assert a == b
    assert hash(a) == hash(b)


def test_e434_duplicate_domains_are_deduplicated():
    resolucao = _valid_admissible(context_domain_ids=(_D1, _D1, _D2))
    assert resolucao.context_domain_ids == tuple(sorted({_D1, _D2}))


def test_e434_external_list_is_isolated_and_becomes_a_tuple():
    """`frozen` protege a referência, não o conteúdo."""
    dominios = [_D1]
    resolucao = _valid_admissible(context_domain_ids=dominios)
    dominios.append(_D2)
    assert resolucao.context_domain_ids == (_D1,)
    assert isinstance(resolucao.context_domain_ids, tuple)
    assert isinstance(hash(resolucao), int)


@pytest.mark.parametrize("invalido", [None, "abc", b"abc", 123, _D1])
def test_e434_invalid_domain_collections_are_refused(invalido):
    with pytest.raises(TypeError, match="context_domain_ids"):
        _valid_admissible(context_domain_ids=invalido)


def test_e434_non_uuid_domain_is_refused():
    with pytest.raises(TypeError, match="apenas uuid.UUID"):
        _valid_admissible(context_domain_ids=("nao-e-uuid",))


@pytest.mark.parametrize("campo", ["context_actor_ref", "context_purpose"])
@pytest.mark.parametrize(("valor", "excecao"), [(123, TypeError), ("  ", ValueError)])
def test_e434_actor_and_purpose_are_typed_and_non_blank(campo, valor, excecao):
    """Ausência se declara com `None`, não com espaços."""
    with pytest.raises(excecao):
        _valid_admissible(**{campo: valor})


def test_e434_omitting_the_context_arguments_does_not_build():
    """`OMITTED CONTEXT != EXPLICITLY EMPTY CONTEXT`."""
    with pytest.raises(TypeError, match="context_domain_ids"):
        GovernanceResolution(
            outcome=GovernanceOutcome.NOT_APPLICABLE,
            operation=CognitiveOperation.READ,
            safety_boundary_version=PLATFORM_SAFETY_BOUNDARY_VERSION,
        )


def test_e434_explicitly_empty_context_is_valid():
    resolucao = _valid_admissible()
    assert resolucao.context_domain_ids == ()
    assert resolucao.context_actor_ref is None
    assert resolucao.context_purpose is None


def test_e434_decision_enforces_the_same_context_invariants():
    """`GovernanceDecision` já transportava as três dimensões, mas com
    defaults — omissão era indistinguível de contexto vazio."""
    with pytest.raises(TypeError, match="context_domain_ids"):
        GovernanceDecision(
            outcome=GovernanceOutcome.ADMISSIBLE,
            operation=CognitiveOperation.READ,
            policy_key="p",
            policy_version=1,
            policy_id=uuid.uuid4(),
        )
    dominios = [_D2, _D1, _D1]
    decisao = GovernanceDecision(
        outcome=GovernanceOutcome.ADMISSIBLE,
        operation=CognitiveOperation.READ,
        policy_key="p",
        policy_version=1,
        policy_id=uuid.uuid4(),
        context_domain_ids=dominios,
        context_actor_ref="ana",
        context_purpose="curadoria",
        matched_rule_id="r",
    )
    dominios.append(uuid.uuid4())
    assert decisao.context_domain_ids == tuple(sorted({_D1, _D2}))
    assert isinstance(hash(decisao), int)


def test_e434_session_id_is_not_part_of_the_resolution():
    """`CONTEXT != SESSION`; `SESSION DIFFERENCE != GOVERNANCE DIFFERENCE`.

    `session_id` não participa de `GovernanceRule.matches()`; acrescentá-lo
    seria proveniência falsa.
    """
    campos = {f.name for f in dataclasses.fields(GovernanceResolution)}
    assert "context_session_id" not in campos
    assert "session_id" not in campos


def test_e434_helper_is_shared_between_decision_and_resolution():
    """Duas cópias da mesma regra divergem com o tempo — lição da
    E4.5.1."""
    import app.memory.schemas.governance as mod

    assert hasattr(mod, "_contexto_avaliado")
    fonte = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert fonte.count("def _contexto_avaliado(") == 1
    assert fonte.count("_contexto_avaliado(") >= 3


def test_e434_binding_comparison_reports_every_divergence():
    resolucao = _valid_admissible(
        context_domain_ids=(_D1,), context_actor_ref="ana", context_purpose="p1"
    )
    assert (
        resolucao_vincula_contexto(resolucao, domain_ids=(_D1,), actor_ref="ana", purpose="p1")
        == ()
    )
    motivos = resolucao_vincula_contexto(
        resolucao, domain_ids=(_D2,), actor_ref="bob", purpose="p2"
    )
    assert len(motivos) == 3
