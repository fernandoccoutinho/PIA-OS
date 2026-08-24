"""
Integração da E4.6 — Memory Retrieval, contra PostgreSQL real.

Cobre os 25 itens do §18. A prova decisiva é a **composição real**: o
`SearchEngine` da E3.8 injetado diretamente na porta estrutural, sem
adapter, satisfazendo-a apenas por sua forma.

Este arquivo importa os dois lados para montar a composição — permitido;
o que a fronteira veda é o import de `app.cognitive` no **código de
produção** de `app/memory`.

Não substitui por SQLite: FK real, `timestamptz`, ordenação canônica e a
contagem de escritas por listener de cursor só valem no banco de
produção.
"""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import AccessibilityState, RevisionStatus
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.search_repository import SearchRepository
from app.cognitive.schemas.search_criteria import SearchCriteria
from app.cognitive.services.search_engine import SearchEngine
from app.database.health import check_database_health
from app.memory.models.governance_enums import (
    CognitiveOperation,
    GovernanceEffect,
    GovernanceOutcome,
)
from app.memory.ports.retrieval import CognitiveObjectView, CognitiveSearchPort
from app.memory.repositories.governance_policy_repository import GovernancePolicyRepository
from app.memory.repositories.memory_domain_membership_repository import (
    MemoryDomainMembershipRepository,
)
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository
from app.memory.schemas.governance import GovernanceResolution, GovernanceRule
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.context_manager import ContextManager
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.platform_safety_boundary import (
    CapabilityDescriptor,
    CapabilityEngagement,
    CriticalCapability,
)
from app.memory.services.retrieval_manager import MemoryRetrievalManager
from app.repositories.unit_of_work import UnitOfWork

_MOMENTO_E434 = datetime(2024, 6, 1, tzinfo=UTC)

_BASE = datetime(2024, 1, 1, tzinfo=UTC)


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


pytestmark = pytest.mark.skipif(
    not _postgres_pronto(),
    reason="PostgreSQL real indisponível ou migrações não aplicadas.",
)


def _compor(session, *, policy_key: str | None = None):
    """Composição real: `SearchEngine` da E3.8 injetado na porta.

    A porta é genérica sobre os critérios, então o `SearchCriteria` da
    E3.8 atravessa a E4.6 opaco, sem ser inspecionado nem recriado.
    """
    porta = SearchEngine(SearchRepository(session))
    governanca = GovernanceManager(GovernancePolicyRepository(session))
    contexto = ContextManager(MemoryDomainRepository(session))
    memberships = MemoryDomainMembershipRepository(session)
    return MemoryRetrievalManager(porta, governanca, contexto, memberships), porta


def _descritor(
    operation: CognitiveOperation = CognitiveOperation.READ,
    *,
    capabilities=(),
    engagement=CapabilityEngagement.ANALYTICAL,
) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        operation=operation,
        capabilities=frozenset(capabilities),
        engagement=engagement,
    )


def _criar_objetos(
    quantidade: int,
    *,
    accessibility: AccessibilityState = AccessibilityState.ACTIVE,
    revision_status: RevisionStatus | None = None,
    clid: uuid.UUID | None = None,
    trace_id: str | None = None,
    soft_delete: bool = False,
) -> list[uuid.UUID]:
    """Cria objetos com `trace_id` comum para recorte determinístico.

    `trace_id` **não** vive no `CognitiveObject`: ele pertence ao
    `ProvenanceRecord` (E3.6), e a Search da E3.8 casa por junção. Cada
    objeto de teste recebe portanto uma proveniência mínima carregando o
    trace — que é o caminho real, não um atalho de teste.
    """
    from app.cognitive.models.enums import ProvenanceActorType, ProvenanceSourceType
    from app.cognitive.models.provenance_record import ProvenanceRecord
    from app.cognitive.repositories.provenance_repository import ProvenanceRepository

    with UnitOfWork() as uow:
        objetos = ObjectRepository(uow.session)
        proveniencias = ProvenanceRepository(uow.session)
        criados = []
        for _ in range(quantidade):
            objeto = objetos.add(CognitiveObject())
            objeto.accessibility = accessibility
            if revision_status is not None:
                objeto.revision_status = revision_status
            if clid is not None:
                objeto.clid = clid
            objetos.update(objeto)
            if trace_id is not None:
                proveniencias.add(
                    ProvenanceRecord(
                        coid=objeto.id,
                        source_type=ProvenanceSourceType.HUMAN,
                        actor_type=ProvenanceActorType.HUMAN,
                        trace_id=trace_id,
                    )
                )
            criados.append(objeto)
        uow.commit()
        ids = [o.id for o in criados]

    if soft_delete:
        with UnitOfWork() as uow:
            objetos = ObjectRepository(uow.session)
            for coid in ids:
                objetos.soft_delete(objetos.get_by_id(coid))
            uow.commit()
    return ids


def _criar_dominio(nome: str, coids: list[uuid.UUID]) -> uuid.UUID:
    with UnitOfWork() as uow:
        dominio = MemoryDomainRepository(uow.session).add_domain(name=nome)
        memberships = MemoryDomainMembershipRepository(uow.session)
        for coid in coids:
            memberships.add_membership(domain_id=dominio.id, coid=coid)
        uow.commit()
        return dominio.id


def _publicar_policy(policy_key: str, *, effect: GovernanceEffect, domain_ids=()) -> None:
    with UnitOfWork() as uow:
        GovernancePolicyRepository(uow.session).add_policy(
            policy_key=policy_key,
            version=1,
            rules=(
                GovernanceRule(
                    rule_id="r1",
                    effect=effect,
                    operations=frozenset({CognitiveOperation.READ}),
                    domain_ids=frozenset(domain_ids),
                ),
            ),
            effective_from=_BASE,
        )
        uow.commit()


def _limpar(coids: list[uuid.UUID], dominios: list[uuid.UUID], policy_keys: list[str]) -> None:
    with UnitOfWork() as uow:
        s = uow.session
        if dominios:
            s.execute(
                sa.text("DELETE FROM memory_domain_memberships WHERE domain_id = ANY(:d ::uuid[])"),
                {"d": [str(d) for d in dominios]},
            )
        if coids:
            s.execute(
                sa.text("DELETE FROM memory_domain_memberships WHERE coid = ANY(:c ::uuid[])"),
                {"c": [str(c) for c in coids]},
            )
            s.execute(
                sa.text("DELETE FROM provenance_records WHERE coid = ANY(:c ::uuid[])"),
                {"c": [str(c) for c in coids]},
            )
            s.execute(
                sa.text("DELETE FROM cognitive_objects WHERE id = ANY(:c ::uuid[])"),
                {"c": [str(c) for c in coids]},
            )
        if dominios:
            s.execute(
                sa.text("DELETE FROM memory_domains WHERE id = ANY(:d ::uuid[])"),
                {"d": [str(d) for d in dominios]},
            )
        if policy_keys:
            s.execute(
                sa.text("DELETE FROM governance_policies WHERE policy_key = ANY(:p ::text[])"),
                {"p": policy_keys},
            )
        uow.commit()


def _trace() -> str:
    return f"e46-{uuid.uuid4().hex[:12]}"


# --- 1/2. Composição real e policy ADMIT ------------------------------


def test_ri1_ri2_real_search_engine_composed_through_the_port():
    trace = _trace()
    coids = _criar_objetos(3, trace_id=trace)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    try:
        with UnitOfWork() as uow:
            manager, porta = _compor(uow.session)
            # Conformidade estrutural verificada, não presumida.
            assert isinstance(porta, SearchEngine)
            assert isinstance(porta, CognitiveSearchPort)

            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                moment=datetime(2024, 6, 1, tzinfo=UTC),
            )
        assert resultado.execution_authorized is True
        assert resultado.search_executed is True
        assert set(resultado.coids) == set(coids)
    finally:
        _limpar(coids, [], [chave])


def test_ri2b_real_cognitive_object_satisfies_the_view_protocol():
    with UnitOfWork() as uow:
        objeto = ObjectRepository(uow.session).add(CognitiveObject())
        assert isinstance(objeto, CognitiveObjectView)


# --- 3/4/5. Recusas ---------------------------------------------------


@pytest.mark.parametrize("cenario", ["deny", "sem_policy", "fronteira"])
def test_ri3_ri4_ri5_denied_paths_never_touch_search_or_memberships(cenario, monkeypatch):
    """Sob recusa, nem Search nem memberships da vista são consultadas."""
    trace = _trace()
    coids = _criar_objetos(3, trace_id=trace)
    dominio = _criar_dominio(f"d-{uuid.uuid4().hex[:8]}", coids)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    if cenario == "deny":
        _publicar_policy(chave, effect=GovernanceEffect.DENY)
        policy_key, descritor = chave, _descritor()
    elif cenario == "sem_policy":
        policy_key, descritor = None, _descritor()
    else:
        policy_key = None
        descritor = _descritor(
            capabilities=(CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT,),
            engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        )
    try:
        buscas = {"n": 0}
        memberships_lidas = {"n": 0}
        original_search = SearchEngine.search
        original_mem = MemoryDomainMembershipRepository.list_memberships_of_domain

        def _contar_busca(self, *a, **kw):  # noqa: ANN001
            buscas["n"] += 1
            return original_search(self, *a, **kw)

        def _contar_mem(self, *a, **kw):  # noqa: ANN001
            memberships_lidas["n"] += 1
            return original_mem(self, *a, **kw)

        monkeypatch.setattr(SearchEngine, "search", _contar_busca)
        monkeypatch.setattr(
            MemoryDomainMembershipRepository, "list_memberships_of_domain", _contar_mem
        )

        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.retrieve(
                context=MemoryContext(domain_ids=(dominio,)),
                descriptor=descritor,
                criteria=SearchCriteria(trace_id=trace),
                policy_key=policy_key,
            )
        monkeypatch.undo()

        assert resultado.execution_authorized is False
        assert resultado.search_executed is False
        assert resultado.items == ()
        assert resultado.has_more is None
        assert buscas["n"] == 0, "Search foi chamada sob recusa"
        assert memberships_lidas["n"] == 0, "memberships foram lidas sob recusa"

        esperado = {
            "deny": GovernanceOutcome.INADMISSIBLE,
            "sem_policy": GovernanceOutcome.NOT_APPLICABLE,
            "fronteira": GovernanceOutcome.PROHIBITED,
        }[cenario]
        assert resultado.governance_resolution.outcome is esperado
    finally:
        _limpar(coids, [dominio], [chave])


# --- 6 a 10. Domínios --------------------------------------------------


def test_ri6_to_ri10_domain_scope_semantics():
    trace = _trace()
    coids = _criar_objetos(4, trace_id=trace)
    d1 = _criar_dominio(f"d1-{uuid.uuid4().hex[:8]}", [coids[0], coids[1]])
    d2 = _criar_dominio(f"d2-{uuid.uuid4().hex[:8]}", [coids[1], coids[2]])
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    criterios = SearchCriteria(trace_id=trace)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)

            # 6 — domínio único
            so_d1 = manager.retrieve(
                context=MemoryContext(domain_ids=(d1,)),
                descriptor=_descritor(),
                criteria=criterios,
                policy_key=chave,
            )
            assert set(so_d1.coids) == {coids[0], coids[1]}

            # 7 e 8 — união, e COID em dois domínios aparece uma vez
            uniao = manager.retrieve(
                context=MemoryContext(domain_ids=(d1, d2)),
                descriptor=_descritor(),
                criteria=criterios,
                policy_key=chave,
            )
            assert set(uniao.coids) == {coids[0], coids[1], coids[2]}
            assert len(uniao.coids) == len(set(uniao.coids)) == 3

            # 9 e 10 — sem domínio, o zero-domain aparece
            sem_dominio = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=criterios,
                policy_key=chave,
            )
            assert set(sem_dominio.coids) == set(coids)
            assert coids[3] in sem_dominio.coids
            assert coids[3] not in uniao.coids
    finally:
        _limpar(coids, [d1, d2], [chave])


# --- 11 a 16. Admissibilidade e preservação ---------------------------


def test_ri11_to_ri16_accessibility_revision_and_soft_delete():
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    clid = uuid.uuid4()

    ativos = _criar_objetos(1, trace_id=trace)
    latentes = _criar_objetos(1, trace_id=trace, accessibility=AccessibilityState.LATENT)
    inacessiveis = _criar_objetos(1, trace_id=trace, accessibility=AccessibilityState.INACCESSIBLE)
    extintos = _criar_objetos(1, trace_id=trace, accessibility=AccessibilityState.CAUSALLY_EXTINCT)
    apagados = _criar_objetos(1, trace_id=trace, soft_delete=True)
    atual = _criar_objetos(1, trace_id=trace, clid=clid, revision_status=RevisionStatus.CURRENT)
    anterior = _criar_objetos(
        1, trace_id=trace, clid=clid, revision_status=RevisionStatus.SUPERSEDED
    )
    todos = [*ativos, *latentes, *inacessiveis, *extintos, *apagados, *atual, *anterior]
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace, include_deleted=True),
                policy_key=chave,
                limit=100,
            )
        visiveis = set(resultado.coids)

        # 11 — ACTIVE e LATENT admitidos
        assert set(ativos) <= visiveis
        assert set(latentes) <= visiveis
        # 12 e 13 — INACCESSIBLE e CAUSALLY_EXTINCT fora da vista
        assert not set(inacessiveis) & visiveis
        assert not set(extintos) & visiveis
        # 15 — soft-deleted fora, mesmo com include_deleted=True
        assert not set(apagados) & visiveis
        # 16 — CURRENT e SUPERSEDED preservados, ambos com o mesmo CLID
        assert set(atual) <= visiveis
        assert set(anterior) <= visiveis
        estados = {item.revision_status for item in resultado.items if item.clid == clid}
        assert estados == {"current", "superseded"}

        # 14 — os excluídos permanecem íntegros no banco
        with UnitOfWork() as uow:
            sobreviventes = uow.session.execute(
                sa.text("SELECT count(*) FROM cognitive_objects WHERE id = ANY(:c ::uuid[])"),
                {"c": [str(c) for c in [*inacessiveis, *extintos, *apagados]]},
            ).scalar_one()
        assert sobreviventes == 3
    finally:
        _limpar(todos, [], [chave])


# --- 17/18/19. Paginação ----------------------------------------------


def test_ri17_ri18_pagination_across_batches_with_filtered_candidates():
    """§18.17 e §18.18, e o caso que uma paginação "filtrar depois do
    limit" erra de forma determinística.

    Admissíveis e inadmissíveis são intercalados, então uma implementação
    que aplicasse `limit` ao conjunto bruto devolveria páginas
    incompletas e `has_more` errado.
    """
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)

    todos: list[uuid.UUID] = []
    admissiveis: list[uuid.UUID] = []
    for _ in range(6):
        visivel = _criar_objetos(1, trace_id=trace)[0]
        oculto = _criar_objetos(1, trace_id=trace, accessibility=AccessibilityState.INACCESSIBLE)[0]
        admissiveis.append(visivel)
        todos.extend([visivel, oculto])
    try:
        coletados: list[uuid.UUID] = []
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            for offset in range(0, 6, 2):
                pagina = manager.retrieve(
                    context=MemoryContext(),
                    descriptor=_descritor(),
                    criteria=SearchCriteria(trace_id=trace),
                    policy_key=chave,
                    limit=2,
                    offset=offset,
                )
                assert len(pagina.items) == 2, "página incompleta — filtro depois do limit"
                assert pagina.has_more is (offset < 4)
                coletados.extend(pagina.coids)

        assert coletados == admissiveis
        assert len(set(coletados)) == 6
    finally:
        _limpar(todos, [], [chave])


def test_ri19_authorized_empty_search_is_legitimate():
    """Busca autorizada sem candidatos permanece distinguível de recusa."""
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=_trace()),
                policy_key=chave,
            )
        assert resultado.search_executed is True
        assert resultado.execution_authorized is True
        assert resultado.items == ()
        assert resultado.has_more is False
    finally:
        _limpar([], [], [chave])


# --- 21/22. Zero escritas ---------------------------------------------


@pytest.mark.parametrize("autorizado", [True, False])
def test_ri21_ri22_zero_writes_and_clean_session(autorizado):
    """`DATABASE_WRITES_DURING_RETRIEVAL = 0`, nos dois caminhos."""
    trace = _trace()
    coids = _criar_objetos(3, trace_id=trace)
    dominio = _criar_dominio(f"d-{uuid.uuid4().hex[:8]}", coids)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT if autorizado else GovernanceEffect.DENY)
    try:
        escritas: list[str] = []

        def _contar(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                escritas.append(statement)

        with UnitOfWork() as uow:
            engine = uow.session.get_bind()
            sa.event.listen(engine, "before_cursor_execute", _contar)
            try:
                manager, _ = _compor(uow.session)
                manager.retrieve(
                    context=MemoryContext(domain_ids=(dominio,)),
                    descriptor=_descritor(),
                    criteria=SearchCriteria(trace_id=trace),
                    policy_key=chave,
                )
                assert not uow.session.new
                assert not uow.session.dirty
                assert not uow.session.deleted
                uow.session.flush()
            finally:
                sa.event.remove(engine, "before_cursor_execute", _contar)

        assert escritas == [], f"escrita durante retrieval: {escritas}"
    finally:
        _limpar(coids, [dominio], [chave])


# --- 23/24/25. Guardas de regressão -----------------------------------


def test_ri23_no_schema_orm_drift():
    """E4.6 não cria tabela, coluna nem enum persistido.

    Recorte de ruído de harness pelo mesmo critério de `IX5` (E3.7),
    `CHI8` (E3.9), E3.4.2 e E4.5.
    """
    import app.cognitive.models  # noqa: F401
    import app.memory.models  # noqa: F401
    import app.orchestration.models  # noqa: F401
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.database.base import Base
    from app.database.engine import engine

    with engine.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    reais = [d for d in diferencas if "test_" not in str(d)]
    assert reais == [], f"schema/ORM drift: {reais}"


def test_ri24_migration_head_is_unchanged_and_single():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    # Atualizado pela E4.7: a migração `7b2e4c9a15df` cria
    # `accessibility_policies`, entidade persistente autorizada pelo
    # §14 do prompt canônico. O head continua ÚNICO — o que este
    # guarda protege é a ausência de branching, não a imobilidade.
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
    assert tuple(heads) == ("b47e9c05d3fa",), f"migration head mudou: {heads}"


def test_ri25_no_new_memory_table_was_introduced():
    """`NEW_PERSISTENT_ENTITY = NO` — a E4.6 não acrescenta model ORM."""
    from app.database.base import Base

    tabelas = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith("app.memory")
    }
    # `accessibility_policies` entra pela E4.7 — nova entidade persistente
    # autorizada pelo §14 do prompt canônico. O guarda continua exigindo
    # o conjunto EXATO: nada além do declarado foi introduzido.
    # Atualizado pela E4.9.5: `erasure_records` entra como primeira
    # fatia de runtime da E4.9, autorizada pelo prompt canônico. O
    # guarda continua exigindo o conjunto EXATO: nada além do
    # declarado foi introduzido.
    # Atualizado pela E4.9.6: `retention_policies` entra como segunda
    # fatia de runtime da E4.9, autorizada pelo prompt canônico. O
    # guarda continua exigindo o conjunto EXATO.
    assert tabelas == {
        "memory_domains",
        "memory_domain_memberships",
        "governance_policies",
        "accessibility_policies",
        "erasure_records",
        "retention_policies",
        # E4.9.9.a — três tabelas de aprovação persistente, autorizadas.
        "approval_records",
        "approval_record_targets",
        "approval_record_governance_items",
        # E4.11 — UMA tabela de registro append-only, autorizada. O
        # conjunto continua EXATO: a guarda mede que nada ALÉM do
        # declarado entrou, e é isso que ela sempre protegeu.
        "validated_experiences",
    }, tabelas


def test_ri25b_deterministic_order_is_stable_across_repeated_runs():
    """Executado várias vezes: ordem estável não pode depender da ordem
    aleatória de UUIDs — a lição da E3.4.2.1."""
    trace = _trace()
    coids = _criar_objetos(5, trace_id=trace)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    try:
        observadas = []
        for _ in range(5):
            with UnitOfWork() as uow:
                manager, _ = _compor(uow.session)
                resultado = manager.retrieve(
                    context=MemoryContext(),
                    descriptor=_descritor(),
                    criteria=SearchCriteria(trace_id=trace),
                    policy_key=chave,
                )
            observadas.append(resultado.coids)
        assert len(set(observadas)) == 1
        assert set(observadas.pop()) == set(coids)
    finally:
        _limpar(coids, [], [chave])


def test_ri25c_criteria_from_e38_travel_opaque_through_e46():
    """O `SearchCriteria` da E3.8 atravessa a E4.6 sem ser recriado."""
    trace = _trace()
    coids = _criar_objetos(2, trace_id=trace, clid=uuid.uuid4())
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    try:
        criterios = SearchCriteria(
            trace_id=trace,
            accessibility=AccessibilityState.ACTIVE,
            created_from=_BASE - timedelta(days=1),
        )
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=criterios,
                policy_key=chave,
            )
        assert set(resultado.coids) == set(coids)
    finally:
        _limpar(coids, [], [chave])


# ======================================================================
# E4.6.1 — fidelidade de autoridade contra o banco real
# ======================================================================


class _PortaAdulterada:
    """Delega ao `SearchEngine` real e adultera um campo do hit.

    A adulteração ocorre **depois** de a Search real executar, então o
    candidato existe de fato — é a forma devolvida que viola o contrato.
    """

    def __init__(self, real, *, campo: str, valor: object) -> None:
        self._real = real
        self._campo = campo
        self._valor = valor
        self.chamadas = 0

    def search(self, criteria, *, limit=None, offset=None):
        self.chamadas += 1
        hits = list(self._real.search(criteria, limit=limit, offset=offset))
        return [_HitAdulterado(hit, self._campo, self._valor) for hit in hits]


class _HitAdulterado:
    """Espelha um hit real trocando um único campo."""

    def __init__(self, real, campo: str, valor: object) -> None:
        self._real = real
        self._campo = campo
        self._valor = valor

    def __getattr__(self, nome: str):
        if nome == self._campo:
            return self._valor
        return getattr(self._real, nome)


def test_ri461_transform_resolution_never_authorizes_a_real_read(monkeypatch):
    """Defeito A contra o banco: Search e memberships intocadas."""
    import dataclasses

    from app.memory.errors.exceptions import RetrievalContractViolationError
    from app.memory.schemas.governance import GovernanceResolution

    trace = _trace()
    coids = _criar_objetos(3, trace_id=trace)
    dominio = _criar_dominio(f"d-{uuid.uuid4().hex[:8]}", coids)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    try:
        buscas = {"n": 0}
        memberships = {"n": 0}
        original_search = SearchEngine.search
        original_mem = MemoryDomainMembershipRepository.list_memberships_of_domain
        original_resolve = GovernanceManager.resolve

        def _contar_busca(self, *a, **kw):  # noqa: ANN001
            buscas["n"] += 1
            return original_search(self, *a, **kw)

        def _contar_mem(self, *a, **kw):  # noqa: ANN001
            memberships["n"] += 1
            return original_mem(self, *a, **kw)

        def _resolver_torto(self, **kw):  # noqa: ANN001
            real: GovernanceResolution = original_resolve(self, **kw)
            return dataclasses.replace(real, operation=CognitiveOperation.TRANSFORM)

        monkeypatch.setattr(SearchEngine, "search", _contar_busca)
        monkeypatch.setattr(
            MemoryDomainMembershipRepository, "list_memberships_of_domain", _contar_mem
        )
        monkeypatch.setattr(GovernanceManager, "resolve", _resolver_torto)

        with pytest.raises(RetrievalContractViolationError) as exc, UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            manager.retrieve(
                context=MemoryContext(domain_ids=(dominio,)),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
            )
        monkeypatch.undo()

        assert exc.value.code == "PIA-8034"
        assert buscas["n"] == 0, "Search foi chamada com resolução de outra operação"
        assert memberships["n"] == 0
    finally:
        _limpar(coids, [dominio], [chave])


def test_ri461_resolved_policy_must_match_the_requested_one(monkeypatch):
    """Defeito B contra o banco."""
    import dataclasses

    from app.memory.errors.exceptions import RetrievalContractViolationError

    trace = _trace()
    coids = _criar_objetos(2, trace_id=trace)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    try:
        buscas = {"n": 0}
        original_search = SearchEngine.search
        original_resolve = GovernanceManager.resolve

        def _contar_busca(self, *a, **kw):  # noqa: ANN001
            buscas["n"] += 1
            return original_search(self, *a, **kw)

        def _resolver_outra(self, **kw):  # noqa: ANN001
            return dataclasses.replace(original_resolve(self, **kw), policy_key="outra-policy")

        monkeypatch.setattr(SearchEngine, "search", _contar_busca)
        monkeypatch.setattr(GovernanceManager, "resolve", _resolver_outra)

        with pytest.raises(RetrievalContractViolationError) as exc, UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
            )
        monkeypatch.undo()
        assert exc.value.code == "PIA-8034"
        assert buscas["n"] == 0
    finally:
        _limpar(coids, [], [chave])


def test_ri461_context_manager_cannot_substitute_the_requested_context(monkeypatch):
    """Defeito C contra o banco: a substituição é detectada antes da
    governança."""
    from app.memory.errors.exceptions import RetrievalContractViolationError

    trace = _trace()
    coids = _criar_objetos(2, trace_id=trace)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    try:
        buscas = {"n": 0}
        resolucoes = {"n": 0}
        original_search = SearchEngine.search
        original_resolve = GovernanceManager.resolve

        def _contar_busca(self, *a, **kw):  # noqa: ANN001
            buscas["n"] += 1
            return original_search(self, *a, **kw)

        def _contar_resolve(self, **kw):  # noqa: ANN001
            resolucoes["n"] += 1
            return original_resolve(self, **kw)

        monkeypatch.setattr(SearchEngine, "search", _contar_busca)
        monkeypatch.setattr(GovernanceManager, "resolve", _contar_resolve)
        monkeypatch.setattr(
            ContextManager,
            "validate",
            lambda self, context: MemoryContext(actor_ref="other", purpose="substituted"),
        )

        with pytest.raises(RetrievalContractViolationError) as exc, UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            manager.retrieve(
                context=MemoryContext(actor_ref="user", purpose="requested"),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
            )
        monkeypatch.undo()
        assert exc.value.code == "PIA-8034"
        assert resolucoes["n"] == 0, "governança foi consultada com contexto substituído"
        assert buscas["n"] == 0
    finally:
        _limpar(coids, [], [chave])


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("accessibility", 123),
        ("accessibility", "quantum"),
        ("deleted_at", "yesterday"),
        ("revision_status", "garbage"),
        ("created_at", "ontem"),
    ],
)
def test_ri461_malformed_real_hit_is_a_violation_not_an_empty_view(campo, valor):
    """Defeito D contra o banco: o candidato existe, a forma é que viola.

    Antes do corretivo isto saía como `search_executed=True, items=()` —
    uma violação de contrato mascarada de busca legítima sem resultados.
    """
    from app.memory.errors.exceptions import RetrievalContractViolationError

    trace = _trace()
    coids = _criar_objetos(2, trace_id=trace)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    try:
        with UnitOfWork() as uow:
            _, porta_real = _compor(uow.session)
            porta = _PortaAdulterada(porta_real, campo=campo, valor=valor)
            manager = MemoryRetrievalManager(
                porta,
                GovernanceManager(GovernancePolicyRepository(uow.session)),
                ContextManager(MemoryDomainRepository(uow.session)),
                MemoryDomainMembershipRepository(uow.session),
            )
            with pytest.raises(RetrievalContractViolationError) as exc:
                manager.retrieve(
                    context=MemoryContext(),
                    descriptor=_descritor(),
                    criteria=SearchCriteria(trace_id=trace),
                    policy_key=chave,
                )
        assert exc.value.code == "PIA-8034"
        assert porta.chamadas == 1, "a Search real precisa ter executado"
    finally:
        _limpar(coids, [], [chave])


def test_ri461_untampered_real_composition_remains_intact():
    """O endurecimento não recusa o caminho legítimo."""
    trace = _trace()
    coids = _criar_objetos(3, trace_id=trace)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
            )
        assert resultado.search_executed is True
        assert set(resultado.coids) == set(coids)
        assert resultado.governance_resolution.policy_key == chave
        assert resultado.governance_resolution.operation is CognitiveOperation.READ
    finally:
        _limpar(coids, [], [chave])


# ======================================================================
# E4.6.2 — Sequence & no-reflection, contra o banco real
# ======================================================================


class _PortaNaoSequencial:
    """Delega ao `SearchEngine` real e reembrulha o retorno.

    A Search real executa e devolve `list`; só o **tipo do invólucro**
    muda. É o defeito F na forma em que ele apareceria de verdade: uma
    implementação de porta que devolve algo ordenado por acaso, ou nada
    ordenado.
    """

    def __init__(self, real, tipo: str) -> None:
        self._real = real
        self._tipo = tipo
        self.chamadas = 0

    def search(self, criteria, *, limit=None, offset=None):
        self.chamadas += 1
        hits = list(self._real.search(criteria, limit=limit, offset=offset))
        if self._tipo == "generator":
            return (h for h in hits)
        if self._tipo == "set":
            return set(hits)
        return {h: 1 for h in hits}


@pytest.mark.parametrize("tipo", ["generator", "set", "dict"])
def test_ri462_non_sequence_return_from_a_real_port_is_a_violation(tipo):
    """Defeito F contra o banco: a Search real executou, o invólucro é
    que viola o contrato.

        SEQUENCE != ARBITRARY ITERABLE
        UNORDERED COLLECTION != DETERMINISTIC SEARCH RESULT
    """
    from app.memory.errors.exceptions import RetrievalContractViolationError

    trace = _trace()
    coids = _criar_objetos(4, trace_id=trace)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    try:
        with UnitOfWork() as uow:
            _, porta_real = _compor(uow.session)
            porta = _PortaNaoSequencial(porta_real, tipo)
            manager = MemoryRetrievalManager(
                porta,
                GovernanceManager(GovernancePolicyRepository(uow.session)),
                ContextManager(MemoryDomainRepository(uow.session)),
                MemoryDomainMembershipRepository(uow.session),
            )
            with pytest.raises(RetrievalContractViolationError) as exc:
                manager.retrieve(
                    context=MemoryContext(),
                    descriptor=_descritor(),
                    criteria=SearchCriteria(trace_id=trace),
                    policy_key=chave,
                )
        assert exc.value.code == "PIA-8034"
        assert porta.chamadas == 1, "a Search real precisa ter executado"
    finally:
        _limpar(coids, [], [chave])


def test_ri462_real_search_returns_a_sequence_and_composition_is_intact():
    """§Stop Condition 1 verificada: o `SearchEngine` real devolve
    `list`, que é `Sequence` — a correção não o exclui."""
    from collections.abc import Sequence

    trace = _trace()
    coids = _criar_objetos(3, trace_id=trace)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    try:
        with UnitOfWork() as uow:
            manager, porta = _compor(uow.session)
            bruto = porta.search(SearchCriteria(trace_id=trace))
            assert isinstance(bruto, Sequence)
            assert not isinstance(bruto, str | bytes)

            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
            )
        assert set(resultado.coids) == set(coids)
    finally:
        _limpar(coids, [], [chave])


def test_ri462_official_order_and_pagination_survive_repeated_runs():
    """§15 — ordem e paginação oficiais preservadas, verificadas várias
    vezes para descartar coincidência de ordenação de UUID."""
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(7, trace_id=trace)
    try:
        observadas: list[tuple[uuid.UUID, ...]] = []
        for _ in range(5):
            paginas: list[uuid.UUID] = []
            with UnitOfWork() as uow:
                manager, _ = _compor(uow.session)
                for offset in range(0, 8, 3):
                    pagina = manager.retrieve(
                        context=MemoryContext(),
                        descriptor=_descritor(),
                        criteria=SearchCriteria(trace_id=trace),
                        policy_key=chave,
                        limit=3,
                        offset=offset,
                    )
                    paginas.extend(pagina.coids)
            observadas.append(tuple(paginas))

        assert len(set(observadas)) == 1, "ordem instável entre execuções"
        completo = observadas[0]
        assert len(completo) == 7
        assert len(set(completo)) == 7
        assert set(completo) == set(coids)
    finally:
        _limpar(coids, [], [chave])


def test_ri462_no_writes_during_a_violating_retrieval():
    """§16 — nem o caminho de violação escreve."""
    from app.memory.errors.exceptions import RetrievalContractViolationError

    trace = _trace()
    coids = _criar_objetos(3, trace_id=trace)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    try:
        escritas: list[str] = []

        def _contar(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                escritas.append(statement)

        with UnitOfWork() as uow:
            engine = uow.session.get_bind()
            sa.event.listen(engine, "before_cursor_execute", _contar)
            try:
                _, porta_real = _compor(uow.session)
                manager = MemoryRetrievalManager(
                    _PortaNaoSequencial(porta_real, "set"),
                    GovernanceManager(GovernancePolicyRepository(uow.session)),
                    ContextManager(MemoryDomainRepository(uow.session)),
                    MemoryDomainMembershipRepository(uow.session),
                )
                with pytest.raises(RetrievalContractViolationError):
                    manager.retrieve(
                        context=MemoryContext(),
                        descriptor=_descritor(),
                        criteria=SearchCriteria(trace_id=trace),
                        policy_key=chave,
                    )
                assert not uow.session.new
                assert not uow.session.dirty
                assert not uow.session.deleted
            finally:
                sa.event.remove(engine, "before_cursor_execute", _contar)

        assert escritas == []
    finally:
        _limpar(coids, [], [chave])


# ======================================================================
# E4.3.4.1 — prova de integração do vínculo de contexto (consumidor E4.6)
# ======================================================================
#
# A E4.3.4 provou o vínculo com dublês unitários e com o
# `GovernanceManager` real em `test_governance_integration.py`, mas
# **não** provou a composição ponta a ponta neste consumidor. Este
# arquivo fecha a evidência que faltava.
#
#     REQUESTED CONTEXT MUST EQUAL RESOLVED CONTEXT
#
# O wrapper abaixo NÃO fabrica resolução: ele chama o manager real e
# adultera exatamente uma dimensão contextual do objeto devolvido, por
# `dataclasses.replace()`. Uma resolução inteiramente inventada provaria
# outra coisa — provaria que o consumidor recusa lixo, não que ele
# detecta uma autorização legítima emitida sob outra pergunta.


class _GovernancaAdulterada:
    """Delega ao `GovernanceManager` real e troca uma dimensão do
    contexto vinculado.

    Registra a resolução original para que o teste possa afirmar que a
    policy real **foi** consultada antes da adulteração.
    """

    def __init__(self, real: GovernanceManager, *, campo: str | None, valor: object) -> None:
        self._real = real
        self._campo = campo
        self._valor = valor
        self.chamadas = 0
        self.original: GovernanceResolution | None = None

    def resolve(self, *, descriptor, context, policy_key=None, moment=None):
        self.chamadas += 1
        resolucao = self._real.resolve(
            descriptor=descriptor,
            context=context,
            policy_key=policy_key,
            moment=moment,
        )
        self.original = resolucao
        if self._campo is None:
            return resolucao
        return dataclasses.replace(resolucao, **{self._campo: self._valor})


def _compor_com_governanca(session, governanca):
    """Composição real da E4.6, trocando apenas o colaborador de
    governança pelo wrapper."""
    return MemoryRetrievalManager(
        SearchEngine(SearchRepository(session)),
        governanca,
        ContextManager(MemoryDomainRepository(session)),
        MemoryDomainMembershipRepository(session),
    )


@pytest.mark.parametrize(
    ("descricao", "campo", "valor", "trecho"),
    [
        ("domínio", "context_domain_ids", (uuid.uuid4(),), "emitida para os domínios"),
        ("ator", "context_actor_ref", "outro-ator", "emitida para o ator"),
        ("propósito", "context_purpose", "outro-proposito", "emitida para o propósito"),
    ],
)
def test_ri434_tampered_context_is_refused_before_search_and_memberships(
    descricao, campo, valor, trecho, monkeypatch
):
    """Defeito B do §6 da E4.3.4, agora provado com a composição real.

    A policy real é consultada; a adulteração acontece **depois**; e
    nenhum patrimônio é lido em seguida.
    """
    from app.memory.errors.exceptions import RetrievalContractViolationError

    trace = _trace()
    coids = _criar_objetos(3, trace_id=trace)
    dominio = _criar_dominio(f"d-{uuid.uuid4().hex[:8]}", coids)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    contexto = MemoryContext(domain_ids=(dominio,), actor_ref="ana", purpose="curadoria")
    try:
        buscas = {"n": 0}
        memberships = {"n": 0}
        original_search = SearchEngine.search
        original_mem = MemoryDomainMembershipRepository.list_memberships_of_domain

        def _contar_busca(self, *a, **kw):  # noqa: ANN001
            buscas["n"] += 1
            return original_search(self, *a, **kw)

        def _contar_mem(self, *a, **kw):  # noqa: ANN001
            memberships["n"] += 1
            return original_mem(self, *a, **kw)

        monkeypatch.setattr(SearchEngine, "search", _contar_busca)
        monkeypatch.setattr(
            MemoryDomainMembershipRepository, "list_memberships_of_domain", _contar_mem
        )

        escritas: list[str] = []

        def _contar_escrita(
            conn, cursor, statement, parameters, context_, executemany
        ):  # noqa: ANN001
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "TRUNCATE")):
                escritas.append(statement)

        with UnitOfWork() as uow:
            engine = uow.session.get_bind()
            sa.event.listen(engine, "before_cursor_execute", _contar_escrita)
            try:
                governanca = _GovernancaAdulterada(
                    GovernanceManager(GovernancePolicyRepository(uow.session)),
                    campo=campo,
                    valor=valor,
                )
                manager = _compor_com_governanca(uow.session, governanca)
                with pytest.raises(RetrievalContractViolationError) as exc:
                    manager.retrieve(
                        context=contexto,
                        descriptor=_descritor(),
                        criteria=SearchCriteria(trace_id=trace),
                        policy_key=chave,
                        moment=_MOMENTO_E434,
                    )
                assert not uow.session.dirty
                uow.session.flush()
            finally:
                sa.event.remove(engine, "before_cursor_execute", _contar_escrita)
        monkeypatch.undo()

        assert exc.value.code == "PIA-8034"
        assert any(trecho in m for m in exc.value.reasons)

        # a policy REAL foi consultada antes da adulteração
        assert governanca.chamadas == 1
        assert governanca.original is not None
        assert governanca.original.outcome is GovernanceOutcome.ADMISSIBLE
        assert governanca.original.policy_key == chave

        # e nenhum patrimônio foi lido depois dela
        assert buscas["n"] == 0, "Search executada após divergência de contexto"
        assert memberships["n"] == 0, "memberships lidas após divergência de contexto"
        assert escritas == []
    finally:
        _limpar(coids, [dominio], [chave])


def test_ri434_faithful_wrapper_preserves_normal_behaviour():
    """Controle positivo: o wrapper em modo fiel não invalida a
    composição."""
    trace = _trace()
    coids = _criar_objetos(3, trace_id=trace)
    dominio = _criar_dominio(f"d-{uuid.uuid4().hex[:8]}", coids)
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    contexto = MemoryContext(domain_ids=(dominio,), actor_ref="ana", purpose="curadoria")
    try:
        with UnitOfWork() as uow:
            governanca = _GovernancaAdulterada(
                GovernanceManager(GovernancePolicyRepository(uow.session)),
                campo=None,
                valor=None,
            )
            resultado = _compor_com_governanca(uow.session, governanca).retrieve(
                context=contexto,
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                moment=_MOMENTO_E434,
            )
        assert governanca.chamadas == 1
        assert resultado.search_executed is True
        assert set(resultado.coids) == set(coids)
        # o contexto resolvido é exatamente o solicitado
        resolucao = resultado.governance_resolution
        assert resolucao.context_domain_ids == contexto.domain_ids
        assert resolucao.context_actor_ref == contexto.actor_ref
        assert resolucao.context_purpose == contexto.purpose
    finally:
        _limpar(coids, [dominio], [chave])


# ======================================================================
# E4.6.3 — Retrieval Composition Point, contra PostgreSQL real
#
# O que só o banco demonstra: que o gate compõe com a Search REAL da
# E3.8 (lotes, ordem canônica, junção de proveniência), que o backfill
# atravessa lotes de verdade, e que rejeitar não escreve nada.
# ======================================================================


def _erro_de_contrato():
    from app.memory.errors.exceptions import RetrievalContractViolationError

    return RetrievalContractViolationError


def _ordem_canonica(chave: str, trace: str) -> list[uuid.UUID]:
    """Ordem REAL devolvida pela E4.6 sem gate.

    Os objetos de teste nascem na MESMA transação, então `created_at` é
    idêntico (o `now()` do PostgreSQL é o instante de início da
    transação) e o desempate canônico cai em `id ASC` — UUID aleatório.
    Assumir a ordem de criação faria o teste passar por sorte; a ordem é
    derivada do próprio caminho canônico.
    """
    with UnitOfWork() as uow:
        manager, _ = _compor(uow.session)
        return list(
            manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=100,
            ).coids
        )


class GateEspiaoReal:
    """Gate real, injetado na composição verdadeira. Registra o que viu."""

    def __init__(self, decisao=None, *, erro: Exception | None = None, retorno=None) -> None:
        self._decisao = decisao
        self._erro = erro
        self._retorno = retorno
        self.vistos: list[uuid.UUID] = []

    def allows(self, candidate):
        self.vistos.append(candidate.id)
        if self._erro is not None:
            raise self._erro
        if self._retorno is not None:
            return self._retorno
        return True if self._decisao is None else self._decisao(candidate)


def test_ri463_gate_composes_with_the_real_search_engine():
    """O gate recebe o `CognitiveObject` REAL da E3, satisfazendo
    `CognitiveObjectView` apenas por sua forma."""
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(4, trace_id=trace)
    try:
        ordem = _ordem_canonica(chave, trace)
        vistos_tipados: list[bool] = []

        def _decidir(candidato):
            vistos_tipados.append(isinstance(candidato, CognitiveObjectView))
            return candidato.id != ordem[1]

        gate = GateEspiaoReal(_decidir)
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=10,
                candidate_gate=gate,
            )

        assert all(vistos_tipados)
        assert gate.vistos == ordem
        assert list(resultado.coids) == [c for c in ordem if c != ordem[1]]
    finally:
        _limpar(coids, [], [chave])


def test_ri463_backfill_crosses_real_search_batches():
    """Rejeitar candidatos força a coleta a puxar lotes seguintes da
    Search real até completar a página — e a página sai completa."""
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(8, trace_id=trace)
    try:
        ordem = _ordem_canonica(chave, trace)
        # rejeita os 5 primeiros: a página de 3 só fecha com os 3 últimos
        rejeitados = set(ordem[:5])
        gate = GateEspiaoReal(lambda c: c.id not in rejeitados)
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=3,
                candidate_gate=gate,
            )
        assert list(resultado.coids) == ordem[5:]
        assert len(resultado.items) == 3
        assert resultado.has_more is False
        assert gate.vistos == ordem
    finally:
        _limpar(coids, [], [chave])


def test_ri463_offset_and_has_more_count_only_approved_candidates():
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(6, trace_id=trace)
    try:
        ordem = _ordem_canonica(chave, trace)
        rejeitados = {ordem[0], ordem[1]}
        aprovados = [c for c in ordem if c not in rejeitados]
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            pagina = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=2,
                offset=1,
                candidate_gate=GateEspiaoReal(lambda c: c.id not in rejeitados),
            )
        # offset=1 corta o primeiro APROVADO, não o primeiro bruto
        assert list(pagina.coids) == aprovados[1:3]
        assert pagina.has_more is True
    finally:
        _limpar(coids, [], [chave])


def test_ri463_gate_never_sees_candidates_denied_by_governance():
    """Sob recusa nada é tocado: nem Search, nem memberships, nem gate."""
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.DENY)
    coids = _criar_objetos(3, trace_id=trace)
    try:
        gate = GateEspiaoReal()
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                candidate_gate=gate,
            )
        assert resultado.execution_authorized is False
        assert resultado.search_executed is False
        assert gate.vistos == []
    finally:
        _limpar(coids, [], [chave])


def test_ri463_gate_never_sees_candidates_outside_the_base_scope():
    """Soft-deleted e inacessível são descartados pela admissibilidade
    base e nunca chegam ao gate."""
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    visiveis = _criar_objetos(2, trace_id=trace)
    ocultos = _criar_objetos(1, trace_id=trace, accessibility=AccessibilityState.INACCESSIBLE)
    apagados = _criar_objetos(1, trace_id=trace, soft_delete=True)
    try:
        gate = GateEspiaoReal()
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=10,
                candidate_gate=gate,
            )
        assert set(gate.vistos) == set(visiveis)
        assert not set(gate.vistos) & set(ocultos + apagados)
    finally:
        _limpar(visiveis + ocultos + apagados, [], [chave])


@pytest.mark.parametrize("retorno", [0, 1, "sim", []], ids=["zero", "um", "str", "lista"])
def test_ri463_non_bool_gate_result_fails_typed_against_the_database(retorno):
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(2, trace_id=trace)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            with pytest.raises(_erro_de_contrato()):
                manager.retrieve(
                    context=MemoryContext(),
                    descriptor=_descritor(),
                    criteria=SearchCriteria(trace_id=trace),
                    policy_key=chave,
                    candidate_gate=GateEspiaoReal(retorno=retorno),
                )
    finally:
        _limpar(coids, [], [chave])


def test_ri463_gate_exception_fails_typed_and_preserves_cause():
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(2, trace_id=trace)
    original = RuntimeError("colaborador quebrou")
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            with pytest.raises(_erro_de_contrato()) as exc:
                manager.retrieve(
                    context=MemoryContext(),
                    descriptor=_descritor(),
                    criteria=SearchCriteria(trace_id=trace),
                    policy_key=chave,
                    candidate_gate=GateEspiaoReal(erro=original),
                )
        assert exc.value.__cause__ is original
    finally:
        _limpar(coids, [], [chave])


def test_ri463_rejection_writes_nothing_and_is_transitory():
    """`False` não marca, não apaga, não transiciona.

    NOT RETURNED IN THIS RESPONSE != FORGOTTEN
    """
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(3, trace_id=trace)
    escritas: list[str] = []

    def _espiao(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip()[:6].upper() in {"INSERT", "UPDATE", "DELETE"}:
            escritas.append(statement)

    try:
        from sqlalchemy import event

        from app.database.engine import engine

        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            event.listen(engine, "before_cursor_execute", _espiao)
            try:
                vazio = manager.retrieve(
                    context=MemoryContext(),
                    descriptor=_descritor(),
                    criteria=SearchCriteria(trace_id=trace),
                    policy_key=chave,
                    limit=10,
                    candidate_gate=GateEspiaoReal(lambda c: False),
                )
            finally:
                event.remove(engine, "before_cursor_execute", _espiao)

        assert vazio.items == ()
        assert vazio.has_more is False
        assert escritas == []

        # e o patrimônio continua lá, íntegro, na chamada seguinte
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            depois = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=10,
            )
        assert list(depois.coids) == _ordem_canonica(chave, trace)

        with UnitOfWork() as uow:
            estados = uow.session.execute(
                sa.text(
                    "SELECT accessibility, deleted_at FROM cognitive_objects "
                    "WHERE id = ANY(:c ::uuid[])"
                ),
                {"c": [str(c) for c in coids]},
            ).all()
        assert all(estado == "active" and apagado is None for estado, apagado in estados)
    finally:
        _limpar(coids, [], [chave])


def test_ri463_none_gate_reproduces_the_baseline_result():
    """Chamadas sem gate continuam válidas e idênticas à cadeia 67."""
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(5, trace_id=trace)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            sem = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=3,
            )
            com_none = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=3,
                candidate_gate=None,
            )
        assert list(sem.coids) == list(com_none.coids)
        assert sem.has_more == com_none.has_more is True
    finally:
        _limpar(coids, [], [chave])


def test_ri463_successive_calls_with_different_gates_are_independent():
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(4, trace_id=trace)
    try:
        ordem = _ordem_canonica(chave, trace)
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            r1 = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=10,
                candidate_gate=GateEspiaoReal(lambda c: c.id != ordem[0]),
            )
            r2 = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=10,
                candidate_gate=GateEspiaoReal(lambda c: c.id != ordem[3]),
            )
        assert list(r1.coids) == ordem[1:]
        assert list(r2.coids) == ordem[:3]
    finally:
        _limpar(coids, [], [chave])


def test_ri463_isolation_e48_is_unaffected_and_does_not_expose_a_gate():
    """A E4.8 não foi alterada: o caminho isolado segue chamando a E4.6
    sem gate, e sua assinatura não o admite.

        E4.6.3 OFFERS COMPOSITION
        E4.6.3 DOES NOT MAKE ANY CALLER RETENTION-AWARE
    """
    import inspect

    from app.memory.services.memory_isolation_manager import MemoryIsolationManager

    assinatura = inspect.signature(MemoryIsolationManager.retrieve_isolated)
    assert "candidate_gate" not in assinatura.parameters


# ======================================================================
# E4.6.3.1 — isolamento contra entidade ORM REAL
#
# O que só o banco demonstra: que um gate hostil não suja a `Session`.
# Um `CognitiveObject` ligado à sessão, mutado pelo colaborador, entraria
# em `session.dirty` e alcançaria um flush posterior — contradizendo
# `DATABASE_WRITES = 0` e a natureza transitória do gate.
# ======================================================================


class GateHostilReal:
    """Reproduz a prova adversarial da auditoria contra o ORM real."""

    def __init__(self, *, tudo: bool = False) -> None:
        self.fabricado = uuid.uuid4()
        self.tudo = tudo
        self.recebidos: list[object] = []

    def allows(self, candidate) -> bool:
        self.recebidos.append(candidate)
        object.__setattr__(candidate, "id", self.fabricado)
        object.__setattr__(candidate, "accessibility", "latent")
        if self.tudo:
            object.__setattr__(candidate, "clid", uuid.uuid4())
            object.__setattr__(candidate, "revision_status", "superseded")
            object.__setattr__(candidate, "deleted_at", datetime(2030, 1, 1, tzinfo=UTC))
        return True


def test_ri4631_gate_receives_a_snapshot_not_the_orm_entity():
    """GATE RECEIVES SNAPSHOT, NOT SEARCH HIT"""
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(2, trace_id=trace)
    try:
        recebidos: list[object] = []

        class Captura:
            def allows(self, candidate) -> bool:
                recebidos.append(candidate)
                return True

        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=10,
                candidate_gate=Captura(),
            )
            entidades = (
                uow.session.query(CognitiveObject).filter(CognitiveObject.id.in_(coids)).all()
            )
            por_coid = {e.id: e for e in entidades}
            for visto in recebidos:
                assert visto is not por_coid[visto.id]
                assert not isinstance(visto, CognitiveObject)
    finally:
        _limpar(coids, [], [chave])


def test_ri4631_hostile_gate_does_not_dirty_the_session():
    """O ponto central: `session.dirty` vazio depois da avaliação."""
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(3, trace_id=trace)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=10,
                candidate_gate=GateHostilReal(tudo=True),
            )
            sujas = list(uow.session.dirty)
            novas = list(uow.session.new)
            removidas = list(uow.session.deleted)

        assert sujas == []
        assert novas == []
        assert removidas == []
        assert set(resultado.coids) == set(coids)
    finally:
        _limpar(coids, [], [chave])


def test_ri4631_hostile_gate_produces_no_write_and_no_flush():
    """Nenhum INSERT/UPDATE/DELETE decorre do gate."""
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(3, trace_id=trace)
    escritas: list[str] = []

    def _espiao(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip()[:6].upper() in {"INSERT", "UPDATE", "DELETE"}:
            escritas.append(statement)

    try:
        from sqlalchemy import event

        from app.database.engine import engine

        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            event.listen(engine, "before_cursor_execute", _espiao)
            try:
                manager.retrieve(
                    context=MemoryContext(),
                    descriptor=_descritor(),
                    criteria=SearchCriteria(trace_id=trace),
                    policy_key=chave,
                    limit=10,
                    candidate_gate=GateHostilReal(tudo=True),
                )
                uow.session.flush()
            finally:
                event.remove(engine, "before_cursor_execute", _espiao)

        assert escritas == []
    finally:
        _limpar(coids, [], [chave])


def test_ri4631_persisted_state_is_untouched_after_a_hostile_gate():
    """O banco não mudou: COIDs, acessibilidade e `deleted_at` intactos."""
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(3, trace_id=trace)
    try:
        gate = GateHostilReal(tudo=True)
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=10,
                candidate_gate=gate,
            )

        with UnitOfWork() as uow:
            linhas = uow.session.execute(
                sa.text(
                    "SELECT id, accessibility, revision_status, clid, deleted_at "
                    "FROM cognitive_objects WHERE id = ANY(:c ::uuid[])"
                ),
                {"c": [str(c) for c in coids]},
            ).all()
            fabricado = uow.session.execute(
                sa.text("SELECT COUNT(*) FROM cognitive_objects WHERE id = :i"),
                {"i": str(gate.fabricado)},
            ).scalar_one()

        assert len(linhas) == 3
        for _id, acessibilidade, revisao, clid, apagado in linhas:
            assert acessibilidade == "active"
            assert revisao is None
            assert clid is None
            assert apagado is None
        assert fabricado == 0
        assert gate.fabricado not in set(resultado.coids)
        assert set(resultado.coids) == set(coids)
    finally:
        _limpar(coids, [], [chave])


def test_ri4631_result_with_hostile_gate_is_a_subsequence_of_the_base_view():
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    coids = _criar_objetos(5, trace_id=trace)
    try:
        ordem = _ordem_canonica(chave, trace)
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=10,
                candidate_gate=GateHostilReal(),
            )
        assert list(resultado.coids) == ordem
    finally:
        _limpar(coids, [], [chave])


def test_ri4631_snapshot_carries_the_real_values_of_the_orm_entity():
    """O gate decide com os valores ORIGINAIS lidos da entidade real."""
    trace = _trace()
    chave = f"pol-{uuid.uuid4().hex[:8]}"
    _publicar_policy(chave, effect=GovernanceEffect.ADMIT)
    ativos = _criar_objetos(2, trace_id=trace)
    latentes = _criar_objetos(1, trace_id=trace, accessibility=AccessibilityState.LATENT)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.retrieve(
                context=MemoryContext(),
                descriptor=_descritor(),
                criteria=SearchCriteria(trace_id=trace),
                policy_key=chave,
                limit=10,
                candidate_gate=GateEspiaoReal(lambda c: c.accessibility == "active"),
            )
        assert set(resultado.coids) == set(ativos)
        assert not set(resultado.coids) & set(latentes)
    finally:
        _limpar(ativos + latentes, [], [chave])
