"""
A porta de leitura governada contra o `MemoryRetrievalManager` real (`E5.a`).

A prova decisiva é a **composição real**: o manager da E4.6, montado com
`SearchEngine`, `GovernanceManager` e `ContextManager` de verdade,
satisfazendo a porta estrutural da E5 apenas por sua forma — sem adapter,
sem duplo e sem adaptação em produção.

Este arquivo importa os dois lados para montar a composição; o que a
fronteira veda é o import de `app.memory`/`app.cognitive` no **código de
produção** da E5, e isso é medido por `tests/static/test_piap_isolation.py`.

```text
E5_CONSUMES_E4_ACCESSIBLE_CONTEXT_READ_ONLY = TRUE
E5_A_NAO_CONSTROI_DESCRITOR_E4
E5_A_NAO_REIMPLEMENTA_A_GOVERNANCA_DA_E4
```

Não substitui PostgreSQL por SQLite: FK real, `timestamptz` e ordenação
canônica só valem no banco de produção.
"""

import pytest
import sqlalchemy as sa

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.search_repository import SearchRepository
from app.cognitive.schemas.search_criteria import SearchCriteria
from app.cognitive.services.search_engine import SearchEngine
from app.database.health import check_database_health
from app.memory.models.governance_enums import CognitiveOperation
from app.memory.repositories.governance_policy_repository import GovernancePolicyRepository
from app.memory.repositories.memory_domain_membership_repository import (
    MemoryDomainMembershipRepository,
)
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository
from app.memory.schemas.memory_context import MemoryContext
from app.memory.schemas.retrieval import MemoryRetrievalResult
from app.memory.services.context_manager import ContextManager
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.platform_safety_boundary import (
    CapabilityDescriptor,
    CapabilityEngagement,
)
from app.memory.services.retrieval_manager import MemoryRetrievalManager
from app.predictive_accessibility.ports.governed_read import (
    GovernedReadPort,
    RetrievalResultView,
)
from app.repositories.unit_of_work import UnitOfWork

pytestmark = pytest.mark.integration


def _postgres_pronto() -> bool:
    if not check_database_health().available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    tabelas = inspect(engine).get_table_names()
    return {
        "cognitive_objects",
        "memory_domains",
        "memory_domain_memberships",
        "governance_policies",
    }.issubset(tabelas)


_TRACE = "e5a-governed-read-probe"
"""Recorte determinístico e inexistente: a busca é legítima e não casa nada."""

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _postgres_pronto(),
        reason="PostgreSQL real indisponível ou migrações não aplicadas.",
    ),
]


def _compor(session) -> MemoryRetrievalManager:
    return MemoryRetrievalManager(
        SearchEngine(SearchRepository(session)),
        GovernanceManager(GovernancePolicyRepository(session)),
        ContextManager(MemoryDomainRepository(session)),
        MemoryDomainMembershipRepository(session),
    )


def _descritor(operation: CognitiveOperation) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        operation=operation,
        capabilities=frozenset(),
        engagement=CapabilityEngagement.ANALYTICAL,
    )


def test_manager_real_satisfaz_a_porta_estruturalmente() -> None:
    """A composição real, sem adapter: a forma basta."""
    with UnitOfWork() as uow:
        manager = _compor(uow.session)
        assert isinstance(manager, GovernedReadPort)
        porta: GovernedReadPort[
            MemoryContext, CapabilityDescriptor, SearchCriteria, MemoryRetrievalResult
        ] = manager
        assert porta is manager


def test_resultado_real_satisfaz_a_vista_read_only() -> None:
    with UnitOfWork() as uow:
        contexto = MemoryContext(purpose="e5a.port.probe")
        resultado = _compor(uow.session).retrieve(
            context=contexto,
            descriptor=_descritor(CognitiveOperation.READ),
            criteria=SearchCriteria(trace_id=_TRACE),
        )
        assert isinstance(resultado, RetrievalResultView)
        assert isinstance(resultado.search_executed, bool)
        assert resultado.has_more is None or isinstance(resultado.has_more, bool)


def test_read_admite_o_caminho_governado() -> None:
    with UnitOfWork() as uow:
        contexto = MemoryContext(purpose="e5a.port.read")
        resultado = _compor(uow.session).retrieve(
            context=contexto,
            descriptor=_descritor(CognitiveOperation.READ),
            criteria=SearchCriteria(trace_id=_TRACE),
        )
        assert isinstance(resultado, MemoryRetrievalResult)


@pytest.mark.parametrize(
    "operation",
    [
        CognitiveOperation.TRANSFORM,
        CognitiveOperation.CONSOLIDATE,
        CognitiveOperation.LEGAL_ERASURE,
    ],
)
def test_operacao_diferente_de_read_e_rejeitada_antes_da_search(
    operation: CognitiveOperation,
) -> None:
    """A governança continua pertencendo à E4 — a E5 não a reimplementa."""
    with UnitOfWork() as uow:
        contexto = MemoryContext(purpose="e5a.port.reject")
        with pytest.raises(ValueError, match="READ"):
            _compor(uow.session).retrieve(
                context=contexto,
                descriptor=_descritor(operation),
                criteria=SearchCriteria(trace_id=_TRACE),
            )


def test_leitura_pela_porta_nao_produz_escrita_no_patrimonio() -> None:
    """Nenhum objeto cognitivo nasce, muda ou desaparece por causa da E5."""
    with UnitOfWork() as uow:
        antes = uow.session.execute(
            sa.select(sa.func.count()).select_from(CognitiveObject.__table__)
        ).scalar_one()

    with UnitOfWork() as uow:
        contexto = MemoryContext(purpose="e5a.port.readonly")
        _compor(uow.session).retrieve(
            context=contexto,
            descriptor=_descritor(CognitiveOperation.READ),
            criteria=SearchCriteria(trace_id=_TRACE),
        )

    with UnitOfWork() as uow:
        depois = uow.session.execute(
            sa.select(sa.func.count()).select_from(CognitiveObject.__table__)
        ).scalar_one()
        assert depois == antes
        assert ObjectRepository(uow.session) is not None
