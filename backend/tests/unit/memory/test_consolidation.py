"""
Testes unitários da E4.5 — Consolidation Manager.

Cobrem as 46 exigências do §17 do prompt canônico. Usam dublês da porta
E3 e do `PersistenceManager`: aqui o objeto sob teste é a **disciplina**
da E4.5 — validação do pedido, encaminhamento sem invenção e
verificação de pós-condição.

A composição real com o `MultiInputTransformationManager` da E3.4.2 e o
banco vive em
`tests/integration/memory/test_consolidation_integration.py`, contra
PostgreSQL. Dublê não prova composição; banco não prova disciplina.
"""

import ast
import dataclasses
import pathlib
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime

import pytest

from app.memory.errors.exceptions import ConsolidationVerificationError
from app.memory.ports import MultiInputTransformationReceiptPort
from app.memory.schemas.consolidation import ConsolidationResult
from app.memory.schemas.persistence import (
    PersistenceAssessment,
    PersistenceEvidence,
    PersistenceEvidenceKind,
    PersistenceOutcome,
)
from app.memory.services.consolidation_manager import (
    CONSOLIDATION_OPERATION_TYPE,
    ConsolidationManager,
)

# --- Dublês -----------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ReciboFalso:
    """Dublê estrutural do recibo da E3 — mesma forma da porta."""

    source_coids: tuple[uuid.UUID, ...]
    target_coid: uuid.UUID
    target_clid: uuid.UUID | None
    transformation_id: uuid.UUID
    lineage_edge_ids: tuple[uuid.UUID, ...]
    causal_event_ids: tuple[uuid.UUID, ...]
    predecessor_event_ids: tuple[uuid.UUID, ...] = ()


class PortaFalsa:
    """Registra a chamada recebida e devolve um recibo coerente."""

    def __init__(self, recibo=None, erro: Exception | None = None) -> None:
        self.recibo = recibo
        self.erro = erro
        self.chamadas: list[dict] = []

    def derive_many(self, **kwargs):
        self.chamadas.append(kwargs)
        if self.erro is not None:
            raise self.erro
        if self.recibo is not None:
            return self.recibo
        fontes = tuple(kwargs["source_coids"])
        return ReciboFalso(
            source_coids=fontes,
            target_coid=uuid.uuid4(),
            target_clid=None,
            transformation_id=uuid.uuid4(),
            lineage_edge_ids=tuple(uuid.uuid4() for _ in fontes),
            causal_event_ids=tuple(uuid.uuid4() for _ in kwargs["predecessor_event_ids"])
            or (uuid.uuid4(),),
            predecessor_event_ids=tuple(kwargs["predecessor_event_ids"]),
        )


class PersistenceFalso:
    """Devolve um assessment coerente com o recibo, salvo instrução em
    contrário."""

    def __init__(self, assessment=None, erro: Exception | None = None) -> None:
        self.assessment = assessment
        self.erro = erro
        self.chamadas: list[uuid.UUID] = []
        self.recibo_para_coerencia = None

    def assess(self, coid: uuid.UUID) -> PersistenceAssessment:
        self.chamadas.append(coid)
        if self.erro is not None:
            raise self.erro
        if self.assessment is not None:
            return self.assessment
        return _assessment_coerente(self.recibo_para_coerencia)


def _assessment_coerente(recibo) -> PersistenceAssessment:
    """Assessment que reflete exatamente o que o recibo afirma."""
    evidencias = [
        PersistenceEvidence(
            kind=PersistenceEvidenceKind.LINEAGE_PARENT,
            reference=str(edge),
            related_coid=fonte,
            qualifier="merge",
        )
        for fonte, edge in zip(recibo.source_coids, recibo.lineage_edge_ids, strict=True)
    ]
    evidencias.append(
        PersistenceEvidence(
            kind=PersistenceEvidenceKind.TRANSFORMATION_OUTPUT,
            reference=str(recibo.transformation_id),
        )
    )
    evidencias.extend(
        PersistenceEvidence(
            kind=PersistenceEvidenceKind.CAUSAL_EVENT,
            reference=str(evento),
            qualifier="TRANSFORMED",
        )
        for evento in recibo.causal_event_ids
    )
    if recibo.target_clid is not None:
        evidencias.append(
            PersistenceEvidence(
                kind=PersistenceEvidenceKind.CLID, reference=str(recibo.target_clid)
            )
        )
    return PersistenceAssessment(
        coid=recibo.target_coid,
        outcome=PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE,
        evidence=tuple(evidencias),
        clid=recibo.target_clid,
        subject_deleted=False,
    )


def _fontes(quantidade: int) -> list[uuid.UUID]:
    """Fontes em ordem canônica — o resultado a recusa fora de ordem."""
    return sorted(uuid.uuid4() for _ in range(quantidade))


def _recibo(**overrides) -> ReciboFalso:
    fontes = overrides.pop("source_coids", None) or _fontes(2)
    campos = {
        "source_coids": tuple(fontes),
        "target_coid": uuid.uuid4(),
        "target_clid": None,
        "transformation_id": uuid.uuid4(),
        "lineage_edge_ids": tuple(uuid.uuid4() for _ in fontes),
        "causal_event_ids": (uuid.uuid4(),),
        "predecessor_event_ids": (),
    }
    campos.update(overrides)
    return ReciboFalso(**campos)


def _resultado(**overrides) -> ConsolidationResult:
    recibo = _recibo()
    campos = {
        "source_coids": recibo.source_coids,
        "target_coid": recibo.target_coid,
        "target_clid": recibo.target_clid,
        "transformation_id": recibo.transformation_id,
        "lineage_edge_ids": recibo.lineage_edge_ids,
        "causal_event_ids": recibo.causal_event_ids,
        "predecessor_event_ids": recibo.predecessor_event_ids,
        "persistence_assessment": _assessment_coerente(recibo),
    }
    campos.update(overrides)
    return ConsolidationResult(**campos)


def _manager(porta=None, persistencia=None):
    porta = porta or PortaFalsa()
    persistencia = persistencia or PersistenceFalso()

    original = porta.derive_many

    def _capturando(**kwargs):
        recibo = original(**kwargs)
        persistencia.recibo_para_coerencia = recibo
        return recibo

    porta.derive_many = _capturando  # type: ignore[method-assign]
    return ConsolidationManager(porta, persistencia), porta, persistencia


# ======================================================================
# VALUE OBJECT (§17.1 — exigências 1 a 22)
# ======================================================================


def test_cs1_valid_construction():
    resultado = _resultado()
    assert resultado.source_count == 2
    assert resultado.persistence_assessment.coid == resultado.target_coid


def test_cs2_structural_equality():
    recibo = _recibo()
    avaliacao = _assessment_coerente(recibo)
    comum = {
        "target_coid": recibo.target_coid,
        "target_clid": None,
        "transformation_id": recibo.transformation_id,
        "lineage_edge_ids": recibo.lineage_edge_ids,
        "causal_event_ids": recibo.causal_event_ids,
        "persistence_assessment": avaliacao,
    }
    a = ConsolidationResult(source_coids=recibo.source_coids, **comum)
    b = ConsolidationResult(source_coids=list(recibo.source_coids), **comum)
    assert a == b


def test_cs3_hashable():
    resultado = _resultado()
    assert isinstance(hash(resultado), int)
    assert len({resultado, resultado}) == 1


def test_cs4_is_really_frozen():
    resultado = _resultado()
    with pytest.raises(dataclasses.FrozenInstanceError):
        resultado.target_coid = uuid.uuid4()


def test_cs5_lists_become_tuples():
    recibo = _recibo()
    resultado = ConsolidationResult(
        source_coids=list(recibo.source_coids),
        target_coid=recibo.target_coid,
        target_clid=None,
        transformation_id=recibo.transformation_id,
        lineage_edge_ids=list(recibo.lineage_edge_ids),
        causal_event_ids=list(recibo.causal_event_ids),
        persistence_assessment=_assessment_coerente(recibo),
    )
    assert isinstance(resultado.source_coids, tuple)
    assert isinstance(resultado.lineage_edge_ids, tuple)
    assert isinstance(resultado.causal_event_ids, tuple)
    assert isinstance(hash(resultado), int)


def test_cs6_mutating_the_original_list_does_not_change_the_result():
    """O defeito de E4.2.1/E4.3.2/E4.4.1: `frozen` protege a referência,
    não o conteúdo."""
    recibo = _recibo()
    fontes = list(recibo.source_coids)
    resultado = ConsolidationResult(
        source_coids=fontes,
        target_coid=recibo.target_coid,
        target_clid=None,
        transformation_id=recibo.transformation_id,
        lineage_edge_ids=recibo.lineage_edge_ids,
        causal_event_ids=recibo.causal_event_ids,
        persistence_assessment=_assessment_coerente(recibo),
    )
    antes = resultado.source_coids
    fontes.append(uuid.uuid4())
    assert resultado.source_coids == antes


def test_cs7_dataclasses_replace_cannot_bypass_invariants():
    resultado = _resultado()
    with pytest.raises(ValueError, match="ao menos duas fontes"):
        dataclasses.replace(resultado, source_coids=resultado.source_coids[:1])


@pytest.mark.parametrize("invalido", ["nao-e-uuid", 123, None])
def test_cs8_invalid_types_are_rejected(invalido):
    with pytest.raises(TypeError):
        _resultado(source_coids=invalido)


def test_cs8b_invalid_scalar_type_is_rejected():
    with pytest.raises(TypeError, match="transformation_id"):
        _resultado(transformation_id="nao-e-uuid")


@pytest.mark.parametrize("quantidade", [0, 1])
def test_cs9_fewer_than_two_sources(quantidade):
    fontes = _fontes(quantidade)
    with pytest.raises(ValueError, match="ao menos duas fontes"):
        _resultado(source_coids=tuple(fontes), lineage_edge_ids=tuple(uuid.uuid4() for _ in fontes))


def test_cs10_duplicate_sources():
    repetido = uuid.uuid4()
    with pytest.raises(ValueError, match="DUPLICATE SOURCE"):
        _resultado(source_coids=(repetido, repetido))


def test_cs11_non_canonical_source_order():
    menor, maior = _fontes(2)
    with pytest.raises(ValueError, match="ordem canônica estrita"):
        _resultado(source_coids=(maior, menor))


def test_cs12_target_equal_to_a_source():
    fontes = _fontes(2)
    with pytest.raises(ValueError, match="CognitiveObject novo"):
        _resultado(source_coids=tuple(fontes), target_coid=fontes[0])


@pytest.mark.parametrize("quantidade_edges", [1, 3])
def test_cs13_wrong_edge_cardinality(quantidade_edges):
    with pytest.raises(ValueError, match="uma LineageEdge"):
        _resultado(lineage_edge_ids=tuple(uuid.uuid4() for _ in range(quantidade_edges)))


def test_cs14_repeated_edge():
    repetido = uuid.uuid4()
    with pytest.raises(ValueError, match="lineage_edge_ids"):
        _resultado(lineage_edge_ids=(repetido, repetido))


def test_cs15_empty_causal_events():
    with pytest.raises(ValueError, match="ao menos um evento causal"):
        _resultado(causal_event_ids=())


def test_cs16_repeated_causal_events():
    repetido = uuid.uuid4()
    with pytest.raises(ValueError, match="causal_event_ids"):
        _resultado(causal_event_ids=(repetido, repetido), predecessor_event_ids=_fontes(2))


def test_cs17_repeated_predecessors():
    repetido = uuid.uuid4()
    with pytest.raises(ValueError, match="predecessor_event_ids"):
        _resultado(
            causal_event_ids=(uuid.uuid4(), uuid.uuid4()),
            predecessor_event_ids=(repetido, repetido),
        )


def test_cs18a_root_case_requires_exactly_one_event():
    with pytest.raises(ValueError, match="exatamente um evento-raiz"):
        _resultado(causal_event_ids=(uuid.uuid4(), uuid.uuid4()), predecessor_event_ids=())


def test_cs18b_one_event_per_predecessor():
    with pytest.raises(ValueError, match="um evento por predecessor"):
        _resultado(causal_event_ids=(uuid.uuid4(),), predecessor_event_ids=_fontes(2))


def test_cs19_assessment_of_another_target():
    recibo = _recibo()
    outro = _recibo()
    with pytest.raises(ValueError, match="não sobre o alvo"):
        ConsolidationResult(
            source_coids=recibo.source_coids,
            target_coid=recibo.target_coid,
            target_clid=None,
            transformation_id=recibo.transformation_id,
            lineage_edge_ids=recibo.lineage_edge_ids,
            causal_event_ids=recibo.causal_event_ids,
            persistence_assessment=_assessment_coerente(outro),
        )


def test_cs20_subject_not_found_is_rejected():
    recibo = _recibo()
    with pytest.raises(ValueError, match="SUBJECT_NOT_FOUND"):
        _resultado(
            source_coids=recibo.source_coids,
            target_coid=recibo.target_coid,
            lineage_edge_ids=recibo.lineage_edge_ids,
            causal_event_ids=recibo.causal_event_ids,
            transformation_id=recibo.transformation_id,
            persistence_assessment=PersistenceAssessment(
                coid=recibo.target_coid, outcome=PersistenceOutcome.SUBJECT_NOT_FOUND
            ),
        )


def test_cs21_no_recorded_evidence_is_rejected():
    recibo = _recibo()
    with pytest.raises(ValueError, match="RECORDED_CONTINUITY_EVIDENCE"):
        _resultado(
            source_coids=recibo.source_coids,
            target_coid=recibo.target_coid,
            lineage_edge_ids=recibo.lineage_edge_ids,
            causal_event_ids=recibo.causal_event_ids,
            transformation_id=recibo.transformation_id,
            persistence_assessment=PersistenceAssessment(
                coid=recibo.target_coid,
                outcome=PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE,
            ),
        )


def test_cs22_soft_deleted_target_is_rejected():
    recibo = _recibo()
    base = _assessment_coerente(recibo)
    with pytest.raises(ValueError, match="soft-deleted"):
        _resultado(
            source_coids=recibo.source_coids,
            target_coid=recibo.target_coid,
            lineage_edge_ids=recibo.lineage_edge_ids,
            causal_event_ids=recibo.causal_event_ids,
            transformation_id=recibo.transformation_id,
            persistence_assessment=dataclasses.replace(base, subject_deleted=True),
        )


def test_cs22b_assessment_must_be_a_persistence_assessment():
    with pytest.raises(TypeError, match="PersistenceAssessment"):
        _resultado(persistence_assessment="nao-e-assessment")


def test_cs22c_lineage_edge_for_maps_source_to_its_edge():
    resultado = _resultado()
    for posicao, fonte in enumerate(resultado.source_coids):
        assert resultado.lineage_edge_for(fonte) == resultado.lineage_edge_ids[posicao]
    with pytest.raises(ValueError, match="não é uma das fontes"):
        resultado.lineage_edge_for(uuid.uuid4())


# ======================================================================
# MANAGER (§17.2 — exigências 23 a 46)
# ======================================================================


def test_cs23_generators_are_materialized_exactly_once():
    """Um generator consumido duas vezes entregaria vazio na segunda."""
    manager, porta, _ = _manager()
    fontes = _fontes(3)
    manager.consolidate(
        source_coids=(f for f in fontes),
        declared_losses=(p for p in ["perda"]),
        declared_preservations=(p for p in ["tese"]),
    )
    chamada = porta.chamadas[0]
    assert tuple(chamada["source_coids"]) == tuple(sorted(fontes))
    assert list(chamada["declared_losses"]) == ["perda"]
    assert list(chamada["declared_preservations"]) == ["tese"]


def test_cs24_sources_are_canonicalized():
    """`SOURCE ORDER != SOURCE RANKING`."""
    manager, porta, _ = _manager()
    fontes = _fontes(3)
    manager.consolidate(source_coids=[fontes[2], fontes[0], fontes[1]], declared_losses=["x"])
    assert tuple(porta.chamadas[0]["source_coids"]) == tuple(sorted(fontes))


def test_cs24b_fewer_than_two_sources_is_rejected_before_the_port():
    manager, porta, _ = _manager()
    with pytest.raises(ValueError, match="ao menos duas fontes"):
        manager.consolidate(source_coids=_fontes(1), declared_losses=["x"])
    assert porta.chamadas == []


def test_cs24c_duplicate_source_is_rejected_not_deduplicated():
    manager, porta, _ = _manager()
    repetido = uuid.uuid4()
    with pytest.raises(ValueError, match="duplicados"):
        manager.consolidate(source_coids=[repetido, repetido], declared_losses=["x"])
    assert porta.chamadas == []


@pytest.mark.parametrize("invalido", ["abc", 123, uuid.uuid4()])
def test_cs24d_invalid_source_collection_is_rejected(invalido):
    manager, porta, _ = _manager()
    with pytest.raises(TypeError):
        manager.consolidate(source_coids=invalido, declared_losses=["x"])
    assert porta.chamadas == []


def test_cs25_declared_losses_are_mandatory():
    """`MISSING LOSS DECLARATION != LOSSLESS EQUIVALENCE`."""
    manager, porta, _ = _manager()
    with pytest.raises(ValueError, match="MANDATORY"):
        manager.consolidate(source_coids=_fontes(2), declared_losses=[])
    assert porta.chamadas == []


@pytest.mark.parametrize("perda", ["", "   ", "\t\n"])
def test_cs26_blank_loss_is_rejected(perda):
    manager, porta, _ = _manager()
    with pytest.raises(ValueError, match="declaração vazia"):
        manager.consolidate(source_coids=_fontes(2), declared_losses=[perda])
    assert porta.chamadas == []


@pytest.mark.parametrize("invalido", ["perdeu contexto", 123, None, [1]])
def test_cs27_invalid_loss_type_is_rejected(invalido):
    manager, porta, _ = _manager()
    with pytest.raises(TypeError):
        manager.consolidate(source_coids=_fontes(2), declared_losses=invalido)
    assert porta.chamadas == []


def test_cs28_blank_preservation_is_rejected():
    manager, porta, _ = _manager()
    with pytest.raises(ValueError, match="declaração vazia"):
        manager.consolidate(
            source_coids=_fontes(2), declared_losses=["x"], declared_preservations=["  "]
        )
    assert porta.chamadas == []


def test_cs28b_empty_preservations_are_allowed():
    manager, porta, _ = _manager()
    manager.consolidate(source_coids=_fontes(2), declared_losses=["x"])
    assert list(porta.chamadas[0]["declared_preservations"]) == []


def test_cs29_operation_type_is_fixed_as_consolidate():
    """O chamador não escolhe o nome da operação: quem invoca a E4.5
    solicitou uma consolidação."""
    manager, porta, _ = _manager()
    manager.consolidate(source_coids=_fontes(2), declared_losses=["x"])
    assert porta.chamadas[0]["operation_type"] == "consolidate"
    assert CONSOLIDATION_OPERATION_TYPE == "consolidate"


def test_cs29b_consolidate_signature_has_no_operation_type():
    import inspect

    parametros = inspect.signature(ConsolidationManager.consolidate).parameters
    assert "operation_type" not in parametros


def test_cs30_declarations_are_forwarded_without_normalization():
    """`strip()` é predicado de branco, nunca normalizador."""
    manager, porta, _ = _manager()
    perdas = ["  nuance do ramo A  ", "exemplos"]
    preservacoes = ["  tese central  "]
    manager.consolidate(
        source_coids=_fontes(2),
        declared_losses=perdas,
        declared_preservations=preservacoes,
    )
    assert list(porta.chamadas[0]["declared_losses"]) == perdas
    assert list(porta.chamadas[0]["declared_preservations"]) == preservacoes


def test_cs31_actor_ref_is_forwarded():
    manager, porta, _ = _manager()
    ator = uuid.uuid4()
    manager.consolidate(source_coids=_fontes(2), declared_losses=["x"], actor_ref=ator)
    assert porta.chamadas[0]["actor_ref"] == ator


def test_cs31b_absent_actor_ref_stays_none():
    manager, porta, _ = _manager()
    manager.consolidate(source_coids=_fontes(2), declared_losses=["x"])
    assert porta.chamadas[0]["actor_ref"] is None


def test_cs32_policy_ref_is_forwarded_without_being_authorization():
    """`policy_ref` é referência declarada, não autorização verificada."""
    manager, porta, _ = _manager()
    manager.consolidate(source_coids=_fontes(2), declared_losses=["x"], policy_ref="policy://x")
    assert porta.chamadas[0]["policy_ref"] == "policy://x"


def test_cs33_occurred_at_none_stays_none():
    manager, porta, _ = _manager()
    manager.consolidate(source_coids=_fontes(2), declared_losses=["x"])
    assert porta.chamadas[0]["occurred_at"] is None


def test_cs33b_occurred_at_is_forwarded_when_given():
    manager, porta, _ = _manager()
    quando = datetime(2024, 3, 1, 12, 0, tzinfo=UTC)
    manager.consolidate(source_coids=_fontes(2), declared_losses=["x"], occurred_at=quando)
    assert porta.chamadas[0]["occurred_at"] == quando


def test_cs34_predecessors_are_forwarded():
    manager, porta, _ = _manager()
    predecessores = _fontes(2)
    manager.consolidate(
        source_coids=_fontes(2),
        declared_losses=["x"],
        predecessor_event_ids=predecessores,
    )
    assert tuple(porta.chamadas[0]["predecessor_event_ids"]) == tuple(predecessores)


def test_cs34b_duplicate_predecessor_is_rejected():
    manager, porta, _ = _manager()
    repetido = uuid.uuid4()
    with pytest.raises(ValueError, match="repetições"):
        manager.consolidate(
            source_coids=_fontes(2),
            declared_losses=["x"],
            predecessor_event_ids=[repetido, repetido],
        )
    assert porta.chamadas == []


@pytest.mark.parametrize("invalido", ["abc", 123, uuid.uuid4()])
def test_cs34c_invalid_predecessor_collection_is_rejected(invalido):
    manager, porta, _ = _manager()
    with pytest.raises(TypeError, match="predecessor_event_ids"):
        manager.consolidate(
            source_coids=_fontes(2), declared_losses=["x"], predecessor_event_ids=invalido
        )
    assert porta.chamadas == []


def test_cs35_valid_receipt_is_accepted():
    manager, _, persistencia = _manager()
    resultado = manager.consolidate(source_coids=_fontes(2), declared_losses=["x"])
    assert isinstance(resultado, ConsolidationResult)
    assert persistencia.chamadas == [resultado.target_coid]


def test_cs36_malformed_receipt_is_rejected():
    """Recibo cuja linhagem não corresponde às fontes não vira resultado."""
    recibo = _recibo()
    quebrado = dataclasses.replace(recibo, lineage_edge_ids=(uuid.uuid4(), uuid.uuid4()))
    porta = PortaFalsa(recibo=quebrado)
    persistencia = PersistenceFalso(assessment=_assessment_coerente(recibo))
    manager = ConsolidationManager(porta, persistencia)

    with pytest.raises(ConsolidationVerificationError) as exc:
        manager.consolidate(source_coids=list(recibo.source_coids), declared_losses=["x"])
    assert exc.value.code == "PIA-8032"


def test_cs37_port_error_is_propagated():
    """Nada é absorvido: o erro sobe e o rollback é do chamador."""
    porta = PortaFalsa(erro=RuntimeError("falha na escrita"))
    manager = ConsolidationManager(porta, PersistenceFalso())
    with pytest.raises(RuntimeError, match="falha na escrita"):
        manager.consolidate(source_coids=_fontes(2), declared_losses=["x"])


def test_cs38_persistence_manager_error_is_propagated():
    porta = PortaFalsa()
    persistencia = PersistenceFalso(erro=RuntimeError("falha na avaliação"))
    manager = ConsolidationManager(porta, persistencia)
    with pytest.raises(RuntimeError, match="falha na avaliação"):
        manager.consolidate(source_coids=_fontes(2), declared_losses=["x"])


def _divergente(recibo, caso: str) -> PersistenceAssessment:
    """Assessment **internamente válido** que diverge do recibo.

    `dataclasses.replace` não serve aqui: os invariantes da E4.4.1
    recusam combinações incoerentes (por exemplo `clid` declarado sem
    evidência CLID). Cada divergência precisa ser montada como um
    assessment que o próprio E4.4 aceitaria — é justamente esse o caso
    interessante, porque um assessment obviamente quebrado nem chegaria
    à E4.5.
    """
    if caso == "outcome":
        return PersistenceAssessment(
            coid=recibo.target_coid,
            outcome=PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE,
        )
    if caso == "subject_deleted":
        return dataclasses.replace(_assessment_coerente(recibo), subject_deleted=True)
    if caso == "clid":
        outro_clid = uuid.uuid4()
        base = _assessment_coerente(recibo)
        return dataclasses.replace(
            base,
            clid=outro_clid,
            evidence=(
                *base.evidence,
                PersistenceEvidence(kind=PersistenceEvidenceKind.CLID, reference=str(outro_clid)),
            ),
        )
    raise AssertionError(caso)


@pytest.mark.parametrize("caso", ["outcome", "subject_deleted", "clid"])
def test_cs39_incompatible_assessment_raises_verification_error(caso):
    recibo = _recibo()
    porta = PortaFalsa(recibo=recibo)
    persistencia = PersistenceFalso(assessment=_divergente(recibo, caso))
    manager = ConsolidationManager(porta, persistencia)

    with pytest.raises(ConsolidationVerificationError) as exc:
        manager.consolidate(source_coids=list(recibo.source_coids), declared_losses=["x"])
    assert exc.value.code == "PIA-8032"
    assert exc.value.target_coid == recibo.target_coid
    assert exc.value.reasons


def test_cs39b_verification_error_reports_every_reason_at_once():
    """Uma divergência raramente vem sozinha; reportar só a primeira
    obrigaria a auditoria a descobrir as demais uma execução por vez."""
    recibo = _recibo()
    porta = PortaFalsa(recibo=recibo)
    persistencia = PersistenceFalso(
        assessment=PersistenceAssessment(
            coid=recibo.target_coid,
            outcome=PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE,
            evidence=(),
            clid=None,
            subject_deleted=False,
        )
    )
    manager = ConsolidationManager(porta, persistencia)
    with pytest.raises(ConsolidationVerificationError) as exc:
        manager.consolidate(source_coids=list(recibo.source_coids), declared_losses=["x"])
    assert len(exc.value.reasons) > 1


def test_cs39c_positional_mismatch_is_detected():
    """Conjuntos iguais com pareamento trocado ainda são divergência."""
    recibo = _recibo()
    porta = PortaFalsa(recibo=recibo)
    trocado = [
        PersistenceEvidence(
            kind=PersistenceEvidenceKind.LINEAGE_PARENT,
            reference=str(recibo.lineage_edge_ids[0]),
            related_coid=recibo.source_coids[1],
            qualifier="merge",
        ),
        PersistenceEvidence(
            kind=PersistenceEvidenceKind.LINEAGE_PARENT,
            reference=str(recibo.lineage_edge_ids[1]),
            related_coid=recibo.source_coids[0],
            qualifier="merge",
        ),
        PersistenceEvidence(
            kind=PersistenceEvidenceKind.TRANSFORMATION_OUTPUT,
            reference=str(recibo.transformation_id),
        ),
        PersistenceEvidence(
            kind=PersistenceEvidenceKind.CAUSAL_EVENT,
            reference=str(recibo.causal_event_ids[0]),
            qualifier="TRANSFORMED",
        ),
    ]
    persistencia = PersistenceFalso(
        assessment=PersistenceAssessment(
            coid=recibo.target_coid,
            outcome=PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE,
            evidence=tuple(trocado),
        )
    )
    manager = ConsolidationManager(porta, persistencia)
    with pytest.raises(ConsolidationVerificationError) as exc:
        manager.consolidate(source_coids=list(recibo.source_coids), declared_losses=["x"])
    assert any("deveria apontar" in motivo for motivo in exc.value.reasons)


def test_cs40_assessment_is_never_used_to_rank_sources():
    """O assessment avalia o ALVO, nunca as fontes."""
    manager, _, persistencia = _manager()
    fontes = _fontes(3)
    resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
    assert persistencia.chamadas == [resultado.target_coid]
    for fonte in fontes:
        assert fonte not in persistencia.chamadas


def test_cs41_sources_without_prior_evidence_are_not_refused():
    """`NO_RECORDED_CONTINUITY_EVIDENCE` numa fonte é fato legítimo
    sobre objeto novo — nunca invalidez, nunca critério de admissão."""
    manager, porta, _ = _manager()
    resultado = manager.consolidate(source_coids=_fontes(2), declared_losses=["x"])
    assert isinstance(resultado, ConsolidationResult)
    assert len(porta.chamadas) == 1


def test_cs42_no_governance_search_or_retrieval_dependency():
    import inspect

    parametros = set(inspect.signature(ConsolidationManager.__init__).parameters)
    assert parametros == {"self", "transformation_port", "persistence_manager"}

    assinatura = set(inspect.signature(ConsolidationManager.consolidate).parameters)
    for proibido in ("context", "memory_context", "governance", "policy", "resolution", "domain"):
        assert proibido not in assinatura


def test_cs43_no_internal_commit_and_no_session():
    executavel = _codigo_executavel()
    for proibido in ("commit(", "rollback(", "Session", "UnitOfWork", "sessionmaker"):
        assert proibido not in executavel, f"encontrado: {proibido}"


def test_cs44_no_app_cognitive_import_in_memory_production_code():
    """A fronteira estrutural que a porta existe para preservar."""
    padrao = re.compile(r"^\s*(from|import)\s+app\.cognitive", re.MULTILINE)
    raiz = pathlib.Path(__file__).resolve().parents[3] / "app" / "memory"
    ofensores = [
        str(caminho)
        for caminho in raiz.rglob("*.py")
        if padrao.search(caminho.read_text(encoding="utf-8"))
    ]
    assert ofensores == []


def test_cs45_no_direct_sql_writing():
    executavel = _codigo_executavel()
    for proibido in ("INSERT", "UPDATE", "DELETE", "text(", "execute(", "table(", "column("):
        assert proibido not in executavel, f"encontrado: {proibido}"


def test_cs46_no_score_rank_provider_or_embedding():
    executavel = _codigo_executavel()
    for proibido in (
        "_score",
        "rank",
        "winner",
        "best_source",
        "similarity",
        "embedding",
        "provider",
        "vector",
        "transcript",
        "summar",
        "REVISION",
    ):
        assert proibido not in executavel, f"capacidade proibida encontrada: {proibido}"


def _codigo_executavel() -> str:
    """Fonte da E4.5 sem docstrings.

    Testar ausência é o único modo honesto de provar uma fronteira — um
    teste de comportamento passaria igual se a capacidade proibida
    existisse mas não fosse chamada. As docstrings citam nominalmente o
    que o módulo não faz, então a comparação usa o **código
    executável**, técnica de E4.3.1.
    """
    import app.memory.schemas.consolidation as schema_mod
    import app.memory.services.consolidation_manager as manager_mod

    partes = []
    for modulo in (manager_mod, schema_mod):
        arvore = ast.parse(pathlib.Path(modulo.__file__).read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                corpo = no.body
                if (
                    corpo
                    and isinstance(corpo[0], ast.Expr)
                    and isinstance(corpo[0].value, ast.Constant)
                    and isinstance(corpo[0].value.value, str)
                ):
                    no.body = corpo[1:] or [ast.Pass()]
        partes.append(ast.unparse(arvore))
    return "\n".join(partes)


def test_cs46b_the_real_e3_receipt_satisfies_the_port():
    """Conformidade estrutural verificada, não presumida.

    Importa `app.cognitive` **no teste** — permitido pelo §5, que veda o
    import apenas no código de produção de `app/memory`.
    """
    from app.cognitive.schemas.multi_input_transformation import (
        MultiInputTransformationReceipt,
    )

    fontes = tuple(_fontes(2))
    recibo = MultiInputTransformationReceipt(
        source_coids=fontes,
        target_coid=uuid.uuid4(),
        target_clid=None,
        transformation_id=uuid.uuid4(),
        lineage_edge_ids=tuple(uuid.uuid4() for _ in fontes),
        causal_event_ids=(uuid.uuid4(),),
    )
    assert isinstance(recibo, MultiInputTransformationReceiptPort)


@pytest.mark.parametrize(
    "primeiro_import",
    [
        "app.memory.ports",
        "app.memory.ports.consolidation",
        "app.memory.schemas.consolidation",
        "app.memory.services.consolidation_manager",
    ],
)
def test_cs46c_public_imports_work_in_any_order_in_a_clean_interpreter(primeiro_import):
    """Guarda contra ciclo de import — o sétimo defeito da E4.3.1, que
    só apareceu porque a suíte sempre importava outro módulo antes."""
    resultado = subprocess.run(
        [sys.executable, "-c", f"import {primeiro_import}; print('ok')"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "ok" in resultado.stdout


# ======================================================================
# Ramos descobertos pela exigência de 100%
# ======================================================================


def test_cs47_non_uuid_item_inside_source_collection_is_rejected_by_the_result():
    with pytest.raises(TypeError, match="apenas uuid.UUID"):
        _resultado(source_coids=(uuid.uuid4(), "nao-e-uuid"))


def test_cs48_non_uuid_item_inside_source_collection_is_rejected_by_the_manager():
    manager, porta, _ = _manager()
    with pytest.raises(TypeError, match="apenas uuid.UUID"):
        manager.consolidate(source_coids=[uuid.uuid4(), "nao-e-uuid"], declared_losses=["x"])
    assert porta.chamadas == []


def test_cs49_non_uuid_item_inside_predecessor_collection_is_rejected():
    manager, porta, _ = _manager()
    with pytest.raises(TypeError, match="predecessor_event_ids aceita apenas"):
        manager.consolidate(
            source_coids=_fontes(2),
            declared_losses=["x"],
            predecessor_event_ids=[uuid.uuid4(), "nao-e-uuid"],
        )
    assert porta.chamadas == []


def test_cs50_evidence_of_reads_through_to_the_assessment():
    resultado = _resultado()
    linhagem = resultado.evidence_of(PersistenceEvidenceKind.LINEAGE_PARENT)
    assert len(linhagem) == resultado.source_count
    assert resultado.evidence_of(PersistenceEvidenceKind.LINEAGE_CHILD) == ()


def test_cs51_manager_detects_an_assessment_about_another_coid():
    """Caminho do manager, distinto do invariante do value object: aqui
    a divergência precisa virar `PIA-8032`, não `ValueError`."""
    recibo = _recibo()
    outro = _recibo()
    porta = PortaFalsa(recibo=recibo)
    persistencia = PersistenceFalso(assessment=_assessment_coerente(outro))
    manager = ConsolidationManager(porta, persistencia)

    with pytest.raises(ConsolidationVerificationError) as exc:
        manager.consolidate(source_coids=list(recibo.source_coids), declared_losses=["x"])
    assert any("não sobre o alvo" in motivo for motivo in exc.value.reasons)


def test_cs52_manager_detects_a_wrong_transformation_reference():
    recibo = _recibo()
    porta = PortaFalsa(recibo=recibo)
    base = _assessment_coerente(recibo)
    trocada = tuple(
        (
            PersistenceEvidence(
                kind=PersistenceEvidenceKind.TRANSFORMATION_OUTPUT, reference=str(uuid.uuid4())
            )
            if e.kind is PersistenceEvidenceKind.TRANSFORMATION_OUTPUT
            else e
        )
        for e in base.evidence
    )
    persistencia = PersistenceFalso(assessment=dataclasses.replace(base, evidence=trocada))
    manager = ConsolidationManager(porta, persistencia)

    with pytest.raises(ConsolidationVerificationError) as exc:
        manager.consolidate(source_coids=list(recibo.source_coids), declared_losses=["x"])
    assert any("difere da do recibo" in motivo for motivo in exc.value.reasons)
