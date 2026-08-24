"""
Único caminho de leitura/escrita das nove tabelas do kernel.

```text
PERSISTENCE_ONLY_THROUGH_REPOSITORY = TRUE
RAW_SQL_IN_SERVICE = FORBIDDEN
SESSION_OUTSIDE_REPOSITORY = FORBIDDEN
CROSS_PRINCIPAL_CONNECTION_READ = FORBIDDEN
```

O escopo por `control_principal_ref` mora **aqui**, não numa camada
acima, pela lição já paga três vezes nesta cadeia (Chain110, Chain111,
Chain112):

```text
SCOPED_READ_PATH != SCOPED_WRITE_PATH
CALLER_RESOLVED_ID != AUTHORIZED_ID
OWNER_BINDING != OBJECT_BINDING
```

Nenhum método deriva o dono do próprio dado que quer autorizar — vínculo
derivado do dado a autorizar não é vínculo, é tautologia. Todo caminho
que toque perfil, snapshot, alegação ou recibo exige
`control_principal_ref` do chamador e o impõe na cláusula.

As quatro tabelas de **catálogo** (`ProviderFamily`, `ModelFamily`,
`ModelRelease`, `AccessProvider`) são curadoria global e deliberadamente
**não** são escopadas por principal: elas não descrevem nada de ninguém.
A guarda estática classifica cada método público em categorias disjuntas
e exige que essa distinção seja declarada, e não presumida.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session, SessionTransaction

from app.connections.errors.exceptions import ConnectionScopeViolationError
from app.connections.models.capability import (
    CapabilitySnapshot,
    EntitlementClaim,
    EvaluationEvidence,
)
from app.connections.models.catalog import (
    AccessProvider,
    ModelFamily,
    ModelRelease,
    ProviderFamily,
)
from app.connections.models.connection_execution_receipt import ConnectionExecutionReceipt
from app.connections.models.connection_profile import ConnectionProfile
from app.connections.models.enums import (
    TERMINAL_CONNECTION_STATES,
    ConnectionMethod,
    ConnectionState,
    EntitlementState,
    ModelAttestationLevel,
)

MANUAL_PROFILE_LOCK_NAMESPACE = 0x7401
"""Namespace do advisory lock do perfil manual.

Constante nomeada, e não literal solto: dois namespaces iguais em
subsistemas diferentes serializariam operações que nada têm a ver uma
com a outra, e o efeito seria invisível até virar lentidão inexplicada.
"""


class ConnectionRepository:
    """Persistência do kernel. Nenhum serviço toca `Session` diretamente."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def database_now(self) -> datetime:
        """INFRASTRUCTURE — instante do PostgreSQL — nunca `datetime.now()` da aplicação.

        `observed_at` sai daqui, pelo mesmo precedente de `sealed_at` na
        E7.1: relógio de aplicação diverge entre réplicas, e um recibo
        cujo instante depende de qual processo o gravou não é evidência.
        """
        momento = self._session.execute(sa.select(sa.func.now())).scalar_one()
        if not isinstance(momento, datetime):  # pragma: no cover - defesa de tipo
            raise TypeError("now() do banco não retornou datetime")
        return momento

    def nested_transaction(self) -> SessionTransaction:
        """INFRASTRUCTURE — savepoint. É o repositório quem abre, não o serviço.

        ```text
        SESSION_OUTSIDE_REPOSITORY = FORBIDDEN
        PERDER A CORRIDA != INVALIDAR A TRANSAÇÃO EXTERNA
        ```

        Sem savepoint, o `IntegrityError` do índice parcial invalidaria a
        transação externa inteira — inclusive a Attempt e o `SealReceipt`
        que o chamador está gravando na mesma unidade de trabalho.
        """
        return self._session.begin_nested()

    # --- catálogo (curadoria global, sem escopo de principal) --------------

    def add_provider_family(self, *, slug: str, display_name: str) -> ProviderFamily:
        """CATALOG_WRITE — curadoria global."""
        familia = ProviderFamily(slug=slug, display_name=display_name)
        self._session.add(familia)
        self._session.flush()
        return familia

    def add_model_family(
        self, *, provider_family_id: uuid.UUID, slug: str, display_name: str
    ) -> ModelFamily:
        """CATALOG_WRITE — curadoria global."""
        familia = ModelFamily(
            provider_family_id=provider_family_id, slug=slug, display_name=display_name
        )
        self._session.add(familia)
        self._session.flush()
        return familia

    def add_model_release(
        self,
        *,
        model_family_id: uuid.UUID,
        provider_release_id: str,
        discovered_at: datetime,
        valid_until: datetime,
        discovery_source: object,
    ) -> ModelRelease:
        """CATALOG_WRITE — release **descoberto**, com validade."""
        release = ModelRelease(
            model_family_id=model_family_id,
            provider_release_id=provider_release_id,
            discovered_at=discovered_at,
            valid_until=valid_until,
            discovery_source=discovery_source,
        )
        self._session.add(release)
        self._session.flush()
        return release

    def add_access_provider(
        self, *, slug: str, display_name: str, endpoint_type: object
    ) -> AccessProvider:
        """CATALOG_WRITE — operador do endpoint."""
        provedor = AccessProvider(slug=slug, display_name=display_name, endpoint_type=endpoint_type)
        self._session.add(provedor)
        self._session.flush()
        return provedor

    def get_provider_family(self, *, family_id: uuid.UUID) -> ProviderFamily | None:
        """CATALOG_READ — curadoria global."""
        return self._session.get(ProviderFamily, family_id)

    def get_access_provider(self, *, provider_id: uuid.UUID) -> AccessProvider | None:
        """CATALOG_READ — curadoria global."""
        return self._session.get(AccessProvider, provider_id)

    def list_model_releases(self, *, model_family_id: uuid.UUID) -> list[ModelRelease]:
        """CATALOG_READ — ordem determinística canônica do programa."""
        consulta = (
            sa.select(ModelRelease)
            .where(ModelRelease.model_family_id == model_family_id)
            .order_by(ModelRelease.created_at.asc(), ModelRelease.id.asc())
        )
        return list(self._session.execute(consulta).scalars().all())

    # --- perfis (escopados por principal) ----------------------------------

    def acquire_manual_profile_lock(self, *, control_principal_ref: str) -> None:
        """SCOPED_WRITE — lock consultivo por principal, dentro da transação.

        `pg_advisory_xact_lock` e não `pg_advisory_lock`: o primeiro é
        liberado no fim da transação, aconteça o que acontecer. O segundo
        exigiria alguém lembrar de soltá-lo, e "alguém lembra" não é
        garantia — é a forma como deadlocks nascem.

        Em dialeto que não seja PostgreSQL a chamada é silenciosamente
        ignorada, porque não há advisory lock a tomar; a unicidade
        continua imposta pelo índice parcial, que é o que sobrevive fora
        dos serviços.
        """
        if self._session.get_bind().dialect.name != "postgresql":
            return
        self._session.execute(
            sa.text("SELECT pg_advisory_xact_lock(:ns, hashtext(:ref))"),
            {"ns": MANUAL_PROFILE_LOCK_NAMESPACE, "ref": control_principal_ref},
        )

    def get_manual_profile(self, *, control_principal_ref: str) -> ConnectionProfile | None:
        """SCOPED_READ — o perfil manual não terminal deste principal."""
        consulta = sa.select(ConnectionProfile).where(
            ConnectionProfile.control_principal_ref == control_principal_ref,
            ConnectionProfile.method == ConnectionMethod.MANUAL_HANDOFF,
            ConnectionProfile.state.not_in(tuple(TERMINAL_CONNECTION_STATES)),
        )
        return self._session.execute(consulta).scalars().one_or_none()

    def create_profile(
        self,
        *,
        control_principal_ref: str,
        method: ConnectionMethod,
        state: ConnectionState,
        endpoint_ref: str | None,
        access_provider_id: uuid.UUID | None,
        display_name: str | None = None,
        credential_ref: str | None = None,
    ) -> ConnectionProfile:
        """SCOPED_WRITE — cria perfil já vinculado ao principal do chamador."""
        perfil = ConnectionProfile(
            control_principal_ref=control_principal_ref,
            method=method,
            state=state,
            endpoint_ref=endpoint_ref,
            access_provider_id=access_provider_id,
            display_name=display_name,
            credential_ref=credential_ref,
        )
        self._session.add(perfil)
        self._session.flush()
        return perfil

    def get_profile(
        self, *, control_principal_ref: str, connection_id: uuid.UUID
    ) -> ConnectionProfile | None:
        """SCOPED_READ — as duas condições juntas, nenhuma derivada da outra."""
        consulta = sa.select(ConnectionProfile).where(
            ConnectionProfile.id == connection_id,
            ConnectionProfile.control_principal_ref == control_principal_ref,
        )
        return self._session.execute(consulta).scalars().one_or_none()

    def require_profile(
        self, *, control_principal_ref: str, connection_id: uuid.UUID
    ) -> ConnectionProfile:
        """SCOPED_WRITE — recusa tipada, nunca `None`.

        Um escritor que devolve `None` para escopo alheio convida o
        chamador a tratar recusa como ausência.
        """
        perfil = self.get_profile(
            control_principal_ref=control_principal_ref, connection_id=connection_id
        )
        if perfil is None:
            raise ConnectionScopeViolationError(
                message="conexão inexistente sob este principal de controle",
                detail={"connection_id": str(connection_id)},
            )
        return perfil

    def list_profiles(self, *, control_principal_ref: str) -> list[ConnectionProfile]:
        """SCOPED_READ — ordem determinística canônica."""
        consulta = (
            sa.select(ConnectionProfile)
            .where(ConnectionProfile.control_principal_ref == control_principal_ref)
            .order_by(ConnectionProfile.created_at.asc(), ConnectionProfile.id.asc())
        )
        return list(self._session.execute(consulta).scalars().all())

    # --- capacidade (escopada) ---------------------------------------------

    def create_capability_snapshot(
        self,
        *,
        control_principal_ref: str,
        connection_id: uuid.UUID,
        observed_at: datetime,
        valid_until: datetime,
        source: object,
        capabilities: list[str],
    ) -> CapabilitySnapshot:
        """SCOPED_WRITE — exige que a conexão seja do principal informado."""
        self.require_profile(
            control_principal_ref=control_principal_ref, connection_id=connection_id
        )
        snapshot = CapabilitySnapshot(
            control_principal_ref=control_principal_ref,
            connection_id=connection_id,
            observed_at=observed_at,
            valid_until=valid_until,
            source=source,
            capabilities=list(capabilities),
        )
        self._session.add(snapshot)
        self._session.flush()
        return snapshot

    def get_latest_capability_snapshot(
        self, *, control_principal_ref: str, connection_id: uuid.UUID
    ) -> CapabilitySnapshot | None:
        """SCOPED_READ — o mais recente por `observed_at`, desempate por id."""
        consulta = (
            sa.select(CapabilitySnapshot)
            .where(
                CapabilitySnapshot.connection_id == connection_id,
                CapabilitySnapshot.control_principal_ref == control_principal_ref,
            )
            .order_by(CapabilitySnapshot.observed_at.desc(), CapabilitySnapshot.id.desc())
            .limit(1)
        )
        return self._session.execute(consulta).scalars().one_or_none()

    # --- entitlement (escopado) --------------------------------------------

    def create_entitlement_claim(
        self,
        *,
        control_principal_ref: str,
        provider_family_id: uuid.UUID,
        plan_ref: str,
        origin: object,
        claimed_at: datetime,
    ) -> EntitlementClaim:
        """SCOPED_WRITE — toda alegação nasce `ACTIVE`."""
        alegacao = EntitlementClaim(
            control_principal_ref=control_principal_ref,
            provider_family_id=provider_family_id,
            plan_ref=plan_ref,
            origin=origin,
            state=EntitlementState.ACTIVE,
            claimed_at=claimed_at,
        )
        self._session.add(alegacao)
        self._session.flush()
        return alegacao

    def supersede_entitlement_claim(
        self,
        *,
        control_principal_ref: str,
        antecedent_id: uuid.UUID,
        successor_id: uuid.UUID,
    ) -> bool:
        """SCOPED_WRITE — `ACTIVE -> SUPERSEDED`, condicional e atômica.

        ```text
        MUTAR o registro declarado = PROIBIDO
        CRIAR registro que o SUPERSEDA = CAMINHO NORMAL
        ```

        `UPDATE` condicional revalida `state='active'` e o dono na
        própria cláusula: sob concorrência, exatamente um chamador vê
        `rowcount == 1` e os demais veem zero. Um `SELECT` seguido de
        `UPDATE` deixaria a janela aberta.

        Origem, `plan_ref` e `claimed_at` **não** entram no `SET`, e a
        trigger recusa quem tentar mudá-los por SQL bruto.
        """
        comando = (
            sa.update(EntitlementClaim)
            .where(
                EntitlementClaim.id == antecedent_id,
                EntitlementClaim.control_principal_ref == control_principal_ref,
                EntitlementClaim.state == EntitlementState.ACTIVE,
                EntitlementClaim.id != successor_id,
            )
            .values(state=EntitlementState.SUPERSEDED, superseded_by_id=successor_id)
        )
        return self._session.execute(comando).rowcount == 1

    def get_entitlement_claim(
        self, *, control_principal_ref: str, entitlement_id: uuid.UUID
    ) -> EntitlementClaim | None:
        """SCOPED_READ — as duas condições juntas."""
        consulta = sa.select(EntitlementClaim).where(
            EntitlementClaim.id == entitlement_id,
            EntitlementClaim.control_principal_ref == control_principal_ref,
        )
        return self._session.execute(consulta).scalars().one_or_none()

    def get_active_entitlement(
        self, *, control_principal_ref: str, provider_family_id: uuid.UUID
    ) -> EntitlementClaim | None:
        """SCOPED_READ — a alegação vigente daquela família, se houver."""
        consulta = (
            sa.select(EntitlementClaim)
            .where(
                EntitlementClaim.control_principal_ref == control_principal_ref,
                EntitlementClaim.provider_family_id == provider_family_id,
                EntitlementClaim.state == EntitlementState.ACTIVE,
            )
            .order_by(EntitlementClaim.claimed_at.desc(), EntitlementClaim.id.desc())
            .limit(1)
        )
        return self._session.execute(consulta).scalars().one_or_none()

    # --- recibo de execução (escopado) -------------------------------------

    def create_execution_receipt(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        attempt_id: uuid.UUID,
        connection_id: uuid.UUID,
        connection_method: ConnectionMethod,
        access_provider: str | None,
        requested_model: str | None,
        observed_model: str | None,
        model_attestation_level: ModelAttestationLevel,
        observed_at: datetime,
    ) -> ConnectionExecutionReceipt:
        """SCOPED_WRITE — seis campos **copiados**, nunca derivados na leitura.

        A conexão é exigida sob o mesmo principal antes de qualquer
        escrita: a FK composta recusaria de qualquer forma, e recusar
        aqui produz erro tipado em vez de `IntegrityError` cru.
        """
        self.require_profile(
            control_principal_ref=control_principal_ref, connection_id=connection_id
        )
        recibo = ConnectionExecutionReceipt(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_id=attempt_id,
            connection_id=connection_id,
            connection_method=connection_method,
            access_provider=access_provider,
            requested_model=requested_model,
            observed_model=observed_model,
            model_attestation_level=model_attestation_level,
            observed_at=observed_at,
        )
        self._session.add(recibo)
        self._session.flush()
        return recibo

    def get_execution_receipt_by_attempt(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> ConnectionExecutionReceipt | None:
        """SCOPED_READ — três condições juntas, nenhuma derivada de outra.

        `schedule_id` vem do chamador e **não** é lido do próprio recibo:
        derivar o Schedule do dado que se quer autorizar é a tautologia
        que reprovou a Chain111.
        """
        consulta = sa.select(ConnectionExecutionReceipt).where(
            ConnectionExecutionReceipt.attempt_id == attempt_id,
            ConnectionExecutionReceipt.schedule_id == schedule_id,
            ConnectionExecutionReceipt.control_principal_ref == control_principal_ref,
        )
        return self._session.execute(consulta).scalars().one_or_none()

    # --- evidência externa (global, e nunca decisória) ---------------------

    def create_evaluation_evidence(
        self,
        *,
        source_slug: str,
        category: object,
        observed_at: datetime,
        summary: dict[str, object],
    ) -> EvaluationEvidence:
        """CATALOG_WRITE — registro append-only que **não** decide nada.

        `is_authoritative` não é parâmetro: o valor é sempre falso, e o
        `CHECK` da migration recusa qualquer outro. Aceitá-lo como
        argumento deixaria a proibição a cargo do chamador.
        """
        evidencia = EvaluationEvidence(
            source_slug=source_slug,
            category=category,
            observed_at=observed_at,
            summary=dict(summary),
            is_authoritative=False,
        )
        self._session.add(evidencia)
        self._session.flush()
        return evidencia

    def list_evaluation_evidence(self, *, source_slug: str) -> list[EvaluationEvidence]:
        """CATALOG_READ — ordem determinística canônica."""
        consulta = (
            sa.select(EvaluationEvidence)
            .where(EvaluationEvidence.source_slug == source_slug)
            .order_by(EvaluationEvidence.created_at.asc(), EvaluationEvidence.id.asc())
        )
        return list(self._session.execute(consulta).scalars().all())
