"""
E4.3.1 — testes do corretivo de Governance Safety & Resolution.

Cobrem os sete defeitos reproduzidos e a lista mínima do corretivo.

Nota sobre o método: cada teste desta suíte foi verificado contra o
código anterior. Um teste que passasse nos dois lados não provaria
correção alguma.
"""

import inspect
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
from app.memory.schemas.governance import GovernanceResolution, GovernanceRule
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
    )

    assert resolucao.preserved_intent == "proteção de vítimas"
    assert any("proteção de vítimas" in p for p in resolucao.declared_preservations)
    assert resolucao.declared_losses
    assert resolucao.execution_authorized is False
