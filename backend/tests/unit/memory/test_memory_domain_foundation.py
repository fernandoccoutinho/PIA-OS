"""
E4.1 — testes unitários de `MemoryDomain` e membership.

Cobrem MD1–MD6 (domínio) e MM1–MM14 (pertencimento) do §38 do prompt
canônico. Os gates COUT fortes e os de banco real vivem em
`tests/integration/memory/`.
"""

import pathlib
import re
import uuid

import pytest

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import AccessibilityState, RevisionStatus
from app.memory.errors.exceptions import (
    MemoryDomainMembershipDuplicateError,
    MemoryDomainMembershipObjectNotFoundError,
    MemoryDomainNotFoundError,
)
from app.memory.models.memory_domain import MemoryDomain
from app.memory.repositories.memory_domain_membership_repository import (
    MemoryDomainMembershipRepository,
)
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository
from app.memory.services.memory_domain_manager import MemoryDomainManager

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[3]
_MEMORY_PACKAGE = _BACKEND_ROOT / "app" / "memory"


def _manager(session) -> MemoryDomainManager:
    return MemoryDomainManager(
        MemoryDomainRepository(session), MemoryDomainMembershipRepository(session)
    )


def _object(session, **kwargs) -> CognitiveObject:
    obj = CognitiveObject(**kwargs)
    session.add(obj)
    session.flush()
    return obj


# ======================================================================
# MD — MemoryDomain
# ======================================================================


def test_md1_create_memory_domain(memory_session):
    """MD1 — criar um domínio persiste identidade e nome."""
    domain = _manager(memory_session).create_domain(name="pesquisa")
    memory_session.flush()

    assert domain.id is not None
    assert domain.name == "pesquisa"
    assert domain.created_at is not None


def test_md2_domain_has_its_own_identity(memory_session):
    """MD2 — `domain_id` é identidade própria, distinta de COID.

    Dois domínios com o **mesmo nome** são dois domínios: nome não é
    identidade, e nenhuma unicidade de nome foi contratada.
    """
    manager = _manager(memory_session)
    d1 = manager.create_domain(name="livro")
    d2 = manager.create_domain(name="livro")
    memory_session.flush()

    assert d1.id != d2.id
    assert d1.name == d2.name
    assert isinstance(d1.id, uuid.UUID)
    assert d1.domain_id == d1.id


def test_md3_name_is_an_attribute_not_an_identity(memory_session):
    """MD3 — `same name != same domain`.

    O teste protege a ausência de `UNIQUE(name)`: se alguém a
    acrescentar por conveniência, o cenário acima quebra e a decisão
    volta à mesa em vez de passar silenciosamente.
    """
    manager = _manager(memory_session)
    manager.create_domain(name="duplicado")
    manager.create_domain(name="duplicado")
    memory_session.flush()

    assert len(manager.list_domains()) == 2


def test_md4_domain_is_not_a_cognitive_object(memory_session):
    """MD4 — `MemoryDomain` não é `CognitiveObject`.

    Não tem CLID, `accessibility`, `revision_status`, e criar um
    domínio não cria objeto cognitivo algum.
    """
    manager = _manager(memory_session)
    antes = memory_session.query(CognitiveObject).count()
    domain = manager.create_domain(name="empresa")
    memory_session.flush()
    depois = memory_session.query(CognitiveObject).count()

    assert depois == antes == 0, "criar domínio não pode criar CognitiveObject"
    for atributo in ("clid", "accessibility", "revision_status", "coid"):
        assert not hasattr(domain, atributo), f"MemoryDomain não deve ter {atributo}"


def test_md5_get_and_list_are_deterministic(memory_session):
    """MD5 — `get`/`list` funcionam e a ordem é determinística."""
    manager = _manager(memory_session)
    criados = [manager.create_domain(name=f"d{i}") for i in range(5)]
    memory_session.flush()

    assert manager.get_domain(criados[2].id) is criados[2]
    assert manager.get_domain(uuid.uuid4()) is None, "ausência não é exceção"

    primeira = [d.id for d in manager.list_domains()]
    segunda = [d.id for d in manager.list_domains()]
    assert primeira == segunda
    assert set(primeira) == {d.id for d in criados}


def test_md6_memory_package_never_imports_the_cognitive_domain():
    """MD6 — a fronteira E3/E4 é estrutural, não documental.

    `app/memory/` não pode importar `app.cognitive` em nenhuma linha.
    Isso é exigido pelo gate `G17` da E3.12 (que varre `backend/app/`
    inteiro) e é o que impede a E4 de virar uma segunda Biblioteca
    Cognitiva.

    O teste vive aqui, e não só lá, porque a violação deve falhar no
    módulo que a introduziria — não num teste da entrega anterior.
    """
    padrao = re.compile(r"^\s*(from|import)\s+app\.cognitive", re.MULTILINE)
    achados = [
        str(caminho.relative_to(_BACKEND_ROOT))
        for caminho in _MEMORY_PACKAGE.rglob("*.py")
        if padrao.search(caminho.read_text(encoding="utf-8"))
    ]
    assert achados == [], f"app/memory/ passou a depender de app.cognitive: {achados}"


# ======================================================================
# MM — membership
# ======================================================================


def test_mm1_add_coid_to_domain(memory_session):
    """MM1 — classificar um COID num domínio."""
    manager = _manager(memory_session)
    obj = _object(memory_session)
    domain = manager.create_domain(name="d1")
    memory_session.flush()

    membership = manager.add_object(domain_id=domain.id, coid=obj.id)
    memory_session.flush()

    assert membership.domain_id == domain.id
    assert membership.coid == obj.id
    assert manager.contains(domain_id=domain.id, coid=obj.id)


def test_mm2_same_coid_in_two_domains(memory_session):
    """MM2 — um COID pertence a vários domínios sem duplicar nada.

    Gate obrigatório (§32): mesmo COID, mesmo CLID, mesma história,
    duas memberships, **um** `CognitiveObject`.
    """
    manager = _manager(memory_session)
    clid = uuid.uuid4()
    obj = _object(memory_session, clid=clid)
    d1 = manager.create_domain(name="d1")
    d2 = manager.create_domain(name="d2")
    memory_session.flush()

    manager.add_object(domain_id=d1.id, coid=obj.id)
    manager.add_object(domain_id=d2.id, coid=obj.id)
    memory_session.flush()

    assert memory_session.query(CognitiveObject).count() == 1
    assert obj.clid == clid
    assert set(manager.list_domains_for_object(obj.id)) == {d1.id, d2.id}


def test_mm3_two_coids_in_the_same_domain(memory_session):
    """MM3 — um domínio classifica muitos COIDs."""
    manager = _manager(memory_session)
    o1, o2 = _object(memory_session), _object(memory_session)
    domain = manager.create_domain(name="d1")
    memory_session.flush()

    manager.add_object(domain_id=domain.id, coid=o1.id)
    manager.add_object(domain_id=domain.id, coid=o2.id)
    memory_session.flush()

    assert set(manager.list_members(domain.id)) == {o1.id, o2.id}


def test_mm4_duplicate_membership_is_rejected(memory_session):
    """MM4 — o mesmo par `(domain_id, coid)` não entra duas vezes."""
    manager = _manager(memory_session)
    obj = _object(memory_session)
    domain = manager.create_domain(name="d1")
    memory_session.flush()

    manager.add_object(domain_id=domain.id, coid=obj.id)
    memory_session.flush()

    with pytest.raises(MemoryDomainMembershipDuplicateError) as exc:
        manager.add_object(domain_id=domain.id, coid=obj.id)
    assert exc.value.error_code.code == "PIA-8024"


def test_mm5_nonexistent_coid_is_rejected(memory_session):
    """MM5 — COID inexistente é rejeitado, e nenhum objeto é fabricado.

    O diagnóstico é **determinado**: como o domínio foi confirmado
    antes da escrita, a violação de FK restante só pode ser o `coid`.
    """
    manager = _manager(memory_session)
    domain = manager.create_domain(name="d1")
    memory_session.flush()
    ausente = uuid.uuid4()

    with pytest.raises(MemoryDomainMembershipObjectNotFoundError) as exc:
        manager.add_object(domain_id=domain.id, coid=ausente)
    assert exc.value.error_code.code == "PIA-8025"
    assert exc.value.coid == ausente

    memory_session.rollback()
    assert memory_session.query(CognitiveObject).count() == 0


def test_mm6_nonexistent_domain_is_rejected(memory_session):
    """MM6 — domínio inexistente produz erro próprio, não FK genérica."""
    manager = _manager(memory_session)
    obj = _object(memory_session)
    memory_session.flush()
    ausente = uuid.uuid4()

    with pytest.raises(MemoryDomainNotFoundError) as exc:
        manager.add_object(domain_id=ausente, coid=obj.id)
    assert exc.value.error_code.code == "PIA-8023"
    assert exc.value.domain_id == ausente


def test_mm7_zero_domain_object_remains_valid(memory_session):
    """MM7 — `ZERO DOMAIN MEMBERSHIP != NONEXISTENCE`.

    Objeto sem domínio nenhum existe, é consultável e devolve lista
    vazia — não erro.
    """
    manager = _manager(memory_session)
    obj = _object(memory_session)
    memory_session.flush()

    assert manager.list_domains_for_object(obj.id) == []
    assert memory_session.get(CognitiveObject, obj.id) is obj


def test_mm8_membership_does_not_alter_the_cognitive_object(memory_session):
    """MM8 — classificar não muda identidade nem estado do objeto."""
    manager = _manager(memory_session)
    obj = _object(
        memory_session,
        clid=uuid.uuid4(),
        accessibility=AccessibilityState.LATENT,
        revision_status=RevisionStatus.SUPERSEDED,
    )
    domain = manager.create_domain(name="d1")
    memory_session.flush()
    antes = (obj.id, obj.clid, obj.accessibility, obj.revision_status)

    manager.add_object(domain_id=domain.id, coid=obj.id)
    memory_session.flush()
    memory_session.refresh(obj)

    assert (obj.id, obj.clid, obj.accessibility, obj.revision_status) == antes


def test_mm9_membership_does_not_alter_clid(memory_session):
    """MM9 — CLID intocado, inclusive quando é `None`."""
    manager = _manager(memory_session)
    sem_clid = _object(memory_session)
    com_clid = _object(memory_session, clid=uuid.uuid4())
    domain = manager.create_domain(name="d1")
    memory_session.flush()
    clid_original = com_clid.clid

    manager.add_object(domain_id=domain.id, coid=sem_clid.id)
    manager.add_object(domain_id=domain.id, coid=com_clid.id)
    memory_session.flush()

    assert sem_clid.clid is None
    assert com_clid.clid == clid_original


@pytest.mark.parametrize("estado", list(AccessibilityState))
def test_mm10_membership_does_not_alter_accessibility(memory_session, estado):
    """MM10 — `DOMAIN MEMBERSHIP != ACCESSIBILITY`, nos quatro estados.

    Inclui `CAUSALLY_EXTINCT`: classificar não ressuscita distinção
    extinta. A política de transição é E4.7, não este módulo.
    """
    manager = _manager(memory_session)
    obj = _object(memory_session, accessibility=estado)
    domain = manager.create_domain(name="d1")
    memory_session.flush()

    manager.add_object(domain_id=domain.id, coid=obj.id)
    memory_session.flush()
    memory_session.refresh(obj)

    assert obj.accessibility is estado


def test_mm11_membership_creates_no_provenance(memory_session):
    """MM11 — classificação administrativa não é evento de origem.

    Nenhum `ProvenanceRecord` é fabricado (§17). O teste conta as
    linhas por SQL para não depender de importar o modelo no código de
    produção.
    """
    from sqlalchemy import text

    manager = _manager(memory_session)
    obj = _object(memory_session)
    domain = manager.create_domain(name="d1")
    memory_session.flush()

    manager.add_object(domain_id=domain.id, coid=obj.id)
    memory_session.flush()

    tabelas = {
        row[0]
        for row in memory_session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    assert "provenance_records" not in tabelas, (
        "E4.1 não deve exigir a tabela de proveniência para operar — "
        "prova de que nenhuma proveniência é criada por membership"
    )


def test_mm12_membership_creates_no_causal_event(memory_session):
    """MM12 — organização lógica não é causalidade cognitiva (§18).

    Mesmo argumento de MM11: as tabelas causais sequer existem no
    engine deste teste, e a operação funciona — logo nenhum
    `CausalHistoryEvent` é criado.
    """
    from sqlalchemy import text

    manager = _manager(memory_session)
    obj = _object(memory_session)
    domain = manager.create_domain(name="d1")
    memory_session.flush()

    manager.add_object(domain_id=domain.id, coid=obj.id)
    memory_session.flush()

    tabelas = {
        row[0]
        for row in memory_session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    assert "causal_history_events" not in tabelas
    assert "causal_histories" not in tabelas


def test_mm13_co_membership_creates_no_cognitive_relation(memory_session):
    """MM13 — estar no mesmo domínio não relaciona dois objetos.

    `DOMAIN BOUNDARY != COGNITIVE BOUNDARY`: co-pertencimento não cria
    `Relationship`, não iguala CLID e não sugere equivalência.
    """
    from sqlalchemy import text

    manager = _manager(memory_session)
    o1 = _object(memory_session, clid=uuid.uuid4())
    o2 = _object(memory_session, clid=uuid.uuid4())
    domain = manager.create_domain(name="d1")
    memory_session.flush()

    manager.add_object(domain_id=domain.id, coid=o1.id)
    manager.add_object(domain_id=domain.id, coid=o2.id)
    memory_session.flush()

    assert o1.clid != o2.clid, "co-membership não iguala continuidade"
    assert o1.id != o2.id
    tabelas = {
        row[0]
        for row in memory_session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    assert "relationships" not in tabelas


def test_mm14_membership_queries_are_deterministic(memory_session):
    """MM14 — as duas consultas de membership têm ordem total estável."""
    manager = _manager(memory_session)
    domain = manager.create_domain(name="d1")
    outros = [manager.create_domain(name=f"o{i}") for i in range(4)]
    objs = [_object(memory_session) for _ in range(4)]
    memory_session.flush()

    for obj in objs:
        manager.add_object(domain_id=domain.id, coid=obj.id)
    for outro in outros:
        manager.add_object(domain_id=outro.id, coid=objs[0].id)
    memory_session.flush()

    assert manager.list_members(domain.id) == manager.list_members(domain.id)
    assert manager.list_domains_for_object(objs[0].id) == manager.list_domains_for_object(
        objs[0].id
    )
    assert set(manager.list_members(domain.id)) == {o.id for o in objs}


def test_mm15_repository_reraises_unclassified_persistence_errors(memory_session):
    """Causa desconhecida de `PersistenceError` é relançada sem
    reinterpretação — a lição de E3.2.1: não classificar por eliminação.
    """
    from app.repositories.exceptions import PersistenceError

    repo = MemoryDomainMembershipRepository(memory_session)
    domain = MemoryDomainRepository(memory_session).add_domain(name="d1")
    memory_session.flush()

    def _explode(_entity):
        raise PersistenceError("falha sem sqlstate conhecido")

    repo.add = _explode  # type: ignore[method-assign]

    with pytest.raises(PersistenceError):
        repo.add_membership(domain_id=domain.id, coid=uuid.uuid4())


def test_mm16_contains_is_false_for_unrelated_pairs(memory_session):
    """`contains` distingue o par exato, não apenas a presença de cada
    lado isoladamente."""
    manager = _manager(memory_session)
    o1, o2 = _object(memory_session), _object(memory_session)
    d1 = manager.create_domain(name="d1")
    d2 = manager.create_domain(name="d2")
    memory_session.flush()

    manager.add_object(domain_id=d1.id, coid=o1.id)
    memory_session.flush()

    assert manager.contains(domain_id=d1.id, coid=o1.id)
    assert not manager.contains(domain_id=d1.id, coid=o2.id)
    assert not manager.contains(domain_id=d2.id, coid=o1.id)


def test_md7_domain_repository_pagination_is_bounded(memory_session):
    """`list_domains` respeita `limit`/`offset` sobre ordem total."""
    repo = MemoryDomainRepository(memory_session)
    for i in range(6):
        repo.add_domain(name=f"d{i}")
    memory_session.flush()

    todos = repo.list_domains()
    assert len(todos) == 6
    assert [d.id for d in repo.list_domains(limit=2)] == [d.id for d in todos[:2]]
    assert [d.id for d in repo.list_domains(limit=2, offset=2)] == [d.id for d in todos[2:4]]
    assert [d.id for d in repo.list_domains(offset=4)] == [d.id for d in todos[4:]]


def test_md8_exists_domain_reflects_persistence(memory_session):
    """`exists_domain` é a pré-checagem que torna determinado o
    diagnóstico entre as duas FKs da membership."""
    repo = MemoryDomainRepository(memory_session)
    domain = repo.add_domain(name="d1")
    memory_session.flush()

    assert repo.exists_domain(domain.id)
    assert not repo.exists_domain(uuid.uuid4())


def test_md9_membership_model_has_no_lifecycle_column():
    """O contrato mínimo não tem coluna de lifecycle.

    A ausência é decisão registrada (E4.1 §4.2), não esquecimento:
    remoção de membership está `DEFERRED` até E4.3 definir autoridade,
    e uma coluna que nenhum código escreve não preserva história — só
    promete preservação que o módulo não entrega.
    """
    from app.memory.models.memory_domain_membership import MemoryDomainMembership

    colunas = {c.name for c in MemoryDomainMembership.__table__.columns}
    assert colunas == {"id", "domain_id", "coid", "created_at", "updated_at"}
    for proibida in ("left_at", "retired_at", "deleted_at", "metadata", "role"):
        assert proibida not in colunas


def test_md10_domain_model_contract_is_minimal():
    """O contrato de `MemoryDomain` não cresceu por antecipação."""
    colunas = {c.name for c in MemoryDomain.__table__.columns}
    assert colunas == {"id", "name", "created_at", "updated_at"}
    for proibida in (
        "description",
        "metadata",
        "owner",
        "owner_id",
        "acl",
        "policy_ref",
        "parent_domain_id",
        "path",
        "provider_id",
        "model_id",
        "importance_score",
        "persistence_score",
        "relevance_score",
    ):
        assert proibida not in colunas, f"campo não autorizado presente: {proibida}"
