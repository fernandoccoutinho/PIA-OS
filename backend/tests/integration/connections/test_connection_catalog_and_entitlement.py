"""
Provas do catálogo, do entitlement e da capacidade (`E7.4-1`).

```text
USER_DECLARED -> OFFICIALLY_DISCOVERED = PROIBIDO (mutação)
USER_DECLARED -> SUPERSEDED BY OFFICIALLY_DISCOVERED = OBRIGATÓRIO (sucessão)
discovery stale DEGRADA, não substitui
BENCHMARK NÃO SOBREPÕE AUTORIDADE
SUGESTÃO != EXECUÇÃO
```

Cobre as provas 16 a 25 e 30 do plano R3 que dependem de banco real. As
que são puramente estruturais (7, 10, 24, 28) vivem em
`tests/static/test_e741_connection_boundary.py` — a fronteira que não
existe é melhor provada por ausência medida do que por execução.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.connections.models.enums import (
    CapabilitySource,
    ConnectionMethod,
    ConnectionState,
    EntitlementOrigin,
    EntitlementState,
    EvidenceCategory,
    GenericEndpointType,
    SelectionMode,
)
from app.connections.repositories.connection_repository import ConnectionRepository
from app.connections.schemas.projection import (
    CapabilityView,
    ConnectionProfileView,
    EntitlementView,
    FriendlyConnectionProjection,
)
from app.connections.services.connection_profile_service import ConnectionProfileService
from app.database.engine import engine
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not check_database_health().available,
        reason="PostgreSQL real indisponível — triggers e CHECK são a prova.",
    ),
]

_AGORA = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def _limpar() -> None:
    with engine.begin() as conexao:
        for tabela in (
            "connection_execution_receipts",
            "connection_capability_snapshots",
            "connection_evaluation_evidence",
        ):
            conexao.execute(sa.text(f"ALTER TABLE {tabela} DISABLE TRIGGER USER"))
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))
            conexao.execute(sa.text(f"ALTER TABLE {tabela} ENABLE TRIGGER USER"))
        conexao.execute(sa.text("ALTER TABLE connection_entitlement_claims DISABLE TRIGGER USER"))
        conexao.execute(sa.text("DELETE FROM connection_entitlement_claims"))
        conexao.execute(sa.text("ALTER TABLE connection_entitlement_claims ENABLE TRIGGER USER"))
        for tabela in (
            "connection_profiles",
            "connection_model_releases",
            "connection_model_families",
            "connection_access_providers",
            "connection_provider_families",
        ):
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))


@pytest.fixture(autouse=True)
def _base_limpa():
    _limpar()
    yield
    _limpar()


# --- 16. família, release, provedor e conexão não colapsam ------------------


def test_e741c16_quatro_identidades_distintas_persistem_separadas() -> None:
    """Prova 16 — quatro tabelas, quatro chaves naturais, zero fusão.

    O caso interessante é o homônimo: duas famílias de provedores
    diferentes com o **mesmo** slug de família de modelo precisam
    coexistir. Unicidade global de slug faria a curadoria de um limitar a
    do outro.
    """
    with UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        fam_a = repo.add_provider_family(slug="op-a", display_name="Operador A")
        fam_b = repo.add_provider_family(slug="op-b", display_name="Operador B")
        mf_a = repo.add_model_family(provider_family_id=fam_a.id, slug="pro", display_name="Pro")
        mf_b = repo.add_model_family(provider_family_id=fam_b.id, slug="pro", display_name="Pro")
        release = repo.add_model_release(
            model_family_id=mf_a.id,
            provider_release_id="pro-2026-08-01",
            discovered_at=_AGORA,
            valid_until=_AGORA + timedelta(hours=6),
            discovery_source=CapabilitySource.OFFICIAL_DISCOVERY,
        )
        provedor = repo.add_access_provider(
            slug="gateway-x",
            display_name="Gateway X",
            endpoint_type=GenericEndpointType.OPENAI_COMPATIBLE_ENDPOINT,
        )
        ids = {mf_a.id, mf_b.id, release.id, provedor.id, fam_a.id, fam_b.id}
        uow.commit()
    assert len(ids) == 6, "duas identidades colapsaram no mesmo id"


def test_e741c17_mesmo_release_nao_se_repete_na_mesma_familia() -> None:
    """A chave natural do release é `(família, id oficial do provedor)`."""
    with UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        fam = repo.add_provider_family(slug="op", display_name="Op")
        mf = repo.add_model_family(provider_family_id=fam.id, slug="pro", display_name="Pro")
        familia_id = mf.id
        repo.add_model_release(
            model_family_id=familia_id,
            provider_release_id="r-1",
            discovered_at=_AGORA,
            valid_until=_AGORA + timedelta(hours=1),
            discovery_source=CapabilitySource.OFFICIAL_DISCOVERY,
        )
        uow.commit()

    with pytest.raises(IntegrityError), UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        repo.add_model_release(
            model_family_id=familia_id,
            provider_release_id="r-1",
            discovered_at=_AGORA + timedelta(minutes=1),
            valid_until=_AGORA + timedelta(hours=2),
            discovery_source=CapabilitySource.OFFICIAL_DISCOVERY,
        )
        uow.commit()


# --- 17 e 30. sucessão, nunca mutação ---------------------------------------


def _duas_alegacoes(principal: str = "p") -> tuple[uuid.UUID, uuid.UUID]:
    with UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        fam = repo.add_provider_family(slug="op", display_name="Op")
        declarada = repo.create_entitlement_claim(
            control_principal_ref=principal,
            provider_family_id=fam.id,
            plan_ref="plano-pago",
            origin=EntitlementOrigin.USER_DECLARED,
            claimed_at=_AGORA,
        )
        oficial = repo.create_entitlement_claim(
            control_principal_ref=principal,
            provider_family_id=fam.id,
            plan_ref="plano-pago",
            origin=EntitlementOrigin.OFFICIALLY_DISCOVERED,
            claimed_at=_AGORA + timedelta(hours=1),
        )
        ids = (declarada.id, oficial.id)
        uow.commit()
    return ids


def test_e741c18_oficial_supersede_o_declarado_preservando_origem_e_instante() -> None:
    """Provas 17 e 30 — a história mostra as duas coisas, não uma só.

    ```text
    "o usuário disse X, e depois a integração oficial confirmou X"
    ```

    Origem e instante do declarado permanecem intactos: o que muda é
    apenas o estado e o ponteiro para quem o superou.
    """
    declarada, oficial = _duas_alegacoes()
    with UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        assert repo.supersede_entitlement_claim(
            control_principal_ref="p", antecedent_id=declarada, successor_id=oficial
        )
        uow.commit()

    with engine.connect() as conexao:
        linha = conexao.execute(
            sa.text(
                "SELECT origin, state, claimed_at, plan_ref, superseded_by_id "
                "FROM connection_entitlement_claims WHERE id = :i"
            ),
            {"i": declarada},
        ).one()
    assert linha.origin == EntitlementOrigin.USER_DECLARED.value, "a origem foi mutada"
    assert linha.state == EntitlementState.SUPERSEDED.value
    assert linha.plan_ref == "plano-pago"
    assert linha.claimed_at == _AGORA
    assert linha.superseded_by_id == oficial


def test_e741c19_mutar_a_origem_declarada_e_recusado_pelo_banco() -> None:
    """O ataque chega por SQL bruto; a trigger é quem recusa.

    ACHADO DE MÉTODO, registrado. A primeira versão deste teste mudava
    só a `origin`, deixando `state = 'active'` — e a trigger recusava
    pela guarda de **transição**, não pela de payload. A recusa estava
    certa e a prova estava errada: ela media outra guarda e teria
    continuado verde com a imutabilidade do payload removida.

    ```text
    REFUSAL_BY_THE_WRONG_GUARD = UNPROVEN_INVARIANT
    ```

    A versão correta faz uma sucessão **legítima** e, no mesmo `UPDATE`,
    tenta reescrever a origem: assim a transição passa e o único motivo
    possível de recusa é a imutabilidade.
    """
    declarada, oficial = _duas_alegacoes()
    with pytest.raises(Exception, match="immutable"), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "UPDATE connection_entitlement_claims "
                "SET state = 'superseded', superseded_by_id = :s, "
                "    origin = 'officially_discovered' WHERE id = :i"
            ),
            {"s": oficial, "i": declarada},
        )


def test_e741c20_autossucessao_e_recusada() -> None:
    declarada, _ = _duas_alegacoes()
    with pytest.raises(IntegrityError), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "UPDATE connection_entitlement_claims "
                "SET state = 'superseded', superseded_by_id = id WHERE id = :i"
            ),
            {"i": declarada},
        )


def test_e741c21_um_sucessor_supera_no_maximo_um_antecedente() -> None:
    """Sem isso, um único registro oficial poderia "confirmar" várias
    alegações, e a história deixaria de dizer qual foi confirmada."""
    with UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        fam = repo.add_provider_family(slug="op", display_name="Op")
        a = repo.create_entitlement_claim(
            control_principal_ref="p",
            provider_family_id=fam.id,
            plan_ref="a",
            origin=EntitlementOrigin.USER_DECLARED,
            claimed_at=_AGORA,
        )
        b = repo.create_entitlement_claim(
            control_principal_ref="p",
            provider_family_id=fam.id,
            plan_ref="b",
            origin=EntitlementOrigin.USER_DECLARED,
            claimed_at=_AGORA,
        )
        oficial = repo.create_entitlement_claim(
            control_principal_ref="p",
            provider_family_id=fam.id,
            plan_ref="a",
            origin=EntitlementOrigin.OFFICIALLY_DISCOVERED,
            claimed_at=_AGORA + timedelta(hours=1),
        )
        ids = (a.id, b.id, oficial.id)
        uow.commit()

    with UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        assert repo.supersede_entitlement_claim(
            control_principal_ref="p", antecedent_id=ids[0], successor_id=ids[2]
        )
        uow.commit()

    with pytest.raises(IntegrityError), UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        repo.supersede_entitlement_claim(
            control_principal_ref="p", antecedent_id=ids[1], successor_id=ids[2]
        )
        uow.commit()


def test_e741c22_terminal_nao_volta_e_delete_e_recusado() -> None:
    declarada, oficial = _duas_alegacoes()
    with UnitOfWork() as uow:
        ConnectionRepository(uow.session).supersede_entitlement_claim(
            control_principal_ref="p", antecedent_id=declarada, successor_id=oficial
        )
        uow.commit()

    with pytest.raises(Exception, match="terminal"), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "UPDATE connection_entitlement_claims "
                "SET state = 'active', superseded_by_id = NULL WHERE id = :i"
            ),
            {"i": declarada},
        )
    with pytest.raises(Exception, match="not deletable"), engine.begin() as conexao:
        conexao.execute(
            sa.text("DELETE FROM connection_entitlement_claims WHERE id = :i"), {"i": declarada}
        )


def test_e741c23_sucessor_de_outro_principal_e_recusado() -> None:
    """O sucessor precisa ser coerente **e** do mesmo dono."""
    with UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        fam = repo.add_provider_family(slug="op", display_name="Op")
        minha = repo.create_entitlement_claim(
            control_principal_ref="p",
            provider_family_id=fam.id,
            plan_ref="a",
            origin=EntitlementOrigin.USER_DECLARED,
            claimed_at=_AGORA,
        )
        alheia = repo.create_entitlement_claim(
            control_principal_ref="outro",
            provider_family_id=fam.id,
            plan_ref="a",
            origin=EntitlementOrigin.OFFICIALLY_DISCOVERED,
            claimed_at=_AGORA,
        )
        ids = (minha.id, alheia.id)
        uow.commit()

    with pytest.raises(IntegrityError), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "UPDATE connection_entitlement_claims "
                "SET state = 'superseded', superseded_by_id = :s WHERE id = :i"
            ),
            {"s": ids[1], "i": ids[0]},
        )


# --- 23. discovery stale degrada, não substitui -----------------------------


def test_e741c24_snapshot_vencido_e_lido_como_stale_e_nao_e_apagado() -> None:
    """Prova 23 — vencer **degrada**; não some, não é trocado por palpite."""
    with UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        perfil = repo.create_profile(
            control_principal_ref="p",
            method=ConnectionMethod.LOCAL_MODEL_ADAPTER,
            state=ConnectionState.DECLARED,
            endpoint_ref="opaco://1",
            access_provider_id=None,
        )
        repo.create_capability_snapshot(
            control_principal_ref="p",
            connection_id=perfil.id,
            observed_at=_AGORA - timedelta(hours=10),
            valid_until=_AGORA - timedelta(hours=9),
            source=CapabilitySource.OFFICIAL_DISCOVERY,
            capabilities=["texto"],
        )
        conexao_id = perfil.id
        uow.commit()

    with UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        snapshot = repo.get_latest_capability_snapshot(
            control_principal_ref="p", connection_id=conexao_id
        )
        vista = CapabilityView(
            connection_id=conexao_id,
            observed_at=snapshot.observed_at,
            valid_until=snapshot.valid_until,
            is_stale=snapshot.valid_until <= _AGORA,
            capabilities=tuple(snapshot.capabilities),
        )
        uow.commit()
    assert vista.is_stale is True
    assert vista.capabilities == ("texto",), "o vencido foi apagado em vez de rotulado"


def test_e741c25_snapshot_e_append_only() -> None:
    with UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        perfil = repo.create_profile(
            control_principal_ref="p",
            method=ConnectionMethod.LOCAL_MODEL_ADAPTER,
            state=ConnectionState.DECLARED,
            endpoint_ref="opaco://1",
            access_provider_id=None,
        )
        repo.create_capability_snapshot(
            control_principal_ref="p",
            connection_id=perfil.id,
            observed_at=_AGORA,
            valid_until=_AGORA + timedelta(hours=1),
            source=CapabilitySource.OFFICIAL_DISCOVERY,
            capabilities=["texto"],
        )
        uow.commit()
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(sa.text("UPDATE connection_capability_snapshots SET capabilities = '[]'"))


# --- 18, 19. compatibilidade prova protocolo, e só ---------------------------


def test_e741c26_endpoint_compativel_nao_falsifica_operador_nem_marca() -> None:
    """Provas 18 e 19 — o tipo genérico descreve **protocolo**.

    Um endpoint `openai_compatible_endpoint` pertence a um operador
    qualquer, e o roteador opaco não produz identidade verificada: o
    perfil que aponta para ele não ganha família nem release.
    """
    with UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        provedor = repo.add_access_provider(
            slug="terceiro-qualquer",
            display_name="Terceiro",
            endpoint_type=GenericEndpointType.OPENAI_COMPATIBLE_ENDPOINT,
        )
        perfil = repo.create_profile(
            control_principal_ref="p",
            method=ConnectionMethod.ENTERPRISE_GATEWAY_OR_BROKER,
            state=ConnectionState.DECLARED,
            endpoint_ref="opaco://gw",
            access_provider_id=provedor.id,
        )
        colunas = set(perfil.__table__.columns.keys())
        uow.commit()

    assert "model_family_id" not in colunas
    assert "model_release_id" not in colunas
    assert "provider_family_id" not in colunas


# --- 22. benchmark não decide -----------------------------------------------


def test_e741c27_evidencia_externa_nunca_e_autoritativa() -> None:
    """Prova 22 — a proibição está **escrita** no schema, não só ausente."""
    with UnitOfWork() as uow:
        repo = ConnectionRepository(uow.session)
        repo.create_evaluation_evidence(
            source_slug="arena",
            category=EvidenceCategory.EXTERNAL_EVALUATION,
            observed_at=_AGORA,
            summary={"posicao": 1},
        )
        uow.commit()
    # O `UPDATE` é recusado pelo append-only ANTES de chegar ao `CHECK`;
    # medir o CHECK exige o caminho que o append-only não bloqueia, que é
    # o INSERT. As duas recusas são reais e vêm de guardas diferentes.
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(
            sa.text("UPDATE connection_evaluation_evidence SET is_authoritative = true")
        )
    with pytest.raises(IntegrityError), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO connection_evaluation_evidence "
                "(id, source_slug, category, observed_at, summary, is_authoritative) "
                "VALUES (gen_random_uuid(), 'arena', 'external_evaluation', now(), "
                "'{}'::jsonb, true)"
            )
        )


# --- 20, 21. seleção: sugestão não executa ----------------------------------


def test_e741c28_apenas_a_selecao_manual_executa_sem_confirmacao() -> None:
    """Provas 20 e 21 — `SUGESTÃO != EXECUÇÃO`, `DELEGAÇÃO != CARTA_BRANCA`."""
    from app.connections.models.enums import EXECUTING_SELECTION_MODES

    assert frozenset({SelectionMode.MANUAL_SELECTION}) == EXECUTING_SELECTION_MODES
    assert SelectionMode.ASSISTED_SELECTION not in EXECUTING_SELECTION_MODES
    assert (
        SelectionMode.DELEGATED_SELECTION_WITH_REVOCABLE_USER_POLICY
        not in EXECUTING_SELECTION_MODES
    )
    assert len(SelectionMode) == 3, "modo de seleção novo sem decisão declarada"


# --- 25. projeção amigável preserva atribuição -------------------------------


def test_e741c29_projecao_amigavel_nao_substitui_a_atribuicao() -> None:
    """Prova 25 — o nome bonito **acompanha**, nunca ocupa o lugar do id.

    O mutante correspondente troca o identificador pelo rótulo; aqui os
    dois viajam lado a lado, e o campo tipado continua sendo o perfil.
    """
    with UnitOfWork() as uow:
        servico = ConnectionProfileService(ConnectionRepository(uow.session))
        resultado = servico.ensure_manual_profile(control_principal_ref="p")
        uow.commit()

    projecao = FriendlyConnectionProjection(
        profile=resultado.profile,
        friendly_name="Meu repasse manual",
        provider_family_slug=None,
        capability=None,
        entitlement=None,
    )
    assert isinstance(projecao.profile, ConnectionProfileView)
    assert projecao.profile.connection_id == resultado.profile.connection_id
    assert projecao.friendly_name != str(projecao.profile.connection_id)
    with pytest.raises(ValueError, match="friendly_name"):
        FriendlyConnectionProjection(
            profile=resultado.profile,
            friendly_name="  ",
            provider_family_slug=None,
            capability=None,
            entitlement=None,
        )


def test_e741c30_o_value_object_recusa_manual_com_endpoint_ou_available_alheio() -> None:
    """Invariante material no **value object**, não só no serviço.

    Lição reincidente da auditoria: um invariante que existe apenas no
    manager é contornado pelo construtor público.
    """
    with pytest.raises(ValueError, match="endpoint"):
        ConnectionProfileView(
            connection_id=uuid.uuid4(),
            method=ConnectionMethod.MANUAL_HANDOFF,
            state=ConnectionState.AVAILABLE,
            endpoint_ref="x://y",
            access_provider_slug=None,
            display_name=None,
        )
    with pytest.raises(ValueError, match="AVAILABLE"):
        ConnectionProfileView(
            connection_id=uuid.uuid4(),
            method=ConnectionMethod.PROVIDER_NATIVE_MCP_INBOUND,
            state=ConnectionState.AVAILABLE,
            endpoint_ref="x://y",
            access_provider_slug="op",
            display_name=None,
        )
    bicondicional = EntitlementView(
        entitlement_id=uuid.uuid4(),
        plan_ref="a",
        origin=EntitlementOrigin.USER_DECLARED,
        state=EntitlementState.ACTIVE,
        claimed_at=_AGORA,
        superseded_by_id=None,
    )
    assert bicondicional.superseded_by_id is None


def test_e741c31_banco_recusa_available_para_metodo_nao_manual() -> None:
    """Prova 10 no banco — `ENUM_OR_REGISTRY != AVAILABLE`, por SQL bruto."""
    with pytest.raises(IntegrityError), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO connection_profiles "
                "(id, control_principal_ref, method, endpoint_ref, state) "
                "VALUES (gen_random_uuid(), 'p', 'provider_native_mcp_inbound', "
                "'x://y', 'available')"
            )
        )


def test_e741c32_banco_recusa_perfil_manual_com_endpoint() -> None:
    with pytest.raises(IntegrityError), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO connection_profiles "
                "(id, control_principal_ref, method, endpoint_ref, state) "
                "VALUES (gen_random_uuid(), 'p', 'manual_handoff', 'x://y', 'available')"
            )
        )


def test_e741c33_banco_recusa_segundo_perfil_manual_do_mesmo_principal() -> None:
    """O índice parcial, e não o serviço: `NULL_NÃO_COLIDE_COM_NULL`."""
    with UnitOfWork() as uow:
        ConnectionProfileService(ConnectionRepository(uow.session)).ensure_manual_profile(
            control_principal_ref="p"
        )
        uow.commit()
    with pytest.raises(IntegrityError), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO connection_profiles "
                "(id, control_principal_ref, method, endpoint_ref, state) "
                "VALUES (gen_random_uuid(), 'p', 'manual_handoff', NULL, 'available')"
            )
        )
