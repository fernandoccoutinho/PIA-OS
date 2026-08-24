"""
Contratos congelados de saída do kernel.

```text
E7.4 FORNECE DADOS. E8 FORNECE INTERFACE.
PROJEÇÃO_AMIGÁVEL PRESERVA ATRIBUIÇÃO EXATA NO RECIBO
BRAND_LOGO_OR_ICON_ASSET = FORBIDDEN NESTA ETAPA
```

Nenhuma instância ORM cruza esta fronteira: os serviços devolvem
dataclasses congeladas, extraídas **dentro** da sessão. A lição é
reincidente no programa — conservar entidade ORM além do fim da
UnitOfWork dá `DetachedInstanceError`, e o custo já foi pago na E4.5, na
E7.1 e na E7.2.

O nome bonito é da tela. O recibo continua guardando provedor, modelo
solicitado e modelo observado, e a projeção **acrescenta** o rótulo
amigável em vez de substituir qualquer um deles.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.connections.models.enums import (
    ConnectionMethod,
    ConnectionState,
    EntitlementOrigin,
    EntitlementState,
    ModelAttestationLevel,
)


@dataclass(frozen=True)
class ConnectionProfileView:
    """Um perfil de conexão, como o kernel o expõe."""

    connection_id: uuid.UUID
    method: ConnectionMethod
    state: ConnectionState
    endpoint_ref: str | None
    access_provider_slug: str | None
    display_name: str | None

    def __post_init__(self) -> None:
        """Invariantes materiais moram no value object, não só no serviço.

        Lição reincidente da auditoria (E4.2.1, E4.3.2, E4.4.1, E4.5.1,
        E4.6.1): um invariante que existe apenas no manager é contornado
        pelo construtor público.
        """
        if self.method is ConnectionMethod.MANUAL_HANDOFF and self.endpoint_ref is not None:
            raise ValueError("perfil manual não tem endpoint; endpoint_ref precisa ser None")
        if self.method is ConnectionMethod.MANUAL_HANDOFF and self.access_provider_slug is not None:
            raise ValueError("perfil manual não tem operador de acesso")
        if self.state is ConnectionState.AVAILABLE and self.method is not (
            ConnectionMethod.MANUAL_HANDOFF
        ):
            raise ValueError(
                "ENUM_OR_REGISTRY != AVAILABLE: só manual_handoff está disponível nesta entrega"
            )


@dataclass(frozen=True)
class CapabilityView:
    """Capacidade observada, com a validade **explícita**.

    ```text
    discovery stale DEGRADA, não substitui
    ```

    `is_stale` é derivado da comparação entre `valid_until` e o instante
    de referência informado pelo chamador, e não de um relógio lido aqui
    dentro: um value object que consulta o tempo não é reproduzível em
    teste, e um teste não reproduzível não prova nada sobre TTL.
    """

    connection_id: uuid.UUID
    observed_at: datetime
    valid_until: datetime
    is_stale: bool
    capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.valid_until <= self.observed_at:
            raise ValueError("valid_until precisa ser posterior a observed_at")


@dataclass(frozen=True)
class EntitlementView:
    """Alegação de direito de uso, com origem e instante preservados."""

    entitlement_id: uuid.UUID
    plan_ref: str
    origin: EntitlementOrigin
    state: EntitlementState
    claimed_at: datetime
    superseded_by_id: uuid.UUID | None

    def __post_init__(self) -> None:
        if (self.state is EntitlementState.SUPERSEDED) != (self.superseded_by_id is not None):
            raise ValueError("SUPERSEDED e superseded_by_id são bicondicionais")
        if self.superseded_by_id == self.entitlement_id:
            raise ValueError("uma alegação não sucede a si mesma")


@dataclass(frozen=True)
class ConnectionExecutionReceiptView:
    """Os seis campos operacionais, exatamente como foram copiados.

    ```text
    connection_id · connection_method · access_provider
    requested_model · observed_model · model_attestation_level
    ```
    """

    receipt_id: uuid.UUID
    attempt_id: uuid.UUID
    step_id: uuid.UUID
    schedule_id: uuid.UUID
    connection_id: uuid.UUID
    connection_method: ConnectionMethod
    access_provider: str | None
    requested_model: str | None
    observed_model: str | None
    model_attestation_level: ModelAttestationLevel
    observed_at: datetime

    def __post_init__(self) -> None:
        """Os DOIS invariantes, e não só a bicondicional.

        ```text
        attested       <=> observed_model IS NOT NULL
        manual_handoff  => provider/requested/observed NULL, atestação unknown
        ```

        ACHADO R1 DA AUDITORIA DA CHAIN119. O corretivo R1 declarou, no
        handoff e na matriz, que os mesmos invariantes tinham entrado em
        `ExecutionAttribution` **e** aqui. Só entraram no primeiro: a
        edição do segundo foi feita com um `str.replace` que não casou e
        falhou em **silêncio**, e a prova `p15` exercitava apenas o outro
        construtor.

        ```text
        SILENT_EDIT = UNAPPLIED_EDIT
        UM CONSTRUTOR PÚBLICO PROVADO != TODOS OS CONSTRUTORES PÚBLICOS
        ```

        Esta view é construtível diretamente por qualquer chamador — é
        um segundo caminho público para a mesma atribuição, e um
        invariante que existe só no primeiro é contornado pelo segundo.
        """
        atestado = self.model_attestation_level is ModelAttestationLevel.ATTESTED
        if atestado != (self.observed_model is not None):
            raise ValueError("atestação `attested` exige observed_model não nulo, e vice-versa")
        if self.connection_method is ConnectionMethod.MANUAL_HANDOFF and any(
            (
                self.access_provider is not None,
                self.requested_model is not None,
                self.observed_model is not None,
                self.model_attestation_level is not ModelAttestationLevel.UNKNOWN,
            )
        ):
            raise ValueError(
                "repasse manual não tem operador, modelo solicitado, modelo observado "
                "nem atestação diferente de `unknown`"
            )


@dataclass(frozen=True)
class FriendlyConnectionProjection:
    """O que a E8 precisa para montar cartão, busca e intenção de voz.

    Contrato, **não** interface: sem ícone, sem logo, sem ativo de marca.

    A atribuição exata continua no `receipt`, que é carregado junto e
    não é resumido pelo rótulo: substituir o identificador pelo nome
    bonito é exatamente o mutante `M-...` que esta estrutura mata, porque
    os dois viajam lado a lado e o recibo é o campo tipado.
    """

    profile: ConnectionProfileView
    friendly_name: str
    provider_family_slug: str | None
    capability: CapabilityView | None
    entitlement: EntitlementView | None

    def __post_init__(self) -> None:
        if not self.friendly_name.strip():
            raise ValueError("friendly_name não pode ser vazio")
