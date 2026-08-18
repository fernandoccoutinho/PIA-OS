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
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType

from app.memory.models.approval_enums import (
    ApprovalBlockerKind,
    AssuranceLevel,
    DestructiveOperation,
    ImpactVolumeKind,
    InputChannel,
    VoiceReviewState,
)
from app.memory.models.erasure_enums import ErasureTargetClass
from app.memory.models.governance_enums import CognitiveOperation, GovernanceOutcome
from app.memory.models.target_resolution_enums import LegacyProtectionState
from app.memory.schemas.erasure_target import (
    CLASSES_DE_CONTEUDO,
    TEXTO_OCULTO,
    ControlScope,
    CustodyNamespace,
    ErasureTargetDescriptor,
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


OPERACAO_DE_GOVERNANCA: Mapping[DestructiveOperation, CognitiveOperation] = MappingProxyType(
    {
        DestructiveOperation.MOVE_TO_TRASH: (CognitiveOperation.RETENTION_DISPOSITION),
        DestructiveOperation.PERMANENT_ERASURE: CognitiveOperation.LEGAL_ERASURE,
    }
)
"""Correspondência **positiva** entre operação destrutiva e a pergunta
que a governança precisa ter respondido (`E4.9.8.1`).

```text
MUTABLE_AUTHORITY_MATRIX = NONE
```

**Somente leitura desde a E4.9.8.2, e a mudança não é estilística.** A
cadeia 86 publicou esta tabela como `dict`, e a auditoria mediu a
consequência: uma atribuição pública trocava `PERMANENT_ERASURE` por
`READ` e uma resolução de leitura passava a autorizar apagamento
permanente — reabrindo exatamente o binding que a E4.9.8.1 existia para
fechar.

`frozen=True` nos value objects **não** protege uma dependência global
mutável. A guarda que eu escrevi (`s19`) contava um único `AnnAssign` e
as ocorrências no texto executável: provava unicidade **textual**, nunca
tentou mutar, e por isso não podia falhar.

O `MappingProxyType` recusa `__setitem__` e não expõe `update`, `pop`,
`clear`, `setdefault`, `popitem` nem `__delitem__`. O dicionário
subjacente é um **literal sem nome**: nenhum símbolo de módulo o
referencia, então não há atributo por onde alcançá-lo e mutá-lo.

Limite declarado, e não escondido: isto protege contra mutação
**acidental e idiomática**, não contra introspecção deliberada de runtime
(por exemplo `gc.get_referents`). É a mesma posição das redações de
representação das fatias anteriores.

```text
GOVERNANCE_RESOLUTION_PRESENT != GOVERNANCE_AUTHORITY_FOR_THIS_ACTION
WRONG_OPERATION != APPROVABLE
```

Fonte **única** no módulo. A cadeia 85 incorporava o objeto exato e
verificava apenas `isinstance` — então uma resolução de
`CognitiveOperation.READ` autorizava um apagamento permanente. Objeto
exato não é resolução exata **daquela pergunta**.

Correspondência positiva, sem fallback: `READ`, `RETENTION_ASSESSMENT`,
`ACCESSIBILITY_TRANSITION` e qualquer outra são erro controlado. Um
membro novo em `DestructiveOperation` sem entrada aqui derruba os testes
antes de virar autorização implícita.
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
    legacy_protection_state: LegacyProtectionState
    """Proteção de legado apresentada, parte do binding (`E4.9.8.3`).

    Obrigatório e sem default, pelas mesmas razões de
    `ErasureTargetDescriptor.legacy_protection_state`, e participa da
    igualdade estrutural: dois snapshots idênticos exceto pela proteção são
    **diferentes**.

    ```text
    STRUCTURAL_DISTINGUISHABILITY = IMPLEMENTED_HERE
    EFFECTIVE_INVALIDATION = DEFERRED_TO_E4_9_9_D
    ```

    Registro honesto do alcance: esta fatia torna estados opostos
    distinguíveis e vinculáveis. Comparar o snapshot aprovado com uma
    re-resolução fresca — e recusar a execução quando divergirem — é da
    E4.9.9.d. A proposta **armazena e valida** o lote; não compara contra
    resolução futura, porque não existe resolução futura ainda.
    """

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
        if not isinstance(self.legacy_protection_state, LegacyProtectionState):
            raise TypeError(
                f"legacy_protection_state deve ser um LegacyProtectionState, "
                f"recebido {type(self.legacy_protection_state).__name__} — "
                "string equivalente, bool e None não são membros"
            )
        if self.version_etag is not None:
            validar_texto_opaco("version_etag", self.version_etag)

    @classmethod
    def from_descriptor(cls, descriptor: ErasureTargetDescriptor) -> "SafeTargetSnapshot":
        """Materializador canônico do snapshot a partir do descritor.

        ```text
        SNAPSHOT != DESCRIPTOR
        LOCATOR_NEVER_CROSSES
        ```

        Acrescentado pela `E4.9.8.3`. Antes desta fatia não havia nenhuma
        conversão de produção — medido: **zero** construções de
        `SafeTargetSnapshot` e **zero** conversões descritor→snapshot fora
        de teste. Sem um ponto canônico, a cópia dos sete campos ficaria
        espalhada por cada chamador futuro, e a exclusão do localizador
        dependeria de cada um lembrar de não copiá-lo.

        Cópia **explícita**, campo a campo. Sem `dataclasses.asdict`, sem
        `**`, sem reflexão: o que passa é exatamente o que está escrito
        aqui, e uma guarda estática fixa esta lista na AST.

        Copiados — os sete:

        ```text
        target_class · subject_coid · control_scope · custody_namespace
        origin · version_etag · legacy_protection_state
        ```

        Excluídos — os três, e cada um por uma razão distinta:

        ```text
        transient_locator  endereça o objeto material; a E4.9.7 gastou dois
                           corretivos estabelecendo que ele não sobrevive
                           ao efeito, e um snapshot que circula e é
                           apresentado o levaria junto
        capability         é o que a CONTA pode; o snapshot descreve o que
                           foi APRESENTADO ao usuário, não a autoridade
        resolved_at        instante da resolução, transitório por natureza;
                           o instante que importa à aprovação é o da
                           materialização da proposta
        ```

        Não valida nem reinterpreta: o descritor já é válido por
        construção, e o snapshot revalida por `__post_init__`.
        """
        if not isinstance(descriptor, ErasureTargetDescriptor):
            raise TypeError(
                f"from_descriptor exige ErasureTargetDescriptor, recebido "
                f"{type(descriptor).__name__}"
            )
        return cls(
            target_class=descriptor.target_class,
            subject_coid=descriptor.subject_coid,
            control_scope=descriptor.control_scope,
            custody_namespace=descriptor.custody_namespace,
            origin=descriptor.origin,
            legacy_protection_state=descriptor.legacy_protection_state,
            version_etag=descriptor.version_etag,
        )

    def __repr__(self) -> str:
        return (
            f"SafeTargetSnapshot(target_class={self.target_class.value!r}, "
            f"subject_coid={self.subject_coid!r}, "
            f"control_scope={self.control_scope!r}, "
            f"custody_namespace={self.custody_namespace!r}, "
            f"origin={self.origin!r}, "
            f"legacy_protection_state={self.legacy_protection_state.value!r}, "
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
        vistos_bloqueios: set[ApprovalBlockerKind] = set()
        for indice, bloqueio in enumerate(self.blockers):
            if not isinstance(bloqueio, ApprovalBlockerKind):
                raise TypeError(
                    f"blockers[{indice}] deve ser ApprovalBlockerKind, recebido "
                    f"{type(bloqueio).__name__}"
                )
            # E4.9.8.1: duplicata recusada, NÃO desduplicada. Um `set` ou
            # `frozenset` perderia a ordem declarada, e absorver a
            # repetição em silêncio esconderia um erro de quem montou a
            # proposta. A ordem faz parte do que foi apresentado.
            if bloqueio in vistos_bloqueios:
                raise ValueError(
                    f"blocker duplicado: {bloqueio.value} — repetição não é "
                    "absorvida nem reordenada, é recusada"
                )
            vistos_bloqueios.add(bloqueio)

        validar_instante_ciente("materialized_at", self.materialized_at)

        if not self.provenance.voice_review.permite_proposta(self.provenance.channel):
            raise ValueError(
                f"entrada de voz em estado {self.provenance.voice_review.value} não "
                "forma proposta — baixa confiança, ambiguidade e ausência de "
                "revisão pertencem à fronteira anterior e não são corrigidas aqui"
            )

        # ------------------------------------------------------------------
        # E4.9.8.1 — a governança respondeu ESTA pergunta?
        #
        # A cadeia 85 exigia apenas que o campo fosse uma
        # `GovernanceResolution`. Eu escrevi no EDR que ação, policy,
        # domínio e finalidade estavam vinculados, e o runtime não
        # comparava nada. As quatro checagens abaixo são o binding que a
        # matriz do §5 daquele documento afirmava existir.
        #
        # HUMAN_CONFIRMATION CANNOT CREATE MISSING AUTHORITY
        # ------------------------------------------------------------------
        resolucao = self.governance_resolution

        if resolucao.outcome is not GovernanceOutcome.ADMISSIBLE:
            raise ValueError(
                f"governança respondeu {resolucao.outcome.value} — proposta "
                "destrutiva exige ADMISSIBLE. INADMISSIBLE, NOT_APPLICABLE e "
                "PROHIBITED não concedem, e confirmação humana não cria "
                "autoridade ausente"
            )
        # Segunda condição, INDEPENDENTE da primeira. Hoje
        # `execution_authorized` é derivada do outcome, mas o contrato não
        # deve depender disso: se a E4.3 passar a derivá-la de outra coisa,
        # esta linha continua exigindo autorização de execução.
        if not resolucao.execution_authorized:
            raise ValueError(
                "governança não autoriza execução — outcome admissível sem "
                "execution_authorized não é autorização"
            )

        esperada = OPERACAO_DE_GOVERNANCA[self.operation]
        if resolucao.operation is not esperada:
            raise ValueError(
                f"{self.operation.value} exige resolução de {esperada.value}, "
                f"e a apresentada avaliou {resolucao.operation.value} — "
                "resolução de outra ação não autoriza esta"
            )

        if resolucao.context_domain_ids != (self.context.domain_id,):
            raise ValueError(
                "domínio avaliado pela governança diverge do domínio da "
                "proposta — subconjunto, interseção e conjunto mais amplo não "
                "são a mesma pergunta"
            )

        if resolucao.context_purpose != self.context.purpose_ref:
            raise ValueError(
                "finalidade avaliada pela governança diverge da finalidade da "
                "proposta — finalidade aproximada não é a mesma pergunta"
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

        # ------------------------------------------------------------------
        # E4.9.8.1 — a governança avaliou o MESMO principal que a fronteira
        # externa declarou autenticado, e esse principal controla os alvos?
        #
        # A igualdade NÃO promove `context_actor_ref` a autenticador. Ela
        # impede que governança, identidade externa e alvo descrevam
        # PESSOAS DIFERENTES — que é coisa distinta, e a única que um
        # contrato sem autenticador pode verificar.
        #
        # STRING_EQUALITY != AUTHENTICATION
        # ------------------------------------------------------------------
        if self.proposal.governance_resolution.context_actor_ref != (self.identity.principal_ref):
            raise ValueError(
                "ator avaliado pela governança diverge do principal declarado "
                "autenticado — a governança respondeu sobre outra pessoa"
            )

        # Enquanto não existe delegação modelada, o contrato só representa o
        # caso DIRETO: quem confirma é quem controla. Papel, grupo,
        # procuração, ACL e admin override NÃO são modelados aqui, e
        # inventá-los seria criar autoridade organizacional sem contrato.
        for indice, alvo in enumerate(self.proposal.targets):
            if alvo.control_scope.control_principal_ref != self.identity.principal_ref:
                raise ValueError(
                    f"alvo[{indice}] é controlado por outro principal — sem "
                    "modelo de delegação, apenas o próprio controlador forma "
                    "envelope"
                )

        # `authenticated_at` participa da ordem temporal desde a E4.9.8.1.
        # Antes da proposta é sessão antiga, não step-up vinculado à ação;
        # depois da confirmação é causalmente impossível como fundamento
        # dela. Nenhuma duração canônica é inventada.
        if not self.proposal.materialized_at <= self.identity.authenticated_at:
            raise ValueError(
                "authenticated_at anterior à materialização da proposta — "
                "sessão antiga não é step-up vinculado a esta ação"
            )
        if not self.identity.authenticated_at <= self.confirmed_at:
            raise ValueError(
                "authenticated_at posterior à confirmação — uma autenticação "
                "que ocorre depois não pode ser o fundamento dela"
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
