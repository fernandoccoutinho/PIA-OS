"""
E4.3 — testes de integração contra PostgreSQL real.

Cobrem os requisitos que só o banco pode demonstrar: versionamento
imutável, vigência determinística, concorrência real, ausência de
escrita durante a avaliação, e a garantia de que nenhuma decisão toca
patrimônio.
"""

import re
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import (
    AccessibilityState,
    CausalEventType,
    LineageRelation,
    ProvenanceActorType,
    ProvenanceSourceType,
)
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.schemas.synchronization import SECTION_BY_TABLE
from app.cognitive.services.accessibility_manager import AccessibilityManager
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.provenance_manager import ProvenanceManager
from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.memory.errors.exceptions import (
    GovernancePolicyImmutableError,
    GovernancePolicyVersionExistsError,
)
from app.memory.models.governance_enums import (
    CognitiveOperation,
    GovernanceEffect,
    GovernanceOutcome,
)
from app.memory.models.governance_policy import GovernancePolicy
from app.memory.repositories.governance_policy_repository import GovernancePolicyRepository
from app.memory.repositories.memory_domain_membership_repository import (
    MemoryDomainMembershipRepository,
)
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository
from app.memory.schemas.governance import GovernanceRule
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.platform_safety_boundary import (
    CapabilityDescriptor,
    CapabilityEngagement,
    CriticalCapability,
)
from app.repositories.unit_of_work import UnitOfWork

_INICIO = datetime(2024, 1, 1, tzinfo=UTC)
_MOMENTO = datetime(2024, 6, 1, tzinfo=UTC)

_GOVERNANCE_TABLES = ("governance_policies",)
_MEMORY_TABLES = ("memory_domain_memberships", "memory_domains")
_COGNITIVE_TABLES = (
    "causal_history_events",
    "causal_histories",
    "provenance_records",
    "relationships",
    "lineage_edges",
    "transformation_records",
    "cognitive_objects",
)


def _available() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _available(),
    reason="PostgreSQL real indisponível — E4.3 valida constraints e concorrência reais.",
)


@pytest.fixture(autouse=True)
def _clean():
    migrations.upgrade("head")
    _truncate()
    yield
    _truncate()


def _truncate() -> None:
    todas = _GOVERNANCE_TABLES + _MEMORY_TABLES + _COGNITIVE_TABLES
    with engine.begin() as conn:
        conn.execute(sa.text(f"TRUNCATE {', '.join(todas)} CASCADE"))


def _census(tables: tuple[str, ...]) -> dict[str, list[tuple[Any, ...]]]:
    snapshot: dict[str, list[tuple[Any, ...]]] = {}
    with engine.connect() as conn:
        for table in tables:
            columns = sorted(sa.inspect(engine).get_columns(table), key=lambda c: c["name"])
            names = ", ".join(f'"{c["name"]}"' for c in columns)
            rows = conn.execute(sa.text(f"SELECT {names} FROM {table} ORDER BY id")).fetchall()
            snapshot[table] = [tuple(row) for row in rows]
    return snapshot


def _manager(session) -> GovernanceManager:
    return GovernanceManager(GovernancePolicyRepository(session))


def _seed_patrimony() -> dict[str, uuid.UUID]:
    """Patrimônio completo mais um domínio povoado."""
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        prov = ProvenanceManager(ProvenanceRepository(uow.session))
        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
        lineage = LineageRepository(uow.session)
        accessibility = AccessibilityManager(objects)

        clid = uuid.uuid4()
        o1 = objects.add(CognitiveObject(clid=clid))
        o2 = objects.add(CognitiveObject(clid=clid))
        o3 = objects.add(CognitiveObject())
        uow.session.flush()
        p = prov.record(
            coid=o1.id,
            source_type=ProvenanceSourceType.HUMAN,
            actor_type=ProvenanceActorType.HUMAN,
            trace_id="e43",
        )
        uow.session.flush()
        lineage.add_edge(parent_coid=o1.id, child_coid=o2.id, relation_type=LineageRelation.BRANCH)
        raiz = causal.record(subject_coid=o1.id, event_type=CausalEventType.CREATED, actor_ref=p.id)
        causal.record(subject_coid=o2.id, event_type=CausalEventType.TRANSFORMED, predecessor=raiz)
        accessibility.transition(o2, AccessibilityState.INACCESSIBLE)
        accessibility.transition(o3, AccessibilityState.CAUSALLY_EXTINCT, reason="broken glass")

        d1 = MemoryDomainRepository(uow.session).add_domain(name="D1")
        uow.session.flush()
        MemoryDomainMembershipRepository(uow.session).add_membership(domain_id=d1.id, coid=o1.id)
        uow.commit()
        return {"o1": o1.id, "o2": o2.id, "o3": o3.id, "d1": d1.id, "clid": clid}


# ======================================================================
# 1–3 — criação, versionamento e imutabilidade
# ======================================================================


def test_gi1_policy_is_created_and_retrieved():
    """(1) Criação e recuperação, com regras tipadas preservadas."""
    d1 = uuid.uuid4()
    regra = GovernanceRule(
        rule_id="ler-d1",
        effect=GovernanceEffect.ADMIT,
        operations=frozenset({CognitiveOperation.READ}),
        domain_ids=frozenset({d1}),
    )
    with UnitOfWork() as uow:
        _manager(uow.session).publish_version(policy_key="p", rules=(regra,))
        uow.commit()

    with UnitOfWork() as uow:
        recuperada = _manager(uow.session).get_version("p", 1)
        assert recuperada is not None
        assert recuperada.policy_key == "p"
        assert recuperada.version == 1
        assert recuperada.typed_rules == (regra,)


def test_gi2_new_version_is_explicit_and_previous_survives():
    """(2) Nova versão é explícita; a anterior continua intacta.

    É isso que permite responder, depois, sob qual versão algo foi
    decidido.
    """
    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        manager.publish_version(
            policy_key="p",
            rules=(GovernanceRule(rule_id="v1", effect=GovernanceEffect.ADMIT),),
        )
        uow.commit()
    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        manager.publish_version(
            policy_key="p",
            rules=(GovernanceRule(rule_id="v2", effect=GovernanceEffect.DENY),),
        )
        uow.commit()

    with UnitOfWork() as uow:
        versoes = _manager(uow.session).list_versions("p")
        assert [v.version for v in versoes] == [1, 2]
        assert versoes[0].typed_rules[0].rule_id == "v1"
        assert versoes[0].typed_rules[0].effect is GovernanceEffect.ADMIT
        assert versoes[1].typed_rules[0].rule_id == "v2"


def test_gi3_existing_version_cannot_be_silently_overwritten():
    """(3) Recriar versão publicada é recusado — nunca sobrescreve.

    Verificado pelos dois lados: pela exceção de domínio e por
    `INSERT` direto, que ignora o repositório e encontra a constraint.
    """
    with UnitOfWork() as uow:
        _manager(uow.session).publish_version(
            policy_key="p",
            rules=(GovernanceRule(rule_id="original", effect=GovernanceEffect.ADMIT),),
        )
        uow.commit()

    with UnitOfWork() as uow, pytest.raises(GovernancePolicyVersionExistsError) as exc:
        _manager(uow.session).publish_version(
            policy_key="p",
            version=1,
            rules=(GovernanceRule(rule_id="impostora", effect=GovernanceEffect.DENY),),
        )
    assert exc.value.error_code.code == "PIA-8027"

    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO governance_policies "
                "(id, policy_key, version, rules, created_at, updated_at) "
                "VALUES (:i, 'p', 1, '[]', now(), now())"
            ),
            {"i": uuid.uuid4()},
        )

    with UnitOfWork() as uow:
        versoes = _manager(uow.session).list_versions("p")
        # Ler dentro da sessão: instâncias ORM não sobrevivem ao
        # fechamento da UnitOfWork.
        assert len(versoes) == 1
        assert versoes[0].typed_rules[0].rule_id == "original"


# ======================================================================
# 4 — vigência
# ======================================================================


def test_gi4_temporal_effectiveness_is_deterministic():
    """(4) Vigência `[from, until)`, com limite final exclusivo.

    Exclusivo de propósito: com limite inclusivo, duas versões
    contíguas se sobrepõem exatamente no instante da virada e "qual
    valia?" passa a ter duas respostas.
    """
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 6, 1, tzinfo=UTC)
    t2 = datetime(2026, 12, 1, tzinfo=UTC)

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        manager.publish_version(policy_key="p", effective_from=t0, effective_until=t1)
        uow.commit()
    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        manager.publish_version(policy_key="p", effective_from=t1, effective_until=t2)
        uow.commit()

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        assert manager.effective_version_at("p", t0).version == 1
        assert manager.effective_version_at("p", t1 - timedelta(seconds=1)).version == 1
        # No instante exato da virada, apenas a segunda vigora.
        assert manager.effective_version_at("p", t1).version == 2
        assert manager.effective_version_at("p", t2 - timedelta(seconds=1)).version == 2
        assert manager.effective_version_at("p", t2) is None
        assert manager.effective_version_at("p", t0 - timedelta(days=1)) is None


def test_gi4b_invalid_effective_window_is_rejected_by_the_database():
    """A janela incoerente é recusada pelo `CHECK`, não só pelo código."""
    with UnitOfWork() as uow, pytest.raises(ValueError):
        _manager(uow.session).publish_version(
            policy_key="p",
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            effective_until=datetime(2026, 1, 1, tzinfo=UTC),
        )

    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO governance_policies "
                "(id, policy_key, version, rules, effective_from, effective_until, "
                "created_at, updated_at) VALUES "
                "(:i, 'x', 1, '[]', '2026-06-01', '2026-01-01', now(), now())"
            ),
            {"i": uuid.uuid4()},
        )

    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO governance_policies "
                "(id, policy_key, version, rules, created_at, updated_at) "
                "VALUES (:i, 'x', 0, '[]', now(), now())"
            ),
            {"i": uuid.uuid4()},
        )


# ======================================================================
# 5–6 — aplicabilidade e ausência de concessão implícita
# ======================================================================


def test_gi5_applicability_uses_authorized_context_dimensions():
    """(5) Aplicabilidade vem de `domain_ids`, `actor_ref` e `purpose`.

    Exatamente as dimensões que o `MemoryContext` da E4.2 expõe —
    nenhuma inventada, e `session_id` deliberadamente **não**
    participa: sessão não é identidade nem autoridade.
    """
    refs = _seed_patrimony()
    regra = GovernanceRule(
        rule_id="revisao-d1",
        effect=GovernanceEffect.ADMIT,
        operations=frozenset({CognitiveOperation.READ}),
        domain_ids=frozenset({refs["d1"]}),
        actor_refs=frozenset({"ana"}),
        purposes=frozenset({"revisão"}),
    )
    with UnitOfWork() as uow:
        _manager(uow.session).publish_version(policy_key="p", rules=(regra,))
        uow.commit()

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        policy = manager.get_version("p", 1)

        casa = MemoryContext.build(
            domain_ids=[refs["d1"]], actor_ref="ana", purpose="revisão", session_id="s1"
        )
        assert (
            manager.evaluate(policy=policy, operation=CognitiveOperation.READ, context=casa).outcome
            is GovernanceOutcome.ADMISSIBLE
        )

        # Sessão diferente, mesmas dimensões relevantes: mesmo resultado.
        outra_sessao = casa.derive(session_id="s2")
        assert (
            manager.evaluate(
                policy=policy, operation=CognitiveOperation.READ, context=outra_sessao
            ).outcome
            is GovernanceOutcome.ADMISSIBLE
        )

        for divergente in (
            casa.derive(actor_ref="zoe"),
            casa.derive(purpose="outro"),
            casa.without_domains(),
        ):
            assert (
                manager.evaluate(
                    policy=policy, operation=CognitiveOperation.READ, context=divergente
                ).outcome
                is GovernanceOutcome.NOT_APPLICABLE
            )


def test_gi6_actor_without_applicable_rule_is_not_admissible():
    """(6) Ator presente, nenhuma regra aplicável ⇒ não concede."""
    with UnitOfWork() as uow:
        _manager(uow.session).publish_version(
            policy_key="p",
            rules=(
                GovernanceRule(
                    rule_id="so-expose",
                    effect=GovernanceEffect.ADMIT,
                    operations=frozenset({CognitiveOperation.EXPOSE}),
                ),
            ),
        )
        uow.commit()

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        decisao = manager.evaluate(
            policy=manager.get_version("p", 1),
            operation=CognitiveOperation.READ,
            context=MemoryContext.build(actor_ref="ana"),
        )

    assert decisao.outcome is GovernanceOutcome.NOT_APPLICABLE
    assert decisao.is_admissible is False


# ======================================================================
# 11–12 — nenhuma decisão altera nada
# ======================================================================


def test_gi11_evaluation_is_read_only_and_changes_nothing():
    """(11) Nenhuma decisão altera patrimônio, domínio, membership,
    acessibilidade, proveniência ou história.

    Censo das dez tabelas mais listener de cursor contando escritas —
    a prova é o SQL emitido, não a intenção do código.
    """
    refs = _seed_patrimony()
    with UnitOfWork() as uow:
        _manager(uow.session).publish_version(
            policy_key="p",
            rules=(
                GovernanceRule(rule_id="a", effect=GovernanceEffect.ADMIT),
                GovernanceRule(
                    rule_id="d",
                    effect=GovernanceEffect.DENY,
                    operations=frozenset({CognitiveOperation.EXPOSE}),
                ),
            ),
        )
        uow.commit()

    todas = _COGNITIVE_TABLES + _MEMORY_TABLES + _GOVERNANCE_TABLES
    censo_antes = _census(todas)

    escritas = {"n": 0}
    padrao = re.compile(r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b", re.IGNORECASE)

    def _listen(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if padrao.match(statement):
            escritas["n"] += 1

    event.listen(engine, "before_cursor_execute", _listen)
    try:
        with UnitOfWork() as uow:
            manager = _manager(uow.session)
            policy = manager.get_version("p", 1)
            for operacao in CognitiveOperation:
                manager.evaluate(
                    policy=policy,
                    operation=operacao,
                    context=MemoryContext.build(
                        domain_ids=[refs["d1"]], actor_ref="ana", purpose="p"
                    ),
                )
    finally:
        event.remove(engine, "before_cursor_execute", _listen)

    assert escritas["n"] == 0, "DATABASE_WRITES_DURING_EVALUATION deve ser 0"
    assert _census(todas) == censo_antes

    # E o estado cognitivo continua exatamente o mesmo.
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        assert objects.get_by_id(refs["o2"]).accessibility is AccessibilityState.INACCESSIBLE
        assert objects.get_by_id(refs["o3"]).accessibility is AccessibilityState.CAUSALLY_EXTINCT
        assert objects.get_by_id(refs["o1"]).clid == refs["clid"]


def test_gi12_denial_does_not_produce_nonexistence():
    """(12) `DENIED != NONEXISTENT`.

    Depois de uma negativa, tudo continua existindo e recuperável — a
    decisão restringiu a operação, não o patrimônio.
    """
    refs = _seed_patrimony()
    with UnitOfWork() as uow:
        _manager(uow.session).publish_version(
            policy_key="p",
            rules=(GovernanceRule(rule_id="nega-tudo", effect=GovernanceEffect.DENY),),
        )
        uow.commit()

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        decisao = manager.evaluate(
            policy=manager.get_version("p", 1),
            operation=CognitiveOperation.READ,
            context=MemoryContext.build(domain_ids=[refs["d1"]], actor_ref="ana"),
        )
    assert decisao.outcome is GovernanceOutcome.INADMISSIBLE
    assert decisao.implies_nonexistence is False

    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        for coid in (refs["o1"], refs["o2"], refs["o3"]):
            assert objects.get_by_id(coid) is not None
        memberships = MemoryDomainMembershipRepository(uow.session)
        assert memberships.contains(domain_id=refs["d1"], coid=refs["o1"])
        assert MemoryDomainRepository(uow.session).get_by_id(refs["d1"]) is not None


# ======================================================================
# 13 — sync
# ======================================================================


def test_gi13_policy_never_enters_the_e3_sync_envelope():
    """(13) `GOVERNANCE_POLICY_SYNC = NONE`.

    Autoridade não é transferível: uma policy importada produziria
    objetos invisíveis no destino sem que ninguém ali tivesse
    decidido isso.
    """
    assert set(SECTION_BY_TABLE) == set(_COGNITIVE_TABLES)
    assert "governance_policies" not in SECTION_BY_TABLE
    for tabela in _MEMORY_TABLES + _GOVERNANCE_TABLES:
        assert tabela not in SECTION_BY_TABLE


# ======================================================================
# 14 — concorrência real
# ======================================================================


def test_gi14_concurrent_version_creation_yields_exactly_one():
    """(14) Duas sessões publicando a mesma versão ⇒ exatamente uma.

    A unicidade estrutural do banco basta; nenhum lock global foi
    acrescentado — mesma disciplina de E3.4.1 e da E4.1.
    """
    with UnitOfWork() as uow:
        _manager(uow.session).publish_version(policy_key="p")
        uow.commit()

    barreira = threading.Barrier(2)
    resultados: list[str] = []
    trava = threading.Lock()

    def _publicar() -> None:
        barreira.wait(timeout=10)
        try:
            with UnitOfWork() as uow:
                _manager(uow.session).publish_version(policy_key="p", version=2)
                uow.commit()
            desfecho = "ok"
        except GovernancePolicyVersionExistsError:
            desfecho = "exists"
        except Exception as exc:  # pragma: no cover - diagnóstico
            desfecho = f"outro:{type(exc).__name__}"
        with trava:
            resultados.append(desfecho)

    threads = [threading.Thread(target=_publicar) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    with engine.connect() as conn:
        total = conn.execute(
            sa.text("SELECT COUNT(*) FROM governance_policies WHERE policy_key='p' AND version=2")
        ).scalar_one()

    assert total == 1, f"exatamente uma versão 2 esperada; resultados={resultados}"
    assert resultados.count("ok") == 1
    assert all(r in ("ok", "exists") for r in resultados), resultados


# ======================================================================
# 15 — upgrade/downgrade
# ======================================================================


def test_gi15_downgrade_is_blocked_when_policies_exist():
    """(15) `CONDITIONALLY_REVERSIBLE` com guarda desde a migração
    inicial.

    Vazio: ciclo `head → anterior → head` funciona. Com policies
    publicadas: bloqueado, e nada é alterado.
    """
    anterior = "3799d45ff96d"

    migrations.downgrade(anterior)
    assert "governance_policies" not in sa.inspect(engine).get_table_names()
    migrations.upgrade("head")
    assert "governance_policies" in sa.inspect(engine).get_table_names()

    with UnitOfWork() as uow:
        _manager(uow.session).publish_version(
            policy_key="p", rules=(GovernanceRule(rule_id="r", effect=GovernanceEffect.ADMIT),)
        )
        uow.commit()

    with pytest.raises(Exception) as exc:
        migrations.downgrade(anterior)
    assert "GOVERNANCE_POLICY_DOWNGRADE_SEMANTICALLY_BLOCKED" in str(exc.value)

    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT COUNT(*) FROM governance_policies")).scalar_one() == 1
    assert "governance_policies" in sa.inspect(engine).get_table_names()


def test_gi16_publishing_writes_only_to_its_own_table():
    """Publicar escreve — e **apenas** na tabela de policies.

    A distinção que o prompt exige: criação/versionamento podem
    escrever nas suas próprias tabelas; avaliação é read-only.
    """
    refs = _seed_patrimony()
    censo_alheio = _census(_COGNITIVE_TABLES + _MEMORY_TABLES)

    with UnitOfWork() as uow:
        _manager(uow.session).publish_version(
            policy_key="p",
            rules=(
                GovernanceRule(
                    rule_id="r",
                    effect=GovernanceEffect.ADMIT,
                    domain_ids=frozenset({refs["d1"]}),
                ),
            ),
        )
        uow.commit()

    assert _census(_COGNITIVE_TABLES + _MEMORY_TABLES) == censo_alheio
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT COUNT(*) FROM governance_policies")).scalar_one() == 1


def test_gi17_policy_references_domain_without_owning_it():
    """A policy referencia `domain_id` **por valor**, sem FK.

    `owner`/`policy_ref` não entram em `MemoryDomain`: governança não
    é dona do domínio, e travar a evolução do domínio por causa de uma
    regra seria incorporar governança onde ela não pertence.
    """
    fks = sa.inspect(engine).get_foreign_keys("governance_policies")
    assert fks == [], "governance_policies não deve ter FK alguma"

    colunas_dominio = {c["name"] for c in sa.inspect(engine).get_columns("memory_domains")}
    assert colunas_dominio == {
        "id",
        "name",
        "created_at",
        "updated_at",
    }, "E4_1_SEMANTICS_UNCHANGED: MemoryDomain não ganhou owner nem policy_ref"

    # E uma regra pode citar um domínio que nem existe — governança
    # informa; não valida patrimônio alheio nem o fabrica.
    inexistente = uuid.uuid4()
    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        manager.publish_version(
            policy_key="p",
            rules=(
                GovernanceRule(
                    rule_id="r",
                    effect=GovernanceEffect.ADMIT,
                    domain_ids=frozenset({inexistente}),
                ),
            ),
        )
        uow.commit()
    with engine.connect() as conn:
        assert (
            conn.execute(
                sa.text("SELECT COUNT(*) FROM memory_domains WHERE id = :d"), {"d": inexistente}
            ).scalar_one()
            == 0
        )


# ======================================================================
# E4.3.3 — Explicit Accessibility Transition Authority, contra o banco
# ======================================================================


def _chave_e433() -> str:
    return f"e433-{uuid.uuid4().hex[:10]}"


def _limpar_policy(chave: str) -> None:
    with UnitOfWork() as uow:
        uow.session.execute(
            sa.text("DELETE FROM governance_policies WHERE policy_key = :k"), {"k": chave}
        )
        uow.commit()


def _descritor_transicao() -> CapabilityDescriptor:
    return CapabilityDescriptor(
        operation=CognitiveOperation.ACCESSIBILITY_TRANSITION,
        engagement=CapabilityEngagement.ANALYTICAL,
    )


def test_gi433_wildcard_policy_does_not_authorize_the_new_operation():
    """O caso central: policy publicada com curinga histórico não ganha
    autoridade sobre a capacidade nova.

        OLD AUTHORIZATION != CONSENT TO A NEW CAPABILITY
    """
    chave = _chave_e433()
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="curinga",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset(),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()

        with UnitOfWork() as uow:
            manager = GovernanceManager(GovernancePolicyRepository(uow.session))
            # a mesma policy AUTORIZA uma operação histórica...
            historica = manager.resolve(
                descriptor=CapabilityDescriptor(operation=CognitiveOperation.READ),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 6, 1, tzinfo=UTC),
            )
            # ...e NÃO alcança a nova
            nova = manager.resolve(
                descriptor=_descritor_transicao(),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 6, 1, tzinfo=UTC),
            )

        assert historica.outcome is GovernanceOutcome.ADMISSIBLE
        assert historica.execution_authorized is True

        assert nova.outcome is GovernanceOutcome.NOT_APPLICABLE
        assert nova.execution_authorized is False
        assert nova.matched_rule_id is None
    finally:
        _limpar_policy(chave)


def test_gi433_explicit_opt_in_authorizes_the_new_operation():
    chave = _chave_e433()
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="opt-in",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset({CognitiveOperation.ACCESSIBILITY_TRANSITION}),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()

        with UnitOfWork() as uow:
            manager = GovernanceManager(GovernancePolicyRepository(uow.session))
            resolucao = manager.resolve(
                descriptor=_descritor_transicao(),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 6, 1, tzinfo=UTC),
            )
            # e o opt-in explícito NÃO passa a autorizar READ
            leitura = manager.resolve(
                descriptor=CapabilityDescriptor(operation=CognitiveOperation.READ),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 6, 1, tzinfo=UTC),
            )

        assert resolucao.outcome is GovernanceOutcome.ADMISSIBLE
        assert resolucao.execution_authorized is True
        assert resolucao.matched_rule_id == "opt-in"
        assert resolucao.policy_key == chave

        assert leitura.outcome is GovernanceOutcome.NOT_APPLICABLE
        assert leitura.execution_authorized is False
    finally:
        _limpar_policy(chave)


def test_gi433_explicit_deny_is_inadmissible_not_merely_not_applicable():
    chave = _chave_e433()
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="nega",
                        effect=GovernanceEffect.DENY,
                        operations=frozenset({CognitiveOperation.ACCESSIBILITY_TRANSITION}),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()

        with UnitOfWork() as uow:
            resolucao = GovernanceManager(GovernancePolicyRepository(uow.session)).resolve(
                descriptor=_descritor_transicao(),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 6, 1, tzinfo=UTC),
            )
        assert resolucao.outcome is GovernanceOutcome.INADMISSIBLE
        assert resolucao.execution_authorized is False
    finally:
        _limpar_policy(chave)


def test_gi433_published_policy_is_not_rewritten_by_the_corrective():
    """O payload histórico continua byte a byte o mesmo, e a versão
    publicada permanece imutável."""
    chave = _chave_e433()
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="curinga",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset(),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()

        with UnitOfWork() as uow:
            antes = uow.session.execute(
                sa.text("SELECT rules::text FROM governance_policies WHERE policy_key = :k"),
                {"k": chave},
            ).scalar_one()

        # avaliar a nova operação não pode tocar a linha
        with UnitOfWork() as uow:
            GovernanceManager(GovernancePolicyRepository(uow.session)).resolve(
                descriptor=_descritor_transicao(),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 6, 1, tzinfo=UTC),
            )

        with UnitOfWork() as uow:
            depois = uow.session.execute(
                sa.text("SELECT rules::text FROM governance_policies WHERE policy_key = :k"),
                {"k": chave},
            ).scalar_one()
        assert depois == antes
        assert '"operations": []' in depois

        # e continua imutável pelo repositório
        with UnitOfWork() as uow:
            repo = GovernancePolicyRepository(uow.session)
            publicada = repo.get_version(chave, 1)
            with pytest.raises(GovernancePolicyImmutableError):
                repo.update(publicada)
            with pytest.raises(GovernancePolicyImmutableError):
                repo.delete(publicada)
    finally:
        _limpar_policy(chave)


def test_gi433_new_version_can_grant_what_the_old_one_could_not():
    """O caminho legítimo para autorizar a nova capacidade: publicar uma
    versão nova, não reescrever a antiga."""
    chave = _chave_e433()
    try:
        with UnitOfWork() as uow:
            repo = GovernancePolicyRepository(uow.session)
            repo.add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="curinga",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset(),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
                effective_until=datetime(2024, 6, 1, tzinfo=UTC),
            )
            repo.add_policy(
                policy_key=chave,
                version=2,
                rules=(
                    GovernanceRule(
                        rule_id="opt-in",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset({CognitiveOperation.ACCESSIBILITY_TRANSITION}),
                    ),
                ),
                effective_from=datetime(2024, 6, 1, tzinfo=UTC),
            )
            uow.commit()

        with UnitOfWork() as uow:
            manager = GovernanceManager(GovernancePolicyRepository(uow.session))
            antiga = manager.resolve(
                descriptor=_descritor_transicao(),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 3, 1, tzinfo=UTC),
            )
            nova = manager.resolve(
                descriptor=_descritor_transicao(),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 9, 1, tzinfo=UTC),
            )
        assert antiga.outcome is GovernanceOutcome.NOT_APPLICABLE
        assert nova.outcome is GovernanceOutcome.ADMISSIBLE
        assert nova.policy_version == 2
    finally:
        _limpar_policy(chave)


def test_gi433_new_operation_round_trips_through_postgresql():
    chave = _chave_e433()
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="opt-in",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset({CognitiveOperation.ACCESSIBILITY_TRANSITION}),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()

        with UnitOfWork() as uow:
            bruto = uow.session.execute(
                sa.text("SELECT rules::text FROM governance_policies WHERE policy_key = :k"),
                {"k": chave},
            ).scalar_one()
            assert '"accessibility_transition"' in bruto

            publicada = GovernancePolicyRepository(uow.session).get_version(chave, 1)
            regras = GovernancePolicy.deserialize_rules(publicada.rules)
        assert regras[0].operations == frozenset({CognitiveOperation.ACCESSIBILITY_TRANSITION})
    finally:
        _limpar_policy(chave)


def test_gi433_no_writes_during_resolution_of_the_new_operation():
    chave = _chave_e433()
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="curinga",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset(),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()

        escritas: list[str] = []

        def _contar(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                escritas.append(statement)

        with UnitOfWork() as uow:
            engine = uow.session.get_bind()
            event.listen(engine, "before_cursor_execute", _contar)
            try:
                GovernanceManager(GovernancePolicyRepository(uow.session)).resolve(
                    descriptor=_descritor_transicao(),
                    context=MemoryContext(),
                    policy_key=chave,
                    moment=datetime(2024, 6, 1, tzinfo=UTC),
                )
                assert not uow.session.new
                assert not uow.session.dirty
                assert not uow.session.deleted
            finally:
                event.remove(engine, "before_cursor_execute", _contar)

        assert escritas == []
    finally:
        _limpar_policy(chave)


# ======================================================================
# E4.3.4 — vínculo de contexto contra o banco real
# ======================================================================


def test_gi434_resolutions_for_different_domains_are_distinguishable():
    """O defeito do preflight da E4.8, fechado com o manager real."""
    chave = f"e434-{uuid.uuid4().hex[:10]}"
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="curinga",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset({CognitiveOperation.READ}),
                    ),
                ),
                effective_from=_INICIO,
            )
            uow.commit()

        with UnitOfWork() as uow:
            manager = GovernanceManager(GovernancePolicyRepository(uow.session))
            a = manager.resolve(
                descriptor=CapabilityDescriptor(operation=CognitiveOperation.READ),
                context=MemoryContext(domain_ids=(d1,)),
                policy_key=chave,
                moment=_MOMENTO,
            )
            b = manager.resolve(
                descriptor=CapabilityDescriptor(operation=CognitiveOperation.READ),
                context=MemoryContext(domain_ids=(d2,)),
                policy_key=chave,
                moment=_MOMENTO,
            )
        # mesmo outcome, mas resoluções distinguíveis
        assert a.outcome is b.outcome is GovernanceOutcome.ADMISSIBLE
        assert a != b
        assert a.context_domain_ids == (d1,)
        assert b.context_domain_ids == (d2,)
    finally:
        _limpar_policy(chave)


def test_gi434_session_only_difference_keeps_resolutions_equal():
    """`SESSION DIFFERENCE != GOVERNANCE DIFFERENCE`."""
    chave = f"e434-{uuid.uuid4().hex[:10]}"
    dominio = uuid.uuid4()
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="curinga",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset({CognitiveOperation.READ}),
                    ),
                ),
                effective_from=_INICIO,
            )
            uow.commit()
        with UnitOfWork() as uow:
            manager = GovernanceManager(GovernancePolicyRepository(uow.session))
            comum = {
                "descriptor": CapabilityDescriptor(operation=CognitiveOperation.READ),
                "policy_key": chave,
                "moment": _MOMENTO,
            }
            a = manager.resolve(
                context=MemoryContext(domain_ids=(dominio,), session_id="s1"), **comum
            )
            b = manager.resolve(
                context=MemoryContext(domain_ids=(dominio,), session_id="s2"), **comum
            )
        assert a == b
    finally:
        _limpar_policy(chave)


@pytest.mark.parametrize("cenario", ["sem_policy", "sem_versao_vigente", "proibido"])
def test_gi434_refusals_still_bind_the_received_context(cenario):
    """`NO LOCAL POLICY CONSULTED != NO CONTEXT RECEIVED`."""
    chave = f"e434-{uuid.uuid4().hex[:10]}"
    dominio = uuid.uuid4()
    contexto = MemoryContext(domain_ids=(dominio,), actor_ref="ana", purpose="curadoria")
    try:
        if cenario == "sem_versao_vigente":
            with UnitOfWork() as uow:
                GovernancePolicyRepository(uow.session).add_policy(
                    policy_key=chave,
                    version=1,
                    rules=(),
                    effective_from=datetime(2030, 1, 1, tzinfo=UTC),
                )
                uow.commit()

        descritor = CapabilityDescriptor(operation=CognitiveOperation.READ)
        policy_key: str | None = chave
        if cenario == "sem_policy":
            policy_key = None
        elif cenario == "proibido":
            policy_key = None
            descritor = CapabilityDescriptor(
                operation=CognitiveOperation.READ,
                capabilities=frozenset({CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT}),
                engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
            )

        with UnitOfWork() as uow:
            resolucao = GovernanceManager(GovernancePolicyRepository(uow.session)).resolve(
                descriptor=descritor,
                context=contexto,
                policy_key=policy_key,
                moment=_MOMENTO,
            )

        assert resolucao.execution_authorized is False
        assert resolucao.context_domain_ids == (dominio,)
        assert resolucao.context_actor_ref == "ana"
        assert resolucao.context_purpose == "curadoria"
        if cenario == "proibido":
            assert resolucao.outcome is GovernanceOutcome.PROHIBITED
            # a policy local continua não consultada
            assert resolucao.policy_key is None
            assert resolucao.matched_rule_id is None
    finally:
        _limpar_policy(chave)


def test_gi434_no_writes_during_resolution():
    chave = f"e434-{uuid.uuid4().hex[:10]}"
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="r",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset({CognitiveOperation.READ}),
                    ),
                ),
                effective_from=_INICIO,
            )
            uow.commit()

        escritas: list[str] = []

        def _contar(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                escritas.append(statement)

        with UnitOfWork() as uow:
            engine = uow.session.get_bind()
            event.listen(engine, "before_cursor_execute", _contar)
            try:
                GovernanceManager(GovernancePolicyRepository(uow.session)).resolve(
                    descriptor=CapabilityDescriptor(operation=CognitiveOperation.READ),
                    context=MemoryContext(domain_ids=(uuid.uuid4(),)),
                    policy_key=chave,
                    moment=_MOMENTO,
                )
                assert not uow.session.dirty
            finally:
                event.remove(engine, "before_cursor_execute", _contar)
        assert escritas == []
    finally:
        _limpar_policy(chave)


# ======================================================================
# E4.3.5 — Retention Operation Authority, contra o banco
#
# O que só o PostgreSQL demonstra: que policies JÁ PUBLICADAS não ganham
# a autoridade nova, que o payload gravado antes do corretivo continua
# byte-idêntico, e que resolver as operações novas não escreve nada.
# ======================================================================


_OPERACOES_E435 = (
    CognitiveOperation.RETENTION_ASSESSMENT,
    CognitiveOperation.RETENTION_DISPOSITION,
    CognitiveOperation.LEGAL_ERASURE,
)


def _chave_e435() -> str:
    return f"e435-{uuid.uuid4().hex[:10]}"


def _descritor_e435(operacao: CognitiveOperation) -> CapabilityDescriptor:
    return CapabilityDescriptor(operation=operacao, engagement=CapabilityEngagement.ANALYTICAL)


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_gi435_published_wildcard_policy_does_not_authorize_retention(operacao):
    """O caso central do corretivo, contra uma policy REAL já gravada.

    OLD WILDCARD AUTHORITY != FUTURE RETENTION AUTHORITY
    """
    chave = _chave_e435()
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="curinga",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset(),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()

        with UnitOfWork() as uow:
            manager = GovernanceManager(GovernancePolicyRepository(uow.session))
            historica = manager.resolve(
                descriptor=CapabilityDescriptor(operation=CognitiveOperation.READ),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 6, 1, tzinfo=UTC),
            )
            nova = manager.resolve(
                descriptor=_descritor_e435(operacao),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 6, 1, tzinfo=UTC),
            )

        assert historica.outcome is GovernanceOutcome.ADMISSIBLE
        assert nova.outcome is GovernanceOutcome.NOT_APPLICABLE
        assert nova.execution_authorized is False
        assert nova.matched_rule_id is None
    finally:
        _limpar_policy(chave)


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_gi435_explicit_opt_in_authorizes_only_that_retention_operation(operacao):
    """Opt-in explícito concede — e concede **só** a operação citada."""
    chave = _chave_e435()
    outras = [op for op in _OPERACOES_E435 if op is not operacao]
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="opt-in",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset({operacao}),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()

        with UnitOfWork() as uow:
            manager = GovernanceManager(GovernancePolicyRepository(uow.session))
            concedida = manager.resolve(
                descriptor=_descritor_e435(operacao),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 6, 1, tzinfo=UTC),
            )
            negadas = [
                manager.resolve(
                    descriptor=_descritor_e435(outra),
                    context=MemoryContext(),
                    policy_key=chave,
                    moment=datetime(2024, 6, 1, tzinfo=UTC),
                )
                for outra in outras
            ]

        assert concedida.outcome is GovernanceOutcome.ADMISSIBLE
        assert concedida.operation is operacao
        assert concedida.matched_rule_id == "opt-in"
        for resolucao in negadas:
            assert resolucao.outcome is GovernanceOutcome.NOT_APPLICABLE
    finally:
        _limpar_policy(chave)


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_gi435_explicit_deny_is_inadmissible_against_the_database(operacao):
    chave = _chave_e435()
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="nega",
                        effect=GovernanceEffect.DENY,
                        operations=frozenset({operacao}),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()

        with UnitOfWork() as uow:
            resolucao = GovernanceManager(GovernancePolicyRepository(uow.session)).resolve(
                descriptor=_descritor_e435(operacao),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 6, 1, tzinfo=UTC),
            )

        assert resolucao.outcome is GovernanceOutcome.INADMISSIBLE
        assert resolucao.matched_rule_id == "nega"
    finally:
        _limpar_policy(chave)


def test_gi435_published_policy_row_is_not_rewritten_by_the_corrective():
    """Nenhuma linha de policy existente é alterada pelo corretivo.

    Grava o payload, lê os bytes do JSONB, resolve as três operações
    novas e confere que o payload permaneceu idêntico — inclusive o
    `updated_at`, que denunciaria uma reescrita silenciosa.
    """
    chave = _chave_e435()
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="historica",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset(
                            {CognitiveOperation.READ, CognitiveOperation.TRANSFORM}
                        ),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()

        with UnitOfWork() as uow:
            antes = uow.session.execute(
                sa.text(
                    "SELECT rules::text, updated_at FROM governance_policies "
                    "WHERE policy_key = :k"
                ),
                {"k": chave},
            ).one()

        with UnitOfWork() as uow:
            manager = GovernanceManager(GovernancePolicyRepository(uow.session))
            for operacao in _OPERACOES_E435:
                manager.resolve(
                    descriptor=_descritor_e435(operacao),
                    context=MemoryContext(),
                    policy_key=chave,
                    moment=datetime(2024, 6, 1, tzinfo=UTC),
                )

        with UnitOfWork() as uow:
            depois = uow.session.execute(
                sa.text(
                    "SELECT rules::text, updated_at FROM governance_policies "
                    "WHERE policy_key = :k"
                ),
                {"k": chave},
            ).one()

        assert depois[0] == antes[0]
        assert depois[1] == antes[1]
        # e o payload continua sem citar operação alguma do corretivo
        for token in ("retention_assessment", "retention_disposition", "legal_erasure"):
            assert token not in antes[0]
    finally:
        _limpar_policy(chave)


def test_gi435_a_new_version_can_grant_what_the_old_one_could_not():
    """A autoridade nova entra por **novo ato de publicação**, nunca
    retroativamente na versão antiga."""
    chave = _chave_e435()
    operacao = CognitiveOperation.LEGAL_ERASURE
    try:
        with UnitOfWork() as uow:
            repo = GovernancePolicyRepository(uow.session)
            repo.add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="curinga",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset(),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
                effective_until=datetime(2024, 6, 1, tzinfo=UTC),
            )
            repo.add_policy(
                policy_key=chave,
                version=2,
                rules=(
                    GovernanceRule(
                        rule_id="opt-in",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset({operacao}),
                    ),
                ),
                effective_from=datetime(2024, 6, 1, tzinfo=UTC),
            )
            uow.commit()

        with UnitOfWork() as uow:
            manager = GovernanceManager(GovernancePolicyRepository(uow.session))
            sob_v1 = manager.resolve(
                descriptor=_descritor_e435(operacao),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 3, 1, tzinfo=UTC),
            )
            sob_v2 = manager.resolve(
                descriptor=_descritor_e435(operacao),
                context=MemoryContext(),
                policy_key=chave,
                moment=datetime(2024, 9, 1, tzinfo=UTC),
            )

        assert sob_v1.outcome is GovernanceOutcome.NOT_APPLICABLE
        assert sob_v1.policy_version == 1
        assert sob_v2.outcome is GovernanceOutcome.ADMISSIBLE
        assert sob_v2.policy_version == 2
    finally:
        _limpar_policy(chave)


def test_gi435_published_policy_cannot_be_mutated_to_gain_retention_authority():
    """§9.4: policy publicada é imutável — nem pelo repositório, nem por
    mutação ORM direta."""
    chave = _chave_e435()
    try:
        with UnitOfWork() as uow:
            repo = GovernancePolicyRepository(uow.session)
            policy = repo.add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="curinga",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset(),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()
            policy_id = policy.id

        novas_regras = GovernancePolicy.serialize_rules(
            (
                GovernanceRule(
                    rule_id="curinga",
                    effect=GovernanceEffect.ADMIT,
                    operations=frozenset(_OPERACOES_E435),
                ),
            )
        )

        with UnitOfWork() as uow:
            repo = GovernancePolicyRepository(uow.session)
            alvo = repo.get_version(chave, 1)
            with pytest.raises(GovernancePolicyImmutableError):
                alvo.rules = novas_regras
                uow.session.flush()

        with UnitOfWork() as uow:
            preservada = GovernancePolicyRepository(uow.session).get_version(chave, 1)
            assert preservada.id == policy_id
            assert preservada.rules[0]["operations"] == []
    finally:
        _limpar_policy(chave)


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_gi435_no_writes_during_resolution_of_the_new_operations(operacao):
    """Resolver autoridade de retenção não escreve nada — nem na policy,
    nem no patrimônio. O corretivo é vocabulário."""
    chave = _chave_e435()
    escritas: list[str] = []

    def _espiao(conn, cursor, statement, parameters, context, executemany):
        if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", statement, re.IGNORECASE):
            escritas.append(statement)

    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="opt-in",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset({operacao}),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()

        event.listen(engine, "before_cursor_execute", _espiao)
        try:
            with UnitOfWork() as uow:
                resolucao = GovernanceManager(GovernancePolicyRepository(uow.session)).resolve(
                    descriptor=_descritor_e435(operacao),
                    context=MemoryContext(),
                    policy_key=chave,
                    moment=datetime(2024, 6, 1, tzinfo=UTC),
                )
        finally:
            event.remove(engine, "before_cursor_execute", _espiao)

        assert resolucao.outcome is GovernanceOutcome.ADMISSIBLE
        assert escritas == []
    finally:
        _limpar_policy(chave)


@pytest.mark.parametrize("operacao", _OPERACOES_E435)
def test_gi435_new_operation_round_trips_through_postgresql(operacao):
    """O token atravessa o JSONB e volta como o mesmo membro tipado."""
    chave = _chave_e435()
    try:
        with UnitOfWork() as uow:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=chave,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="r",
                        effect=GovernanceEffect.ADMIT,
                        operations=frozenset({operacao}),
                    ),
                ),
                effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
            uow.commit()

        with UnitOfWork() as uow:
            gravado = uow.session.execute(
                sa.text("SELECT rules::text FROM governance_policies WHERE policy_key = :k"),
                {"k": chave},
            ).scalar_one()
            assert operacao.value in gravado

            (regra,) = GovernancePolicyRepository(uow.session).get_version(chave, 1).typed_rules
            assert regra.operations == frozenset({operacao})
    finally:
        _limpar_policy(chave)


def test_gi435_corrective_created_no_table_and_no_migration_head_change():
    """§14.3: o corretivo da E4.3.5 é vocabulário — não criou tabela
    nem migração.

    Atualizado pela E4.9.6. Até a cadeia 75 este teste asseverava a
    AUSÊNCIA de `retention_policies`; a tabela passou a existir pela
    migração `c8a3f5017e94`, autorizada pelo prompt canônico da
    E4.9.6. O que continua protegido é a **autoria**: a tabela foi
    criada por aquela fatia, não por este corretivo — e o guarda
    irmão `test_e435_production_diff_is_confined_to_the_enum_module`
    segue provando que a E4.3.5 não tocou produção além do enum.
    """
    with UnitOfWork() as uow:
        existe = uow.session.execute(
            sa.text("SELECT to_regclass('public.retention_policies')")
        ).scalar_one()
    assert existe is not None
    assert migrations.head_revision() == "a7f31c05be24"
    assert migrations.current_revision() == "a7f31c05be24"
