"""
E4.12 — Gate final de integração da Entrega 4.

```text
CONTEXT CHANGES VIEW
CONTEXT DOES NOT REWRITE PATRIMONY
INACCESSIBLE REMAINS HISTORICALLY REPRESENTABLE
NOT_RETRIEVED != FORGOTTEN
```

Um cenário contínuo sobre PostgreSQL real, atravessando as fronteiras de
E4.1 a E4.11 **sem criar orquestrador de produção**. Tudo aqui usa APIs
públicas já entregues e dublês confinados a `tests/`.

## O que este módulo prova, e o que ele não prova

```text
PROVED      as fronteiras compõem sem apagar as distinções
NOT_PROVED  adaptador material, autenticador, API, transporte, learning
```

O gate é de **integração**: mede que nenhuma fronteira, ao ser usada
junto com as outras, reescreve patrimônio, concede autoridade que não
tem ou faz uma distinção colapsar em outra.

## Censo canônico, não contagem

```text
ROW_COUNT != CANONICAL_CENSUS
```

Contagem igual não detecta alteração de valor, identidade, estado,
história ou linhagem. Todo `before/after` deste módulo compara um censo
**linha a linha**, ordenado e serializado deterministicamente.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import (
    AccessibilityState,
    CausalEventType,
    ProvenanceActorType,
    ProvenanceSourceType,
)
from app.cognitive.models.provenance_record import ProvenanceRecord
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.repositories.search_repository import SearchRepository
from app.cognitive.repositories.transformation_repository import TransformationRepository
from app.cognitive.schemas.search_criteria import SearchCriteria
from app.cognitive.services.accessibility_manager import AccessibilityManager
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.clid_manager import ClidManager
from app.cognitive.services.multi_input_transformation_manager import (
    MultiInputTransformationManager,
)
from app.cognitive.services.search_engine import SearchEngine
from app.database.engine import engine
from app.database.health import check_database_health
from app.memory.models.compliance_enums import (
    ComplianceOutcome,
    ObservedOperationState,
    PolicyKind,
)
from app.memory.models.compliance_enums import (
    ComplianceSubjectKind as ComplianceSubject,
)
from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.memory.models.governance_enums import CognitiveOperation, GovernanceEffect
from app.memory.models.retention_assessment_enums import RetentionAssessmentDecision
from app.memory.models.retention_enums import RetentionScopeKind
from app.memory.models.target_resolution_enums import LegacyProtectionState
from app.memory.models.validated_experience_enums import (
    CriterionOriginKind,
    EvidenceKind,
    ExperienceSubjectKind,
    ValidatorKind,
)
from app.memory.repositories.accessibility_policy_repository import (
    AccessibilityPolicyRepository,
)
from app.memory.repositories.approval_record_repository import ApprovalRecordRepository
from app.memory.repositories.continuity_evidence_repository import (
    ContinuityEvidenceRepository,
)
from app.memory.repositories.governance_policy_repository import GovernancePolicyRepository
from app.memory.repositories.memory_domain_membership_repository import (
    MemoryDomainMembershipRepository,
)
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository
from app.memory.repositories.validated_experience_repository import (
    ValidatedExperienceRepository,
)
from app.memory.schemas.accessibility import AccessibilityRule
from app.memory.schemas.compliance import ComplianceReport
from app.memory.schemas.destructive_execution import (
    ApprovalConsumptionRefusal,
    DestructiveExecutionReport,
    DestructiveExecutionRequest,
)
from app.memory.schemas.erasure_effect import ObservedAttemptResult
from app.memory.schemas.erasure_target import ErasureTargetDescriptor
from app.memory.schemas.governance import GovernanceRule
from app.memory.schemas.memory_context import MemoryContext
from app.memory.schemas.retention import RetentionRule
from app.memory.schemas.validated_experience import (
    AttributedValidator,
    CriterionReference,
    EvidenceReference,
    ExperienceSubjectRef,
    ObservedOutcome,
    OriginAttribution,
    ValidatedExperienceAppend,
)
from app.memory.services.accessibility_policy_manager import AccessibilityPolicyManager
from app.memory.services.compliance_evaluator import (
    ComplianceSubject as SujeitoDeConformidade,
)
from app.memory.services.compliance_evaluator import (
    EvaluatedPolicy,
    GovernedOperationObservation,
    avaliar_conformidade,
)
from app.memory.services.consolidation_manager import ConsolidationManager
from app.memory.services.context_manager import ContextManager
from app.memory.services.destructive_execution_service import DestructiveExecutionService
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.memory_isolation_manager import MemoryIsolationManager
from app.memory.services.persistence_manager import PersistenceManager
from app.memory.services.platform_safety_boundary import CapabilityDescriptor
from app.memory.services.retention_evaluator import RetentionCandidate, avaliar_retencao
from app.memory.services.retrieval_manager import MemoryRetrievalManager
from app.repositories.unit_of_work import UnitOfWork

INICIO = datetime(2020, 1, 1, tzinfo=UTC)
AGORA = datetime(2026, 8, 19, 18, 0, tzinfo=UTC)
EXTINTO = "causally_extinct"


def _disponivel() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _disponivel(),
    reason="PostgreSQL real indisponível — o gate final exige banco.",
)


# ======================================================================
# Composição real e censo canônico
# ======================================================================


def _compor(session: object) -> AccessibilityPolicyManager:
    """Composição real, sobre a MESMA `Session` — padrão da E4.7."""
    objetos = ObjectRepository(session)
    return AccessibilityPolicyManager(
        objetos,
        AccessibilityManager(objetos),
        CausalHistoryRepository(session),
        AccessibilityPolicyRepository(session),
        GovernanceManager(GovernancePolicyRepository(session)),
        ContextManager(MemoryDomainRepository(session)),
    )


def censo_canonico(coids: tuple[uuid.UUID, ...]) -> tuple[tuple[object, ...], ...]:
    """Censo **linha a linha** do patrimônio, ordenado e determinístico.

    ```text
    ROW_COUNT != CANONICAL_CENSUS
    ```

    Cobre identidade, estado, revisão, remoção lógica, história causal e
    linhagem. Detecta alteração de **valor**, não só de quantidade — uma
    contagem igual passaria por cima de um estado reescrito.
    """
    alvos = [str(coid) for coid in coids]
    with UnitOfWork() as uow:
        objetos = uow.session.execute(
            sa.text(
                "SELECT id::text, clid::text, accessibility, revision_status, "
                "deleted_at FROM cognitive_objects WHERE id = ANY(:c ::uuid[]) "
                "ORDER BY id"
            ),
            {"c": alvos},
        ).all()
        eventos = uow.session.execute(
            sa.text(
                "SELECT h.subject_coid::text, e.event_type, e.actor_ref::text, "
                "e.predecessor_event_id::text FROM causal_history_events e "
                "JOIN causal_histories h ON h.id = e.history_id "
                "WHERE h.subject_coid = ANY(:c ::uuid[]) "
                "ORDER BY h.subject_coid, e.occurred_at, e.id"
            ),
            {"c": alvos},
        ).all()
        linhagem = uow.session.execute(
            sa.text(
                "SELECT parent_coid::text, child_coid::text, relation_type "
                "FROM lineage_edges WHERE parent_coid = ANY(:c ::uuid[]) "
                "OR child_coid = ANY(:c ::uuid[]) "
                "ORDER BY parent_coid, child_coid, relation_type"
            ),
            {"c": alvos},
        ).all()
    return (
        tuple(tuple(linha) for linha in objetos),
        tuple(tuple(linha) for linha in eventos),
        tuple(tuple(linha) for linha in linhagem),
    )


def _vista(session: object, contexto: MemoryContext, chave: str, trace: str) -> set[str]:
    """Conjunto canônico de COIDs que o contexto ALCANÇA.

    ```text
    PERSISTENT_TRANSITION != CONTEXTUAL_VIEW
    ```

    Vista é o que o `MemoryRetrievalManager` devolve para **este**
    contexto — não o estado gravado no objeto. Comparar estados provaria
    que uma transição persistiu; comparar vistas prova que o contexto
    muda o alcance.
    """
    gestor: MemoryRetrievalManager = MemoryRetrievalManager(
        SearchEngine(SearchRepository(session)),
        GovernanceManager(GovernancePolicyRepository(session)),
        ContextManager(MemoryDomainRepository(session)),
        MemoryDomainMembershipRepository(session),
    )
    resultado = gestor.retrieve(
        context=contexto,
        descriptor=CapabilityDescriptor(operation=CognitiveOperation.READ),
        criteria=SearchCriteria(trace_id=trace),
        policy_key=chave,
        moment=AGORA,
    )
    return {str(item.coid) for item in resultado.items}


def _chaves() -> tuple[str, str]:
    sufixo = uuid.uuid4().hex[:8]
    return f"gov-e412-{sufixo}", f"acc-e412-{sufixo}"


def _publicar(gk: str, ak: str) -> None:
    padrao = tuple(
        AccessibilityRule(
            rule_id=f"r-{destino}",
            effect=GovernanceEffect.ADMIT,
            source_states=frozenset({"active"}),
            target_states=frozenset({destino}),
        )
        for destino in ("latent", "inaccessible", EXTINTO)
    )
    with UnitOfWork() as uow:
        GovernancePolicyRepository(uow.session).add_policy(
            policy_key=gk,
            version=1,
            rules=(
                GovernanceRule(
                    rule_id="g1",
                    effect=GovernanceEffect.ADMIT,
                    # READ entra porque o gate compara VISTAS reais do
                    # `MemoryRetrievalManager`, e sem ela a governança
                    # recusaria antes da Search — a vista viria vazia por
                    # negação, não por escopo, e a condição 1 mediria
                    # outra coisa.
                    operations=frozenset(
                        {
                            CognitiveOperation.READ,
                            CognitiveOperation.ACCESSIBILITY_TRANSITION,
                        }
                    ),
                ),
            ),
            effective_from=INICIO,
        )
        AccessibilityPolicyRepository(uow.session).add_policy(
            policy_key=ak,
            version=1,
            governance_policy_key=gk,
            rules=padrao,
            effective_from=INICIO,
        )
        uow.commit()


def _criar_patrimonio(quantidade: int = 1, *, trace: str | None = None) -> tuple[uuid.UUID, ...]:
    """Patrimônio com identidade estável, proveniência e história causal.

    `trace_id` vive no `ProvenanceRecord` (E3.6), não no
    `CognitiveObject`, e a Search da E3.8 casa por junção — é o caminho
    real, não um atalho de teste.
    """
    criados: list[uuid.UUID] = []
    with UnitOfWork() as uow:
        objetos = ObjectRepository(uow.session)
        proveniencias = ProvenanceRepository(uow.session)
        historias = CausalHistoryManager(CausalHistoryRepository(uow.session))
        for _ in range(quantidade):
            objeto = objetos.add(CognitiveObject())
            uow.session.flush()
            if trace is not None:
                proveniencias.add(
                    ProvenanceRecord(
                        coid=objeto.id,
                        source_type=ProvenanceSourceType.HUMAN,
                        actor_type=ProvenanceActorType.HUMAN,
                        trace_id=trace,
                    )
                )
            # `actor_ref` referencia `provenance_records` por FK real; um
            # UUID inventado violaria a integridade que a E3.6 impôs.
            # `None` é legítimo e declarado: o evento simplesmente não
            # nomeia ator, e o sistema não inventa um.
            historias.record(subject_coid=objeto.id, event_type=CausalEventType.CREATED)
            criados.append(objeto.id)
        uow.commit()
    return tuple(criados)


def _contexto(dominio: uuid.UUID, ator: str) -> MemoryContext:
    """Contexto canônico da E4.2 — domínios, sessão, ator e propósito."""
    with UnitOfWork() as uow:
        return ContextManager(MemoryDomainRepository(uow.session)).build(
            domain_ids=(dominio,),
            session_id=f"sess-{uuid.uuid4().hex[:8]}",
            actor_ref=ator,
            purpose="purpose:gate-final",
        )


def _dominio(nome: str) -> uuid.UUID:
    from app.memory.models.memory_domain import MemoryDomain

    with UnitOfWork() as uow:
        dominio = MemoryDomain(name=f"{nome}-{uuid.uuid4().hex[:8]}")
        uow.session.add(dominio)
        uow.session.flush()
        identificador = dominio.id
        uow.commit()
    return identificador


def _estado(coid: uuid.UUID) -> str:
    with UnitOfWork() as uow:
        objeto = ObjectRepository(uow.session).get_by_id(coid, include_deleted=True)
        return objeto.accessibility.value


def _eventos(coid: uuid.UUID) -> int:
    with UnitOfWork() as uow:
        return uow.session.execute(
            sa.text(
                "SELECT count(*) FROM causal_history_events e JOIN causal_histories h "
                "ON h.id = e.history_id WHERE h.subject_coid = :c"
            ),
            {"c": str(coid)},
        ).scalar_one()


@pytest.fixture
def cenario() -> Iterator[dict[str, object]]:
    """Patrimônio, políticas e dois contextos distintos."""
    gk, ak = _chaves()
    _publicar(gk, ak)
    trace = f"trace-e412-{uuid.uuid4().hex[:12]}"
    coids = _criar_patrimonio(3, trace=trace)
    dominio_um = _dominio("c1")
    dominio_dois = _dominio("c2")
    with UnitOfWork() as uow:
        memberships = MemoryDomainMembershipRepository(uow.session)
        for coid in coids:
            memberships.add_membership(domain_id=dominio_um, coid=coid)
        uow.commit()
    contexto_um = _contexto(dominio_um, "ator:c1")
    contexto_dois = _contexto(dominio_dois, "ator:c2")
    yield {
        "coids": coids,
        "gk": gk,
        "ak": ak,
        "c1": contexto_um,
        "c2": contexto_dois,
        "dominios": (dominio_um, dominio_dois),
        "trace": trace,
    }
    with UnitOfWork() as uow:
        alvos = [str(c) for c in coids]
        uow.session.execute(
            sa.text(
                "DELETE FROM causal_history_events WHERE history_id IN "
                "(SELECT id FROM causal_histories WHERE subject_coid = ANY(:c ::uuid[]))"
            ),
            {"c": alvos},
        )
        uow.session.execute(
            sa.text("DELETE FROM causal_histories WHERE subject_coid = ANY(:c ::uuid[])"),
            {"c": alvos},
        )
        uow.session.execute(
            sa.text("DELETE FROM memory_domain_memberships WHERE coid = ANY(:c ::uuid[])"),
            {"c": alvos},
        )
        uow.session.execute(
            sa.text("DELETE FROM provenance_records WHERE coid = ANY(:c ::uuid[])"),
            {"c": alvos},
        )
        uow.session.execute(
            sa.text("DELETE FROM cognitive_objects WHERE id = ANY(:c ::uuid[])"),
            {"c": alvos},
        )
        uow.session.execute(
            sa.text("DELETE FROM accessibility_policies WHERE policy_key = :k"), {"k": ak}
        )
        uow.session.execute(
            sa.text("DELETE FROM governance_policies WHERE policy_key = :k"), {"k": gk}
        )
        # Os domínios são da E4.1 e NÃO são append-only. Deixá-los para
        # trás bloquearia o downgrade de `memory_domains` e reprovaria os
        # testes de round trip da E3 e da E4.1 — a mesma armadilha que a
        # E4.11 pagou. Removo só os que este cenário criou.
        uow.session.execute(
            sa.text("DELETE FROM memory_domains WHERE id = ANY(:d ::uuid[])"),
            {"d": [str(dominio_um), str(dominio_dois)]},
        )
        uow.commit()


# ======================================================================
# 1 — Acessibilidade depende do contexto
# ======================================================================


def test_g01_acessibilidade_depende_do_contexto(cenario):
    """`Accessible(P, C1) != Accessible(P, C2)`, por vistas REAIS.

    ```text
    PERSISTENT_TRANSITION != CONTEXTUAL_VIEW
    ```

    CORRIGIDO NO CORRETIVO DA CADEIA 97 (achado A1). A versão anterior
    provava apenas que uma transição persistente mudou o estado gravado
    do objeto — o que é outra coisa. O que a condição 1 exige é que o
    **alcance** difira entre contextos.

    Aqui os dois contextos declaram domínios distintos, e o mesmo
    patrimônio pertence apenas ao primeiro. Dois `retrieve` reais do
    `MemoryRetrievalManager`, dois conjuntos canônicos de COIDs.
    """
    esperados = {str(c) for c in cenario["coids"]}

    with UnitOfWork() as uow:
        vista_um = _vista(uow.session, cenario["c1"], cenario["gk"], cenario["trace"])
        vista_dois = _vista(uow.session, cenario["c2"], cenario["gk"], cenario["trace"])

    assert vista_um == esperados
    assert vista_dois == set()
    assert vista_um != vista_dois


def test_g01_1_isolamento_entre_dominios_declarados(cenario):
    """`MemoryIsolationManager` composto — vazamento entre domínios.

    ACRESCENTADO NO CORRETIVO (achado A2). Isolamento é fronteira
    própria da E4.8: alcance sob escopo de domínio **explícito**, com
    cada domínio autorizado individualmente.
    """
    with UnitOfWork() as uow:
        # A porta de recuperação do isolamento é o próprio
        # `MemoryRetrievalManager`, não o motor de busca: o isolamento
        # DECIDE por domínio e delega a vista.
        recuperacao = MemoryRetrievalManager(
            SearchEngine(SearchRepository(uow.session)),
            GovernanceManager(GovernancePolicyRepository(uow.session)),
            ContextManager(MemoryDomainRepository(uow.session)),
            MemoryDomainMembershipRepository(uow.session),
        )
        gestor: MemoryIsolationManager = MemoryIsolationManager(
            recuperacao,
            GovernanceManager(GovernancePolicyRepository(uow.session)),
            ContextManager(MemoryDomainRepository(uow.session)),
            MemoryDomainMembershipRepository(uow.session),
        )
        resultado = gestor.retrieve_isolated(
            context=cenario["c2"],
            descriptor=CapabilityDescriptor(operation=CognitiveOperation.READ),
            criteria=SearchCriteria(trace_id=cenario["trace"]),
            policy_key=cenario["gk"],
            moment=AGORA,
        )

    # `MemoryIsolationResult` carrega a vista em `retrieval`, e não itens
    # próprios: o isolamento DECIDE por domínio e delega a recuperação —
    # e é por isso que a decisão por domínio é observável.
    alcancados = (
        set() if resultado.retrieval is None else {str(coid) for coid in resultado.retrieval.coids}
    )
    # O patrimônio pertence ao domínio de C1; sob o escopo de C2 ele NÃO
    # vaza, mesmo casando o mesmo trace.
    assert alcancados == set()
    assert resultado.decisions


def test_g02_o_patrimonio_e_invariante_a_mudanca_de_contexto(cenario):
    """`Patrimony(P)_before == Patrimony(P)_after`, por censo canônico.

    ```text
    CONTEXT DOES NOT REWRITE PATRIMONY
    ```

    O censo cobre identidade, CLID, revisão, remoção lógica, história
    causal e linhagem. Trocar de contexto e reavaliar não altera nenhum
    deles.
    """
    coids = cenario["coids"]
    antes = censo_canonico(coids)

    # Avaliação em dois contextos distintos, sem transição alguma.
    for contexto in (cenario["c1"], cenario["c2"]):
        with UnitOfWork() as uow:
            GovernanceManager(GovernancePolicyRepository(uow.session)).resolve(
                descriptor=CapabilityDescriptor(operation=CognitiveOperation.READ),
                context=contexto,
                policy_key=cenario["gk"],
                moment=AGORA,
            )

    assert censo_canonico(coids) == antes


# ======================================================================
# 2 — As quatro distinções congeladas
# ======================================================================


def test_g03_distincao_1_context_changes_view(cenario):
    """`CONTEXT CHANGES VIEW` — mesmo patrimônio, dois contextos.

    ```text
    PERSISTENT_TRANSITION != CONTEXTUAL_VIEW
    ```

    CORRIGIDO NO CORRETIVO FINAL. As versões anteriores chamavam
    `transition` e comparavam o estado gravado — uma transição
    **persistente**, no mesmo contexto, que é justamente o que a
    distinção NÃO afirma.

    Aqui não há transição alguma. O mesmo patrimônio é consultado por
    dois contextos distintos, e os conjuntos canônicos diferem porque a
    vista é do contexto.
    """
    esperados = {str(c) for c in cenario["coids"]}

    with UnitOfWork() as uow:
        vista_um = _vista(uow.session, cenario["c1"], cenario["gk"], cenario["trace"])
        vista_dois = _vista(uow.session, cenario["c2"], cenario["gk"], cenario["trace"])

    assert vista_um == esperados
    assert vista_dois == set()
    assert vista_um != vista_dois
    # O patrimônio não mudou de estado: nenhuma transição foi pedida.
    assert _estado(cenario["coids"][0]) == "active"


def test_g04_distincao_2_context_does_not_rewrite_patrimony(cenario):
    """`CONTEXT DOES NOT REWRITE PATRIMONY` — censo integral, sem transição.

    ```text
    ROW_COUNT != CANONICAL_CENSUS
    ```

    Censo canônico completo antes, dois retrievals reais em contextos
    diferentes, censo canônico completo depois, igualdade **exata**.
    Nenhuma chamada a `transition`: consultar não reescreve.
    """
    coids = cenario["coids"]
    antes = censo_canonico(coids)

    with UnitOfWork() as uow:
        vista_um = _vista(uow.session, cenario["c1"], cenario["gk"], cenario["trace"])
        vista_dois = _vista(uow.session, cenario["c2"], cenario["gk"], cenario["trace"])

    assert vista_um != vista_dois, "premissa: os contextos precisam divergir"
    assert censo_canonico(coids) == antes


def test_g05_distincao_3_inaccessible_remains_historically_representable(cenario):
    """`INACCESSIBLE REMAINS HISTORICALLY REPRESENTABLE`.

    ```text
    INACCESSIBLE != NONEXISTENT
    ```

    `INACCESSIBLE` e `CAUSALLY_EXTINCT` continuam **no repositório**,
    com história causal e linhagem preservadas, e ambos estão **ausentes
    da vista contextual real** — não da vista alegada.
    """
    inacessivel, extinto = cenario["coids"][0], cenario["coids"][1]
    descritor = CapabilityDescriptor(operation=CognitiveOperation.ACCESSIBILITY_TRANSITION)

    with UnitOfWork() as uow:
        uow.session.execute(
            sa.text(
                "INSERT INTO lineage_edges (id, parent_coid, child_coid, relation_type, "
                "created_at, updated_at) VALUES (gen_random_uuid(), :p, :c, "
                "'derived_from', now(), now())"
            ),
            {"p": str(inacessivel), "c": str(extinto)},
        )
        uow.commit()
    linhagem_antes = censo_canonico((inacessivel, extinto))[2]
    eventos_antes = {c: _eventos(c) for c in (inacessivel, extinto)}

    for coid, destino in ((inacessivel, "inaccessible"), (extinto, EXTINTO)):
        with UnitOfWork() as uow:
            _compor(uow.session).transition(
                coid=coid,
                target_state=destino,
                context=cenario["c1"],
                descriptor=descritor,
                governance_policy_key=cenario["gk"],
                accessibility_policy_key=cenario["ak"],
                causal_event_id=None if destino != EXTINTO else _evento_de(coid),
                reason=None if destino != EXTINTO else "gate final: extinção declarada",
            )
            uow.commit()

    # 1. Continuam existindo no repositório.
    for coid in (inacessivel, extinto):
        with UnitOfWork() as uow:
            objeto = ObjectRepository(uow.session).get_by_id(coid, include_deleted=True)
            assert objeto is not None, "o objeto deixou de existir"
            assert objeto.deleted_at is None, "sair da vista não é remoção"

    # 2. História causal e linhagem preservadas.
    for coid in (inacessivel, extinto):
        assert _eventos(coid) >= eventos_antes[coid], "história causal perdida"
    assert censo_canonico((inacessivel, extinto))[2] == linhagem_antes, "linhagem perdida"

    # 3. AMBOS ausentes da vista contextual REAL.
    with UnitOfWork() as uow:
        vista = _vista(uow.session, cenario["c1"], cenario["gk"], cenario["trace"])
    assert str(inacessivel) not in vista
    assert str(extinto) not in vista
    assert _estado(inacessivel) == "inaccessible"
    assert _estado(extinto) == EXTINTO

    with UnitOfWork() as uow:
        uow.session.execute(
            sa.text("DELETE FROM lineage_edges WHERE parent_coid = :p"),
            {"p": str(inacessivel)},
        )
        uow.commit()


def _evento_de(coid: uuid.UUID) -> uuid.UUID:
    with UnitOfWork() as uow:
        return uow.session.execute(
            sa.text(
                "SELECT e.id FROM causal_history_events e JOIN causal_histories h "
                "ON h.id = e.history_id WHERE h.subject_coid = :c LIMIT 1"
            ),
            {"c": str(coid)},
        ).scalar_one()


def test_g06_distincao_4_not_retrieved_is_not_forgotten(cenario):
    """`NOT_RETRIEVED != FORGOTTEN`.

    O objeto some da vista contextual e **continua existindo**, com
    história intacta. Ausência de recuperação não é alegação de
    inexistência.
    """
    coid = cenario["coids"][0]
    descritor = CapabilityDescriptor(operation=CognitiveOperation.ACCESSIBILITY_TRANSITION)
    eventos_antes = _eventos(coid)

    with UnitOfWork() as uow:
        _compor(uow.session).transition(
            coid=coid,
            target_state="inaccessible",
            context=cenario["c1"],
            descriptor=descritor,
            governance_policy_key=cenario["gk"],
            accessibility_policy_key=cenario["ak"],
        )
        uow.commit()

    with UnitOfWork() as uow:
        ainda_existe = ObjectRepository(uow.session).get_by_id(coid, include_deleted=True)
        assert ainda_existe is not None
        assert ainda_existe.accessibility is AccessibilityState.INACCESSIBLE
        assert ainda_existe.deleted_at is None, "inacessível não é removido"
        assert str(coid) not in _vista(uow.session, cenario["c1"], cenario["gk"], cenario["trace"])
    assert _eventos(coid) >= eventos_antes


# ======================================================================
# 3 — Nenhuma policy altera existência
# ======================================================================


def test_g07_policy_nao_altera_existencia(cenario):
    """`POLICY_CAN_ALTER_EXISTENCE = NO`, medido por censo canônico.

    Governança **decide admissibilidade**, não verdade. Resolver, admitir
    e negar não movem uma linha do patrimônio.
    """
    coids = cenario["coids"]
    antes = censo_canonico(coids)

    with UnitOfWork() as uow:
        gestor = GovernanceManager(GovernancePolicyRepository(uow.session))
        for operacao in (
            CognitiveOperation.READ,
            CognitiveOperation.ACCESSIBILITY_TRANSITION,
        ):
            resolucao = gestor.resolve(
                descriptor=CapabilityDescriptor(operation=operacao),
                context=cenario["c1"],
                policy_key=cenario["gk"],
                moment=AGORA,
            )
            assert resolucao is not None

    assert censo_canonico(coids) == antes


def test_g08_compliance_e_diagnostico_e_nao_decisao(cenario):
    """Conformidade descreve; não decide e não escreve.

    ```text
    COMPLIANCE != GOVERNANCE_DECISION
    ```
    """
    coids = cenario["coids"]
    antes = censo_canonico(coids)

    with UnitOfWork() as uow:
        registro = GovernancePolicyRepository(uow.session).get_version(cenario["gk"], 1)
        from app.memory.models.governance_policy import GovernancePolicy

        politica = EvaluatedPolicy(
            kind=PolicyKind.GOVERNANCE,
            policy_id=registro.id,
            policy_key=registro.policy_key,
            policy_version=registro.version,
            effective_from=registro.effective_from,
            effective_until=registro.effective_until,
            rules=GovernancePolicy.deserialize_rules(registro.rules),
        )

    relatorio = avaliar_conformidade(
        subject=SujeitoDeConformidade(
            kind=ComplianceSubject.GOVERNED_OPERATION,
            subject_coid=coids[0],
            domain_id=next(iter(cenario["c1"].domain_ids)),
        ),
        policy=politica,
        observation=GovernedOperationObservation(
            operation=CognitiveOperation.ACCESSIBILITY_TRANSITION,
            observed_state=ObservedOperationState.EXECUTED,
        ),
        evaluated_at=AGORA,
    )

    assert isinstance(relatorio, ComplianceReport)
    assert relatorio.policy_version == 1
    assert censo_canonico(coids) == antes


# ======================================================================
# 4 — Consolidação rastreável
# ======================================================================


def _consolidador(session: object) -> ConsolidationManager:
    """Composição real da E4.5, sobre a MESMA `Session`."""
    objetos = ObjectRepository(session)
    linhagem = LineageRepository(session)
    historias = CausalHistoryRepository(session)
    porta = MultiInputTransformationManager(
        objetos,
        ClidManager(objetos, linhagem),
        linhagem,
        TransformationRepository(session),
        CausalHistoryManager(historias),
        historias,
    )
    return ConsolidationManager(porta, PersistenceManager(ContinuityEvidenceRepository(session)))


def test_g09_consolidacao_preserva_as_fontes():
    """`S1 <- {M1, M2, M3}` pelo `ConsolidationManager` real.

    A consolidação **acrescenta**: as fontes continuam identificáveis e
    preservadas, e perdas e preservações declaradas permanecem
    rastreáveis. Consolidar não substitui nem elimina.
    """
    fontes = _criar_patrimonio(3)
    antes = censo_canonico(fontes)

    with UnitOfWork() as uow:
        gestor: ConsolidationManager = _consolidador(uow.session)
        resultado = gestor.consolidate(
            source_coids=fontes,
            declared_losses=("granularidade das três fontes",),
            declared_preservations=("identidade de cada fonte",),
        )
        uow.commit()
        alvo = resultado.target_coid

    with UnitOfWork() as uow:
        derivadas = (
            uow.session.execute(
                sa.text(
                    "SELECT parent_coid::text FROM lineage_edges "
                    "WHERE child_coid = :t ORDER BY 1"
                ),
                {"t": str(alvo)},
            )
            .scalars()
            .all()
        )

    assert sorted(derivadas) == sorted(str(f) for f in fontes)
    # As fontes NÃO foram substituídas nem eliminadas: o censo dos
    # objetos-fonte é idêntico ao de antes da consolidação.
    assert censo_canonico(fontes)[0] == antes[0]

    with UnitOfWork() as uow:
        alvos = [str(f) for f in (*fontes, alvo)]
        uow.session.execute(
            sa.text("DELETE FROM lineage_edges WHERE child_coid = ANY(:c ::uuid[])"),
            {"c": alvos},
        )
        # `ContinuityEvidenceRepository` é estritamente read-only: a
        # evidência de continuidade é DERIVADA de `lineage_edges` e
        # `transformation_records`, e não tem tabela própria para limpar.
        # `transformation_records` referencia os COIDs por `output_refs`
        # em JSON, não por coluna própria — a limpeza é pelo alvo.
        uow.session.execute(
            sa.text("DELETE FROM transformation_records WHERE output_refs::text LIKE :alvo"),
            {"alvo": f"%{alvo}%"},
        )
        uow.session.execute(
            sa.text(
                "DELETE FROM causal_history_events WHERE history_id IN "
                "(SELECT id FROM causal_histories WHERE subject_coid = ANY(:c ::uuid[]))"
            ),
            {"c": alvos},
        )
        uow.session.execute(
            sa.text("DELETE FROM causal_histories WHERE subject_coid = ANY(:c ::uuid[])"),
            {"c": alvos},
        )
        uow.session.execute(
            sa.text("DELETE FROM cognitive_objects WHERE id = ANY(:c ::uuid[])"), {"c": alvos}
        )
        uow.commit()


# ======================================================================
# 5 — Retenção informa; não apaga
# ======================================================================


def test_g10_retencao_apenas_informa(cenario):
    """`RETENTION_ASSESSMENT != DELETION_AUTHORITY`.

    A avaliação chega a `ASSESS_AND_INFORM` e **nada** acontece com o
    patrimônio: nenhuma exclusão automática existe.
    """
    coids = cenario["coids"]
    antes = censo_canonico(coids)

    avaliacao = avaliar_retencao(
        candidate=RetentionCandidate(
            subject_coid=coids[0],
            domain_id=next(iter(cenario["c1"].domain_ids)),
            created_at=INICIO,
            legacy_protection_state=LegacyProtectionState.NOT_PROTECTED,
        ),
        rules=(
            RetentionRule(
                rule_id="ret-30",
                scope_kind=RetentionScopeKind.ALL_LOCAL_PATRIMONY,
                minimum_age_days=30,
            ),
        ),
        policy_effective_from=INICIO,
        policy_effective_until=None,
        evaluated_at=AGORA,
    )

    assert avaliacao.decision is RetentionAssessmentDecision.ASSESS_AND_INFORM
    assert censo_canonico(coids) == antes


# ======================================================================
# 6 — Registro de experiência validada
# ======================================================================


def test_g11_registro_validado_nao_concede_autoridade(cenario):
    """`VALIDATED_RECORD != BEHAVIORAL_AUTHORITY`.

    Registrar uma validação não muda estado, vista, política nem
    patrimônio — e o registro é append-only inclusive contra `TRUNCATE`.
    """
    coids = cenario["coids"]
    antes = censo_canonico(coids)
    evidencia = EvidenceReference(kind=EvidenceKind.CAUSAL_EVENT, ref=_evento_de(coids[0]))

    entrada = ValidatedExperienceAppend(
        experience_id=uuid.uuid4(),
        subject_ref=ExperienceSubjectRef(kind=ExperienceSubjectKind.COGNITIVE_OBJECT, ref=coids[0]),
        outcome_observed=ObservedOutcome(
            outcome_token="produced", observed_at=AGORA, primary_evidence_ref=evidencia
        ),
        validated_by=AttributedValidator(
            validator_kind=ValidatorKind.HUMAN, validator_ref="humano:auditor"
        ),
        criterion_ref=CriterionReference(
            criterion_key="crit.gate.final",
            criterion_version=1,
            criterion_origin=CriterionOriginKind.PUBLISHED,
        ),
        evidence_refs=(evidencia,),
        validated_at=AGORA,
        origin=OriginAttribution(origin_ref=uuid.uuid4()),
    )

    # ```text
    # A_TEST_MUST_NOT_DISABLE_THE_GUARANTEE_IT_MEASURES
    # ```
    #
    # CORRIGIDO NO CORRETIVO DA CADEIA 97 (achado A4). A versão anterior
    # limpava a tabela com `SET session_replication_role = replica`, que
    # desliga exatamente a trigger que prova o append-only. A limpeza
    # passou a ser por ROLLBACK: a linha existe dentro da transação,
    # todas as garantias valem, e nada precisa ser desativado.
    sessao = Session(engine)
    try:
        ValidatedExperienceRepository(sessao).append(entrada)
        sessao.flush()
        persistida = sessao.execute(
            sa.text("SELECT count(*) FROM validated_experiences WHERE id = :i"),
            {"i": entrada.experience_id},
        ).scalar_one()
        assert persistida == 1

        for comando in (
            "UPDATE validated_experiences SET outcome_token = 'x'",
            "DELETE FROM validated_experiences",
            "TRUNCATE validated_experiences",
        ):
            with pytest.raises(Exception, match="append-only"):
                sessao.execute(sa.text(comando))
            sessao.rollback()
            ValidatedExperienceRepository(sessao).append(entrada)
            sessao.flush()
    finally:
        sessao.rollback()
        sessao.close()

    assert _estado(coids[0]) == "active"
    assert censo_canonico(coids) == antes
    # Nada ficou: o rollback desfez a linha sem desligar trigger alguma.
    with Session(engine) as leitura:
        assert (
            leitura.execute(sa.text("SELECT count(*) FROM validated_experiences")).scalar_one() == 0
        )


# ======================================================================
# 7 — Galaxy Trace e Broken Glass sob as vistas da E4
# ======================================================================


def test_g12_galaxy_trace_sob_contexto(cenario):
    """Invariantes substantivos da E3.12 continuam válidos sob a E4.

    Linhagem e história causal atravessam a mudança de vista sem perda —
    é o cenário Galaxy Trace, reexecutado com as fronteiras da E4 ativas.
    """
    coids = cenario["coids"]
    descritor = CapabilityDescriptor(operation=CognitiveOperation.ACCESSIBILITY_TRANSITION)

    with UnitOfWork() as uow:
        for origem, destino in zip(coids, coids[1:], strict=False):
            uow.session.execute(
                sa.text(
                    "INSERT INTO lineage_edges (id, parent_coid, child_coid, "
                    "relation_type, created_at, updated_at) VALUES "
                    "(gen_random_uuid(), :s, :t, 'derived_from', now(), now())"
                ),
                {"s": str(origem), "t": str(destino)},
            )
        uow.commit()

    linhagem_antes = censo_canonico(coids)[2]
    eventos_antes = {coid: _eventos(coid) for coid in coids}

    with UnitOfWork() as uow:
        _compor(uow.session).transition(
            coid=coids[0],
            target_state="inaccessible",
            context=cenario["c1"],
            descriptor=descritor,
            governance_policy_key=cenario["gk"],
            accessibility_policy_key=cenario["ak"],
        )
        uow.commit()

    assert censo_canonico(coids)[2] == linhagem_antes, "a linhagem mudou com a vista"
    for coid in coids:
        assert _eventos(coid) >= eventos_antes[coid], "história causal perdida"

    # Reexecutado PELA VISTA da E4: o objeto sai do alcance e os demais
    # continuam alcançáveis, com linhagem e história intactas.
    with UnitOfWork() as uow:
        vista = _vista(uow.session, cenario["c1"], cenario["gk"], cenario["trace"])
    assert str(coids[0]) not in vista
    assert {str(c) for c in coids[1:]} <= vista

    with UnitOfWork() as uow:
        uow.session.execute(
            sa.text("DELETE FROM lineage_edges WHERE parent_coid = ANY(:c ::uuid[])"),
            {"c": [str(c) for c in coids]},
        )
        uow.commit()


def test_g13_broken_glass_extinto_fora_da_vista_sem_apagamento(cenario):
    """Broken Glass: `CAUSALLY_EXTINCT` sai da vista, não da história.

    ```text
    INACCESSIBLE != NONEXISTENT
    ```

    CORRIGIDO NO CORRETIVO FINAL: o cenário passa a **consultar a vista
    contextual da E4**, e não apenas o repositório da E3. Provar que o
    objeto ainda está no banco não prova que ele saiu do alcance.
    """
    coid = cenario["coids"][0]
    outro = cenario["coids"][1]
    descritor = CapabilityDescriptor(operation=CognitiveOperation.ACCESSIBILITY_TRANSITION)

    with UnitOfWork() as uow:
        uow.session.execute(
            sa.text(
                "INSERT INTO lineage_edges (id, parent_coid, child_coid, relation_type, "
                "created_at, updated_at) VALUES (gen_random_uuid(), :p, :c, "
                "'derived_from', now(), now())"
            ),
            {"p": str(coid), "c": str(outro)},
        )
        uow.commit()
    linhagem_antes = censo_canonico((coid, outro))[2]
    eventos_antes = _eventos(coid)

    with UnitOfWork() as uow:
        vista_antes = _vista(uow.session, cenario["c1"], cenario["gk"], cenario["trace"])
    assert str(coid) in vista_antes, "premissa: o objeto precisa estar na vista"

    with UnitOfWork() as uow:
        _compor(uow.session).transition(
            coid=coid,
            target_state=EXTINTO,
            context=cenario["c1"],
            descriptor=descritor,
            governance_policy_key=cenario["gk"],
            accessibility_policy_key=cenario["ak"],
            causal_event_id=_evento_de(coid),
            reason="gate final: extinção declarada",
        )
        uow.commit()

    # Fora da VISTA da E4.
    with UnitOfWork() as uow:
        vista_depois = _vista(uow.session, cenario["c1"], cenario["gk"], cenario["trace"])
        assert str(coid) not in vista_depois
        assert str(outro) in vista_depois, "o irmão continua alcançável"

        # Presente no repositório, com história e linhagem preservadas.
        objeto = ObjectRepository(uow.session).get_by_id(coid, include_deleted=True)
        assert objeto is not None
        assert objeto.accessibility.value == EXTINTO
        assert objeto.deleted_at is None

    assert _eventos(coid) >= eventos_antes
    assert censo_canonico((coid, outro))[2] == linhagem_antes

    with UnitOfWork() as uow:
        uow.session.execute(
            sa.text("DELETE FROM lineage_edges WHERE parent_coid = :p"), {"p": str(coid)}
        )
        uow.commit()


# ======================================================================
# 8 — Resultado negativo forte: desfechos tipados e distintos
# ======================================================================


def test_g14_desfechos_materialmente_distintos_nao_colapsam(cenario):
    """Seis pares que **não** podem virar um `INVALID` genérico.

    ```text
    INACCESSIBLE           != NONEXISTENT
    NOT_RETRIEVED          != FORGOTTEN
    POLICY_NOT_APPLICABLE  != COMPLIANT
    INSUFFICIENT_INFORMATION != VIOLATION_CONFIRMED
    NO_MATERIAL_ATTEMPT    != FAILED_EFFECT
    VALIDATED_RECORD       != BEHAVIORAL_AUTHORITY
    ```
    """
    from app.memory.models.erasure_effect_enums import MaterialAttemptRefusalReason
    from app.memory.models.erasure_enums import ErasureOutcome
    from app.memory.schemas.erasure_effect import MaterialAttemptNotStarted

    # POLICY_NOT_APPLICABLE != COMPLIANT · INSUFFICIENT != VIOLATION
    desfechos = {membro for membro in ComplianceOutcome}
    assert len(desfechos) == 4
    assert ComplianceOutcome.POLICY_NOT_APPLICABLE is not ComplianceOutcome.COMPLIANT
    assert ComplianceOutcome.INSUFFICIENT_INFORMATION is not ComplianceOutcome.VIOLATION_CONFIRMED

    # NO_MATERIAL_ATTEMPT != FAILED_EFFECT — tipos disjuntos, não valores
    nao_iniciada = MaterialAttemptNotStarted(
        approval_id=uuid.uuid4(),
        subject_coid=cenario["coids"][0],
        reason=MaterialAttemptRefusalReason.ADAPTER_UNAVAILABLE,
        observed_at=AGORA,
    )
    assert not hasattr(nao_iniciada, "outcome")
    assert ErasureOutcome.FAILED.value == "failed"

    # INACCESSIBLE != NONEXISTENT
    assert AccessibilityState.INACCESSIBLE.value == "inaccessible"
    with UnitOfWork() as uow:
        assert (
            ObjectRepository(uow.session).get_by_id(cenario["coids"][0], include_deleted=True)
            is not None
        )


# ======================================================================
# 9 — Aprovação e execução destrutiva, com portas confinadas a tests/
# ======================================================================


class _ResolvedorDeTeste:
    """Porta de resolução — **exclusivamente de teste**.

    ```text
    TEST_SANDBOX_PORT != PRODUCTION_ADAPTER
    ```

    Observacional: devolve o descritor programado e não escreve nada.
    Nenhuma classe deste módulo é exportada por `backend/app`, e a
    guarda `m13` mede que nenhum adaptador com corpo vivo existe em
    produção.
    """

    def __init__(self, descritor: ErasureTargetDescriptor) -> None:
        self._descritor = descritor
        self.chamadas = 0

    def resolve_target(self, reference: object) -> ErasureTargetDescriptor:
        self.chamadas += 1
        return self._descritor


class _EfeitoDeTeste:
    """Porta de efeito — **exclusivamente de teste**, sem efeito material."""

    def __init__(self, aprovacao: uuid.UUID, sujeito: uuid.UUID) -> None:
        self._aprovacao = aprovacao
        self._sujeito = sujeito
        self.chamadas = 0

    def attempt_effect(self, request: object) -> ObservedAttemptResult:
        self.chamadas += 1
        instante = datetime.now(UTC).replace(microsecond=0)
        return ObservedAttemptResult(
            approval_id=self._aprovacao,
            subject_coid=self._sujeito,
            target_class=ErasureTargetClass.PIA_MANAGED_ARTIFACT,
            outcome=ErasureOutcome.SUCCEEDED,
            executor_ref="executor:e412",
            attempted_at=instante,
            completed_at=instante,
        )


def test_g15_execucao_destrutiva_exige_aprovacao_e_preserva_a_ordem(cenario):
    """`DestructiveExecutionService` composto, com aprovação consumida.

    ACRESCENTADO NO CORRETIVO DA CADEIA 97 (achado A2). O gate final
    precisa **compor** a execução destrutiva, não apenas citá-la no
    manifesto.

    ```text
    CONSUMPTION_COMMITTED_BEFORE_EFFECT = REQUIRED
    OBSERVED_ATTEMPT -> EXACTLY_ONE_ERASURE_RECORD
    REPLAY_WITH_SAME_APPROVAL = REFUSED
    ```

    O patrimônio da E3 **não é tocado**: o alvo é um artefato gerido,
    e o censo canônico antes e depois é idêntico.
    """
    from tests.helpers.destructive_execution import descritor, envelope, referencia, snapshot

    coids = cenario["coids"]
    antes = censo_canonico(coids)

    aprovado = envelope(alvos=(snapshot(),))
    with UnitOfWork() as uow:
        ApprovalRecordRepository(uow.session).append_approved(aprovado)
        uow.commit()

    alvo = descritor()
    efeito = _EfeitoDeTeste(aprovado.approval_id, alvo.subject_coid)
    servico: DestructiveExecutionService = DestructiveExecutionService(
        unit_of_work_factory=UnitOfWork,
        target_resolver=_ResolvedorDeTeste(alvo),
        effect_port=efeito,
    )
    pedido = DestructiveExecutionRequest(aprovado, (referencia(),))

    resultado = servico.execute(pedido)
    assert isinstance(resultado, DestructiveExecutionReport)
    assert resultado.attempts_observed == 1
    assert len(resultado.receipts_persisted) == 1
    assert efeito.chamadas == 1

    # Replay: a aprovação já foi consumida, e nenhum segundo efeito ocorre.
    segundo_efeito = _EfeitoDeTeste(aprovado.approval_id, alvo.subject_coid)
    replay = DestructiveExecutionService(
        unit_of_work_factory=UnitOfWork,
        target_resolver=_ResolvedorDeTeste(alvo),
        effect_port=segundo_efeito,
    ).execute(pedido)
    assert isinstance(replay, ApprovalConsumptionRefusal)
    assert segundo_efeito.chamadas == 0

    # O patrimônio da E3 permanece intocado.
    assert censo_canonico(coids) == antes

    # ```text
    # A_TEST_MUST_NOT_DISABLE_THE_GUARANTEE_IT_MEASURES
    # ```
    #
    # `approval_records` e `erasure_records` são append-only por trigger,
    # exatamente como devem ser. NADA é removido aqui: as linhas ficam, e
    # é o fato de ficarem que torna a execução destrutiva auditável.
    #
    # O teste não precisa limpar porque cada execução usa uma aprovação
    # de identidade nova — o acúmulo não interfere entre execuções, e o
    # censo do patrimônio da E3 acima já provou que nada foi tocado.
