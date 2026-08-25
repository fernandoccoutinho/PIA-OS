"""
Integração de `MultiInputTransformationManager` contra PostgreSQL real
(E3.4.2).

Cobre as 22 exigências do §13 do prompt canônico. **Não** substitui por
SQLite: as garantias que interessam aqui — atomicidade sob rollback,
`timestamptz`, FK real e concorrência entre conexões — só existem no
banco de produção. SQLite compila `FOR UPDATE` como no-op e não tem
lock de linha; afirmar aqui o que ele não prova seria overclaim.

Cada teste limpa o que criou: a suíte roda contra um banco compartilhado
e um resíduo de um teste vira falha intermitente de outro.
"""

import threading
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from app.cognitive.errors.exceptions import (
    CausalPredecessorNotFoundError,
    CausalPredecessorSubjectMismatchError,
    MultiInputSourceNotFoundError,
)
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import CausalEventType, LineageRelation, TransformationKind
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.transformation_repository import TransformationRepository
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.clid_manager import ClidManager
from app.cognitive.services.multi_input_transformation_manager import (
    MultiInputTransformationManager,
)
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork


def _postgres_pronto() -> bool:
    health = check_database_health()
    if not health.available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    tabelas = inspect(engine).get_table_names()
    return {
        "cognitive_objects",
        "lineage_edges",
        "transformation_records",
        "causal_histories",
        "causal_history_events",
    }.issubset(tabelas)


pytestmark = pytest.mark.skipif(
    not _postgres_pronto(),
    reason="PostgreSQL real indisponível ou migrações cognitivas não aplicadas.",
)


def _kit(session):
    objetos = ObjectRepository(session)
    linhagem = LineageRepository(session)
    transformacoes = TransformationRepository(session)
    historias = CausalHistoryRepository(session)
    clid = ClidManager(objetos, linhagem)
    causal = CausalHistoryManager(historias)
    manager = MultiInputTransformationManager(
        objetos, clid, linhagem, transformacoes, causal, historias
    )
    return manager, objetos, linhagem, transformacoes, historias, causal


def _criar_fontes(quantidade: int, *, clid: uuid.UUID | None = None) -> list[uuid.UUID]:
    """Cria fontes commitadas e devolve seus COIDs."""
    with UnitOfWork() as uow:
        objetos = ObjectRepository(uow.session)
        criados = []
        for _ in range(quantidade):
            objeto = objetos.add(CognitiveObject())
            if clid is not None:
                objeto.clid = clid
                objetos.update(objeto)
            criados.append(objeto)
        uow.commit()
        return [o.id for o in criados]


def _limpar(coids: list[uuid.UUID]) -> None:
    """Remove tudo que os testes criaram, na ordem das dependências."""
    if not coids:
        return
    alvos = [str(c) for c in coids]
    with UnitOfWork() as uow:
        s = uow.session
        s.execute(
            sa.text(
                "DELETE FROM causal_history_events WHERE history_id IN "
                "(SELECT id FROM causal_histories WHERE subject_coid = ANY(:c ::uuid[]))"
            ),
            {"c": alvos},
        )
        s.execute(
            sa.text("DELETE FROM causal_histories WHERE subject_coid = ANY(:c ::uuid[])"),
            {"c": alvos},
        )
        s.execute(
            sa.text(
                "DELETE FROM lineage_edges WHERE parent_coid = ANY(:c ::uuid[]) "
                "OR child_coid = ANY(:c ::uuid[])"
            ),
            {"c": alvos},
        )
        s.execute(
            sa.text(
                "DELETE FROM transformation_records WHERE input_refs::text LIKE ANY("
                "SELECT '%' || x || '%' FROM unnest(:c ::text[]) AS x)"
            ),
            {"c": alvos},
        )
        s.execute(
            sa.text("DELETE FROM provenance_records WHERE coid = ANY(:c ::uuid[])"),
            {"c": alvos},
        )
        s.execute(
            sa.text("DELETE FROM cognitive_objects WHERE id = ANY(:c ::uuid[])"), {"c": alvos}
        )
        uow.commit()


# --- 1/2. Caminho feliz -----------------------------------------------


def test_e342_pg1_happy_path_two_sources_with_common_clid():
    clid = uuid.uuid4()
    fontes = _criar_fontes(2, clid=clid)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=fontes,
                operation_type="consolidar",
                declared_losses=["variações de ramo"],
                declared_preservations=["tese central"],
            )
            uow.commit()
            criados.append(recibo.target_coid)

        with UnitOfWork() as uow:
            _m, objetos, linhagem, transformacoes, *_ = _kit(uow.session)
            alvo = objetos.get_by_id(recibo.target_coid)
            assert alvo is not None
            assert alvo.clid == clid
            assert len(linhagem.list_parents(recibo.target_coid)) == 2
            registro = transformacoes.get_by_id(recibo.transformation_id)
            assert registro.transformation_kind is TransformationKind.DERIVATION
            assert registro.declared_losses == ["variações de ramo"]
            assert registro.declared_preservations == ["tese central"]
    finally:
        _limpar(criados)


def test_e342_pg2_happy_path_three_sources():
    clid = uuid.uuid4()
    fontes = _criar_fontes(3, clid=clid)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=fontes, operation_type="consolidar", declared_losses=["x"]
            )
            uow.commit()
            criados.append(recibo.target_coid)

        assert len(recibo.source_coids) == 3
        assert len(recibo.lineage_edge_ids) == 3
        assert recibo.target_clid == clid
    finally:
        _limpar(criados)


# --- 3/4. CLID divergente ou ausente ---------------------------------


def test_e342_pg3_distinct_clids_produce_a_target_without_clid():
    a = _criar_fontes(1, clid=uuid.uuid4())[0]
    b = _criar_fontes(1, clid=uuid.uuid4())[0]
    criados = [a, b]
    try:
        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=[a, b], operation_type="c", declared_losses=["x"]
            )
            uow.commit()
            criados.append(recibo.target_coid)

        with UnitOfWork() as uow:
            _m, objetos, *_ = _kit(uow.session)
            assert objetos.get_by_id(recibo.target_coid).clid is None
    finally:
        _limpar(criados)


def test_e342_pg4_source_without_clid_produces_a_target_without_clid():
    a = _criar_fontes(1, clid=uuid.uuid4())[0]
    b = _criar_fontes(1)[0]
    criados = [a, b]
    try:
        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=[a, b], operation_type="c", declared_losses=["x"]
            )
            uow.commit()
            criados.append(recibo.target_coid)

        with UnitOfWork() as uow:
            _m, objetos, *_ = _kit(uow.session)
            assert objetos.get_by_id(recibo.target_coid).clid is None
            # e a fonte sem CLID continua sem CLID
            assert objetos.get_by_id(b).clid is None
    finally:
        _limpar(criados)


# --- 5. Fonte soft-deleted -------------------------------------------


def test_e342_pg5_soft_deleted_source_is_preserved_and_referenced():
    fontes = _criar_fontes(2)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            _m, objetos, *_ = _kit(uow.session)
            objetos.soft_delete(objetos.get_by_id(fontes[1]))
            uow.commit()

        with UnitOfWork() as uow:
            _m, objetos, *_ = _kit(uow.session)
            apagada_em = objetos.get_by_id(fontes[1], include_deleted=True).deleted_at
        assert apagada_em is not None

        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=fontes, operation_type="c", declared_losses=["x"]
            )
            uow.commit()
            criados.append(recibo.target_coid)

        with UnitOfWork() as uow:
            _m, objetos, linhagem, transformacoes, *_ = _kit(uow.session)
            registro = transformacoes.get_by_id(recibo.transformation_id)
            assert str(fontes[1]) in registro.input_refs
            assert linhagem.edge_exists(fontes[1], recibo.target_coid, LineageRelation.MERGE)
            ainda_apagada = objetos.get_by_id(fontes[1], include_deleted=True)
            assert ainda_apagada.deleted_at == apagada_em
            assert objetos.get_by_id(fontes[1]) is None
    finally:
        _limpar(criados)


# --- 6/7/8/9. Cardinalidade do que foi escrito ------------------------


def test_e342_pg6_to_pg9_exact_cardinality_of_writes():
    fontes = _criar_fontes(3, clid=uuid.uuid4())
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=fontes, operation_type="c", declared_losses=["x"]
            )
            uow.commit()
            criados.append(recibo.target_coid)

        with UnitOfWork() as uow:
            s = uow.session
            # 6 — exatamente um alvo novo
            alvos = s.execute(
                sa.text("SELECT count(*) FROM cognitive_objects WHERE id = :t"),
                {"t": str(recibo.target_coid)},
            ).scalar_one()
            assert alvos == 1
            # 7 — exatamente N edges MERGE
            edges = s.execute(
                sa.text(
                    "SELECT count(*) FROM lineage_edges WHERE child_coid = :t "
                    "AND relation_type = 'merge'"
                ),
                {"t": str(recibo.target_coid)},
            ).scalar_one()
            assert edges == 3
            # 8 — exatamente um registro multi-input
            registros = s.execute(
                sa.text(
                    "SELECT count(*) FROM transformation_records " "WHERE output_refs::text LIKE :t"
                ),
                {"t": f"%{recibo.target_coid}%"},
            ).scalar_one()
            assert registros == 1
            # 9 — input_refs exatamente as fontes, em ordem canônica
            _m, _o, _l, transformacoes, *_ = _kit(s)
            registro = transformacoes.get_by_id(recibo.transformation_id)
            assert registro.input_refs == [str(c) for c in sorted(fontes)]
            assert registro.output_refs == [str(recibo.target_coid)]
    finally:
        _limpar(criados)


# --- 10. Nenhuma fonte alterada ---------------------------------------


def test_e342_pg10_no_source_row_is_altered():
    """Censo linha a linha das fontes, antes e depois."""
    clid = uuid.uuid4()
    fontes = _criar_fontes(2, clid=clid)
    criados = list(fontes)

    def _censo() -> list[tuple]:
        with UnitOfWork() as uow:
            linhas = uow.session.execute(
                sa.text(
                    "SELECT id, clid, accessibility, revision_status, deleted_at, updated_at "
                    "FROM cognitive_objects WHERE id = ANY(:c ::uuid[]) ORDER BY id"
                ),
                {"c": [str(c) for c in fontes]},
            ).all()
            return [tuple(linha) for linha in linhas]

    try:
        antes = _censo()
        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=fontes, operation_type="c", declared_losses=["x"]
            )
            uow.commit()
            criados.append(recibo.target_coid)
        assert _censo() == antes
    finally:
        _limpar(criados)


# --- 11/12/13/14. Causalidade -----------------------------------------


def test_e342_pg11_root_causal_event_without_predecessor():
    fontes = _criar_fontes(2)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=fontes, operation_type="c", declared_losses=["x"]
            )
            uow.commit()
            criados.append(recibo.target_coid)

        with UnitOfWork() as uow:
            *_, causal = _kit(uow.session)
            eventos = causal.events_for(recibo.target_coid)
            assert len(eventos) == 1
            assert eventos[0].predecessor_event_id is None
            assert eventos[0].event_type is CausalEventType.TRANSFORMED
            assert eventos[0].payload_ref == str(recibo.transformation_id)
    finally:
        _limpar(criados)


def test_e342_pg12_pg13_multiple_explicit_cross_history_predecessors():
    """Predecessor cross-history é legítimo quando o sujeito é uma das
    fontes — duas fontes têm duas histórias distintas."""
    fontes = _criar_fontes(2)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            *_, causal = _kit(uow.session)
            ev_a = causal.record(subject_coid=fontes[0], event_type=CausalEventType.CREATED)
            ev_b = causal.record(subject_coid=fontes[1], event_type=CausalEventType.CREATED)
            uow.commit()
            ids_predecessores = [ev_a.id, ev_b.id]

        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=fontes,
                operation_type="c",
                declared_losses=["x"],
                predecessor_event_ids=ids_predecessores,
            )
            uow.commit()
            criados.append(recibo.target_coid)

        with UnitOfWork() as uow:
            *_, causal = _kit(uow.session)
            eventos = causal.events_for(recibo.target_coid)
            assert len(eventos) == 2
            assert {e.predecessor_event_id for e in eventos} == set(ids_predecessores)
    finally:
        _limpar(criados)


def test_e342_pg14_predecessor_of_a_foreign_object_is_rejected():
    fontes = _criar_fontes(2)
    estranho = _criar_fontes(1)[0]
    criados = [*fontes, estranho]
    try:
        with UnitOfWork() as uow:
            *_, causal = _kit(uow.session)
            ev = causal.record(subject_coid=estranho, event_type=CausalEventType.CREATED)
            uow.commit()
            ev_id = ev.id

        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            with pytest.raises(CausalPredecessorSubjectMismatchError):
                manager.derive_many(
                    source_coids=fontes,
                    operation_type="c",
                    declared_losses=["x"],
                    predecessor_event_ids=[ev_id],
                )

        with pytest.raises(CausalPredecessorNotFoundError), UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            manager.derive_many(
                source_coids=fontes,
                operation_type="c",
                declared_losses=["x"],
                predecessor_event_ids=[uuid.uuid4()],
            )
    finally:
        _limpar(criados)


# --- 15/16/17/18/19. Rollback e atomicidade ---------------------------


def test_e342_pg15_rollback_by_omission_leaves_nothing():
    """A `UnitOfWork` faz rollback por omissão — sem `commit()`, nada
    da operação sobrevive."""
    fontes = _criar_fontes(2)
    try:
        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=fontes, operation_type="c", declared_losses=["x"]
            )
            # sem uow.commit()

        with UnitOfWork() as uow:
            _m, objetos, linhagem, transformacoes, *_ = _kit(uow.session)
            assert objetos.get_by_id(recibo.target_coid, include_deleted=True) is None
            assert linhagem.list_parents(recibo.target_coid) == []
            assert transformacoes.get_by_id(recibo.transformation_id) is None
    finally:
        _limpar(fontes)


@pytest.mark.parametrize(
    ("etapa", "alvo_do_patch"),
    [
        ("edge", "app.cognitive.repositories.lineage_repository.LineageRepository.add_edge"),
        (
            "transformation",
            "app.cognitive.repositories.transformation_repository.TransformationRepository.add",
        ),
        ("causal", "app.cognitive.services.causal_history_manager.CausalHistoryManager.record"),
        ("clid", "app.cognitive.services.clid_manager.ClidManager.assign"),
    ],
)
def test_e342_pg16_pg17_pg18_pg19_rollback_after_injected_failure(
    monkeypatch, etapa, alvo_do_patch
):
    """Falha injetada em cada etapa material: nada parcial sobrevive e
    nenhuma fonte é mutada.

    `orphan target = 0`, `partial lineage = 0`,
    `partial transformation = 0`, `partial causal history = 0`,
    `source mutation = 0`, `source clid mutation = 0`,
    `internal commit = 0`.

    O quarto caso — `ClidManager.assign` — entra no corretivo E3.4.2.1.
    Ele **só é alcançável** porque as fontes deste cenário compartilham
    um CLID não nulo: com CLIDs divergentes o alvo nasceria com
    `clid=None` e `assign()` nunca seria chamado, o que tornaria a
    injeção uma prova vazia. `_criar_fontes(3, clid=clid)` garante o
    caminho de herança.
    """
    clid = uuid.uuid4()
    fontes = _criar_fontes(3, clid=clid)

    def _censo_fontes() -> list[tuple]:
        with UnitOfWork() as uow:
            return [
                tuple(linha)
                for linha in uow.session.execute(
                    sa.text(
                        "SELECT id, clid, accessibility, revision_status, deleted_at "
                        "FROM cognitive_objects WHERE id = ANY(:c ::uuid[]) ORDER BY id"
                    ),
                    {"c": [str(c) for c in fontes]},
                ).all()
            ]

    try:
        antes = _censo_fontes()
        objetos_antes = _contar("cognitive_objects")
        edges_antes = _contar("lineage_edges")
        registros_antes = _contar("transformation_records")
        eventos_antes = _contar("causal_history_events")
        historias_antes = _contar("causal_histories")

        modulo, _, atributo = alvo_do_patch.rpartition(".")
        import importlib

        caminho_modulo, _, nome_classe = modulo.rpartition(".")
        classe = getattr(importlib.import_module(caminho_modulo), nome_classe)
        original = getattr(classe, atributo)
        chamadas = {"n": 0}

        def _falhar(self, *args, **kwargs):
            chamadas["n"] += 1
            # falha na segunda chamada quando há várias (edge do meio),
            # e na primeira quando só existe uma
            if etapa == "edge" and chamadas["n"] < 2:
                return original(self, *args, **kwargs)
            raise RuntimeError(f"falha injetada em {etapa}")

        monkeypatch.setattr(classe, atributo, _falhar)

        with pytest.raises(RuntimeError, match="falha injetada"), UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            manager.derive_many(source_coids=fontes, operation_type="c", declared_losses=["x"])
            uow.commit()

        monkeypatch.undo()

        # A injeção precisa ter sido realmente alcançada. Sem isto, um
        # caso cujo caminho não fosse exercitado passaria como prova
        # vazia — o risco concreto do caso `clid`, que só existe quando
        # as fontes compartilham CLID.
        assert chamadas["n"] > 0, f"a etapa '{etapa}' nunca foi alcançada — prova vazia"

        assert _contar("cognitive_objects") == objetos_antes, "alvo órfão sobreviveu"
        assert _contar("lineage_edges") == edges_antes, "linhagem parcial sobreviveu"
        assert _contar("transformation_records") == registros_antes
        assert _contar("causal_history_events") == eventos_antes
        assert _contar("causal_histories") == historias_antes

        depois = _censo_fontes()
        assert depois == antes, "fonte foi mutada"
        # SOURCE_CLID_MUTATION = 0, dito separadamente do censo geral
        # para que o diagnóstico não dependa de ler uma tupla inteira.
        assert [linha[1] for linha in depois] == [linha[1] for linha in antes]
        assert all(str(linha[1]) == str(clid) for linha in depois)
    finally:
        _limpar(fontes)


def _contar(tabela: str) -> int:
    with UnitOfWork() as uow:
        return uow.session.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar_one()


# --- 20. Concorrência --------------------------------------------------


def test_e342_pg20_two_concurrent_consolidations_produce_two_targets():
    """Duas consolidações deliberadas das mesmas fontes são duas
    derivações legítimas, não duplicata automática:

        REPEATED CONSOLIDATION != SAME EVENT
        MULTIPLE HISTORY PRESERVATION

    Nenhuma constraint deve impedir isso, e a ordem canônica de
    aquisição evita ordem divergente de lock entre as duas.
    """
    fontes = _criar_fontes(2, clid=uuid.uuid4())
    criados = list(fontes)
    resultados: list[uuid.UUID] = []
    erros: list[BaseException] = []
    barreira = threading.Barrier(2, timeout=30)

    def _consolidar(rotulo: str) -> None:
        try:
            with UnitOfWork() as uow:
                manager, *_ = _kit(uow.session)
                barreira.wait()
                recibo = manager.derive_many(
                    source_coids=fontes, operation_type=rotulo, declared_losses=["x"]
                )
                uow.commit()
                resultados.append(recibo.target_coid)
        except BaseException as exc:  # noqa: BLE001
            erros.append(exc)

    threads = [
        threading.Thread(target=_consolidar, args=("c1",)),
        threading.Thread(target=_consolidar, args=("c2",)),
    ]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert erros == [], f"consolidação concorrente falhou: {erros}"
        assert len(resultados) == 2
        assert resultados[0] != resultados[1]
        criados.extend(resultados)

        with UnitOfWork() as uow:
            _m, objetos, linhagem, *_ = _kit(uow.session)
            for alvo in resultados:
                assert objetos.get_by_id(alvo) is not None
                assert len(linhagem.list_parents(alvo)) == 2
            # fontes intocadas
            for coid in fontes:
                assert objetos.get_by_id(coid).deleted_at is None
    finally:
        _limpar(criados)


# --- 21/22. Schema -----------------------------------------------------


def test_e342_pg21_no_schema_orm_drift():
    """Nenhuma tabela, coluna ou enum novo.

    Recorta o ruído de harness pelo mesmo critério que `IX5` (E3.7) já
    usava e `CHI8` (E3.9) repetiu: modelos declarados apenas por
    fixtures de teste (`test_base_model_concrete_entity`,
    `test_base_model_soft_delete_entity`, `test_mixin_fixture_entity`)
    também se registram no `Base` real durante a coleta e apareceriam
    como `add_table`. Isso é ruído do harness, não divergência de
    schema — e foi exatamente o que a primeira versão deste teste
    acusou quando rodou na suíte completa em vez de isolada.

    O recorte é por prefixo `test_`, e ele não enfraquece a asserção
    para o que este corretivo poderia introduzir: qualquer tabela,
    coluna ou enum que a E3.4.2 criasse teria nome de domínio, não de
    fixture.
    """
    import app.cognitive.models  # noqa: F401
    import app.memory.models  # noqa: F401
    import app.orchestration.models  # noqa: F401
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.database.base import Base
    from app.database.engine import engine

    with engine.connect() as conexao:
        contexto = MigrationContext.configure(conexao)
        diferencas = compare_metadata(contexto, Base.metadata)

    reais = [d for d in diferencas if "test_" not in str(d)]
    assert reais == [], f"schema/ORM drift: {reais}"


def test_e342_pg22_migration_head_is_unchanged_and_single():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
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
    assert tuple(heads) == ("f4c8b0d51e73",), f"migration head mudou: {heads}"


# --- Guardas adicionais -------------------------------------------------


def test_e342_occurred_at_survives_as_timestamptz():
    """Aqui a coluna é `timestamptz` de verdade — a asserção com fuso
    preservado que o SQLite dos unitários não consegue sustentar."""
    fontes = _criar_fontes(2)
    criados = list(fontes)
    quando = datetime(2024, 3, 1, 12, 0, tzinfo=UTC)
    try:
        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=fontes,
                operation_type="c",
                declared_losses=["x"],
                occurred_at=quando,
            )
            uow.commit()
            criados.append(recibo.target_coid)

        with UnitOfWork() as uow:
            *_, causal = _kit(uow.session)
            assert causal.events_for(recibo.target_coid)[0].occurred_at == quando
    finally:
        _limpar(criados)


def test_e342_missing_source_is_rejected_against_real_database():
    fontes = _criar_fontes(2)
    try:
        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            with pytest.raises(MultiInputSourceNotFoundError):
                manager.derive_many(
                    source_coids=[*fontes, uuid.uuid4()],
                    operation_type="c",
                    declared_losses=["x"],
                )
    finally:
        _limpar(fontes)


def test_e342_traceability_s1_can_be_reconstructed_from_its_sources():
    """`S1 ← {M1, M2, M3}` é reconstruível a partir do patrimônio, sem
    nenhuma entidade nova — pela linhagem e pelo registro."""
    fontes = _criar_fontes(3, clid=uuid.uuid4())
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=fontes, operation_type="consolidar", declared_losses=["x"]
            )
            uow.commit()
            criados.append(recibo.target_coid)

        with UnitOfWork() as uow:
            _m, _o, linhagem, transformacoes, *_ = _kit(uow.session)
            por_linhagem = {
                aresta.parent_coid
                for aresta in linhagem.list_parents(recibo.target_coid)
                if aresta.relation_type is LineageRelation.MERGE
            }
            registro = transformacoes.get_by_id(recibo.transformation_id)
            por_registro = {uuid.UUID(ref) for ref in registro.input_refs}

            assert por_linhagem == set(fontes)
            assert por_registro == set(fontes)
    finally:
        _limpar(criados)


# ======================================================================
# E3.4.2.1 — prova persistente de `actor_ref`
# ======================================================================


def test_e3421_actor_ref_is_propagated_to_both_persisted_records():
    """`actor_ref` chega aos DOIS registros produzidos, e é o mesmo.

    A E3.4.2 propagava corretamente no código, mas não havia prova
    contra o estado persistido. Aqui o valor é consultado direto no
    banco, não pelo objeto que o manager devolveu.

    Usa um `ProvenanceRecord` **real**: `causal_history_events.actor_ref`
    é FK para `provenance_records.id`, e a FK continua sendo a
    autoridade final. Nada de ator fictício, nada de remover
    `actor_ref` para contornar a restrição.

        PROVENANCE != CAUSAL HISTORY
    """
    from app.cognitive.models.enums import ProvenanceActorType, ProvenanceSourceType
    from app.cognitive.models.provenance_record import ProvenanceRecord
    from app.cognitive.repositories.provenance_repository import ProvenanceRepository

    fontes = _criar_fontes(2, clid=uuid.uuid4())
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            registro_prov = ProvenanceRepository(uow.session).add(
                ProvenanceRecord(
                    coid=fontes[0],
                    source_type=ProvenanceSourceType.HUMAN,
                    actor_type=ProvenanceActorType.HUMAN,
                )
            )
            uow.commit()
            ator_solicitado = registro_prov.id

        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=fontes,
                operation_type="consolidar",
                declared_losses=["x"],
                actor_ref=ator_solicitado,
            )
            uow.commit()
            criados.append(recibo.target_coid)

        # Consulta ao estado persistido, não ao objeto em memória.
        with UnitOfWork() as uow:
            ator_na_transformacao = uow.session.execute(
                sa.text("SELECT actor_ref FROM transformation_records WHERE id = :t"),
                {"t": str(recibo.transformation_id)},
            ).scalar_one()

            atores_causais = [
                linha[0]
                for linha in uow.session.execute(
                    sa.text(
                        "SELECT e.actor_ref FROM causal_history_events e "
                        "JOIN causal_histories h ON h.id = e.history_id "
                        "WHERE h.subject_coid = :t"
                    ),
                    {"t": str(recibo.target_coid)},
                ).all()
            ]

        assert atores_causais, "nenhum evento causal foi persistido para o alvo"
        assert ator_na_transformacao == ator_solicitado
        assert set(atores_causais) == {ator_solicitado}
        assert ator_na_transformacao == atores_causais[0] == ator_solicitado
    finally:
        _limpar(criados)


def test_e3421_absent_actor_ref_stays_absent_in_both_persisted_records():
    """Ausência continua ausência: `None` não vira ator fabricado.

    MISSING PROVENANCE != AUTHORIZATION TO INVENT PROVENANCE
    """
    fontes = _criar_fontes(2)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, *_ = _kit(uow.session)
            recibo = manager.derive_many(
                source_coids=fontes, operation_type="c", declared_losses=["x"]
            )
            uow.commit()
            criados.append(recibo.target_coid)

        with UnitOfWork() as uow:
            na_transformacao = uow.session.execute(
                sa.text("SELECT actor_ref FROM transformation_records WHERE id = :t"),
                {"t": str(recibo.transformation_id)},
            ).scalar_one()
            causais = [
                linha[0]
                for linha in uow.session.execute(
                    sa.text(
                        "SELECT e.actor_ref FROM causal_history_events e "
                        "JOIN causal_histories h ON h.id = e.history_id "
                        "WHERE h.subject_coid = :t"
                    ),
                    {"t": str(recibo.target_coid)},
                ).all()
            ]

        assert na_transformacao is None
        assert causais == [None]
    finally:
        _limpar(criados)
