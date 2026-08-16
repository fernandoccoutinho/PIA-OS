"""
Integração da E4.7 — Accessibility Policy, contra PostgreSQL real.

A prova decisiva é a **composição real**: `ObjectRepository`,
`AccessibilityManager` e `CausalHistoryRepository` injetados diretamente
nas portas, sem adapter, satisfazendo-as apenas por sua forma.

Este arquivo importa os dois lados para montar a composição — permitido;
o que a fronteira veda é o import de `app.cognitive` no **código de
produção** de `app/memory`.

Não substitui por SQLite: o SQLite compila `FOR UPDATE` como no-op, e a
atomicidade da E4.7 depende de lock de linha real.
"""

import threading
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import AccessibilityState, CausalEventType
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.services.accessibility_manager import AccessibilityManager
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.database.health import check_database_health
from app.memory.errors.exceptions import (
    AccessibilityPolicyImmutableError,
    AccessibilityPolicyVersionExistsError,
    AccessibilitySubjectNotFoundError,
    AccessibilityTransitionContractViolationError,
)
from app.memory.models.governance_enums import (
    CognitiveOperation,
    GovernanceEffect,
    GovernanceOutcome,
)
from app.memory.ports.accessibility import (
    AccessibilityTransitionPort,
    CausalEvidencePort,
    CognitiveSubjectPort,
)
from app.memory.repositories.accessibility_policy_repository import (
    AccessibilityPolicyRepository,
)
from app.memory.repositories.governance_policy_repository import GovernancePolicyRepository
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository
from app.memory.schemas.accessibility import CAUSALLY_EXTINCT_TOKEN, AccessibilityRule
from app.memory.schemas.governance import GovernanceRule
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.accessibility_policy_manager import AccessibilityPolicyManager
from app.memory.services.context_manager import ContextManager
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.platform_safety_boundary import CapabilityDescriptor
from app.repositories.unit_of_work import UnitOfWork

_INICIO = datetime(2024, 1, 1, tzinfo=UTC)
_MOMENTO = datetime(2024, 6, 1, tzinfo=UTC)


def _postgres_pronto() -> bool:
    if not check_database_health().available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    return "accessibility_policies" in inspect(engine).get_table_names()


pytestmark = pytest.mark.skipif(
    not _postgres_pronto(),
    reason="PostgreSQL real indisponível ou migração da E4.7 não aplicada.",
)


def _compor(session):
    """Composição real, sobre a MESMA `Session`.

    A partilha da sessão é o que faz o lock adquirido em
    `refresh_for_update()` valer até a escrita do
    `AccessibilityManager` — sem ela, a atomicidade não existiria.
    """
    objetos = ObjectRepository(session)
    return AccessibilityPolicyManager(
        objetos,
        AccessibilityManager(objetos),
        CausalHistoryRepository(session),
        AccessibilityPolicyRepository(session),
        GovernanceManager(GovernancePolicyRepository(session)),
        ContextManager(MemoryDomainRepository(session)),
    )


def _descritor(operation=None) -> CapabilityDescriptor:
    return CapabilityDescriptor(operation=operation or CognitiveOperation.ACCESSIBILITY_TRANSITION)


def _chaves() -> tuple[str, str]:
    sufixo = uuid.uuid4().hex[:8]
    return f"gov-{sufixo}", f"acc-{sufixo}"


def _publicar(
    gk: str,
    ak: str,
    *,
    governanca: GovernanceEffect = GovernanceEffect.ADMIT,
    regras: tuple[AccessibilityRule, ...] | None = None,
    com_governanca: bool = True,
) -> None:
    # Uma aresta por regra (corretivo E4.7.1): o conjunto anterior era
    # ele próprio uma regra cartesiana. Três destinos exigem três regras.
    padrao = tuple(
        AccessibilityRule(
            rule_id=f"r-{destino}",
            effect=GovernanceEffect.ADMIT,
            source_states=frozenset({"active"}),
            target_states=frozenset({destino}),
        )
        for destino in ("latent", "inaccessible", CAUSALLY_EXTINCT_TOKEN)
    )
    with UnitOfWork() as uow:
        if com_governanca:
            GovernancePolicyRepository(uow.session).add_policy(
                policy_key=gk,
                version=1,
                rules=(
                    GovernanceRule(
                        rule_id="g1",
                        effect=governanca,
                        operations=frozenset({CognitiveOperation.ACCESSIBILITY_TRANSITION}),
                    ),
                ),
                effective_from=_INICIO,
            )
        AccessibilityPolicyRepository(uow.session).add_policy(
            policy_key=ak,
            version=1,
            governance_policy_key=gk,
            rules=regras if regras is not None else padrao,
            effective_from=_INICIO,
        )
        uow.commit()


def _criar_objeto(estado: AccessibilityState = AccessibilityState.ACTIVE) -> uuid.UUID:
    with UnitOfWork() as uow:
        objetos = ObjectRepository(uow.session)
        objeto = objetos.add(CognitiveObject())
        if estado is not AccessibilityState.ACTIVE:
            objeto.accessibility = estado
            objetos.update(objeto)
        uow.commit()
        return objeto.id


def _estado(coid: uuid.UUID) -> str:
    with UnitOfWork() as uow:
        objeto = ObjectRepository(uow.session).get_by_id(coid, include_deleted=True)
        return objeto.accessibility.value


def _censo(coid: uuid.UUID) -> tuple:
    with UnitOfWork() as uow:
        return tuple(
            uow.session.execute(
                sa.text(
                    "SELECT clid, revision_status, deleted_at FROM cognitive_objects "
                    "WHERE id = :c"
                ),
                {"c": str(coid)},
            ).one()
        )


def _limpar(coids: list[uuid.UUID], chaves: list[str]) -> None:
    with UnitOfWork() as uow:
        s = uow.session
        if coids:
            alvos = [str(c) for c in coids]
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
                sa.text("DELETE FROM cognitive_objects WHERE id = ANY(:c ::uuid[])"),
                {"c": alvos},
            )
        if chaves:
            s.execute(
                sa.text("DELETE FROM governance_policies WHERE policy_key = ANY(:k ::text[])"),
                {"k": chaves},
            )
            s.execute(
                sa.text("DELETE FROM accessibility_policies WHERE policy_key = ANY(:k ::text[])"),
                {"k": chaves},
            )
        uow.commit()


def _transicionar(session, coid, alvo, gk, ak, **kw):
    return _compor(session).transition(
        coid=coid,
        target_state=alvo,
        context=kw.pop("context", MemoryContext()),
        descriptor=kw.pop("descriptor", _descritor()),
        governance_policy_key=gk,
        accessibility_policy_key=ak,
        moment=kw.pop("moment", _MOMENTO),
        **kw,
    )


# --- Composição real ---------------------------------------------------


def test_ai1_real_e3_objects_are_injected_directly_into_the_ports():
    with UnitOfWork() as uow:
        objetos = ObjectRepository(uow.session)
        assert isinstance(objetos, CognitiveSubjectPort)
        assert isinstance(AccessibilityManager(objetos), AccessibilityTransitionPort)
        assert isinstance(CausalHistoryRepository(uow.session), CausalEvidencePort)


def test_ai2_admitted_transition_writes_through_the_sanctioned_manager():
    gk, ak = _chaves()
    _publicar(gk, ak)
    coid = _criar_objeto()
    try:
        censo_antes = _censo(coid)
        with UnitOfWork() as uow:
            resultado = _transicionar(uow.session, coid, "latent", gk, ak)
            uow.commit()
        assert resultado.state_changed is True
        assert resultado.observed_state == "latent"
        assert resultado.decision is not None
        assert resultado.decision.policy_key == ak
        assert resultado.decision.policy_version == 1
        assert _estado(coid) == "latent"
        # identidade e patrimônio intocados
        assert _censo(coid) == censo_antes
    finally:
        _limpar([coid], [gk, ak])


# --- Autoridade --------------------------------------------------------


def test_ai3_governance_deny_blocks_and_writes_nothing():
    gk, ak = _chaves()
    _publicar(gk, ak, governanca=GovernanceEffect.DENY)
    coid = _criar_objeto()
    try:
        with UnitOfWork() as uow:
            resultado = _transicionar(uow.session, coid, "latent", gk, ak)
            uow.commit()
        assert resultado.governance_resolution.outcome is GovernanceOutcome.INADMISSIBLE
        assert resultado.state_changed is False
        assert resultado.decision is None
        assert _estado(coid) == "active"
    finally:
        _limpar([coid], [gk, ak])


def test_ai4_wildcard_governance_policy_does_not_authorize_the_transition():
    """A E4.3.3 em ação: policy antiga com curinga não alcança a nova
    operação, e sem opt-in explícito nada é transicionado."""
    gk, ak = _chaves()
    with UnitOfWork() as uow:
        GovernancePolicyRepository(uow.session).add_policy(
            policy_key=gk,
            version=1,
            rules=(
                GovernanceRule(
                    rule_id="curinga",
                    effect=GovernanceEffect.ADMIT,
                    operations=frozenset(),
                ),
            ),
            effective_from=_INICIO,
        )
        uow.commit()
    _publicar(gk, ak, com_governanca=False)
    coid = _criar_objeto()
    try:
        with UnitOfWork() as uow:
            resultado = _transicionar(uow.session, coid, "latent", gk, ak)
            uow.commit()
        assert resultado.governance_resolution.outcome is GovernanceOutcome.NOT_APPLICABLE
        assert resultado.state_changed is False
        assert _estado(coid) == "active"
    finally:
        _limpar([coid], [gk, ak])


def test_ai5_wrong_operation_never_reaches_the_subject():
    gk, ak = _chaves()
    _publicar(gk, ak)
    coid = _criar_objeto()
    try:
        with UnitOfWork() as uow, pytest.raises(ValueError, match="ACCESSIBILITY_TRANSITION"):
            _transicionar(
                uow.session,
                coid,
                "latent",
                gk,
                ak,
                descriptor=_descritor(CognitiveOperation.TRANSFORM),
            )
        assert _estado(coid) == "active"
    finally:
        _limpar([coid], [gk, ak])


# --- Policy ------------------------------------------------------------


def test_ai6_no_matching_rule_is_not_applicable_and_writes_nothing():
    gk, ak = _chaves()
    _publicar(
        gk,
        ak,
        regras=(
            AccessibilityRule(
                rule_id="r1",
                effect=GovernanceEffect.ADMIT,
                source_states=frozenset({"latent"}),
                target_states=frozenset({"inaccessible"}),
            ),
        ),
    )
    coid = _criar_objeto()
    try:
        with UnitOfWork() as uow:
            resultado = _transicionar(uow.session, coid, "latent", gk, ak)
            uow.commit()
        assert resultado.decision is not None
        assert resultado.decision.outcome is GovernanceOutcome.NOT_APPLICABLE
        assert _estado(coid) == "active"
    finally:
        _limpar([coid], [gk, ak])


def test_ai7_deny_overrides_admit_in_the_accessibility_policy():
    gk, ak = _chaves()
    _publicar(
        gk,
        ak,
        regras=(
            AccessibilityRule(
                rule_id="admite",
                effect=GovernanceEffect.ADMIT,
                source_states=frozenset({"active"}),
                target_states=frozenset({"latent"}),
            ),
            AccessibilityRule(
                rule_id="nega",
                effect=GovernanceEffect.DENY,
                source_states=frozenset({"active"}),
                target_states=frozenset({"latent"}),
            ),
        ),
    )
    coid = _criar_objeto()
    try:
        with UnitOfWork() as uow:
            resultado = _transicionar(uow.session, coid, "latent", gk, ak)
            uow.commit()
        assert resultado.decision is not None
        assert resultado.decision.outcome is GovernanceOutcome.INADMISSIBLE
        assert resultado.decision.matched_rule_id == "nega"
        assert _estado(coid) == "active"
    finally:
        _limpar([coid], [gk, ak])


def test_ai8_published_version_is_immutable():
    gk, ak = _chaves()
    _publicar(gk, ak)
    try:
        with UnitOfWork() as uow:
            repo = AccessibilityPolicyRepository(uow.session)
            publicada = repo.get_version(ak, 1)
            with pytest.raises(AccessibilityPolicyImmutableError):
                repo.update(publicada)
            with pytest.raises(AccessibilityPolicyImmutableError):
                repo.delete(publicada)

        # e também pelo caminho ORM, contornando o repositório
        with pytest.raises(AccessibilityPolicyImmutableError), UnitOfWork() as uow:
            publicada = AccessibilityPolicyRepository(uow.session).get_version(ak, 1)
            publicada.governance_policy_key = "outra"
            uow.commit()
    finally:
        _limpar([], [gk, ak])


def test_ai9_duplicate_version_is_refused():
    gk, ak = _chaves()
    _publicar(gk, ak)
    try:
        with pytest.raises(AccessibilityPolicyVersionExistsError), UnitOfWork() as uow:
            AccessibilityPolicyRepository(uow.session).add_policy(
                policy_key=ak, version=1, governance_policy_key=gk
            )
            uow.commit()
    finally:
        _limpar([], [gk, ak])


def test_ai10_concurrent_version_publication_yields_exactly_one():
    """A autoridade é o `UNIQUE`, não a pré-checagem."""
    gk, ak = _chaves()
    _publicar(gk, ak)
    sucessos: list[int] = []
    conflitos: list[int] = []
    barreira = threading.Barrier(2, timeout=30)

    def _publicar_v2() -> None:
        try:
            with UnitOfWork() as uow:
                repo = AccessibilityPolicyRepository(uow.session)
                barreira.wait()
                repo.add_policy(policy_key=ak, version=2, governance_policy_key=gk)
                uow.commit()
                sucessos.append(2)
        except AccessibilityPolicyVersionExistsError:
            conflitos.append(2)
        except Exception:  # noqa: BLE001 - conflito de integridade equivale a recusa
            conflitos.append(2)

    threads = [threading.Thread(target=_publicar_v2) for _ in range(2)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        assert len(sucessos) == 1, f"esperado exatamente um sucesso: {sucessos}"
        assert len(conflitos) == 1
        with UnitOfWork() as uow:
            total = uow.session.execute(
                sa.text(
                    "SELECT count(*) FROM accessibility_policies "
                    "WHERE policy_key = :k AND version = 2"
                ),
                {"k": ak},
            ).scalar_one()
        assert total == 1
    finally:
        _limpar([], [gk, ak])


# --- No-op, soft delete, ausência --------------------------------------


def test_ai11_no_op_does_not_write_and_does_not_fabricate_anything():
    gk, ak = _chaves()
    _publicar(gk, ak)
    coid = _criar_objeto()
    try:
        with UnitOfWork() as uow:
            resultado = _transicionar(uow.session, coid, "active", gk, ak)
            uow.commit()
        assert resultado.no_change is True
        assert resultado.decision is None
        assert resultado.causal_event_id is None
        assert _estado(coid) == "active"
        with UnitOfWork() as uow:
            eventos = uow.session.execute(
                sa.text("SELECT count(*) FROM causal_histories WHERE subject_coid = :c"),
                {"c": str(coid)},
            ).scalar_one()
        assert eventos == 0, "no-op fabricou história causal"
    finally:
        _limpar([coid], [gk, ak])


def test_ai12_soft_deleted_subject_is_not_revived_and_deleted_at_is_untouched():
    """`SOFT_DELETED != NEVER EXISTED`, e a E4.7 nunca reverte exclusão."""
    gk, ak = _chaves()
    _publicar(gk, ak)
    coid = _criar_objeto()
    try:
        with UnitOfWork() as uow:
            objetos = ObjectRepository(uow.session)
            objetos.soft_delete(objetos.get_by_id(coid))
            uow.commit()
        with UnitOfWork() as uow:
            apagado_em = (
                ObjectRepository(uow.session).get_by_id(coid, include_deleted=True).deleted_at
            )
        assert apagado_em is not None

        with UnitOfWork() as uow:
            resultado = _transicionar(uow.session, coid, "latent", gk, ak)
            uow.commit()

        assert resultado.state_changed is True
        assert _estado(coid) == "latent"
        with UnitOfWork() as uow:
            ainda = ObjectRepository(uow.session).get_by_id(coid, include_deleted=True)
            assert ainda.deleted_at == apagado_em, "deleted_at foi alterado"
            assert ObjectRepository(uow.session).get_by_id(coid) is None
    finally:
        _limpar([coid], [gk, ak])


def test_ai13_absent_subject_has_its_own_diagnostic():
    gk, ak = _chaves()
    _publicar(gk, ak)
    try:
        with UnitOfWork() as uow, pytest.raises(AccessibilitySubjectNotFoundError) as exc:
            _transicionar(uow.session, uuid.uuid4(), "latent", gk, ak)
        assert exc.value.code == "PIA-8038"
    finally:
        _limpar([], [gk, ak])


# --- CAUSALLY_EXTINCT --------------------------------------------------


def test_ai14_extinction_requires_a_real_event_of_the_same_subject():
    gk, ak = _chaves()
    _publicar(gk, ak)
    coid = _criar_objeto()
    outro = _criar_objeto()
    try:
        with UnitOfWork() as uow:
            causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
            evento_proprio = causal.record(subject_coid=coid, event_type=CausalEventType.CREATED)
            evento_alheio = causal.record(subject_coid=outro, event_type=CausalEventType.CREATED)
            uow.commit()
            id_proprio, id_alheio = evento_proprio.id, evento_alheio.id

        # sem evento
        with UnitOfWork() as uow, pytest.raises(AccessibilityTransitionContractViolationError):
            _transicionar(uow.session, coid, CAUSALLY_EXTINCT_TOKEN, gk, ak, reason="fim")
        assert _estado(coid) == "active"

        # evento inexistente
        with UnitOfWork() as uow, pytest.raises(AccessibilityTransitionContractViolationError):
            _transicionar(
                uow.session,
                coid,
                CAUSALLY_EXTINCT_TOKEN,
                gk,
                ak,
                reason="fim",
                causal_event_id=uuid.uuid4(),
            )
        assert _estado(coid) == "active"

        # evento de outro sujeito
        with (
            UnitOfWork() as uow,
            pytest.raises(AccessibilityTransitionContractViolationError) as exc,
        ):
            _transicionar(
                uow.session,
                coid,
                CAUSALLY_EXTINCT_TOKEN,
                gk,
                ak,
                reason="fim",
                causal_event_id=id_alheio,
            )
        # A mensagem passou a nomear a divergência exata (corretivo
        # E4.7.1): a história devolvida pertence a outro sujeito.
        assert any("história" in m for m in exc.value.reasons)
        assert _estado(coid) == "active"

        # evento real do mesmo sujeito
        eventos_antes = _contar_eventos(coid)
        with UnitOfWork() as uow:
            resultado = _transicionar(
                uow.session,
                coid,
                CAUSALLY_EXTINCT_TOKEN,
                gk,
                ak,
                reason="fim",
                causal_event_id=id_proprio,
            )
            uow.commit()
        assert resultado.state_changed is True
        assert resultado.causal_event_id == id_proprio
        assert _estado(coid) == CAUSALLY_EXTINCT_TOKEN
        # nenhum evento criado pela E4.7, e a história anterior intacta
        assert _contar_eventos(coid) == eventos_antes
    finally:
        _limpar([coid, outro], [gk, ak])


def _contar_eventos(coid: uuid.UUID) -> int:
    with UnitOfWork() as uow:
        return uow.session.execute(
            sa.text(
                "SELECT count(*) FROM causal_history_events e "
                "JOIN causal_histories h ON h.id = e.history_id "
                "WHERE h.subject_coid = :c"
            ),
            {"c": str(coid)},
        ).scalar_one()


def test_ai15_extinct_object_still_exists_historically():
    """`CAUSALLY_EXTINCT != HISTORICAL_ERASURE`."""
    gk, ak = _chaves()
    _publicar(gk, ak)
    coid = _criar_objeto()
    try:
        with UnitOfWork() as uow:
            evento = CausalHistoryManager(CausalHistoryRepository(uow.session)).record(
                subject_coid=coid, event_type=CausalEventType.CREATED
            )
            uow.commit()
            evento_id = evento.id
        with UnitOfWork() as uow:
            _transicionar(
                uow.session,
                coid,
                CAUSALLY_EXTINCT_TOKEN,
                gk,
                ak,
                reason="fim",
                causal_event_id=evento_id,
            )
            uow.commit()
        with UnitOfWork() as uow:
            existe = uow.session.execute(
                sa.text("SELECT count(*) FROM cognitive_objects WHERE id = :c"),
                {"c": str(coid)},
            ).scalar_one()
        assert existe == 1
        assert _contar_eventos(coid) == 1
    finally:
        _limpar([coid], [gk, ak])


# --- Atomicidade e concorrência ----------------------------------------


def test_ai16_rollback_by_omission_leaves_the_state_untouched():
    gk, ak = _chaves()
    _publicar(gk, ak)
    coid = _criar_objeto()
    try:
        with UnitOfWork() as uow:
            resultado = _transicionar(uow.session, coid, "latent", gk, ak)
            # sem uow.commit()
        assert resultado.state_changed is True
        assert _estado(coid) == "active", "escrita sobreviveu ao rollback"
    finally:
        _limpar([coid], [gk, ak])


def test_ai17_concurrent_transitions_are_serialized_by_the_row_lock():
    """A prova da Tensão D contra o banco real.

    Duas transações pedem transições **diferentes** a partir de
    `active`. O lock adquirido antes da avaliação impede que a segunda
    avalie sobre um estado que já mudou:

        PRE-LOCK SOURCE STATE != AUTHORIZED WRITE PRECONDITION
        LAST-WRITE-WINS != VALID TRANSITION

    A segunda transação observa o estado já commitado pela primeira, e
    como a regra publicada só admite `active → …`, ela resulta em
    `NOT_APPLICABLE` — nunca numa escrita autorizada sobre a transição
    errada.
    """
    gk, ak = _chaves()
    _publicar(gk, ak)
    coid = _criar_objeto()
    resultados: list[tuple[str, bool, str]] = []
    erros: list[BaseException] = []
    barreira = threading.Barrier(2, timeout=30)

    def _executar(alvo: str) -> None:
        try:
            with UnitOfWork() as uow:
                manager = _compor(uow.session)
                barreira.wait()
                r = manager.transition(
                    coid=coid,
                    target_state=alvo,
                    context=MemoryContext(),
                    descriptor=_descritor(),
                    governance_policy_key=gk,
                    accessibility_policy_key=ak,
                    moment=_MOMENTO,
                )
                uow.commit()
                origem = r.decision.source_state if r.decision else "n/a"
                resultados.append((alvo, r.state_changed, origem))
        except BaseException as exc:  # noqa: BLE001
            erros.append(exc)

    threads = [
        threading.Thread(target=_executar, args=("latent",)),
        threading.Thread(target=_executar, args=("inaccessible",)),
    ]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert erros == [], f"transição concorrente falhou: {erros}"
        assert len(resultados) == 2
        mudaram = [r for r in resultados if r[1]]
        assert len(mudaram) == 1, f"exatamente uma deveria escrever: {resultados}"

        # a que não escreveu observou o estado JÁ alterado, não `active`
        nao_mudou = [r for r in resultados if not r[1]][0]
        assert (
            nao_mudou[2] != "active"
        ), "a segunda transação avaliou sobre um estado obsoleto — TOCTOU"
        assert _estado(coid) == mudaram[0][0]
    finally:
        _limpar([coid], [gk, ak])


# --- Guardas -----------------------------------------------------------


def test_ai18_evaluation_path_writes_nothing_when_denied():
    gk, ak = _chaves()
    _publicar(gk, ak, governanca=GovernanceEffect.DENY)
    coid = _criar_objeto()
    try:
        escritas: list[str] = []

        def _contar(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                escritas.append(statement)

        with UnitOfWork() as uow:
            engine = uow.session.get_bind()
            sa.event.listen(engine, "before_cursor_execute", _contar)
            try:
                _transicionar(uow.session, coid, "latent", gk, ak)
                assert not uow.session.dirty
                uow.session.flush()
            finally:
                sa.event.remove(engine, "before_cursor_execute", _contar)
        assert escritas == []
    finally:
        _limpar([coid], [gk, ak])


def test_ai19_no_schema_orm_drift():
    import app.cognitive.models  # noqa: F401
    import app.memory.models  # noqa: F401
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.database.base import Base
    from app.database.engine import engine

    with engine.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    reais = [d for d in diferencas if "test_" not in str(d)]
    assert reais == [], f"schema/ORM drift: {reais}"


def test_ai20_migration_head_is_the_new_one_and_single():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    assert tuple(heads) == ("7b2e4c9a15df",), f"migration head: {heads}"


def test_ai21_no_new_column_on_cognitive_object():
    """A E4.7 não cria um segundo lugar onde o estado viva."""
    from sqlalchemy import inspect

    from app.database.engine import engine

    colunas = {c["name"] for c in inspect(engine).get_columns("cognitive_objects")}
    for proibida in ("accessibility_policy_key", "accessibility_policy_version"):
        assert proibida not in colunas
    assert "accessibility" in colunas


def test_ai22_repository_validates_its_arguments():
    gk, ak = _chaves()
    try:
        with UnitOfWork() as uow:
            repo = AccessibilityPolicyRepository(uow.session)
            for kwargs, trecho in (
                ({"policy_key": "  ", "version": 1, "governance_policy_key": gk}, "policy_key"),
                (
                    {"policy_key": ak, "version": 1, "governance_policy_key": "  "},
                    "governance_policy_key",
                ),
                ({"policy_key": ak, "version": 0, "governance_policy_key": gk}, "version"),
                (
                    {
                        "policy_key": ak,
                        "version": 1,
                        "governance_policy_key": gk,
                        "effective_from": _MOMENTO,
                        "effective_until": _INICIO,
                    },
                    "effective_until",
                ),
            ):
                with pytest.raises(ValueError, match=trecho):
                    repo.add_policy(**kwargs)
    finally:
        _limpar([], [gk, ak])


def test_ai23_repository_lookup_helpers_behave():
    gk, ak = _chaves()
    _publicar(gk, ak)
    try:
        with UnitOfWork() as uow:
            repo = AccessibilityPolicyRepository(uow.session)
            assert repo.get_version(ak, 1) is not None
            assert repo.get_version(ak, 99) is None
            assert repo.max_version(ak) == 1
            assert repo.max_version("inexistente") == 0
            # fora da vigência declarada
            assert repo.effective_version_at(ak, datetime(2023, 1, 1, tzinfo=UTC)) is None
            with pytest.raises(AccessibilityPolicyImmutableError):
                repo.delete_by_id(repo.get_version(ak, 1).id)
    finally:
        _limpar([], [gk, ak])


def test_ai24_effective_window_selects_the_right_version():
    """`[from, until)` — limite final exclusivo."""
    gk, ak = _chaves()
    _publicar(gk, ak)
    try:
        with UnitOfWork() as uow:
            AccessibilityPolicyRepository(uow.session).add_policy(
                policy_key=ak,
                version=2,
                governance_policy_key=gk,
                rules=(
                    AccessibilityRule(
                        rule_id="r2",
                        effect=GovernanceEffect.DENY,
                        source_states=frozenset({"active"}),
                        target_states=frozenset({"latent"}),
                    ),
                ),
                effective_from=_MOMENTO,
            )
            uow.commit()
        # Leitura DENTRO da sessão: instâncias ORM saem detached quando a
        # UnitOfWork fecha, e tocar um atributo depois disso dispara
        # DetachedInstanceError. Mesma lição da E4.5.
        with UnitOfWork() as uow:
            repo = AccessibilityPolicyRepository(uow.session)
            antes = repo.effective_version_at(ak, datetime(2024, 3, 1, tzinfo=UTC))
            depois = repo.effective_version_at(ak, datetime(2024, 9, 1, tzinfo=UTC))
            assert antes is not None
            assert depois is not None
            assert antes.version == 1
            assert depois.version == 2
    finally:
        _limpar([], [gk, ak])
