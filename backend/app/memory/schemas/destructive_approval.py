"""
Contratos tipados de proposta e aprovação destrutiva (`E4.9.8`).

```text
ASSESS != PROPOSE != AUTHORIZE != EXECUTE != RECEIPT
```

Esta fatia materializa **somente** `PROPOSE` e o artefato contratual de
`AUTHORIZE`. Nada aqui autentica, executa, move para a lixeira, apaga,
persiste aprovação, consome nonce ou escreve recibo.

```text
CONSTRUCTIBLE_VALUE_OBJECT != VERIFIED_EXTERNAL_APPROVAL
PROPOSAL                   != APPROVAL
APPROVAL                   != EXECUTION
EXECUTION                  != RECEIPT
APPROVAL_RECORD            != ERASURE_RECORD
```

Construir um `DestructiveApprovalEnvelope` em Python **não** concede
autoridade de execução. O objeto representa evidência tipada que uma
fronteira externa futura deverá verificar — e é assim que o EDR o
descreve, porque descrevê-lo como prova de autenticação seria a sexta
alegação acima da camada nesta mesma linha de trabalho.

## Garantias, por camada

```text
lote imutável, ordenado, sem duplicata      TYPE_LEVEL + APPLICATION_LEVEL
snapshot sem localizador                    TYPE_LEVEL
step-up exigido para apagamento definitivo  APPLICATION_LEVEL
bloqueio impede envelope                    APPLICATION_LEVEL
binding proposta↔envelope                   APPLICATION_LEVEL
coerência temporal                          APPLICATION_LEVEL (instante recebido)
redação textual direta e composta           APPLICATION_LEVEL
evidência de identidade                     EXTERNAL_BOUNDARY_LEVEL
nonce de uso único                          DEFERRED
revogação, replay, TOCTOU, re-resolução     DEFERRED
persistência e consumo atômico              DEFERRED
```

```text
TYPED_ASSURANCE_CLAIM != AUTHENTICATION_PERFORMED
NONCE_PRESENT         != SINGLE_USE_ENFORCED
EXPIRES_AT_PRESENT    != EXPIRY_ENFORCED
IMMUTABLE_BATCH       != FRESH_TARGET_RE_RESOLUTION
```

## Confidencialidade

Todo campo textual livre é redigido em `repr` e `str`, direta e
composicionalmente — a regra `UNRESTRICTED_PUBLIC_STR =
MAY_CONTAIN_SENSITIVE_VALUE` que a E4.9.7.3 pagou para aprender.

Há um caso que merece registro: `GovernanceResolution` é incorporada
inteira, como o §5.1 exige, e ela tem **onze** campos `str` livres
visíveis no próprio `repr`. Não posso redigi-los na origem — alterar um
contrato público da E4.3 seria Stop Condition. Então a proposta **não
delega** a representação dela; substitui-a por um marcador. Ver
`DestructiveApprovalProposal.__repr__`.

```text
REDACTED_REPR != SECRET_FREE_OBJECT
FIELD_NAME    != ENFORCED_DOMAIN
```
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.memory.models.approval_enums import (
    ApprovalBlockerKind,
    AssuranceLevel,
    DestructiveOperation,
    ImpactVolumeKind,
    InputChannel,
    VoiceReviewState,
)
from app.memory.models.erasure_enums import ErasureTargetClass
from app.memory.schemas.erasure_target import (
    CLASSES_DE_CONTEUDO,
    TEXTO_OCULTO,
    ControlScope,
    CustodyNamespace,
    ReferenceProvenance,
    validar_instante_ciente,
    validar_texto_opaco,
)
from app.memory.schemas.governance import GovernanceResolution

RESOLUCAO_OCULTA = "<governance_resolution:redacted>"
"""O que `repr()` mostra no lugar da `GovernanceResolution` incorporada.

`GovernanceResolution` é da E4.3 e tem onze campos `str` livres visíveis
no `repr` dela — `context_actor_ref`, `context_purpose`,
`safety_rationale`, `preserved_intent`, `admissible_alternatives`,
`constraints`, `declared_preservations`, `declared_losses`,
`policy_key`, `matched_rule_id` e `policy_rationale`.

Delegar `resolution!r` vazaria os onze pela composição, que é exatamente
o defeito medido na cadeia 82. Redigi-los na origem seria alterar
assinatura pública existente — Stop Condition. Resta redigir aqui.
"""


def validar_uuid(nome: str, valor: object) -> uuid.UUID:
    """Identificadores opacos são `UUID`, não texto.

    O §5.2 pede "tipo não textual já seguro no projeto": `UUID` não
    carrega conteúdo, não relocaliza nada e é seguro em `repr`.
    """
    if not isinstance(valor, uuid.UUID):
        raise TypeError(f"{nome} deve ser UUID, recebido {type(valor).__name__}")
    return valor


def validar_inteiro_nao_negativo(nome: str, valor: object) -> int:
    """`bool` é subclasse de `int` e **não** é número aqui.

    `True` valendo `1` numa contagem de itens ou num volume em bytes é a
    forma silenciosa de um flag virar quantidade.
    """
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"{nome} deve ser int, recebido {type(valor).__name__}")
    if valor < 0:
        raise ValueError(f"{nome} deve ser >= 0")
    return valor


@dataclass(frozen=True)
class SafeTargetSnapshot:
    """O alvo **como foi apresentado ao usuário** — sem localizador.

    ```text
    SNAPSHOT != ErasureTargetDescriptor
    ```

    O §5.1 proíbe reutilizar `ErasureTargetDescriptor` inteiro, e a razão
    é um campo: `transient_locator`. Um descritor dentro de uma proposta
    que circula, é apresentada em interface e futuramente persistida
    levaria junto o endereço material do objeto — e a E4.9.7 gastou dois
    corretivos estabelecendo que localizador não sobrevive ao efeito.

    Este snapshot carrega o que a decisão do usuário precisa: qual
    classe, qual sujeito histórico, sob que controle, em que custódia, de
    que origem e em que versão observada. **Não** carrega como chegar lá.

    `version_etag` é opcional porque nem todo provedor oferece versão —
    mas é `str` livre, logo redigido, pela regra da E4.9.7.3.
    """

    target_class: ErasureTargetClass
    subject_coid: uuid.UUID
    control_scope: ControlScope
    custody_namespace: CustodyNamespace
    origin: ReferenceProvenance
    version_etag: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.target_class, ErasureTargetClass):
            raise TypeError("target_class deve ser um ErasureTargetClass")
        if self.target_class not in CLASSES_DE_CONTEUDO:
            raise ValueError(
                f"{self.target_class.value} não é conteúdo apagável — metadado "
                "cognitivo e referência não resolvida não entram em proposta "
                "destrutiva"
            )
        validar_uuid("subject_coid", self.subject_coid)
        if not isinstance(self.control_scope, ControlScope):
            raise TypeError("control_scope deve ser um ControlScope")
        if not isinstance(self.custody_namespace, CustodyNamespace):
            raise TypeError("custody_namespace deve ser um CustodyNamespace")
        if not isinstance(self.origin, ReferenceProvenance):
            raise TypeError("origin deve ser um ReferenceProvenance")
        if self.version_etag is not None:
            validar_texto_opaco("version_etag", self.version_etag)

    def __repr__(self) -> str:
        return (
            f"SafeTargetSnapshot(target_class={self.target_class.value!r}, "
            f"subject_coid={self.subject_coid!r}, "
            f"control_scope={self.control_scope!r}, "
            f"custody_namespace={self.custody_namespace!r}, "
            f"origin={self.origin!r}, "
            f"version_etag={TEXTO_OCULTO if self.version_etag else None!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class PresentedImpact:
    """O impacto **exibido** ao usuário antes da confirmação.

    ```text
    UNKNOWN_VOLUME != ZERO_VOLUME
    ```

    `item_count` tem de bater com o lote — a proposta verifica. Um número
    que diverge do lote é pior que nenhum número: o usuário confirma uma
    quantidade e a operação alcança outra.

    `bytes_total` só existe quando `volume_kind` é `KNOWN`. Fabricar `0`
    para o desconhecido prometeria que nada de espaço é recuperado.
    """

    item_count: int
    volume_kind: ImpactVolumeKind
    bytes_total: int | None = None

    def __post_init__(self) -> None:
        validar_inteiro_nao_negativo("item_count", self.item_count)
        if not isinstance(self.volume_kind, ImpactVolumeKind):
            raise TypeError("volume_kind deve ser um ImpactVolumeKind")
        if self.volume_kind is ImpactVolumeKind.KNOWN:
            if self.bytes_total is None:
                raise ValueError(
                    "volume KNOWN exige bytes_total — um volume conhecido sem "
                    "número não é conhecido"
                )
            validar_inteiro_nao_negativo("bytes_total", self.bytes_total)
        elif self.bytes_total is not None:
            raise ValueError(
                "volume UNKNOWN não pode ter bytes_total — fabricar número "
                "para o desconhecido é a mesma coisa que mentir o impacto"
            )


@dataclass(frozen=True)
class IdentityEvidence:
    """Evidência de identidade **declarada por fronteira externa futura**.

    ```text
    TYPED_ASSURANCE_CLAIM != AUTHENTICATION_PERFORMED
    EXTERNAL_BOUNDARY_LEVEL
    ```

    Não existe autenticador, IdP, sessão, MFA ou step-up no repositório.
    Este objeto **não** prova identidade: registra, de forma tipada, o
    que uma fronteira externa afirma ter verificado. Quem verifica é
    outro, e essa fronteira ainda não foi construída.

    Sem token, cookie, senha, chave, assinatura, material OAuth,
    credencial ou biometria — nem como campo, nem como texto. O
    identificador do principal é opaco e redigido.
    """

    principal_ref: str = field(repr=False)
    """Referência opaca ao principal. Descritiva, como `actor_ref` da E3:
    não autentica, não prova identidade e é redigida."""

    assurance_level: AssuranceLevel
    authenticated_at: datetime

    def __post_init__(self) -> None:
        validar_texto_opaco("principal_ref", self.principal_ref)
        if not isinstance(self.assurance_level, AssuranceLevel):
            raise TypeError("assurance_level deve ser um AssuranceLevel")
        validar_instante_ciente("authenticated_at", self.authenticated_at)

    def __repr__(self) -> str:
        return (
            f"IdentityEvidence(principal_ref={TEXTO_OCULTO}, "
            f"assurance_level={self.assurance_level.value!r}, "
            f"authenticated_at={self.authenticated_at!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class ApprovalContext:
    """Tenant, workspace, domínio e finalidade — o escopo do binding.

    Separado da evidência de identidade de propósito: **quem** e **onde**
    são coisas distintas, e o envelope precisa provar que as duas
    coincidem com a proposta.
    """

    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    domain_id: uuid.UUID
    purpose_ref: str = field(repr=False)
    """Finalidade declarada. Texto livre, logo redigido."""

    def __post_init__(self) -> None:
        for nome in ("tenant_id", "workspace_id", "domain_id"):
            validar_uuid(nome, getattr(self, nome))
        validar_texto_opaco("purpose_ref", self.purpose_ref)

    def __repr__(self) -> str:
        return (
            f"ApprovalContext(tenant_id={self.tenant_id!r}, "
            f"workspace_id={self.workspace_id!r}, "
            f"domain_id={self.domain_id!r}, "
            f"purpose_ref={TEXTO_OCULTO})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class SafeVoiceProvenance:
    """Canal de entrada e estado da revisão — proveniência, não autoridade.

    ```text
    TEXT_GOVERNANCE = VOICE_GOVERNANCE
    VOICE != IDENTITY
    VOICE_TRANSCRIPT != CONFIRMATION
    ```

    Nenhum áudio, transcrição ou texto original. Só o canal e o estado
    estruturado da revisão, ambos de vocabulário fechado.

    A coerência é exigida nos dois sentidos: `TEXT` declara
    `NOT_APPLICABLE`, `VOICE` não pode declará-lo. Sem isso a revisão de
    uma entrada de voz sumiria sem que ninguém a negasse.
    """

    channel: InputChannel
    voice_review: VoiceReviewState

    def __post_init__(self) -> None:
        if not isinstance(self.channel, InputChannel):
            raise TypeError("channel deve ser um InputChannel")
        if not isinstance(self.voice_review, VoiceReviewState):
            raise TypeError("voice_review deve ser um VoiceReviewState")
        if (
            self.channel is InputChannel.TEXT
            and self.voice_review is not VoiceReviewState.NOT_APPLICABLE
        ):
            raise ValueError(
                "canal TEXT exige voice_review NOT_APPLICABLE — declarar revisão "
                "de voz onde não houve voz falsifica a proveniência"
            )
        if (
            self.channel is InputChannel.VOICE
            and self.voice_review is VoiceReviewState.NOT_APPLICABLE
        ):
            raise ValueError(
                "canal VOICE não pode declarar NOT_APPLICABLE — a revisão tem de "
                "ser afirmada ou negada, nunca omitida"
            )


@dataclass(frozen=True)
class DestructiveApprovalProposal:
    """O que foi apresentado ao usuário — **antes** de qualquer confirmação.

    ```text
    PROPOSAL != APPROVAL
    ```

    Não carrega autoridade. É o registro exato do que a interface exibiu:
    qual operação, sobre qual lote, em que ordem, com que impacto, sob
    qual resolução de governança, por qual canal, em que instante.

    A ordem do lote **faz parte do binding** e não é reordenada em
    silêncio. Se a interface apresentou A, B, C, foi isso que o usuário
    viu, e ordenar por conveniência mudaria o que ele confirmou.

    Qualquer mudança de ação, alvo, escopo, ordem, quantidade, volume,
    versão, policy, custódia, provedor, impacto, identidade, tenant,
    domínio ou finalidade exige **nova instância** — a imutabilidade é o
    mecanismo, e não há método de mutação.
    """

    operation: DestructiveOperation
    targets: tuple[SafeTargetSnapshot, ...]
    impact: PresentedImpact
    governance_resolution: GovernanceResolution = field(repr=False)
    """Resolução exata aplicada, **sem reavaliação**.

    Redigida no `repr` porque tem onze campos `str` livres da E4.3 que
    não posso fechar na origem — ver `RESOLUCAO_OCULTA`.
    """

    context: ApprovalContext
    provenance: SafeVoiceProvenance
    blockers: tuple[ApprovalBlockerKind, ...]
    """Vocabulário fechado. Lote com bloqueio **não** forma envelope."""

    materialized_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.operation, DestructiveOperation):
            raise TypeError("operation deve ser um DestructiveOperation")

        if not isinstance(self.targets, tuple):
            raise TypeError(
                f"targets deve ser tuple[SafeTargetSnapshot, ...], recebido "
                f"{type(self.targets).__name__} — coleção mutável não é "
                f"representação admissível de um lote confirmado"
            )
        if not self.targets:
            raise ValueError(
                "proposta destrutiva exige lote não vazio — apresentar zero "
                "alvos e pedir confirmação não confirma nada"
            )
        for indice, alvo in enumerate(self.targets):
            if not isinstance(alvo, SafeTargetSnapshot):
                raise TypeError(
                    f"targets[{indice}] deve ser SafeTargetSnapshot, recebido "
                    f"{type(alvo).__name__}"
                )
        vistos: set[uuid.UUID] = set()
        for alvo in self.targets:
            if alvo.subject_coid in vistos:
                raise ValueError(
                    f"alvo duplicado no lote: {alvo.subject_coid} — duplicata "
                    "torna a quantidade apresentada ambígua"
                )
            vistos.add(alvo.subject_coid)

        if not isinstance(self.impact, PresentedImpact):
            raise TypeError("impact deve ser um PresentedImpact")
        if self.impact.item_count != len(self.targets):
            raise ValueError(
                f"impacto apresentado ({self.impact.item_count}) diverge do lote "
                f"({len(self.targets)}) — o usuário confirmaria uma quantidade "
                "e a operação alcançaria outra"
            )

        if not isinstance(self.governance_resolution, GovernanceResolution):
            raise TypeError("governance_resolution deve ser um GovernanceResolution")
        if not isinstance(self.context, ApprovalContext):
            raise TypeError("context deve ser um ApprovalContext")
        if not isinstance(self.provenance, SafeVoiceProvenance):
            raise TypeError("provenance deve ser um SafeVoiceProvenance")

        if not isinstance(self.blockers, tuple):
            raise TypeError("blockers deve ser tuple[ApprovalBlockerKind, ...]")
        for indice, bloqueio in enumerate(self.blockers):
            if not isinstance(bloqueio, ApprovalBlockerKind):
                raise TypeError(
                    f"blockers[{indice}] deve ser ApprovalBlockerKind, recebido "
                    f"{type(bloqueio).__name__}"
                )

        validar_instante_ciente("materialized_at", self.materialized_at)

        if not self.provenance.voice_review.permite_proposta(self.provenance.channel):
            raise ValueError(
                f"entrada de voz em estado {self.provenance.voice_review.value} não "
                "forma proposta — baixa confiança, ambiguidade e ausência de "
                "revisão pertencem à fronteira anterior e não são corrigidas aqui"
            )

        for alvo in self.targets:
            if alvo.control_scope.workspace_id != self.context.workspace_id:
                raise ValueError("workspace do alvo diverge do contexto da proposta")
            if alvo.control_scope.tenant_id != self.context.tenant_id:
                raise ValueError("tenant do alvo diverge do contexto da proposta")

    @property
    def is_approvable(self) -> bool:
        """Não há bloqueio impedindo a aprovação.

        ```text
        APPROVABLE != APPROVED
        ```

        Ausência de bloqueio não é aprovação — é apenas a ausência do que
        a impediria. A aprovação é o envelope, e ela vem de fora.
        """
        return not self.blockers

    def __repr__(self) -> str:
        return (
            f"DestructiveApprovalProposal(operation={self.operation.value!r}, "
            f"targets={self.targets!r}, "
            f"impact={self.impact!r}, "
            f"governance_resolution={RESOLUCAO_OCULTA}, "
            f"context={self.context!r}, "
            f"provenance={self.provenance!r}, "
            f"blockers={self.blockers!r}, "
            f"materialized_at={self.materialized_at!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class DestructiveApprovalEnvelope:
    """A aprovação externa **daquela** proposta — e de nenhuma outra.

    ```text
    CONSTRUCTIBLE_VALUE_OBJECT != VERIFIED_EXTERNAL_APPROVAL
    APPROVAL != EXECUTION
    ```

    Incorpora a proposta **exata**, não uma reconstrução. O binding é
    estrutural: não há digest, hash ou referência de escopo, porque
    qualquer um deles seria calculado sobre dados de custódia e poderia
    virar chave de relocalização sem canonicalização provada. O §5.2
    manda parar e justificar antes de usar hash; a justificativa é não
    usá-lo.

    ```text
    PROPOSAL_DIGEST = NOT_USED
    ```

    Nenhum campo de autoridade, confirmação ou instante tem default,
    sentinel ou factory — lição direta do A6 da E4.9.7.4, onde um
    `= True` acidental fez a omissão virar verificação.

    O que este objeto **não** faz: autenticar, executar, persistir,
    consumir nonce, revogar, proteger contra replay ou reresolver alvo.
    """

    proposal: DestructiveApprovalProposal
    approval_id: uuid.UUID
    """Identificador opaco do envelope."""

    nonce: uuid.UUID
    """Opaco e **distinto** do identificador.

    ```text
    NONCE_PRESENT != SINGLE_USE_ENFORCED
    ```

    Modelado, não imposto: não há repositório, lock nem consumo atômico
    nesta fatia. Um nonce igual ao `approval_id` não seria nonce — seria
    o mesmo valor com dois nomes.
    """

    identity: IdentityEvidence
    context: ApprovalContext
    provenance: SafeVoiceProvenance
    issued_at: datetime
    confirmed_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, DestructiveApprovalProposal):
            raise TypeError("proposal deve ser um DestructiveApprovalProposal")
        validar_uuid("approval_id", self.approval_id)
        validar_uuid("nonce", self.nonce)
        if self.approval_id == self.nonce:
            raise ValueError(
                "nonce não pode ser igual a approval_id — seria o mesmo valor "
                "com dois nomes, e nenhum dos dois seria nonce"
            )
        if not isinstance(self.identity, IdentityEvidence):
            raise TypeError("identity deve ser um IdentityEvidence")
        if not isinstance(self.context, ApprovalContext):
            raise TypeError("context deve ser um ApprovalContext")
        if not isinstance(self.provenance, SafeVoiceProvenance):
            raise TypeError("provenance deve ser um SafeVoiceProvenance")

        for nome in ("issued_at", "confirmed_at", "expires_at"):
            validar_instante_ciente(nome, getattr(self, nome))

        if self.proposal.blockers:
            raise ValueError(
                "proposta com bloqueio não forma envelope — aprovar sobre "
                "legal hold ou conflito produziria autorização que a governança "
                "já negou"
            )

        if not self.identity.assurance_level.satisfies(self.proposal.operation):
            raise ValueError(
                f"{self.proposal.operation.value} não é admissível com assurance "
                f"{self.identity.assurance_level.value} — apagamento definitivo "
                "exige step-up, e nenhuma operação aceita ausência de evidência"
            )

        if self.context != self.proposal.context:
            raise ValueError(
                "contexto do envelope diverge da proposta — tenant, workspace, "
                "domínio ou finalidade mudaram, e mudança exige nova proposta"
            )
        if self.provenance != self.proposal.provenance:
            raise ValueError(
                "canal do envelope diverge da proposta — a confirmação vincula o "
                "canal em que a intenção foi apresentada"
            )

        if not self.proposal.materialized_at <= self.issued_at:
            raise ValueError("issued_at não pode preceder a materialização da proposta")
        if not self.issued_at <= self.confirmed_at:
            raise ValueError("confirmed_at não pode preceder issued_at")
        if not self.confirmed_at < self.expires_at:
            raise ValueError(
                "expires_at deve ser posterior a confirmed_at — uma aprovação que "
                "expira ao ser confirmada nunca foi válida"
            )

    def is_temporally_coherent_at(self, instante: datetime) -> bool:
        """A janela declarada contém este instante **recebido**?

        ```text
        EXPIRES_AT_PRESENT != EXPIRY_ENFORCED
        ```

        Função pura. Recebe o instante explicitamente — `datetime.now()`
        escondido é proibido, e um relógio interno faria o objeto
        depender de quando é perguntado.

        O nome diz o que ela observa e nada além: **não** verifica
        revogação, consumo, replay ou autoridade externa, porque nada
        disso existe nesta fatia. Nenhuma duração canônica é inventada —
        a janela vem do chamador.
        """
        validar_instante_ciente("instante", instante)
        return self.confirmed_at <= instante < self.expires_at

    def __repr__(self) -> str:
        return (
            f"DestructiveApprovalEnvelope(approval_id={self.approval_id!r}, "
            f"nonce={self.nonce!r}, "
            f"proposal={self.proposal!r}, "
            f"identity={self.identity!r}, "
            f"context={self.context!r}, "
            f"provenance={self.provenance!r}, "
            f"issued_at={self.issued_at!r}, "
            f"confirmed_at={self.confirmed_at!r}, "
            f"expires_at={self.expires_at!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()
