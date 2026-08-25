"""
Integração da E4.8 — Memory Isolation, contra PostgreSQL real.

A prova decisiva é a **composição real**: `MemoryRetrievalManager`,
`GovernanceManager`, `ContextManager` e `MemoryDomainMembershipRepository`
injetados diretamente nas portas, sem adapter.

Este arquivo importa os dois lados para montar o cenário — permitido; o
que a fronteira veda é o import de `app.cognitive` no **código de
produção** de `app/memory`.
"""

import dataclasses
import threading
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import ProvenanceActorType, ProvenanceSourceType
from app.cognitive.models.provenance_record import ProvenanceRecord
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.repositories.search_repository import SearchRepository
from app.cognitive.schemas.search_criteria import SearchCriteria
from app.cognitive.services.search_engine import SearchEngine
from app.database.health import check_database_health
from app.memory.errors.exceptions import (
    IsolationContractViolationError,
    IsolationScopeRequiredError,
)
from app.memory.models.governance_enums import (
    CognitiveOperation,
    GovernanceEffect,
    GovernanceOutcome,
)
from app.memory.repositories.governance_policy_repository import GovernancePolicyRepository
from app.memory.repositories.memory_domain_membership_repository import (
    MemoryDomainMembershipRepository,
)
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository
from app.memory.schemas.governance import GovernanceRule
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.context_manager import ContextManager
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.memory_isolation_manager import MemoryIsolationManager
from app.memory.services.platform_safety_boundary import CapabilityDescriptor
from app.memory.services.retrieval_manager import MemoryRetrievalManager
from app.repositories.unit_of_work import UnitOfWork

_INICIO = datetime(2024, 1, 1, tzinfo=UTC)
_MOMENTO = datetime(2024, 6, 1, tzinfo=UTC)


def _postgres_pronto() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(not _postgres_pronto(), reason="PostgreSQL real indisponível.")


def _compor(session):
    """Composição real: nenhum dublê."""
    retrieval = MemoryRetrievalManager(
        SearchEngine(SearchRepository(session)),
        GovernanceManager(GovernancePolicyRepository(session)),
        ContextManager(MemoryDomainRepository(session)),
        MemoryDomainMembershipRepository(session),
    )
    return MemoryIsolationManager(
        retrieval,
        GovernanceManager(GovernancePolicyRepository(session)),
        ContextManager(MemoryDomainRepository(session)),
        MemoryDomainMembershipRepository(session),
    )


def _descritor() -> CapabilityDescriptor:
    return CapabilityDescriptor(operation=CognitiveOperation.READ)


def _trace() -> str:
    return f"iso-{uuid.uuid4().hex[:12]}"


def _criar_objeto(trace_id: str) -> uuid.UUID:
    with UnitOfWork() as uow:
        objeto = ObjectRepository(uow.session).add(CognitiveObject())
        ProvenanceRepository(uow.session).add(
            ProvenanceRecord(
                coid=objeto.id,
                source_type=ProvenanceSourceType.HUMAN,
                actor_type=ProvenanceActorType.HUMAN,
                trace_id=trace_id,
            )
        )
        uow.commit()
        return objeto.id


def _criar_dominio() -> uuid.UUID:
    with UnitOfWork() as uow:
        dominio = MemoryDomainRepository(uow.session).add_domain(
            name=f"dom-{uuid.uuid4().hex[:10]}"
        )
        uow.commit()
        return dominio.id


def _associar(domain_id: uuid.UUID, coid: uuid.UUID) -> None:
    with UnitOfWork() as uow:
        MemoryDomainMembershipRepository(uow.session).add_membership(domain_id=domain_id, coid=coid)
        uow.commit()


def _publicar(chave: str, *, dominios=(), effect=GovernanceEffect.ADMIT) -> None:
    with UnitOfWork() as uow:
        GovernancePolicyRepository(uow.session).add_policy(
            policy_key=chave,
            version=1,
            rules=(
                GovernanceRule(
                    rule_id="r1",
                    effect=effect,
                    operations=frozenset({CognitiveOperation.READ}),
                    domain_ids=frozenset(dominios),
                ),
            ),
            effective_from=_INICIO,
        )
        uow.commit()


def _limpar(coids, dominios, chaves) -> None:
    with UnitOfWork() as uow:
        s = uow.session
        if coids:
            alvos = [str(c) for c in coids]
            s.execute(
                sa.text("DELETE FROM memory_domain_memberships WHERE coid = ANY(:c ::uuid[])"),
                {"c": alvos},
            )
            s.execute(
                sa.text("DELETE FROM provenance_records WHERE coid = ANY(:c ::uuid[])"),
                {"c": alvos},
            )
            s.execute(
                sa.text("DELETE FROM cognitive_objects WHERE id = ANY(:c ::uuid[])"),
                {"c": alvos},
            )
        if dominios:
            s.execute(
                sa.text("DELETE FROM memory_domains WHERE id = ANY(:d ::uuid[])"),
                {"d": [str(d) for d in dominios]},
            )
        if chaves:
            s.execute(
                sa.text("DELETE FROM governance_policies WHERE policy_key = ANY(:k ::text[])"),
                {"k": chaves},
            )
        uow.commit()


def _isolar(session, contexto, chave, **kw):
    return _compor(session).retrieve_isolated(
        context=contexto,
        descriptor=_descritor(),
        criteria=SearchCriteria(trace_id=kw.pop("trace_id")),
        policy_key=chave,
        moment=kw.pop("moment", _MOMENTO),
        **kw,
    )


# --- Cenário canônico do vazamento ------------------------------------


def test_ii1_domain_not_authorized_stops_before_retrieval():
    """O cenário do §7: policy admite só `D1`, pedido declara `{D1, D2}`.

    Sem a E4.8, a governança casava por interseção e a vista compunha
    por união — e patrimônio exclusivo de `D2` aparecia.
    """
    trace = _trace()
    a, b = _criar_objeto(trace), _criar_objeto(trace)
    d1, d2 = _criar_dominio(), _criar_dominio()
    _associar(d1, a)
    _associar(d2, b)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave, dominios=(d1,))
    try:
        with UnitOfWork() as uow:
            resultado = _isolar(
                uow.session,
                MemoryContext(domain_ids=(d1, d2)),
                chave,
                trace_id=trace,
            )
        assert resultado.authorized is False
        assert resultado.retrieval is None
        assert resultado.refused_domain_ids == (d2,)
        # e a decisão de d1 continua sendo ADMISSIBLE — a recusa é do
        # pedido, não uma reclassificação da autoridade concedida
        decisao_d1 = next(d for d in resultado.decisions if d.domain_id == d1)
        assert decisao_d1.outcome is GovernanceOutcome.ADMISSIBLE
    finally:
        _limpar([a, b], [d1, d2], [chave])


def test_ii2_both_domains_authorized_returns_the_correct_union():
    trace = _trace()
    a, b = _criar_objeto(trace), _criar_objeto(trace)
    d1, d2 = _criar_dominio(), _criar_dominio()
    _associar(d1, a)
    _associar(d2, b)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)  # curinga de domínio: admite READ em qualquer um
    try:
        with UnitOfWork() as uow:
            resultado = _isolar(
                uow.session,
                MemoryContext(domain_ids=(d1, d2)),
                chave,
                trace_id=trace,
            )
        assert resultado.authorized is True
        assert resultado.retrieval is not None
        assert set(resultado.retrieval.coids) == {a, b}
        assert len(resultado.decisions) == 2
    finally:
        _limpar([a, b], [d1, d2], [chave])


def test_ii3_object_exclusive_to_another_domain_never_appears():
    trace = _trace()
    a, b = _criar_objeto(trace), _criar_objeto(trace)
    d1, d2 = _criar_dominio(), _criar_dominio()
    _associar(d1, a)
    _associar(d2, b)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        with UnitOfWork() as uow:
            resultado = _isolar(uow.session, MemoryContext(domain_ids=(d1,)), chave, trace_id=trace)
        assert resultado.authorized is True
        assert resultado.retrieval is not None
        assert set(resultado.retrieval.coids) == {a}
        assert b not in resultado.retrieval.coids
    finally:
        _limpar([a, b], [d1, d2], [chave])


def test_ii4_shared_object_appears_once_without_duplication():
    """Item em `D1` e `D2` aparece uma vez sob `D1`."""
    trace = _trace()
    compartilhado = _criar_objeto(trace)
    d1, d2 = _criar_dominio(), _criar_dominio()
    _associar(d1, compartilhado)
    _associar(d2, compartilhado)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        with UnitOfWork() as uow:
            resultado = _isolar(uow.session, MemoryContext(domain_ids=(d1,)), chave, trace_id=trace)
        assert resultado.retrieval is not None
        assert resultado.retrieval.coids == (compartilhado,)
    finally:
        _limpar([compartilhado], [d1, d2], [chave])


def test_ii5_zero_domain_object_stays_valid_and_outside_the_isolated_view():
    """`ZERO-DOMAIN OBJECT IS VALID` — e continua existindo no banco."""
    trace = _trace()
    orfao = _criar_objeto(trace)
    associado = _criar_objeto(trace)
    d1 = _criar_dominio()
    _associar(d1, associado)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        with UnitOfWork() as uow:
            resultado = _isolar(uow.session, MemoryContext(domain_ids=(d1,)), chave, trace_id=trace)
        assert resultado.retrieval is not None
        assert set(resultado.retrieval.coids) == {associado}
        with UnitOfWork() as uow:
            existe = uow.session.execute(
                sa.text("SELECT count(*) FROM cognitive_objects WHERE id = :c"),
                {"c": str(orfao)},
            ).scalar_one()
        assert existe == 1, "objeto zero-domain continua válido"
    finally:
        _limpar([orfao, associado], [d1], [chave])


def test_ii6_versioned_policy_is_consumed_without_rewrite():
    trace = _trace()
    a = _criar_objeto(trace)
    d1 = _criar_dominio()
    _associar(d1, a)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave, dominios=(d1,))
    try:
        with UnitOfWork() as uow:
            antes = uow.session.execute(
                sa.text("SELECT rules::text FROM governance_policies WHERE policy_key = :k"),
                {"k": chave},
            ).scalar_one()
        with UnitOfWork() as uow:
            _isolar(uow.session, MemoryContext(domain_ids=(d1,)), chave, trace_id=trace)
        with UnitOfWork() as uow:
            depois = uow.session.execute(
                sa.text("SELECT rules::text FROM governance_policies WHERE policy_key = :k"),
                {"k": chave},
            ).scalar_one()
        assert depois == antes
    finally:
        _limpar([a], [d1], [chave])


def test_ii7_empty_scope_is_refused_against_the_real_database():
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        with UnitOfWork() as uow, pytest.raises(IsolationScopeRequiredError) as exc:
            _isolar(uow.session, MemoryContext(), chave, trace_id=trace)
        assert exc.value.code == "PIA-8039"
    finally:
        _limpar([], [], [chave])


# --- Zero escrita, memberships e policies intocadas -------------------


@pytest.mark.parametrize("cenario", ["autorizado", "recusado"])
def test_ii8_no_database_writes_during_isolation(cenario):
    trace = _trace()
    a = _criar_objeto(trace)
    d1, d2 = _criar_dominio(), _criar_dominio()
    _associar(d1, a)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave, dominios=(d1,))
    contexto = (
        MemoryContext(domain_ids=(d1,))
        if cenario == "autorizado"
        else MemoryContext(domain_ids=(d1, d2))
    )
    try:
        escritas: list[str] = []

        def _contar(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "TRUNCATE")):
                escritas.append(statement)

        with UnitOfWork() as uow:
            engine = uow.session.get_bind()
            sa.event.listen(engine, "before_cursor_execute", _contar)
            try:
                _isolar(uow.session, contexto, chave, trace_id=trace)
                assert not uow.session.new
                assert not uow.session.dirty
                assert not uow.session.deleted
                uow.session.flush()
            finally:
                sa.event.remove(engine, "before_cursor_execute", _contar)
        assert escritas == []
    finally:
        _limpar([a], [d1, d2], [chave])


def test_ii9_memberships_are_neither_created_nor_repaired():
    trace = _trace()
    a = _criar_objeto(trace)
    d1 = _criar_dominio()
    _associar(d1, a)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        with UnitOfWork() as uow:
            antes = uow.session.execute(
                sa.text("SELECT count(*) FROM memory_domain_memberships")
            ).scalar_one()
        with UnitOfWork() as uow:
            _isolar(uow.session, MemoryContext(domain_ids=(d1,)), chave, trace_id=trace)
        with UnitOfWork() as uow:
            depois = uow.session.execute(
                sa.text("SELECT count(*) FROM memory_domain_memberships")
            ).scalar_one()
        assert depois == antes
    finally:
        _limpar([a], [d1], [chave])


def test_ii10_no_accessibility_policy_is_touched():
    trace = _trace()
    a = _criar_objeto(trace)
    d1 = _criar_dominio()
    _associar(d1, a)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        with UnitOfWork() as uow:
            antes = uow.session.execute(
                sa.text("SELECT count(*) FROM accessibility_policies")
            ).scalar_one()
            estado = uow.session.execute(
                sa.text("SELECT accessibility FROM cognitive_objects WHERE id = :c"),
                {"c": str(a)},
            ).scalar_one()
        with UnitOfWork() as uow:
            _isolar(uow.session, MemoryContext(domain_ids=(d1,)), chave, trace_id=trace)
        with UnitOfWork() as uow:
            assert (
                uow.session.execute(
                    sa.text("SELECT count(*) FROM accessibility_policies")
                ).scalar_one()
                == antes
            )
            assert (
                uow.session.execute(
                    sa.text("SELECT accessibility FROM cognitive_objects WHERE id = :c"),
                    {"c": str(a)},
                ).scalar_one()
                == estado
            )
    finally:
        _limpar([a], [d1], [chave])


# --- Porta adulterada, com o manager real -----------------------------


class _GovernancaAdulterada:
    """Chama o `GovernanceManager` real e troca uma dimensão do contexto.

    Não fabrica outcome, policy nem operação: a resolução é a real, com
    exatamente um campo contextual substituído. É o cenário que importa
    — uma autorização legítima emitida sob outra pergunta.
    """

    def __init__(self, real: GovernanceManager, *, campo: str, valor: object) -> None:
        self._real = real
        self._campo = campo
        self._valor = valor
        self.chamadas = 0

    def resolve(self, *, descriptor, context, policy_key=None, moment=None):
        self.chamadas += 1
        resolucao = self._real.resolve(
            descriptor=descriptor,
            context=context,
            policy_key=policy_key,
            moment=moment,
        )
        return dataclasses.replace(resolucao, **{self._campo: self._valor})


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("context_domain_ids", (uuid.uuid4(),), "emitida para os domínios"),
        ("context_actor_ref", "outro-ator", "emitida para o ator"),
        ("context_purpose", "outro-proposito", "emitida para o propósito"),
    ],
)
def test_ii11_tampered_resolution_is_refused_before_memberships(campo, valor, trecho, monkeypatch):
    """A E4.8 verifica o vínculo que a E4.3.4 tornou provável."""
    trace = _trace()
    a = _criar_objeto(trace)
    d1 = _criar_dominio()
    _associar(d1, a)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    contexto = MemoryContext(domain_ids=(d1,), actor_ref="ana", purpose="curadoria")
    try:
        lidas = {"n": 0}
        original = MemoryDomainMembershipRepository.list_memberships_of_domain

        def _contar(self, *a_, **kw):  # noqa: ANN001
            lidas["n"] += 1
            return original(self, *a_, **kw)

        monkeypatch.setattr(MemoryDomainMembershipRepository, "list_memberships_of_domain", _contar)

        with UnitOfWork() as uow:
            retrieval = MemoryRetrievalManager(
                SearchEngine(SearchRepository(uow.session)),
                GovernanceManager(GovernancePolicyRepository(uow.session)),
                ContextManager(MemoryDomainRepository(uow.session)),
                MemoryDomainMembershipRepository(uow.session),
            )
            governanca = _GovernancaAdulterada(
                GovernanceManager(GovernancePolicyRepository(uow.session)),
                campo=campo,
                valor=valor,
            )
            manager = MemoryIsolationManager(
                retrieval,
                governanca,
                ContextManager(MemoryDomainRepository(uow.session)),
                MemoryDomainMembershipRepository(uow.session),
            )
            with pytest.raises(IsolationContractViolationError) as exc:
                manager.retrieve_isolated(
                    context=contexto,
                    descriptor=_descritor(),
                    criteria=SearchCriteria(trace_id=trace),
                    policy_key=chave,
                    moment=_MOMENTO,
                )
        monkeypatch.undo()

        assert exc.value.code == "PIA-8040"
        assert any(trecho in m for m in exc.value.reasons)
        assert governanca.chamadas == 1
        assert lidas["n"] == 0, "memberships lidas após divergência de contexto"
    finally:
        _limpar([a], [d1], [chave])


class _RetrievalVazante:
    """Chama a E4.6 real e acrescenta um COID fora do escopo.

    Adultera **depois** da chamada real, para provar a pós-condição sem
    reimplementar a Retrieval no teste.
    """

    def __init__(self, real: MemoryRetrievalManager, *, intruso) -> None:
        self._real = real
        self._intruso = intruso

    def retrieve(self, **kw):
        resultado = self._real.retrieve(**kw)
        return dataclasses.replace(resultado, items=(*resultado.items, self._intruso))


def test_ii12_leak_from_a_faulty_port_is_refused_not_filtered():
    """`LEAK DETECTED != AUTHORIZATION TO SILENTLY FILTER`."""
    from app.memory.schemas.retrieval import RetrievedMemoryItem

    trace = _trace()
    a, b = _criar_objeto(trace), _criar_objeto(trace)
    d1, d2 = _criar_dominio(), _criar_dominio()
    _associar(d1, a)
    _associar(d2, b)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        intruso = RetrievedMemoryItem(
            coid=b,
            clid=None,
            accessibility="active",
            revision_status="current",
            created_at=_MOMENTO,
        )
        with UnitOfWork() as uow:
            real = MemoryRetrievalManager(
                SearchEngine(SearchRepository(uow.session)),
                GovernanceManager(GovernancePolicyRepository(uow.session)),
                ContextManager(MemoryDomainRepository(uow.session)),
                MemoryDomainMembershipRepository(uow.session),
            )
            manager = MemoryIsolationManager(
                _RetrievalVazante(real, intruso=intruso),
                GovernanceManager(GovernancePolicyRepository(uow.session)),
                ContextManager(MemoryDomainRepository(uow.session)),
                MemoryDomainMembershipRepository(uow.session),
            )
            with pytest.raises(IsolationContractViolationError) as exc:
                manager.retrieve_isolated(
                    context=MemoryContext(domain_ids=(d1,)),
                    descriptor=_descritor(),
                    criteria=SearchCriteria(trace_id=trace),
                    policy_key=chave,
                    moment=_MOMENTO,
                )
        assert exc.value.code == "PIA-8040"
        assert any("fora da união de memberships" in m for m in exc.value.reasons)
    finally:
        _limpar([a, b], [d1, d2], [chave])


# --- Paginação, concorrência e guardas de schema ----------------------


def test_ii13_pagination_of_e46_remains_correct():
    trace = _trace()
    coids = [_criar_objeto(trace) for _ in range(5)]
    d1 = _criar_dominio()
    for coid in coids:
        _associar(d1, coid)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        with UnitOfWork() as uow:
            primeira = _isolar(
                uow.session,
                MemoryContext(domain_ids=(d1,)),
                chave,
                trace_id=trace,
                limit=2,
                offset=0,
            )
            segunda = _isolar(
                uow.session,
                MemoryContext(domain_ids=(d1,)),
                chave,
                trace_id=trace,
                limit=2,
                offset=2,
            )
        assert primeira.retrieval is not None
        assert segunda.retrieval is not None
        assert len(primeira.retrieval.coids) == 2
        assert primeira.retrieval.has_more is True
        assert set(primeira.retrieval.coids) & set(segunda.retrieval.coids) == set()
        assert primeira.retrieval.limit == 2
        assert segunda.retrieval.offset == 2
    finally:
        _limpar(coids, [d1], [chave])


def test_ii14_concurrent_operations_with_distinct_domains_do_not_contaminate():
    trace = _trace()
    a, b = _criar_objeto(trace), _criar_objeto(trace)
    d1, d2 = _criar_dominio(), _criar_dominio()
    _associar(d1, a)
    _associar(d2, b)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    resultados: dict[uuid.UUID, set] = {}
    erros: list[BaseException] = []
    barreira = threading.Barrier(2, timeout=30)

    def _executar(dominio: uuid.UUID) -> None:
        try:
            with UnitOfWork() as uow:
                manager = _compor(uow.session)
                barreira.wait()
                r = manager.retrieve_isolated(
                    context=MemoryContext(domain_ids=(dominio,)),
                    descriptor=_descritor(),
                    criteria=SearchCriteria(trace_id=trace),
                    policy_key=chave,
                    moment=_MOMENTO,
                )
                assert r.retrieval is not None
                resultados[dominio] = set(r.retrieval.coids)
        except BaseException as exc:  # noqa: BLE001
            erros.append(exc)

    threads = [threading.Thread(target=_executar, args=(d,)) for d in (d1, d2)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        assert erros == [], f"execução concorrente falhou: {erros}"
        assert resultados[d1] == {a}
        assert resultados[d2] == {b}
    finally:
        _limpar([a, b], [d1, d2], [chave])


def test_ii15_real_collaborators_satisfy_the_ports():
    from app.memory.ports.isolation import (
        ContextValidationPort,
        DomainMembershipPort,
        GovernanceResolutionPort,
        IsolatedRetrievalPort,
    )

    with UnitOfWork() as uow:
        retrieval = MemoryRetrievalManager(
            SearchEngine(SearchRepository(uow.session)),
            GovernanceManager(GovernancePolicyRepository(uow.session)),
            ContextManager(MemoryDomainRepository(uow.session)),
            MemoryDomainMembershipRepository(uow.session),
        )
        assert isinstance(retrieval, IsolatedRetrievalPort)
        assert isinstance(
            GovernanceManager(GovernancePolicyRepository(uow.session)),
            GovernanceResolutionPort,
        )
        assert isinstance(
            ContextManager(MemoryDomainRepository(uow.session)), ContextValidationPort
        )
        assert isinstance(MemoryDomainMembershipRepository(uow.session), DomainMembershipPort)


def test_ii16_no_schema_orm_drift_and_single_head():
    import app.cognitive.models  # noqa: F401
    import app.memory.models  # noqa: F401
    import app.orchestration.models  # noqa: F401
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from app.database.base import Base
    from app.database.engine import engine

    with engine.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    assert [d for d in diferencas if "test_" not in str(d)] == []

    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    # Atualizado pela E4.9.5: a migração `9d4f1a7c2be8` cria
    # `erasure_records`, primeira fatia de runtime da E4.9. O head
    # continua ÚNICO — o que este guarda protege é a ausência de
    # branching, não a imobilidade.
    # Atualizado pela E4.9.6: a migração `c8a3f5017e94` cria
    # `retention_policies`, segunda fatia de runtime da E4.9. O head
    # continua ÚNICO — o que este guarda protege é a ausência de
    # branching, não a imobilidade.
    # E4.9.9.d: head atualizado para `d5b31f7a08c4` (governance_rule_id
    # textual). A guarda continua medindo head ÚNICO.
    # ATUALIZADO PELA E4.11: a cabeça passou a ser `e7c25a91f4b3`
    # (validated_experiences). A guarda continua medindo head ÚNICO —
    # só o alvo do único mudou.
    assert tuple(heads) == ("d7a4c1e93b28",), f"migration head: {heads}"


def test_ii17_no_new_table_was_introduced():
    from sqlalchemy import inspect

    from app.database.engine import engine

    tabelas = set(inspect(engine).get_table_names())
    for proibida in ("memory_isolations", "workspaces", "isolation_scopes"):
        assert proibida not in tabelas

    # ATUALIZADO PELA E7.1 — colisão de NOME, não de conceito.
    #
    # ```text
    # E4_8_WORKSPACE_SCHEDULE != E7_ORCHESTRATION_SCHEDULE
    # ```
    #
    # `schedules` entrou nesta lista como proxy de "a E4.8 materializou
    # um espaço de trabalho persistente". A Chain110 criou uma tabela
    # `schedules` que é outra coisa: o trabalho governado da orquestração
    # multi-IA, autorizado pelo `MAI-001 R1`. Apagar o nome da lista
    # perderia a guarda; mantê-lo cru reprovaria uma tabela autorizada.
    # A guarda passa a medir a IDENTIDADE da tabela: se `schedules`
    # existe, ela tem de ser a da E7 — que se distingue por
    # `control_principal_ref` — e não pode ter coluna de isolamento de
    # memória.
    if "schedules" in tabelas:
        colunas = {c["name"] for c in inspect(engine).get_columns("schedules")}
        assert "control_principal_ref" in colunas, colunas
        assert not (colunas & {"domain_id", "isolation_scope", "memory_domain_id"}), colunas


# ======================================================================
# E4.8.1 — fidelidade da autoridade, contra o banco real
# ======================================================================


class _RetrievalComOutraAutoridade:
    """Chama a E4.6 real e troca **somente** a `governance_resolution`.

    Itens, contexto, paginação e demais campos são preservados: a
    adulteração é de autoridade, não de conteúdo. Uma resolução
    inteiramente fabricada provaria outra coisa.
    """

    def __init__(self, real: MemoryRetrievalManager, **divergencia) -> None:
        self._real = real
        self._divergencia = divergencia
        self.chamadas = 0

    def retrieve(self, **kw):
        self.chamadas += 1
        resultado = self._real.retrieve(**kw)
        return dataclasses.replace(
            resultado,
            governance_resolution=dataclasses.replace(
                resultado.governance_resolution, **self._divergencia
            ),
        )


def _isolar_com_retrieval(session, retrieval_port, contexto, chave, trace_id, **kw):
    manager = MemoryIsolationManager(
        retrieval_port,
        GovernanceManager(GovernancePolicyRepository(session)),
        ContextManager(MemoryDomainRepository(session)),
        MemoryDomainMembershipRepository(session),
    )
    return manager.retrieve_isolated(
        context=contexto,
        descriptor=_descritor(),
        criteria=SearchCriteria(trace_id=trace_id),
        policy_key=chave,
        moment=_MOMENTO,
        **kw,
    )


@pytest.mark.parametrize(
    ("divergencia", "descricao"),
    [
        ({"policy_key": "policy-nao-solicitada"}, "outra policy_key"),
        ({"policy_version": 99}, "mesma key, outra versão"),
        ({"policy_id": uuid.UUID(int=7)}, "mesma key e versão, outro id"),
    ],
)
def test_ii18_retrieval_under_another_authority_is_refused(divergencia, descricao):
    """Defeito B contra o banco real, com a E4.6 verdadeira."""
    trace = _trace()
    a = _criar_objeto(trace)
    d1 = _criar_dominio()
    _associar(d1, a)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        escritas: list[str] = []

        def _contar(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "TRUNCATE")):
                escritas.append(statement)

        with UnitOfWork() as uow:
            engine = uow.session.get_bind()
            sa.event.listen(engine, "before_cursor_execute", _contar)
            try:
                real = MemoryRetrievalManager(
                    SearchEngine(SearchRepository(uow.session)),
                    GovernanceManager(GovernancePolicyRepository(uow.session)),
                    ContextManager(MemoryDomainRepository(uow.session)),
                    MemoryDomainMembershipRepository(uow.session),
                )
                porta = _RetrievalComOutraAutoridade(real, **divergencia)
                with pytest.raises(IsolationContractViolationError) as exc:
                    _isolar_com_retrieval(
                        uow.session,
                        porta,
                        MemoryContext(domain_ids=(d1,)),
                        chave,
                        trace,
                    )
                assert not uow.session.dirty
                uow.session.flush()
            finally:
                sa.event.remove(engine, "before_cursor_execute", _contar)

        assert exc.value.code == "PIA-8040"
        assert porta.chamadas == 1, "a E4.6 real foi chamada antes da adulteração"
        assert escritas == []
    finally:
        _limpar([a], [d1], [chave])


def test_ii19_refusal_returns_nothing_partial():
    """A recusa não devolve página parcial."""
    trace = _trace()
    coids = [_criar_objeto(trace) for _ in range(3)]
    d1 = _criar_dominio()
    for coid in coids:
        _associar(d1, coid)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        with UnitOfWork() as uow:
            real = MemoryRetrievalManager(
                SearchEngine(SearchRepository(uow.session)),
                GovernanceManager(GovernancePolicyRepository(uow.session)),
                ContextManager(MemoryDomainRepository(uow.session)),
                MemoryDomainMembershipRepository(uow.session),
            )
            porta = _RetrievalComOutraAutoridade(real, policy_key="outra")
            with pytest.raises(IsolationContractViolationError):
                _isolar_com_retrieval(
                    uow.session, porta, MemoryContext(domain_ids=(d1,)), chave, trace
                )
        # patrimônio e memberships intactos
        with UnitOfWork() as uow:
            assert (
                uow.session.execute(
                    sa.text(
                        "SELECT count(*) FROM memory_domain_memberships " "WHERE domain_id = :d"
                    ),
                    {"d": str(d1)},
                ).scalar_one()
                == 3
            )
    finally:
        _limpar(coids, [d1], [chave])


def test_ii20_real_policy_produces_one_identity_across_singletons_and_retrieval():
    """A policy publicada real produz a MESMA identidade local em todos
    os singletons e na Retrieval — o caso legítimo que o corretivo
    preserva."""
    trace = _trace()
    a, b = _criar_objeto(trace), _criar_objeto(trace)
    d1, d2 = _criar_dominio(), _criar_dominio()
    _associar(d1, a)
    _associar(d2, b)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        with UnitOfWork() as uow:
            resultado = _isolar(
                uow.session,
                MemoryContext(domain_ids=(d1, d2), actor_ref="ana", purpose="curadoria"),
                chave,
                trace_id=trace,
            )
        assert resultado.authorized is True
        assert resultado.retrieval is not None
        identidades = {
            (
                d.resolution.policy_key,
                d.resolution.policy_version,
                d.resolution.policy_id,
            )
            for d in resultado.decisions
        }
        assert len(identidades) == 1
        vista = resultado.retrieval.governance_resolution
        assert (vista.policy_key, vista.policy_version, vista.policy_id) == next(iter(identidades))
        # e cada decisão cita o ator/propósito do contexto original
        for decisao in resultado.decisions:
            assert decisao.resolution.context_actor_ref == "ana"
            assert decisao.resolution.context_purpose == "curadoria"
    finally:
        _limpar([a, b], [d1, d2], [chave])


def test_ii21_faithful_wrapper_control_still_passes():
    """Controle positivo: o wrapper em modo fiel não invalida nada."""
    trace = _trace()
    a = _criar_objeto(trace)
    d1 = _criar_dominio()
    _associar(d1, a)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        with UnitOfWork() as uow:
            real = MemoryRetrievalManager(
                SearchEngine(SearchRepository(uow.session)),
                GovernanceManager(GovernancePolicyRepository(uow.session)),
                ContextManager(MemoryDomainRepository(uow.session)),
                MemoryDomainMembershipRepository(uow.session),
            )
            porta = _RetrievalComOutraAutoridade(real)  # sem divergência
            resultado = _isolar_com_retrieval(
                uow.session, porta, MemoryContext(domain_ids=(d1,)), chave, trace
            )
        assert resultado.authorized is True
        assert resultado.retrieval is not None
        assert set(resultado.retrieval.coids) == {a}
    finally:
        _limpar([a], [d1], [chave])


class _GovernancaComIdentidadeDivergente:
    """Chama o `GovernanceManager` real e troca o `policy_id` do segundo
    domínio resolvido.

    A resolução continua legítima em tudo o mais — outcome, operação,
    contexto vinculado. O que diverge é a identidade da autoridade
    local, e é isso que o corretivo E4.8.2 recusa mesmo quando alguma
    decisão já recusa por policy.
    """

    def __init__(self, real: GovernanceManager, *, outcome_do_segundo=None) -> None:
        self._real = real
        self._outcome_do_segundo = outcome_do_segundo
        self.chamadas = 0

    def resolve(self, *, descriptor, context, policy_key=None, moment=None):
        self.chamadas += 1
        resolucao = self._real.resolve(
            descriptor=descriptor,
            context=context,
            policy_key=policy_key,
            moment=moment,
        )
        if self.chamadas == 1:
            return resolucao
        return dataclasses.replace(resolucao, policy_id=uuid.UUID(int=4242))


def test_ii22_divergent_identity_on_the_denied_path_raises_pia_8040():
    """Defeito da E4.8.2 contra o banco real: o `ValueError` cru virou
    `PIA-8040`, e nada de patrimônio é lido."""
    trace = _trace()
    a, b = _criar_objeto(trace), _criar_objeto(trace)
    d1, d2 = _criar_dominio(), _criar_dominio()
    _associar(d1, a)
    _associar(d2, b)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave)
    try:
        escritas: list[str] = []

        def _contar(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "TRUNCATE")):
                escritas.append(statement)

        with UnitOfWork() as uow:
            engine = uow.session.get_bind()
            sa.event.listen(engine, "before_cursor_execute", _contar)
            try:
                retrieval = MemoryRetrievalManager(
                    SearchEngine(SearchRepository(uow.session)),
                    GovernanceManager(GovernancePolicyRepository(uow.session)),
                    ContextManager(MemoryDomainRepository(uow.session)),
                    MemoryDomainMembershipRepository(uow.session),
                )
                governanca = _GovernancaComIdentidadeDivergente(
                    GovernanceManager(GovernancePolicyRepository(uow.session))
                )
                manager = MemoryIsolationManager(
                    retrieval,
                    governanca,
                    ContextManager(MemoryDomainRepository(uow.session)),
                    MemoryDomainMembershipRepository(uow.session),
                )
                with pytest.raises(IsolationContractViolationError) as exc:
                    manager.retrieve_isolated(
                        context=MemoryContext(domain_ids=(d1, d2)),
                        descriptor=_descritor(),
                        criteria=SearchCriteria(trace_id=trace),
                        policy_key=chave,
                        moment=_MOMENTO,
                    )
                assert not uow.session.dirty
                uow.session.flush()
            finally:
                sa.event.remove(engine, "before_cursor_execute", _contar)

        assert exc.value.code == "PIA-8040"
        assert any("identidades de policy local diferentes" in m for m in exc.value.reasons)
        assert governanca.chamadas == 2
        assert escritas == []
    finally:
        _limpar([a, b], [d1, d2], [chave])


def test_ii23_real_denied_path_with_one_identity_stays_a_normal_refusal():
    """Controle: policy real que admite só `D1` recusa atomicamente, com
    uma única identidade local — sem `PIA-8040`."""
    trace = _trace()
    a, b = _criar_objeto(trace), _criar_objeto(trace)
    d1, d2 = _criar_dominio(), _criar_dominio()
    _associar(d1, a)
    _associar(d2, b)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar(chave, dominios=(d1,))
    try:
        with UnitOfWork() as uow:
            resultado = _isolar(
                uow.session,
                MemoryContext(domain_ids=(d1, d2)),
                chave,
                trace_id=trace,
            )
        assert resultado.authorized is False
        assert resultado.retrieval is None
        assert resultado.refused_domain_ids == (d2,)
        identidades = {
            (
                d.resolution.policy_key,
                d.resolution.policy_version,
                d.resolution.policy_id,
            )
            for d in resultado.decisions
            if d.resolution.policy_id is not None
        }
        assert len(identidades) == 1
    finally:
        _limpar([a, b], [d1, d2], [chave])
