"""
E4.1 — testes de integração contra PostgreSQL real.

Cobrem DB1–DB4 (garantias estruturais do banco), CC1 (concorrência) e
COUT1–COUT4 (gates fortes) do §38 do prompt canônico.

O gate central é `COUT1`: um censo completo do patrimônio cognitivo
antes e depois de classificar objetos em domínios, exigindo

    ORGANIZATION CHANGED
    PATRIMONY DID NOT

Este arquivo importa `app.cognitive` livremente — testes vivem fora de
`app/`, e a proibição de import vale para o código de produção
(verificada em `MD6`), onde ela mantém a fronteira estrutural.
"""

import threading
import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import (
    AccessibilityState,
    CausalEventType,
    LineageRelation,
    ProvenanceActorType,
    ProvenanceSourceType,
)
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.integrity_repository import IntegrityRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.repositories.search_repository import SearchRepository
from app.cognitive.schemas.integrity import IntegrityStatus
from app.cognitive.schemas.search_criteria import SearchCriteria
from app.cognitive.schemas.synchronization import SECTION_BY_TABLE
from app.cognitive.services.accessibility_manager import AccessibilityManager
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.integrity_manager import IntegrityManager
from app.cognitive.services.provenance_manager import ProvenanceManager
from app.cognitive.services.search_engine import SearchEngine
from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.memory.errors.exceptions import MemoryDomainMembershipDuplicateError
from app.memory.repositories.memory_domain_membership_repository import (
    MemoryDomainMembershipRepository,
)
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository
from app.memory.services.memory_domain_manager import MemoryDomainManager
from app.repositories.unit_of_work import UnitOfWork

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
    reason="PostgreSQL real indisponível — E4.1 não valida garantias de banco sobre SQLite.",
)


@pytest.fixture(autouse=True)
def _clean():
    migrations.upgrade("head")
    _truncate()
    yield
    _truncate()


def _truncate() -> None:
    with engine.begin() as conn:
        conn.execute(sa.text(f"TRUNCATE {', '.join(_MEMORY_TABLES + _COGNITIVE_TABLES)} CASCADE"))


def _manager(session) -> MemoryDomainManager:
    return MemoryDomainManager(
        MemoryDomainRepository(session), MemoryDomainMembershipRepository(session)
    )


def _cognitive_census() -> dict[str, list[tuple[Any, ...]]]:
    """Censo canônico do patrimônio cognitivo — todas as sete tabelas
    da E3, linha a linha, coluna a coluna, em ordem determinística.

    Comparação por conteúdo, não por contagem: contar provaria apenas
    que nada sumiu; o contrato de E4.1 é que nada **mude**.
    """
    snapshot: dict[str, list[tuple[Any, ...]]] = {}
    with engine.connect() as conn:
        for table in SECTION_BY_TABLE:
            columns = sorted(sa.inspect(engine).get_columns(table), key=lambda c: c["name"])
            names = ", ".join(f'"{c["name"]}"' for c in columns)
            rows = conn.execute(sa.text(f"SELECT {names} FROM {table} ORDER BY id")).fetchall()
            snapshot[table] = [tuple(row) for row in rows]
    return snapshot


def _seed_patrimony() -> dict[str, uuid.UUID]:
    """Patrimônio pequeno mas completo: linhagem, proveniência,
    história causal e os quatro estados de acessibilidade."""
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
            trace_id="e41",
        )
        uow.session.flush()
        lineage.add_edge(parent_coid=o1.id, child_coid=o2.id, relation_type=LineageRelation.BRANCH)
        raiz = causal.record(subject_coid=o1.id, event_type=CausalEventType.CREATED, actor_ref=p.id)
        causal.record(subject_coid=o2.id, event_type=CausalEventType.TRANSFORMED, predecessor=raiz)
        accessibility.transition(o2, AccessibilityState.LATENT)
        accessibility.transition(
            o3, AccessibilityState.CAUSALLY_EXTINCT, reason="extinta para o cenário Broken Glass"
        )
        uow.commit()
        return {"o1": o1.id, "o2": o2.id, "o3": o3.id, "clid": clid}


# ======================================================================
# DB — garantias estruturais do banco
# ======================================================================


def test_db1_duplicate_membership_is_blocked_at_db_level():
    """DB1 — a unicidade `(domain_id, coid)` é do banco, não só do
    código: provada por INSERT direto, que ignora o repositório."""
    with UnitOfWork() as uow:
        obj = ObjectRepository(uow.session).add(CognitiveObject())
        domain = MemoryDomainRepository(uow.session).add_domain(name="d1")
        uow.commit()
        coid, domain_id = obj.id, domain.id

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO memory_domain_memberships "
                "(id, domain_id, coid, created_at, updated_at) "
                "VALUES (:i, :d, :c, now(), now())"
            ),
            {"i": uuid.uuid4(), "d": domain_id, "c": coid},
        )

    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO memory_domain_memberships "
                "(id, domain_id, coid, created_at, updated_at) "
                "VALUES (:i, :d, :c, now(), now())"
            ),
            {"i": uuid.uuid4(), "d": domain_id, "c": coid},
        )


def test_db2_foreign_key_to_cognitive_objects_is_real():
    """DB2 — a FK para `cognitive_objects` é imposta pelo banco.

    A referência é declarada por nome de tabela (sem import de
    `app.cognitive`), e ainda assim a integridade é real — que é
    exatamente o ponto do desenho.
    """
    with UnitOfWork() as uow:
        domain = MemoryDomainRepository(uow.session).add_domain(name="d1")
        uow.commit()
        domain_id = domain.id

    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO memory_domain_memberships "
                "(id, domain_id, coid, created_at, updated_at) "
                "VALUES (:i, :d, :c, now(), now())"
            ),
            {"i": uuid.uuid4(), "d": domain_id, "c": uuid.uuid4()},
        )


def test_db3_no_destructive_cascade_to_cognitive_patrimony():
    """DB3 — `DOMAIN DELETE MUST NOT CASCADE TO COGNITIVE PATRIMONY`.

    Nenhuma FK deste módulo declara `ON DELETE CASCADE`. O teste lê o
    schema real em vez de confiar no modelo: é o banco que executaria
    o cascade.
    """
    inspector = sa.inspect(engine)
    fks = inspector.get_foreign_keys("memory_domain_memberships")
    assert fks, "as duas FKs devem existir"
    for fk in fks:
        regra = (fk.get("options") or {}).get("ondelete")
        assert regra in (None, "NO ACTION", "RESTRICT"), (
            f"FK {fk['constrained_columns']} → {fk['referred_table']} "
            f"tem ondelete={regra!r}; cascade a partir de estado organizacional "
            "poderia apagar patrimônio"
        )

    # E o inverso: apagar um domínio com membership é recusado pelo
    # banco, em vez de arrastar a associação (e, por extensão, sugerir
    # que arrastar patrimônio seria aceitável).
    with UnitOfWork() as uow:
        obj = ObjectRepository(uow.session).add(CognitiveObject())
        domain = MemoryDomainRepository(uow.session).add_domain(name="d1")
        uow.session.flush()
        MemoryDomainMembershipRepository(uow.session).add_membership(
            domain_id=domain.id, coid=obj.id
        )
        uow.commit()
        domain_id, coid = domain.id, obj.id

    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM memory_domains WHERE id = :d"), {"d": domain_id})

    with engine.connect() as conn:
        ainda = conn.execute(
            sa.text("SELECT COUNT(*) FROM cognitive_objects WHERE id = :c"), {"c": coid}
        ).scalar_one()
    assert ainda == 1


def test_db4_downgrade_is_blocked_when_organization_exists():
    """DB4 — `CONDITIONALLY_REVERSIBLE` com guarda desde a migração
    inicial.

    Vazio: `head → anterior → head` funciona. Com organização
    registrada: bloqueado antes de qualquer alteração estrutural, e
    nada é perdido.
    """
    anterior = "c9a3f61b74d2"

    # (a) vazio — o ciclo completo é permitido.
    migrations.downgrade(anterior)
    inspector = sa.inspect(engine)
    assert "memory_domains" not in inspector.get_table_names()
    migrations.upgrade("head")
    assert "memory_domains" in sa.inspect(engine).get_table_names()

    # (b) com organização — bloqueado.
    with UnitOfWork() as uow:
        obj = ObjectRepository(uow.session).add(CognitiveObject())
        domain = MemoryDomainRepository(uow.session).add_domain(name="d1")
        uow.session.flush()
        MemoryDomainMembershipRepository(uow.session).add_membership(
            domain_id=domain.id, coid=obj.id
        )
        uow.commit()

    with pytest.raises(Exception) as exc:
        migrations.downgrade(anterior)
    assert "MEMORY_DOMAIN_DOWNGRADE_SEMANTICALLY_BLOCKED" in str(exc.value)

    # Nada foi alterado: as tabelas e as linhas continuam lá.
    with engine.connect() as conn:
        assert (
            conn.execute(sa.text("SELECT COUNT(*) FROM memory_domain_memberships")).scalar_one()
            == 1
        )
    assert "memory_domains" in sa.inspect(engine).get_table_names()


# ======================================================================
# CC — concorrência
# ======================================================================


def test_cc1_concurrent_identical_membership_yields_exactly_one():
    """CC1 — duas sessões classificando o mesmo COID no mesmo domínio
    ao mesmo tempo produzem **exatamente uma** membership.

    A unicidade estrutural do banco basta — nenhum lock global foi
    adicionado (mesma disciplina de E3.4.1: a constraint é a autoridade
    final, e inventar lock onde a constraint resolve seria custo sem
    invariante novo).
    """
    with UnitOfWork() as uow:
        obj = ObjectRepository(uow.session).add(CognitiveObject())
        domain = MemoryDomainRepository(uow.session).add_domain(name="d1")
        uow.commit()
        coid, domain_id = obj.id, domain.id

    barreira = threading.Barrier(2)
    resultados: list[str] = []
    trava = threading.Lock()

    def _tentar() -> None:
        barreira.wait(timeout=10)
        try:
            with UnitOfWork() as uow:
                MemoryDomainMembershipRepository(uow.session).add_membership(
                    domain_id=domain_id, coid=coid
                )
                uow.commit()
            desfecho = "ok"
        except MemoryDomainMembershipDuplicateError:
            desfecho = "duplicate"
        except Exception as exc:  # pragma: no cover - diagnóstico
            desfecho = f"outro:{type(exc).__name__}"
        with trava:
            resultados.append(desfecho)

    threads = [threading.Thread(target=_tentar) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    with engine.connect() as conn:
        total = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM memory_domain_memberships "
                "WHERE domain_id = :d AND coid = :c"
            ),
            {"d": domain_id, "c": coid},
        ).scalar_one()

    assert total == 1, f"exatamente uma membership esperada; resultados={resultados}"
    assert resultados.count("ok") == 1
    assert all(r in ("ok", "duplicate") for r in resultados), resultados


# ======================================================================
# COUT — gates fortes
# ======================================================================


def test_cout1_organization_changes_without_patrimony_mutation():
    """COUT1 — **o gate central da E4.1**.

        ORGANIZATION CHANGED
        PATRIMONY DID NOT

    Censo completo das sete tabelas cognitivas antes e depois de criar
    domínios e classificar objetos. Exigência: idêntico byte a byte,
    enquanto a organização muda de vazia para povoada.
    """
    refs = _seed_patrimony()
    censo_antes = _cognitive_census()

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        d1 = manager.create_domain(name="D1")
        d2 = manager.create_domain(name="D2")
        uow.session.flush()
        manager.add_object(domain_id=d1.id, coid=refs["o1"])
        manager.add_object(domain_id=d2.id, coid=refs["o1"])
        manager.add_object(domain_id=d1.id, coid=refs["o2"])
        manager.add_object(domain_id=d1.id, coid=refs["o3"])
        uow.commit()

    censo_depois = _cognitive_census()

    assert censo_depois == censo_antes, "classificar não pode alterar patrimônio"

    with engine.connect() as conn:
        memberships = conn.execute(
            sa.text("SELECT COUNT(*) FROM memory_domain_memberships")
        ).scalar_one()
        dominios = conn.execute(sa.text("SELECT COUNT(*) FROM memory_domains")).scalar_one()
    assert (dominios, memberships) == (2, 4), "a organização precisa ter mudado de fato"

    # E a auditoria de integridade da E3 continua limpa: organização
    # nova não é corrupção.
    with UnitOfWork() as uow:
        report = IntegrityManager(IntegrityRepository(uow.session)).audit()
    assert report.status is IntegrityStatus.PASS, report.findings


def test_cout2_multi_domain_preserves_the_same_coid():
    """COUT2 — o mesmo COID em vários domínios continua **um** objeto.

    DOMAIN CLASSIFICATION MUST NOT COLLAPSE COGNITIVE IDENTITY
    """
    refs = _seed_patrimony()

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        dominios = [manager.create_domain(name=f"D{i}") for i in range(5)]
        uow.session.flush()
        for d in dominios:
            manager.add_object(domain_id=d.id, coid=refs["o1"])
        uow.commit()

    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        o1 = objects.get_by_id(refs["o1"])
        assert o1 is not None
        assert o1.id == refs["o1"]
        assert o1.clid == refs["clid"]

        total_objetos = uow.session.execute(
            sa.select(sa.func.count()).select_from(CognitiveObject.__table__)
        ).scalar_one()
        assert total_objetos == 3, "nenhuma cópia foi criada"

        assert len(_manager(uow.session).list_domains_for_object(refs["o1"])) == 5

        # A linhagem e a história causal do objeto seguem intactas.
        assert LineageRepository(uow.session).list_children(refs["o1"])
        assert CausalHistoryManager(CausalHistoryRepository(uow.session)).events_for(refs["o1"])


def test_cout3_zero_domain_object_is_fully_valid():
    """COUT3 — `ZERO DOMAIN MEMBERSHIP != NONEXISTENCE`.

    Um objeto sem domínio nenhum continua existindo, recuperável pelo
    Search da E3 conforme as regras da E3, e a integridade permanece
    válida.
    """
    refs = _seed_patrimony()

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        d1 = manager.create_domain(name="D1")
        uow.session.flush()
        manager.add_object(domain_id=d1.id, coid=refs["o1"])
        uow.commit()

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        assert manager.list_domains_for_object(refs["o2"]) == []

        # Existe, e o Search da E3 o encontra pelas regras da E3 —
        # domínio não é critério de busca cognitiva.
        search = SearchEngine(SearchRepository(uow.session))
        achados = [o.id for o in search.search(SearchCriteria(clid=refs["clid"]))]
        assert refs["o2"] in achados

        report = IntegrityManager(IntegrityRepository(uow.session)).audit()
        assert report.status is IntegrityStatus.PASS, report.findings


def test_cout4_membership_does_not_resurrect_an_extinct_distinction():
    """COUT4 — Broken Glass: `DOMAIN CLASSIFICATION != CAUSAL RESURRECTION`.

    Classificar um objeto `CAUSALLY_EXTINCT` num domínio não o traz de
    volta a `ACTIVE`, e não apaga nem restaura a distinção extinta. A
    história permanece; o estado presente também.
    """
    refs = _seed_patrimony()

    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        o3 = objects.get_by_id(refs["o3"])
        assert o3 is not None
        assert o3.accessibility is AccessibilityState.CAUSALLY_EXTINCT

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        d1 = manager.create_domain(name="arquivo")
        uow.session.flush()
        manager.add_object(domain_id=d1.id, coid=refs["o3"])
        uow.commit()

    with UnitOfWork() as uow:
        o3 = ObjectRepository(uow.session).get_by_id(refs["o3"])
        assert o3 is not None
        assert (
            o3.accessibility is AccessibilityState.CAUSALLY_EXTINCT
        ), "membership não pode transicionar acessibilidade — política é E4.7"
        assert _manager(uow.session).contains(domain_id=d1.id, coid=refs["o3"])


def test_cout5_memory_state_never_entered_the_e3_sync_envelope():
    """`MEMORY_DOMAIN_SYNC = DEFERRED`.

    O envelope da E3 continua com as sete seções congeladas. A
    portabilidade de `MemoryDomain` permanece **em aberto** no freeze
    da E4, e resolvê-la aqui seria antecipar política — o critério
    decisivo registrado (*se carregar semântica de acesso, é LOCAL*) só
    pode ser avaliado depois que E4.3 existir.
    """
    assert set(SECTION_BY_TABLE) == set(_COGNITIVE_TABLES)
    for tabela in _MEMORY_TABLES:
        assert tabela not in SECTION_BY_TABLE


def test_db5_repository_classifies_the_remaining_fk_violation_on_postgres():
    """DB5 — o diagnóstico determinado de §5.2 vale no banco real.

    Os testes unitários exercitam a classificação pelo sinal do SQLite;
    DB2 exercita a FK por SQL direto. Faltava o caminho que de fato
    roda em produção: uma violação de FK **através do repositório**,
    contra PostgreSQL, com o domínio já confirmado — que só pode ser o
    `coid` e deve virar `PIA-8025`, nunca um erro genérico de
    persistência.
    """
    from app.memory.errors.exceptions import MemoryDomainMembershipObjectNotFoundError

    with UnitOfWork() as uow:
        domain = MemoryDomainRepository(uow.session).add_domain(name="d1")
        uow.commit()
        domain_id = domain.id

    ausente = uuid.uuid4()
    with UnitOfWork() as uow, pytest.raises(MemoryDomainMembershipObjectNotFoundError) as exc:
        MemoryDomainMembershipRepository(uow.session).add_membership(
            domain_id=domain_id, coid=ausente
        )
    assert exc.value.error_code.code == "PIA-8025"
    assert exc.value.coid == ausente

    # Nenhum objeto foi fabricado para acomodar a classificação.
    with engine.connect() as conn:
        assert (
            conn.execute(
                sa.text("SELECT COUNT(*) FROM cognitive_objects WHERE id = :c"), {"c": ausente}
            ).scalar_one()
            == 0
        )
