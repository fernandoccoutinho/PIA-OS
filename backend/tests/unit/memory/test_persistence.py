"""
E4.4 — testes unitários de persistência.

Cobrem os invariantes dos value objects e as fronteiras verificáveis
sem banco. Os requisitos que exigem PostgreSQL real (evidências reais,
zero escritas, censo canônico, independência de contexto) vivem em
`tests/integration/memory/`.
"""

import ast
import dataclasses
import inspect
import pathlib
import re
import uuid

import pytest

from app.memory.schemas.persistence import (
    PersistenceAssessment,
    PersistenceEvidence,
    PersistenceEvidenceKind,
    PersistenceOutcome,
)
from app.memory.services.persistence_manager import PersistenceManager

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _evidencia(**kw) -> PersistenceEvidence:
    base = {"kind": PersistenceEvidenceKind.CLID, "reference": str(uuid.uuid4())}
    base.update(kw)
    return PersistenceEvidence(**base)


def _executable_source(alvo) -> str:
    """Fonte sem docstrings — as docstrings deste módulo citam
    nominalmente o que ele não faz, e uma varredura ingênua no texto
    acusaria as frases que negam o uso (lição de E4.3.1)."""
    arvore = ast.parse(inspect.getsource(alvo))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant):
            no.value = ast.Constant(value="")
    return ast.unparse(arvore)


# ======================================================================
# Vocabulários e distinções
# ======================================================================


def test_pv1_three_outcomes_never_collapse():
    """Requisito 1: COID inexistente é distinto de objeto sem evidência.

    ```
    MISSING EVIDENCE != EVIDENCE OF NON-PERSISTENCE
    OBJECT EXISTS    != CONTINUITY IS RECORDED
    ```
    """
    assert {o.value for o in PersistenceOutcome} == {
        "subject_not_found",
        "no_recorded_continuity_evidence",
        "recorded_continuity_evidence",
    }
    assert (
        PersistenceOutcome.SUBJECT_NOT_FOUND
        is not PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE
    )


def test_pv2_evidence_kinds_preserve_direction():
    """Requisitos 4 e 6: parent/child e input/output são distintos.

    Colapsar direção perderia o que torna uma linhagem uma linhagem.
    """
    assert {k.value for k in PersistenceEvidenceKind} == {
        "clid",
        "lineage_parent",
        "lineage_child",
        "transformation_input",
        "transformation_output",
        "causal_event",
    }
    assert PersistenceEvidenceKind.LINEAGE_PARENT is not PersistenceEvidenceKind.LINEAGE_CHILD
    assert (
        PersistenceEvidenceKind.TRANSFORMATION_INPUT
        is not PersistenceEvidenceKind.TRANSFORMATION_OUTPUT
    )


# ======================================================================
# Invariantes dos value objects (requisitos 9–12)
# ======================================================================


def test_pv3_evidence_is_ordered_deterministically():
    """Requisito 9: ordem canônica reproduzível.

    Pré-requisito de qualquer auditoria que compare dois assessments.
    """
    coid = uuid.uuid4()
    a = _evidencia(kind=PersistenceEvidenceKind.CAUSAL_EVENT, reference="b")
    b = _evidencia(kind=PersistenceEvidenceKind.CLID, reference="a")
    c = _evidencia(kind=PersistenceEvidenceKind.CLID, reference="z")

    primeira = PersistenceAssessment(
        coid=coid,
        outcome=PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE,
        evidence=(a, b, c),
    )
    segunda = PersistenceAssessment(
        coid=coid,
        outcome=PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE,
        evidence=(c, a, b),
    )

    assert primeira.evidence == segunda.evidence
    assert primeira == segunda
    # A ordem canônica é por (kind, reference): "causal_event" precede
    # "clid" alfabeticamente. O que importa aqui é ser reproduzível, e
    # não uma ordem de mérito — nenhum tipo de evidência vale mais.
    assert [e.reference for e in primeira.evidence] == ["b", "a", "z"]


def test_pv4_duplicates_do_not_produce_unstable_results():
    """Requisito 10: duplicatas colapsam de forma estável.

    Duas evidências iguais em todos os campos referenciam o **mesmo**
    fato; exibi-lo duas vezes sugeriria dois fatos.
    """
    e = _evidencia(reference="r1")
    resultado = PersistenceAssessment(
        coid=uuid.uuid4(),
        outcome=PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE,
        evidence=(e, e, e),
    )
    assert len(resultado.evidence) == 1
    assert isinstance(hash(resultado), int)


def test_pv5_external_mutable_collections_do_not_alter_built_assessments():
    """Requisito 11: `frozen=True` protege a referência, não o conteúdo.

    O projeto já pagou três vezes por essa lição (E4.2.1, E4.3.1,
    E4.3.2). Aqui o invariante nasce com o módulo.
    """
    origem = [_evidencia(reference="r1")]
    resultado = PersistenceAssessment(
        coid=uuid.uuid4(),
        outcome=PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE,
        evidence=origem,
    )

    origem.append(_evidencia(reference="r2"))
    origem.clear()

    assert len(resultado.evidence) == 1
    assert isinstance(resultado.evidence, tuple)
    assert isinstance(hash(resultado), int)


@pytest.mark.parametrize(
    "kwargs,exc",
    [
        ({"coid": "nao-e-uuid"}, TypeError),
        ({"outcome": "subject_not_found"}, TypeError),
        ({"clid": "nao-e-uuid"}, TypeError),
        ({"revision_status": "  "}, ValueError),
        ({"revision_status": 42}, TypeError),
        ({"evidence": None}, TypeError),
        ({"evidence": "texto"}, TypeError),
        ({"evidence": (1, 2)}, TypeError),
    ],
)
def test_pv6_invalid_assessments_are_rejected_by_the_direct_constructor(kwargs, exc):
    """Requisito 12: o construtor direto impõe os invariantes.

    Tipo inválido é `TypeError`; valor inválido é `ValueError` —
    diagnósticos distintos, como em E4.2.1/E4.3.2.
    """
    base = {
        "coid": uuid.uuid4(),
        "outcome": PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE,
    }
    base.update(kwargs)
    with pytest.raises(exc):
        PersistenceAssessment(**base)


@pytest.mark.parametrize(
    "kwargs,exc",
    [
        ({"kind": "clid"}, TypeError),
        ({"reference": ""}, ValueError),
        ({"reference": "   "}, ValueError),
        ({"reference": 42}, TypeError),
        ({"related_coid": "nao-e-uuid"}, TypeError),
        ({"qualifier": "  "}, ValueError),
        ({"qualifier": 1}, TypeError),
    ],
)
def test_pv7_invalid_evidence_is_rejected(kwargs, exc):
    with pytest.raises(exc):
        _evidencia(**kwargs)


def test_pv8_contradictory_states_are_rejected():
    """Estados que não descrevem nada real.

    `SUBJECT_NOT_FOUND` carregando fato é fabricação de história sobre
    sujeito inexistente — precisamente o que este módulo existe para
    não fazer.
    """
    coid = uuid.uuid4()
    with pytest.raises(ValueError, match="SUBJECT_NOT_FOUND"):
        PersistenceAssessment(
            coid=coid,
            outcome=PersistenceOutcome.SUBJECT_NOT_FOUND,
            evidence=(_evidencia(),),
        )
    with pytest.raises(ValueError, match="SUBJECT_NOT_FOUND"):
        PersistenceAssessment(
            coid=coid, outcome=PersistenceOutcome.SUBJECT_NOT_FOUND, clid=uuid.uuid4()
        )
    with pytest.raises(ValueError, match="SUBJECT_NOT_FOUND"):
        PersistenceAssessment(
            coid=coid,
            outcome=PersistenceOutcome.SUBJECT_NOT_FOUND,
            revision_status="current",
        )
    with pytest.raises(ValueError, match="NO_RECORDED_CONTINUITY_EVIDENCE"):
        PersistenceAssessment(
            coid=coid,
            outcome=PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE,
            evidence=(_evidencia(),),
        )
    with pytest.raises(ValueError, match="RECORDED_CONTINUITY_EVIDENCE exige"):
        PersistenceAssessment(coid=coid, outcome=PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE)


def test_pv9_assessment_is_frozen_and_derived_flag_is_not_a_score():
    """`has_recorded_continuity` é derivada e binária — não é score.

    Responde **se** há evidência registrada, nunca quanta nem se é
    boa. `SUBJECT_NOT_FOUND` e ausência de evidência devolvem `False`
    pelo mesmo motivo, mas continuam distinguíveis por `outcome`.
    """
    coid = uuid.uuid4()
    ausente = PersistenceAssessment(coid=coid, outcome=PersistenceOutcome.SUBJECT_NOT_FOUND)
    vazio = PersistenceAssessment(
        coid=coid, outcome=PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE
    )
    com = PersistenceAssessment(
        coid=coid,
        outcome=PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE,
        evidence=(_evidencia(),),
    )

    assert ausente.has_recorded_continuity is False
    assert vazio.has_recorded_continuity is False
    assert com.has_recorded_continuity is True
    assert ausente.outcome is not vazio.outcome

    with pytest.raises(dataclasses.FrozenInstanceError):
        com.outcome = PersistenceOutcome.SUBJECT_NOT_FOUND  # type: ignore[misc]


def test_pv10_evidence_of_filters_without_ranking():
    """`evidence_of` é filtro de apresentação, não hierarquia."""
    coid = uuid.uuid4()
    clid = _evidencia(kind=PersistenceEvidenceKind.CLID, reference="c")
    pai = _evidencia(kind=PersistenceEvidenceKind.LINEAGE_PARENT, reference="p")
    resultado = PersistenceAssessment(
        coid=coid,
        outcome=PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE,
        evidence=(clid, pai),
    )

    assert resultado.evidence_of(PersistenceEvidenceKind.CLID) == (clid,)
    assert resultado.evidence_of(PersistenceEvidenceKind.CAUSAL_EVENT) == ()
    with pytest.raises(TypeError):
        resultado.evidence_of("clid")  # type: ignore[arg-type]


# ======================================================================
# Fronteiras verificadas por ausência estrutural (requisitos 19, 23, 24)
# ======================================================================


def test_pv11_no_score_rank_or_importance_anywhere():
    """Requisito 19: nenhum atributo ou resultado de mérito.

    ```
    LOP = PERSISTENCE PRINCIPLE, NOT A METRIC
    ```
    """
    campos = {f.name for f in dataclasses.fields(PersistenceAssessment)} | {
        f.name for f in dataclasses.fields(PersistenceEvidence)
    }
    expostos = {
        nome for nome, _ in inspect.getmembers(PersistenceManager) if not nome.startswith("_")
    }
    for proibido in (
        "score",
        "rank",
        "ranking",
        "importance",
        "priority",
        "weight",
        "confidence",
        "survival",
        "promote",
        "promotion",
    ):
        assert not any(proibido in nome for nome in campos), f"campo com '{proibido}'"
        assert not any(proibido in nome for nome in expostos), f"método com '{proibido}'"

    codigo = _executable_source(PersistenceManager) + _executable_source(PersistenceAssessment)
    for proibido in ("A = R * P * T", "importance", "reduce(", "sum("):
        assert proibido not in codigo, f"código não deve conter {proibido!r}"


def test_pv12_manager_does_not_write_search_govern_or_consolidate():
    """Requisito 13/6: o manager não expõe nem conhece caminhos de
    escrita, busca, governança ou consolidação.

    Testar ausência é o único modo honesto de provar uma fronteira: um
    teste de comportamento passaria igual se a capacidade proibida
    existisse mas não fosse chamada naquele caminho.
    """
    expostos = {
        nome for nome, _ in inspect.getmembers(PersistenceManager) if not nome.startswith("_")
    }
    assert expostos == {"assess"}, f"superfície pública inesperada: {expostos}"

    codigo = _executable_source(PersistenceManager)
    for proibido in (
        "commit",
        "flush",
        "add(",
        "delete(",
        "SearchEngine",
        "SearchCriteria",
        "GovernanceManager",
        "MemoryContext",
        "MemoryDomain",
        "consolidat",
        "insert(",
        "update(",
    ):
        assert proibido not in codigo, f"manager não deve conter {proibido}"


def test_pv13_memory_package_still_never_imports_the_cognitive_domain():
    """Requisito 21: a fronteira estrutural da E4.1 continua valendo.

    E4.4 lê o patrimônio da E3 referenciando tabelas **por nome**, do
    mesmo modo que a E4.1 declarou a FK — nunca importando um símbolo.
    """
    padrao = re.compile(r"^\s*(from|import)\s+app\.cognitive", re.MULTILINE)
    achados = [
        str(caminho.relative_to(_BACKEND_ROOT))
        for caminho in (_BACKEND_ROOT / "app" / "memory").rglob("*.py")
        if padrao.search(caminho.read_text(encoding="utf-8"))
    ]
    assert achados == [], f"app/memory passou a depender de app.cognitive: {achados}"


def test_pv14_no_transcript_provider_embedding_or_vector_dependency():
    """Requisitos 23 e 24."""
    import app.memory.repositories.continuity_evidence_repository as repositorio
    import app.memory.schemas.persistence as esquemas
    import app.memory.services.persistence_manager as servico

    codigo = "".join(_executable_source(m) for m in (servico, esquemas, repositorio))
    for proibido in (
        "transcript",
        "prompt",
        "completion",
        "openai",
        "anthropic",
        "embedding",
        "vector",
        "pinecone",
        "faiss",
        "provider_id",
        "model_id",
        "session_id",
    ):
        assert proibido not in codigo, f"E4.4 não deve depender de {proibido}"


def test_pv15_provenance_is_not_reclassified_as_continuity():
    """Proveniência continua sendo proveniência.

    Ela responde "de onde veio", não "atravessou o quê". As quatro
    fontes canônicas congeladas pela E4.0 são CLID, linhagem,
    transformação e história causal — `provenance_records` não está
    entre elas, e o repositório não a consulta.
    """
    import app.memory.repositories.continuity_evidence_repository as repositorio

    codigo = _executable_source(repositorio)
    assert "provenance_records" not in codigo
    for proibido in (
        "memory_domain_memberships",
        "memory_domains",
        "governance_policies",
        "relationships",
    ):
        assert (
            proibido not in codigo
        ), f"{proibido} não é fonte de continuidade — não pode ser lida aqui"


def test_pv16_assess_takes_only_a_coid():
    """Requisitos 15–17: o contexto **não tem por onde entrar**.

    Independência de contexto garantida pela assinatura, não por
    disciplina de chamador:

    ```
    CONTEXT CHANGES VIEW
    CONTEXT DOES NOT CHANGE PERSISTENCE
    ```
    """
    parametros = set(inspect.signature(PersistenceManager.assess).parameters) - {"self"}
    assert parametros == {"coid"}, f"assess() aceita dimensões extras: {parametros}"

    construtor = set(inspect.signature(PersistenceManager.__init__).parameters) - {"self"}
    assert construtor == {"evidence_repository"}


def test_pv17_assess_rejects_a_non_uuid_subject():
    with pytest.raises(TypeError, match="coid"):
        PersistenceManager(evidence_repository=None).assess("nao-e-uuid")  # type: ignore[arg-type]
