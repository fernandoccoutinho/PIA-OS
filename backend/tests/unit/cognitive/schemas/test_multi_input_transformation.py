"""
Testes de `MultiInputTransformationReceipt` (E3.4.2).

Cobrem as 13 exigências do §12.1 do prompt canônico. O eixo central é
que os invariantes valem na **construção direta** — que é API pública
de qualquer dataclass — e não apenas no caminho do manager. Foi
exatamente essa a lição das correções E4.2.1, E4.3.2 e E4.4.1:

    frozen=True ALONE != DEEP IMMUTABILITY
"""

import uuid

import pytest

from app.cognitive.schemas.multi_input_transformation import MultiInputTransformationReceipt


def _ids(quantidade: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(quantidade)]


_AUSENTE = object()
"""Sentinela: `None` é um valor de teste legítimo para `source_coids`
(deve ser recusado pelo value object), então não pode ser usado como
marcador de "não informado" — foi assim que a primeira versão deste
helper engoliu o caso `None` e fez o teste passar por engano."""


def _recibo(**overrides) -> MultiInputTransformationReceipt:
    fontes = overrides.pop("source_coids", _AUSENTE)
    if fontes is _AUSENTE:
        fontes = _ids(2)
    campos = {
        "source_coids": fontes,
        "target_coid": uuid.uuid4(),
        "target_clid": None,
        "transformation_id": uuid.uuid4(),
        "lineage_edge_ids": (
            _ids(len(tuple(fontes)))
            if hasattr(fontes, "__iter__") and not isinstance(fontes, str | bytes)
            else _ids(2)
        ),
        "causal_event_ids": _ids(1),
        "predecessor_event_ids": (),
    }
    campos.update(overrides)
    return MultiInputTransformationReceipt(**campos)


# --- 1. Construção válida --------------------------------------------


def test_e342_receipt_valid_construction():
    fontes = _ids(3)
    edges = _ids(3)
    alvo, clid, transformacao, evento = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    recibo = MultiInputTransformationReceipt(
        source_coids=fontes,
        target_coid=alvo,
        target_clid=clid,
        transformation_id=transformacao,
        lineage_edge_ids=edges,
        causal_event_ids=[evento],
    )

    assert recibo.source_coids == tuple(fontes)
    assert recibo.target_coid == alvo
    assert recibo.target_clid == clid
    assert recibo.transformation_id == transformacao
    assert recibo.lineage_edge_ids == tuple(edges)
    assert recibo.causal_event_ids == (evento,)
    assert recibo.predecessor_event_ids == ()


def test_e342_receipt_accepts_none_clid_as_legitimate_result():
    """`target_clid=None` é resultado válido, não falha: fontes de
    continuidades distintas não produzem continuidade comum."""
    assert _recibo(target_clid=None).target_clid is None


# --- 2. Hashabilidade -------------------------------------------------


def test_e342_receipt_is_hashable():
    recibo = _recibo()
    assert isinstance(hash(recibo), int)
    assert len({recibo, recibo}) == 1


def test_e342_receipt_is_hashable_when_built_from_lists():
    """O caso que quebrava em E4.2.1/E4.3.2: coleção mutável guardada
    como está torna o objeto não-hashable."""
    fontes = _ids(2)
    recibo = MultiInputTransformationReceipt(
        source_coids=list(fontes),
        target_coid=uuid.uuid4(),
        target_clid=None,
        transformation_id=uuid.uuid4(),
        lineage_edge_ids=list(_ids(2)),
        causal_event_ids=list(_ids(1)),
    )
    assert isinstance(hash(recibo), int)


# --- 3. Igualdade estrutural -----------------------------------------


def test_e342_receipt_structural_equality():
    fontes, edges = _ids(2), _ids(2)
    alvo, transformacao, evento = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    comum = {
        "target_coid": alvo,
        "target_clid": None,
        "transformation_id": transformacao,
        "lineage_edge_ids": edges,
        "causal_event_ids": [evento],
    }
    a = MultiInputTransformationReceipt(source_coids=fontes, **comum)
    b = MultiInputTransformationReceipt(source_coids=list(fontes), **comum)
    assert a == b
    assert hash(a) == hash(b)


# --- 4 e 5. Cópia defensiva ------------------------------------------


def test_e342_receipt_converts_lists_to_tuples():
    recibo = _recibo(source_coids=_ids(2))
    assert isinstance(recibo.source_coids, tuple)
    assert isinstance(recibo.lineage_edge_ids, tuple)
    assert isinstance(recibo.causal_event_ids, tuple)
    assert isinstance(recibo.predecessor_event_ids, tuple)


def test_e342_mutating_the_original_list_does_not_change_the_receipt():
    """O defeito crítico das três correções anteriores: mutar a lista
    original alterava o objeto já construído."""
    fontes = _ids(2)
    recibo = MultiInputTransformationReceipt(
        source_coids=fontes,
        target_coid=uuid.uuid4(),
        target_clid=None,
        transformation_id=uuid.uuid4(),
        lineage_edge_ids=_ids(2),
        causal_event_ids=_ids(1),
    )
    antes = recibo.source_coids

    fontes.append(uuid.uuid4())

    assert recibo.source_coids == antes
    assert len(recibo.source_coids) == 2


# --- 6. Menos de duas fontes -----------------------------------------


@pytest.mark.parametrize("quantidade", [0, 1])
def test_e342_receipt_requires_at_least_two_sources(quantidade):
    fontes = _ids(quantidade)
    with pytest.raises(ValueError, match="ao menos duas fontes"):
        MultiInputTransformationReceipt(
            source_coids=fontes,
            target_coid=uuid.uuid4(),
            target_clid=None,
            transformation_id=uuid.uuid4(),
            lineage_edge_ids=_ids(quantidade),
            causal_event_ids=_ids(1),
        )


# --- 7. Fontes duplicadas --------------------------------------------


def test_e342_receipt_rejects_duplicate_sources_without_deduplicating():
    repetido = uuid.uuid4()
    with pytest.raises(ValueError, match="DUPLICATE SOURCE"):
        MultiInputTransformationReceipt(
            source_coids=[repetido, repetido],
            target_coid=uuid.uuid4(),
            target_clid=None,
            transformation_id=uuid.uuid4(),
            lineage_edge_ids=_ids(2),
            causal_event_ids=_ids(1),
        )


# --- 8. Tipos inválidos ----------------------------------------------


@pytest.mark.parametrize("valor", ["nao-e-uuid", 123, None, b"bytes"])
def test_e342_receipt_rejects_non_uuid_source_collections(valor):
    with pytest.raises(TypeError):
        _recibo(source_coids=valor)


def test_e342_receipt_rejects_non_uuid_items_inside_the_collection():
    with pytest.raises(TypeError, match="apenas uuid.UUID"):
        _recibo(source_coids=[uuid.uuid4(), "nao-e-uuid"])


@pytest.mark.parametrize("campo", ["target_coid", "transformation_id"])
def test_e342_receipt_rejects_non_uuid_scalar_fields(campo):
    with pytest.raises(TypeError, match=campo):
        _recibo(**{campo: "nao-e-uuid"})


def test_e342_receipt_rejects_non_uuid_clid():
    with pytest.raises(TypeError, match="target_clid"):
        _recibo(target_clid="nao-e-uuid")


def test_e342_receipt_rejects_string_as_collection():
    """`str` é iterável; aceitá-lo transformaria texto numa coleção de
    caracteres em vez de erro."""
    with pytest.raises(TypeError, match="coleção de uuid.UUID"):
        _recibo(lineage_edge_ids="abc")


# --- 9. Target igual a source ----------------------------------------


def test_e342_receipt_rejects_target_equal_to_a_source():
    fontes = _ids(2)
    with pytest.raises(ValueError, match="CognitiveObject novo"):
        MultiInputTransformationReceipt(
            source_coids=fontes,
            target_coid=fontes[0],
            target_clid=None,
            transformation_id=uuid.uuid4(),
            lineage_edge_ids=_ids(2),
            causal_event_ids=_ids(1),
        )


# --- 10. Quantidade de edges incoerente ------------------------------


@pytest.mark.parametrize("quantidade_edges", [1, 3])
def test_e342_receipt_requires_one_edge_per_source(quantidade_edges):
    with pytest.raises(ValueError, match="uma LineageEdge"):
        _recibo(source_coids=_ids(2), lineage_edge_ids=_ids(quantidade_edges))


def test_e342_receipt_rejects_repeated_edge_ids():
    repetido = uuid.uuid4()
    with pytest.raises(ValueError, match="lineage_edge_ids"):
        _recibo(source_coids=_ids(2), lineage_edge_ids=[repetido, repetido])


# --- 11. Causalidade-raiz incoerente ---------------------------------


def test_e342_receipt_requires_at_least_one_causal_event():
    with pytest.raises(ValueError, match="ao menos um evento causal"):
        _recibo(causal_event_ids=[])


def test_e342_receipt_root_case_requires_exactly_one_event():
    with pytest.raises(ValueError, match="exatamente um evento-raiz"):
        _recibo(causal_event_ids=_ids(2), predecessor_event_ids=())


# --- 12. Causalidade com predecessores incoerente --------------------


def test_e342_receipt_requires_one_event_per_declared_predecessor():
    with pytest.raises(ValueError, match="um evento por predecessor"):
        _recibo(causal_event_ids=_ids(1), predecessor_event_ids=_ids(2))


def test_e342_receipt_accepts_n_events_for_n_predecessors():
    predecessores, eventos = _ids(3), _ids(3)
    recibo = _recibo(causal_event_ids=eventos, predecessor_event_ids=predecessores)
    assert recibo.predecessor_event_ids == tuple(predecessores)
    assert recibo.causal_event_ids == tuple(eventos)


def test_e342_receipt_rejects_repeated_predecessors():
    repetido = uuid.uuid4()
    with pytest.raises(ValueError, match="predecessor_event_ids"):
        _recibo(causal_event_ids=_ids(2), predecessor_event_ids=[repetido, repetido])


def test_e342_receipt_rejects_repeated_causal_events():
    repetido = uuid.uuid4()
    with pytest.raises(ValueError, match="causal_event_ids"):
        _recibo(causal_event_ids=[repetido, repetido], predecessor_event_ids=_ids(2))


# --- 13. Construção direta não contorna invariantes ------------------


def test_e342_direct_construction_enforces_the_same_invariants_as_the_manager():
    """Não existe caminho público capaz de contornar a validação: o
    construtor direto passa exatamente pelas mesmas regras."""
    with pytest.raises(ValueError):
        MultiInputTransformationReceipt(
            source_coids=[uuid.uuid4()],
            target_coid=uuid.uuid4(),
            target_clid=None,
            transformation_id=uuid.uuid4(),
            lineage_edge_ids=[uuid.uuid4()],
            causal_event_ids=[uuid.uuid4()],
        )


def test_e342_dataclasses_replace_cannot_reintroduce_a_mutable_container():
    import dataclasses

    recibo = _recibo()
    substituido = dataclasses.replace(recibo, source_coids=list(_ids(2)))
    assert isinstance(substituido.source_coids, tuple)


def test_e342_receipt_is_frozen():
    import dataclasses

    recibo = _recibo()
    with pytest.raises(dataclasses.FrozenInstanceError):
        recibo.target_coid = uuid.uuid4()
