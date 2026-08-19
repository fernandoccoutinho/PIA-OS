"""
Integração real da aprovação persistente (`E4.9.9.a`).

```text
clock_timestamp()  autoridade temporal
UPDATE ... WHERE ... RETURNING   comando único
ZERO_BY_PROOF != ZERO_BY_CONSTRUCTION_FAILURE
```

Estes testes exigem PostgreSQL: `clock_timestamp()`, as três triggers e os
`CHECK` condicionados ao `kind` não existem em SQLite.

**Sem `sleep` e sem probabilidade.** A concorrência é sincronizada por
barreira real (`threading.Barrier`) e os instantes são preparados no
banco, não esperados no relógio da aplicação.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.memory.errors.exceptions import (
    ApprovalRecordNotUsableError,
    ApprovalRecordPersistedRowInvalidError,
)
from app.memory.models.approval_enums import (
    AssuranceLevel,
    DestructiveOperation,
    ImpactVolumeKind,
    InputChannel,
    VoiceReviewState,
)
from app.memory.models.approval_lifecycle_enums import (
    ApprovalLifecycleState,
    ApprovalUsageRefusalReason,
)
from app.memory.models.approval_record import ApprovalRecord
from app.memory.models.erasure_enums import ErasureTargetClass
from app.memory.models.governance_enums import GovernanceOutcome
from app.memory.models.target_resolution_enums import (
    LegacyProtectionState,
    ReferenceOrigin,
)
from app.memory.repositories.approval_record_repository import (
    ApprovalRecordRepository,
)
from app.memory.schemas.destructive_approval import (
    OPERACAO_DE_GOVERNANCA,
    ApprovalContext,
    DestructiveApprovalEnvelope,
    DestructiveApprovalProposal,
    IdentityEvidence,
    PresentedImpact,
    SafeTargetSnapshot,
    SafeVoiceProvenance,
)
from app.memory.schemas.erasure_target import (
    ControlScope,
    CustodyNamespace,
    ReferenceProvenance,
)
from app.memory.schemas.governance import GovernanceResolution

TENANT = uuid.UUID("00000000-0000-0000-0000-00000000cc01")
WORKSPACE = uuid.UUID("00000000-0000-0000-0000-00000000cc02")
DOMINIO = uuid.UUID("00000000-0000-0000-0000-00000000cc03")
PRINCIPAL = "principal:humano-1"
FINALIDADE = "purpose:remocao-titular"


def _available() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _available(),
    reason="PostgreSQL real indisponível — E4.9.9.a exige clock_timestamp e triggers.",
)


@pytest.fixture(autouse=True)
def _clean():
    migrations.upgrade("head")
    _truncate()
    yield
    _truncate()


def _truncate() -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE approval_records CASCADE"))


# ----------------------------------------------------------------------
# Envelopes — todos integralmente válidos pelos construtores públicos
# ----------------------------------------------------------------------


def envelope(
    *,
    operacao: DestructiveOperation = DestructiveOperation.PERMANENT_ERASURE,
    assurance: AssuranceLevel = AssuranceLevel.STEP_UP_VERIFIED,
    canal: InputChannel = InputChannel.TEXT,
    revisao: VoiceReviewState = VoiceReviewState.NOT_APPLICABLE,
    approval_id: uuid.UUID | None = None,
    nonce: uuid.UUID | None = None,
    janela: timedelta = timedelta(hours=8),
    alvos: tuple[SafeTargetSnapshot, ...] | None = None,
    constraints: tuple[str, ...] = ("preservar rastro causal",),
) -> DestructiveApprovalEnvelope:
    """`ALTERNATIVE_ENVELOPE != PATCHED_INVALID_STATE`.

    Toda variante usada nos testes de divergência é um envelope que a
    E4.9.8.1 aceitaria por si — nenhum `object.__setattr__`, monkeypatch
    ou bypass de validação.
    """
    agora = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    alvos = alvos or (
        SafeTargetSnapshot(
            ErasureTargetClass.PIA_MANAGED_ARTIFACT,
            uuid.UUID("00000000-0000-0000-0000-00000000dd01"),
            ControlScope(WORKSPACE, TENANT, PRINCIPAL),
            CustodyNamespace("pia-storage", "workspace/w1/a"),
            ReferenceProvenance(ReferenceOrigin.OUTPUT_REFS, 0),
            LegacyProtectionState.PROTECTED,
            'W/"v1"',
        ),
        SafeTargetSnapshot(
            ErasureTargetClass.PIA_MANAGED_ARTIFACT,
            uuid.UUID("00000000-0000-0000-0000-00000000dd02"),
            ControlScope(WORKSPACE, TENANT, PRINCIPAL),
            CustodyNamespace("pia-storage", "workspace/w1/b"),
            ReferenceProvenance(ReferenceOrigin.OUTPUT_REFS, 1),
            LegacyProtectionState.NOT_PROTECTED,
            None,
        ),
    )
    contexto = ApprovalContext(TENANT, WORKSPACE, DOMINIO, FINALIDADE)
    proveniencia = SafeVoiceProvenance(canal, revisao)
    resolucao = GovernanceResolution(
        outcome=GovernanceOutcome.ADMISSIBLE,
        operation=OPERACAO_DE_GOVERNANCA[operacao],
        context_domain_ids=(DOMINIO,),
        context_actor_ref=PRINCIPAL,
        context_purpose=FINALIDADE,
        safety_boundary_version=1,
        safety_rationale="titular pediu remoção",
        policy_key="ret.default",
        policy_version=1,
        policy_id=uuid.UUID("00000000-0000-0000-0000-00000000ee01"),
        matched_rule_id="rule-1",
        admissible_alternatives=("mover para lixeira",),
        constraints=constraints,
        declared_preservations=("registro histórico",),
        declared_losses=("conteúdo do artefato",),
    )
    proposta = DestructiveApprovalProposal(
        operation=operacao,
        targets=alvos,
        impact=PresentedImpact(len(alvos), ImpactVolumeKind.KNOWN, 4096),
        governance_resolution=resolucao,
        context=contexto,
        provenance=proveniencia,
        blockers=(),
        materialized_at=agora,
    )
    return DestructiveApprovalEnvelope(
        proposal=proposta,
        approval_id=approval_id or uuid.uuid4(),
        nonce=nonce or uuid.uuid4(),
        identity=IdentityEvidence(PRINCIPAL, assurance, agora),
        context=contexto,
        provenance=proveniencia,
        issued_at=agora,
        confirmed_at=agora,
        expires_at=agora + janela,
    )


def _persistir(e: DestructiveApprovalEnvelope) -> None:
    with Session(engine) as sessao:
        ApprovalRecordRepository(sessao).append_approved(e)
        sessao.commit()


def _estado(approval_id: uuid.UUID) -> ApprovalLifecycleState:
    with Session(engine) as sessao:
        registro = sessao.get(ApprovalRecord, approval_id)
        assert registro is not None
        return registro.state


# ======================================================================
# Persistência e reconstituição
# ======================================================================


def test_i01_envelope_persiste_e_reconstroi_identico():
    e = envelope()
    _persistir(e)
    with Session(engine) as sessao:
        volta = ApprovalRecordRepository(sessao).get_materialized(e.approval_id)
    assert volta == e


def test_i02_reconstituicao_preserva_ordem_protecao_e_versao():
    e = envelope()
    _persistir(e)
    with Session(engine) as sessao:
        volta = ApprovalRecordRepository(sessao).get_materialized(e.approval_id)
    assert volta is not None
    assert [t.subject_coid for t in volta.proposal.targets] == [
        t.subject_coid for t in e.proposal.targets
    ]
    assert [t.legacy_protection_state for t in volta.proposal.targets] == [
        LegacyProtectionState.PROTECTED,
        LegacyProtectionState.NOT_PROTECTED,
    ]
    assert [t.version_etag for t in volta.proposal.targets] == ['W/"v1"', None]


def test_i03_as_seis_tuplas_de_governanca_voltam_ordenadas():
    e = envelope(constraints=("c1", "c2", "c3"))
    _persistir(e)
    with Session(engine) as sessao:
        volta = ApprovalRecordRepository(sessao).get_materialized(e.approval_id)
    assert volta is not None
    r = volta.proposal.governance_resolution
    assert r.constraints == ("c1", "c2", "c3")
    assert r.context_domain_ids == (DOMINIO,)
    assert r.declared_losses == ("conteúdo do artefato",)
    for valor in (
        r.context_domain_ids,
        r.constraints,
        r.admissible_alternatives,
        r.declared_preservations,
        r.declared_losses,
        r.blocked_capabilities,
    ):
        assert isinstance(valor, tuple), "list do ORM não pode escapar"


def test_i04_registro_ausente_devolve_none():
    with Session(engine) as sessao:
        assert ApprovalRecordRepository(sessao).get_materialized(uuid.uuid4()) is None


def test_i05_linha_invalida_falha_de_modo_tipado():
    """`INVALID_ROW != USABLE_APPROVAL`.

    A linha é corrompida por SQL bruto numa coluna que a trigger permite
    (a de item de governança é imutável, então a corrupção vai numa
    inserção direta com valor que o contrato público recusa).
    """
    e = envelope()
    _persistir(e)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO approval_record_governance_items "
                "(id, approval_record_id, kind, position, value_text, "
                " created_at, updated_at) VALUES "
                "(:i, :r, 'CONSTRAINT', 99, '   ', now(), now())"
            ),
            {"i": uuid.uuid4(), "r": e.approval_id},
        )
    with Session(engine) as sessao, pytest.raises(ApprovalRecordPersistedRowInvalidError):
        ApprovalRecordRepository(sessao).get_materialized(e.approval_id)


# ======================================================================
# Consumo, revogação e binding completo
# ======================================================================


def test_i06_consumo_marca_estado_e_instante():
    e = envelope()
    _persistir(e)
    with Session(engine) as sessao:
        registro = ApprovalRecordRepository(sessao).consume_once(e)
        estado, consumido, revogado = (
            registro.state,
            registro.consumed_at,
            registro.revoked_at,
        )
        sessao.commit()
    assert estado is ApprovalLifecycleState.CONSUMED
    assert consumido is not None
    assert revogado is None


def test_i07_segundo_uso_apos_commit_e_recusado():
    """Replay depois de commit, em **sessão nova**."""
    e = envelope()
    _persistir(e)
    with Session(engine) as sessao:
        ApprovalRecordRepository(sessao).consume_once(e)
        sessao.commit()
    with Session(engine) as outra, pytest.raises(ApprovalRecordNotUsableError) as erro:
        ApprovalRecordRepository(outra).consume_once(e)
    assert erro.value.reason is ApprovalUsageRefusalReason.ALREADY_CONSUMED


def test_i08_revogacao_e_transicao_duravel_nao_remocao():
    """`REVOCATION = DURABLE_STATE_TRANSITION` · `ROW_DELETION = FORBIDDEN`."""
    e = envelope()
    _persistir(e)
    with Session(engine) as sessao:
        registro = ApprovalRecordRepository(sessao).revoke_once(e)
        estado, revogado, consumido = (
            registro.state,
            registro.revoked_at,
            registro.consumed_at,
        )
        sessao.commit()
    assert estado is ApprovalLifecycleState.REVOKED
    assert revogado is not None
    assert consumido is None
    with Session(engine) as sessao:
        assert sessao.get(ApprovalRecord, e.approval_id) is not None


def test_i09_revogada_nao_pode_ser_consumida():
    e = envelope()
    _persistir(e)
    with Session(engine) as sessao:
        ApprovalRecordRepository(sessao).revoke_once(e)
        sessao.commit()
    with Session(engine) as outra, pytest.raises(ApprovalRecordNotUsableError) as erro:
        ApprovalRecordRepository(outra).consume_once(e)
    assert erro.value.reason is ApprovalUsageRefusalReason.REVOKED


def test_i10_consumida_nao_pode_ser_revogada():
    """`CONSUMED_BEFORE_REVOCATION -> REVOCATION_CANNOT_UNDO_CONSUMPTION`."""
    e = envelope()
    _persistir(e)
    with Session(engine) as sessao:
        ApprovalRecordRepository(sessao).consume_once(e)
        sessao.commit()
    with Session(engine) as outra, pytest.raises(ApprovalRecordNotUsableError) as erro:
        ApprovalRecordRepository(outra).revoke_once(e)
    assert erro.value.reason is ApprovalUsageRefusalReason.ALREADY_CONSUMED


def test_i11_aprovacao_vencida_nunca_e_consumida():
    """A expiração é decidida por `clock_timestamp()`, não pelo chamador."""
    # Sem `sleep` e sem reescrita: a aprovação NASCE com a janela no
    # passado. `confirmed_at < expires_at` continua valendo — a janela é
    # legítima, apenas já passou quando o consumo é tentado.
    curta = _persistir_com_janela_vencida()
    with Session(engine) as sessao, pytest.raises(ApprovalRecordNotUsableError) as erro:
        ApprovalRecordRepository(sessao).consume_once(curta)
    assert erro.value.reason is ApprovalUsageRefusalReason.EXPIRED


def _persistir_com_janela_vencida() -> DestructiveApprovalEnvelope:
    """Envelope válido cuja janela já passou no instante do teste.

    `confirmed_at < expires_at` continua valendo — a janela é legítima,
    apenas está no passado.
    """
    agora = datetime.now(UTC) - timedelta(hours=2)
    e = envelope()
    from dataclasses import replace

    proposta = replace(e.proposal, materialized_at=agora)
    vencido = DestructiveApprovalEnvelope(
        proposal=proposta,
        approval_id=uuid.uuid4(),
        nonce=uuid.uuid4(),
        identity=IdentityEvidence(PRINCIPAL, AssuranceLevel.STEP_UP_VERIFIED, agora),
        context=e.context,
        provenance=e.provenance,
        issued_at=agora,
        confirmed_at=agora,
        expires_at=agora + timedelta(minutes=1),
    )
    _persistir(vencido)
    return vencido


def test_i12_vencida_ainda_pode_ser_revogada():
    """Retirar aprovação vencida é inócuo e não deve ser recusado."""
    vencida = _persistir_com_janela_vencida()
    with Session(engine) as sessao:
        registro = ApprovalRecordRepository(sessao).revoke_once(vencida)
        estado = registro.state
        sessao.commit()
    assert estado is ApprovalLifecycleState.REVOKED


# --- binding completo, com envelopes alternativos válidos ---------------


def test_i13_operacao_divergente_nao_consome():
    """Dois envelopes **legítimos** que diferem na operação.

    O persistido é apagamento definitivo; o apresentado é lixeira, com a
    governança e o assurance que a lixeira exige — ambos válidos por si.
    """
    persistido = envelope(
        operacao=DestructiveOperation.PERMANENT_ERASURE,
        assurance=AssuranceLevel.STEP_UP_VERIFIED,
    )
    _persistir(persistido)
    alternativo = envelope(
        operacao=DestructiveOperation.MOVE_TO_TRASH,
        assurance=AssuranceLevel.STEP_UP_VERIFIED,
        approval_id=persistido.approval_id,
        nonce=persistido.nonce,
    )
    with Session(engine) as sessao, pytest.raises(ApprovalRecordNotUsableError) as erro:
        ApprovalRecordRepository(sessao).consume_once(alternativo)
    assert erro.value.reason is ApprovalUsageRefusalReason.BINDING_MISMATCH
    assert _estado(persistido.approval_id) is ApprovalLifecycleState.ACTIVE


def test_i14_assurance_divergente_nao_consome():
    """Mesma operação, assurance diferente — as duas combinações válidas.

    Lixeira aceita `AUTHENTICATED` e `STEP_UP_VERIFIED`, então o par
    isola exatamente o campo em teste.
    """
    persistido = envelope(
        operacao=DestructiveOperation.MOVE_TO_TRASH,
        assurance=AssuranceLevel.STEP_UP_VERIFIED,
    )
    _persistir(persistido)
    alternativo = envelope(
        operacao=DestructiveOperation.MOVE_TO_TRASH,
        assurance=AssuranceLevel.AUTHENTICATED,
        approval_id=persistido.approval_id,
        nonce=persistido.nonce,
    )
    with Session(engine) as sessao, pytest.raises(ApprovalRecordNotUsableError) as erro:
        ApprovalRecordRepository(sessao).consume_once(alternativo)
    assert erro.value.reason is ApprovalUsageRefusalReason.BINDING_MISMATCH


def test_i15_canal_divergente_nao_consome():
    persistido = envelope()
    _persistir(persistido)
    alternativo = envelope(
        canal=InputChannel.VOICE,
        revisao=VoiceReviewState.REVIEWED_AND_CONFIRMED,
        approval_id=persistido.approval_id,
        nonce=persistido.nonce,
    )
    with Session(engine) as sessao, pytest.raises(ApprovalRecordNotUsableError) as erro:
        ApprovalRecordRepository(sessao).consume_once(alternativo)
    assert erro.value.reason is ApprovalUsageRefusalReason.BINDING_MISMATCH


def test_i16_cardinalidade_de_governanca_divergente_nao_consome():
    """Uma constraint a mais no envelope apresentado."""
    persistido = envelope(constraints=("c1",))
    _persistir(persistido)
    alternativo = envelope(
        constraints=("c1", "c2"),
        approval_id=persistido.approval_id,
        nonce=persistido.nonce,
    )
    with Session(engine) as sessao, pytest.raises(ApprovalRecordNotUsableError) as erro:
        ApprovalRecordRepository(sessao).consume_once(alternativo)
    assert erro.value.reason is ApprovalUsageRefusalReason.BINDING_MISMATCH


def test_i17_protecao_de_legado_divergente_nao_consome():
    persistido = envelope()
    _persistir(persistido)
    trocados = tuple(
        SafeTargetSnapshot(
            alvo.target_class,
            alvo.subject_coid,
            alvo.control_scope,
            alvo.custody_namespace,
            alvo.origin,
            LegacyProtectionState.NOT_PROTECTED,
            alvo.version_etag,
        )
        for alvo in persistido.proposal.targets
    )
    alternativo = envelope(
        alvos=trocados,
        approval_id=persistido.approval_id,
        nonce=persistido.nonce,
    )
    with Session(engine) as sessao, pytest.raises(ApprovalRecordNotUsableError) as erro:
        ApprovalRecordRepository(sessao).consume_once(alternativo)
    assert erro.value.reason is ApprovalUsageRefusalReason.BINDING_MISMATCH


def test_i18_ordem_do_lote_divergente_nao_consome():
    persistido = envelope()
    _persistir(persistido)
    alternativo = envelope(
        alvos=tuple(reversed(persistido.proposal.targets)),
        approval_id=persistido.approval_id,
        nonce=persistido.nonce,
    )
    with Session(engine) as sessao, pytest.raises(ApprovalRecordNotUsableError) as erro:
        ApprovalRecordRepository(sessao).consume_once(alternativo)
    assert erro.value.reason is ApprovalUsageRefusalReason.BINDING_MISMATCH


# ======================================================================
# Concorrência real — barreira, sem sleep
# ======================================================================


def _corrida(e: DestructiveApprovalEnvelope, operacoes: list[str]) -> list[str]:
    """Duas sessões independentes disputando a mesma linha."""
    barreira = threading.Barrier(len(operacoes))
    resultados: list[str] = ["" for _ in operacoes]

    def executar(indice: int, operacao: str) -> None:
        with Session(engine) as sessao:
            repo = ApprovalRecordRepository(sessao)
            barreira.wait()
            try:
                if operacao == "consume":
                    repo.consume_once(e)
                else:
                    repo.revoke_once(e)
                sessao.commit()
                resultados[indice] = f"{operacao}:WON"
            except ApprovalRecordNotUsableError as erro:
                sessao.rollback()
                resultados[indice] = f"{operacao}:{erro.reason.value}"

    fios = [threading.Thread(target=executar, args=(i, op)) for i, op in enumerate(operacoes)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join(timeout=30)
    return resultados


def test_i19_dois_consumos_concorrentes_tem_um_vencedor():
    e = envelope()
    _persistir(e)
    resultados = _corrida(e, ["consume", "consume"])
    vencedores = [r for r in resultados if r.endswith(":WON")]
    assert len(vencedores) == 1, resultados
    assert _estado(e.approval_id) is ApprovalLifecycleState.CONSUMED


def test_i20_duas_revogacoes_concorrentes_tem_um_vencedor():
    e = envelope()
    _persistir(e)
    resultados = _corrida(e, ["revoke", "revoke"])
    assert len([r for r in resultados if r.endswith(":WON")]) == 1, resultados
    assert _estado(e.approval_id) is ApprovalLifecycleState.REVOKED


def test_i21_consumo_versus_revogacao_tem_um_vencedor():
    """Disputam a mesma autoridade de estado — nunca os dois."""
    e = envelope()
    _persistir(e)
    resultados = _corrida(e, ["consume", "revoke"])
    assert len([r for r in resultados if r.endswith(":WON")]) == 1, resultados
    assert _estado(e.approval_id) in {
        ApprovalLifecycleState.CONSUMED,
        ApprovalLifecycleState.REVOKED,
    }


def test_i22_rollback_antes_do_commit_nao_queima_a_aprovacao():
    e = envelope()
    _persistir(e)
    with Session(engine) as sessao:
        ApprovalRecordRepository(sessao).consume_once(e)
        sessao.rollback()
    assert _estado(e.approval_id) is ApprovalLifecycleState.ACTIVE
    with Session(engine) as outra:
        registro = ApprovalRecordRepository(outra).consume_once(e)
        estado = registro.state
        outra.commit()
    assert estado is ApprovalLifecycleState.CONSUMED


# ======================================================================
# Proteções de banco — contra SQL bruto
# ======================================================================


def test_i23_sql_bruto_nao_altera_campo_de_binding():
    e = envelope()
    _persistir(e)
    for coluna, valor in (
        ("operation", "'MOVE_TO_TRASH'"),
        ("principal_ref", "'principal:outro'"),
        ("expires_at", "clock_timestamp() + interval '1 year'"),
        ("impact_item_count", "99"),
        ("governance_outcome", "'PROHIBITED'"),
    ):
        with pytest.raises(sa.exc.DBAPIError), engine.begin() as conn:
            conn.execute(
                sa.text(f"UPDATE approval_records SET {coluna} = {valor} WHERE id = :i"),
                {"i": e.approval_id},
            )


def test_i24_sql_bruto_nao_apaga_o_pai_nem_as_filhas():
    """`ROW_DELETION = FORBIDDEN` — a trilha de aprovação é permanente."""
    e = envelope()
    _persistir(e)
    for tabela in (
        "approval_records",
        "approval_record_targets",
        "approval_record_governance_items",
    ):
        coluna = "id" if tabela == "approval_records" else "approval_record_id"
        with pytest.raises(sa.exc.DBAPIError), engine.begin() as conn:
            conn.execute(
                sa.text(f"DELETE FROM {tabela} WHERE {coluna} = :i"),
                {"i": e.approval_id},
            )


def test_i25_sql_bruto_nao_altera_o_lote_nem_a_governanca():
    e = envelope()
    _persistir(e)
    with pytest.raises(sa.exc.DBAPIError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE approval_record_targets SET legacy_protection_state = "
                "'NOT_PROTECTED' WHERE approval_record_id = :i"
            ),
            {"i": e.approval_id},
        )
    with pytest.raises(sa.exc.DBAPIError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE approval_record_governance_items SET value_text = 'x' "
                "WHERE approval_record_id = :i"
            ),
            {"i": e.approval_id},
        )


def test_i26_transicao_a_partir_de_estado_terminal_e_recusada_no_banco():
    e = envelope()
    _persistir(e)
    with Session(engine) as sessao:
        ApprovalRecordRepository(sessao).consume_once(e)
        sessao.commit()
    with pytest.raises(sa.exc.DBAPIError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE approval_records SET state = 'REVOKED', "
                "revoked_at = clock_timestamp(), consumed_at = NULL WHERE id = :i"
            ),
            {"i": e.approval_id},
        )


def test_i27_vocabulario_de_estado_e_fechado_no_banco():
    e = envelope()
    _persistir(e)
    with pytest.raises(sa.exc.DBAPIError), engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE approval_records SET state = 'EXPIRED' WHERE id = :i"),
            {"i": e.approval_id},
        )


def test_i28_valor_incoerente_com_o_kind_e_recusado():
    """`CHECK` condicionado ao `kind`, e não coluna textual polimórfica."""
    e = envelope()
    _persistir(e)
    with pytest.raises(sa.exc.DBAPIError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO approval_record_governance_items "
                "(id, approval_record_id, kind, position, value_text, "
                " created_at, updated_at) VALUES "
                "(:i, :r, 'DOMAIN_ID', 5, 'não é uuid', now(), now())"
            ),
            {"i": uuid.uuid4(), "r": e.approval_id},
        )


def test_i29_nonce_e_unico_no_banco():
    primeiro = envelope()
    _persistir(primeiro)
    segundo = envelope(nonce=primeiro.nonce)
    with pytest.raises(sa.exc.IntegrityError), Session(engine) as sessao:
        ApprovalRecordRepository(sessao).append_approved(segundo)
        sessao.commit()


def test_i30_downgrade_e_upgrade_nao_deixam_artefato_orfao():
    # CORRIGIDO NA E4.9.9.d: o passo era RELATIVO (`-1`) e passou a
    # remover a migration errada assim que uma sucessora nasceu — o
    # mesmo defeito que a própria E4.9.9.a corrigiu em `i21`, e que
    # sobreviveu aqui.
    #
    # ```text
    # RELATIVE_STEP != NAMED_TARGET
    # ```
    #
    # O alvo passa a ser EXPLÍCITO: a revisão anterior à desta tabela.
    # Uma guarda cujo alvo se move sozinho mede outra coisa a cada fatia.
    migrations.downgrade("c8a3f5017e94")
    with engine.connect() as conn:
        gatilhos = [
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT tgname FROM pg_trigger t JOIN pg_class r ON t.tgrelid = r.oid "
                    "WHERE NOT t.tgisinternal AND r.relname LIKE 'approval%'"
                )
            )
        ]
        funcoes = [
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT proname FROM pg_proc p JOIN pg_namespace n "
                    "ON p.pronamespace = n.oid WHERE n.nspname = 'public' "
                    "AND proname LIKE '%approval%'"
                )
            )
        ]
        tabelas = [
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename LIKE 'approval%'"
                )
            )
        ]
    assert gatilhos == []
    assert funcoes == []
    assert tabelas == []
    migrations.upgrade("head")


@pytest.mark.parametrize(
    ("canal", "revisao"),
    [
        (InputChannel.TEXT, VoiceReviewState.NOT_APPLICABLE),
        (InputChannel.VOICE, VoiceReviewState.REVIEWED_AND_CONFIRMED),
    ],
)
def test_i31_texto_e_voz_tem_o_mesmo_ciclo_de_vida(canal, revisao):
    """`TEXT_GOVERNANCE = VOICE_GOVERNANCE`, também depois de persistir."""
    e = envelope(canal=canal, revisao=revisao)
    _persistir(e)
    with Session(engine) as sessao:
        registro = ApprovalRecordRepository(sessao).consume_once(e)
        estado = registro.state
        sessao.commit()
    assert estado is ApprovalLifecycleState.CONSUMED
    with Session(engine) as outra, pytest.raises(ApprovalRecordNotUsableError) as erro:
        ApprovalRecordRepository(outra).consume_once(e)
    assert erro.value.reason is ApprovalUsageRefusalReason.ALREADY_CONSUMED


def test_i32_aprovacao_inexistente_recusa_com_motivo_proprio():
    e = envelope()
    with Session(engine) as sessao, pytest.raises(ApprovalRecordNotUsableError) as erro:
        ApprovalRecordRepository(sessao).consume_once(e)
    assert erro.value.reason is ApprovalUsageRefusalReason.NOT_FOUND


def test_i33_append_exige_envelope_e_nao_dicionario():
    with Session(engine) as sessao, pytest.raises(TypeError, match="Envelope"):
        ApprovalRecordRepository(sessao).append_approved({"approval_id": uuid.uuid4()})


def test_i34_transicao_exige_envelope_completo():
    """O binding completo não se expressa em argumentos soltos."""
    with Session(engine) as sessao, pytest.raises(TypeError, match="Envelope"):
        ApprovalRecordRepository(sessao).consume_once(uuid.uuid4())
