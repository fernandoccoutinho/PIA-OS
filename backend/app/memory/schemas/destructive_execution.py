"""
Contratos tipados da composição destrutiva final (`E4.9.9.d`).

```text
aprovação persistida
→ re-resolução fresca e observacional
→ comparação com o snapshot aprovado
→ consumo durável e atômico
→ tentativa pela porta de efeito
→ recibo somente após tentativa material observada
```

Este módulo define **o que entra** e **o que sai** do
`DestructiveExecutionService`. Ele não resolve, não consome, não tenta
efeito e não escreve recibo: é a fronteira de tipos que torna cada
desfecho distinguível sem texto livre.

## O que o resultado nunca transporta

```text
NO_LOCATOR · NO_CAPABILITY · NO_CREDENTIAL · NO_SECRET
NO_CONTENT · NO_NATURAL_LANGUAGE_COMMAND
NO_WHOLE_GOVERNANCE_RESOLUTION_IN_REPR
```

Todo `__repr__` daqui é **escrito**, nunca delegado. A E4.9.9.b já pagou
essa lição do outro lado da fronteira: delegar a um objeto que hoje
redige bem deixa a exposição desta classe depender de uma decisão que
não é dela.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.memory.models.approval_enums import DestructiveOperation
from app.memory.models.approval_lifecycle_enums import ApprovalUsageRefusalReason
from app.memory.models.destructive_execution_enums import (
    PreConsumptionRefusalReason,
    SnapshotDivergenceField,
)
from app.memory.models.erasure_effect_enums import MaterialAttemptRefusalReason
from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.memory.models.target_resolution_enums import TargetResolutionRefusalReason
from app.memory.schemas.destructive_approval import DestructiveApprovalEnvelope
from app.memory.schemas.erasure_target import (
    CLASSES_DE_CONTEUDO,
    ErasureTargetReference,
    validar_instante_ciente,
)

SUFIXO_DE_RESOLUCAO = "governance-resolution"
"""Sufixo canônico da referência de resolução citada no recibo."""


def referencia_de_resolucao_de_governanca(approval_id: uuid.UUID) -> str:
    """Monta `approval:<approval_id>:governance-resolution`.

    ```text
    RESOLUTION_REF = POINTER_TO_EMBEDDED_RESOLUTION
    RESOLUTION_REF != DIGEST
    RESOLUTION_REF != CONTENT_HASH
    RESOLUTION_REF != POINTER_TO_ERASED_MATERIAL
    ```

    Aponta para a `GovernanceResolution` **integral** já incorporada ao
    `ApprovalRecord` — as seis tuplas e os escalares que a E4.9.9.a
    persistiu em três tabelas justamente para que a resolução exata
    fosse reconstruível. Não é digest nem hash: a E4.9.8 recusou hash
    sobre dados de custódia porque um digest sem canonicalização provada
    pode virar chave de relocalização.

    Helper **único e puro**, e é por isso que existe. Concatenação
    espalhada por cada chamador divergiria na primeira mudança de
    formato, e o recibo é append-only: uma referência gravada errada não
    se corrige depois.
    """
    if not isinstance(approval_id, uuid.UUID):
        raise TypeError(
            f"approval_id deve ser UUID, recebido {type(approval_id).__name__} — "
            "texto equivalente não é identificador"
        )
    return f"approval:{approval_id}:{SUFIXO_DE_RESOLUCAO}"


RAZOES_DE_LOTE = frozenset(
    {
        PreConsumptionRefusalReason.BATCH_CARDINALITY_MISMATCH,
        PreConsumptionRefusalReason.GOVERNANCE_PROVENANCE_INCOMPLETE,
    }
)
"""Recusas que descrevem o **lote inteiro**, e por isso não têm posição.

Enumeradas literalmente, e não derivadas por exclusão: um membro novo em
`PreConsumptionRefusalReason` cai no ramo que exige posição, que é o
comportamento seguro — uma recusa sem posição passaria despercebida,
enquanto uma que a exige falha alto.
"""


def _validar_uuid(nome: str, valor: object) -> uuid.UUID:
    if not isinstance(valor, uuid.UUID):
        raise TypeError(f"{nome} deve ser UUID, recebido {type(valor).__name__}")
    return valor


def _validar_posicao(valor: object) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"position deve ser int, recebido {type(valor).__name__}")
    if valor < 0:
        raise ValueError("position deve ser >= 0")
    return valor


@dataclass(frozen=True)
class DestructiveExecutionRequest:
    """O que se pede ao serviço: a aprovação exata e onde reprocurar.

    ```text
    ENVELOPE + ORDERED_REFERENCES -> EXECUTION_ATTEMPT
    ```

    As referências **não** são o lote aprovado: o lote aprovado são os
    `SafeTargetSnapshot` dentro do envelope, e eles não têm localizador.
    As referências dizem por onde re-resolver, e a correspondência
    posicional entre as duas tuplas é verificada aqui, antes de qualquer
    resolução.

    ```text
    APPROVED_SNAPSHOT = WHAT_THE_USER_CONFIRMED
    REFERENCE         = WHERE_TO_LOOK_AGAIN
    ```

    O que este construtor **não** faz: resolver, consumir, comparar com
    resolução fresca (não existe ainda) ou autenticar. Ele só recusa o
    pedido que já é incoerente com o aprovado.
    """

    envelope: DestructiveApprovalEnvelope
    references: tuple[ErasureTargetReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, DestructiveApprovalEnvelope):
            raise TypeError(
                f"envelope deve ser um DestructiveApprovalEnvelope, recebido "
                f"{type(self.envelope).__name__}"
            )
        if not isinstance(self.references, tuple):
            raise TypeError(
                f"references deve ser tuple[ErasureTargetReference, ...], recebido "
                f"{type(self.references).__name__} — coleção mutável e conjunto não "
                "preservam a ordem que faz parte do binding"
            )
        if not self.references:
            raise ValueError(
                "execução destrutiva exige ao menos uma referência — um lote "
                "vazio não corresponde a nenhum lote aprovado"
            )
        for indice, referencia in enumerate(self.references):
            if not isinstance(referencia, ErasureTargetReference):
                raise TypeError(
                    f"references[{indice}] deve ser ErasureTargetReference, "
                    f"recebido {type(referencia).__name__}"
                )

    @property
    def approval_id(self) -> uuid.UUID:
        return self.envelope.approval_id

    @property
    def operation(self) -> DestructiveOperation:
        return self.envelope.proposal.operation

    def __repr__(self) -> str:
        """Identidade e cardinalidade; nunca as referências opacas."""
        return (
            f"DestructiveExecutionRequest(approval_id={self.approval_id!r}, "
            f"operation={self.operation.value!r}, "
            f"reference_count={len(self.references)})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class PreConsumptionRefusal:
    """O lote parou **antes** de qualquer escrita.

    ```text
    NO_CONSUMPTION · NO_EFFECT · NO_RECEIPT
    APPROVAL_REMAINS_ACTIVE
    ```

    A aprovação continua utilizável: nada aconteceu com ela. É o desfecho
    de proteção de legado alterada, `version_etag` mudado, resolução
    recusada, cardinalidade divergente e proveniência de governança
    incompleta.

    `position` é o índice do alvo que motivou a recusa, quando houve um.
    `None` significa que a recusa é do lote inteiro — cardinalidade não
    tem posição.
    """

    approval_id: uuid.UUID
    operation: DestructiveOperation
    reason: PreConsumptionRefusalReason
    position: int | None = None
    diverged_field: SnapshotDivergenceField | None = None
    """Qual campo divergiu — só em `FRESH_SNAPSHOT_DIVERGED`."""

    resolution_refusal: TargetResolutionRefusalReason | None = None
    """Motivo tipado devolvido pela porta — só em `TARGET_RESOLUTION_REFUSED`."""

    def __post_init__(self) -> None:
        _validar_uuid("approval_id", self.approval_id)
        if not isinstance(self.operation, DestructiveOperation):
            raise TypeError("operation deve ser um DestructiveOperation")
        if not isinstance(self.reason, PreConsumptionRefusalReason):
            raise TypeError(
                f"reason deve ser um PreConsumptionRefusalReason, recebido "
                f"{type(self.reason).__name__} — texto livre não é motivo"
            )
        if self.position is not None:
            _validar_posicao(self.position)

        # --------------------------------------------------------------
        # Matriz de coerência. `CORRECT_FACTORY_OUTPUT != SAFE_PUBLIC
        # _RESULT_CONSTRUCTOR` — a décima vez que o projeto aplica a
        # lição de que invariante que só existe na fábrica é contornável
        # pelo construtor direto (E4.9.9.c.1, A2).
        # --------------------------------------------------------------
        divergencia = self.reason is PreConsumptionRefusalReason.FRESH_SNAPSHOT_DIVERGED
        if divergencia and self.diverged_field is None:
            raise ValueError(
                "fresh_snapshot_diverged exige diverged_field — uma divergência "
                "que não diz qual campo divergiu não é acionável"
            )
        if not divergencia and self.diverged_field is not None:
            raise ValueError(
                f"{self.reason.value} não admite diverged_field — só a comparação "
                "com o snapshot aprovado observa campo divergente"
            )
        if self.diverged_field is not None and not isinstance(
            self.diverged_field, SnapshotDivergenceField
        ):
            raise TypeError("diverged_field deve ser um SnapshotDivergenceField")

        recusa = self.reason is PreConsumptionRefusalReason.TARGET_RESOLUTION_REFUSED
        if recusa and self.resolution_refusal is None:
            raise ValueError(
                "target_resolution_refused exige resolution_refusal — a porta "
                "devolve motivo tipado e perdê-lo faria toda recusa parecer igual"
            )
        if not recusa and self.resolution_refusal is not None:
            raise ValueError(f"{self.reason.value} não admite resolution_refusal")
        if self.resolution_refusal is not None and not isinstance(
            self.resolution_refusal, TargetResolutionRefusalReason
        ):
            raise TypeError("resolution_refusal deve ser um TargetResolutionRefusalReason")

        # As DUAS razões que descrevem o lote inteiro, e não um alvo dele.
        # A primeira versão listava só a cardinalidade, e a composição
        # teria levantado `ValueError` ao recusar por proveniência de
        # governança incompleta — o teste `u15` pegou antes do commit.
        #
        # ```text
        # BATCH_LEVEL_REFUSAL -> NO_POSITION
        # ```
        exige_posicao = self.reason not in RAZOES_DE_LOTE
        if exige_posicao and self.position is None:
            raise ValueError(
                f"{self.reason.value} exige position — a recusa observou um alvo "
                "específico do lote"
            )
        if not exige_posicao and self.position is not None:
            raise ValueError(
                f"{self.reason.value} não admite position — a divergência é do "
                "lote inteiro, não de um alvo"
            )


@dataclass(frozen=True)
class ApprovalConsumptionRefusal:
    """O consumo foi tentado e **não venceu**.

    ```text
    NO_EFFECT · NO_RECEIPT
    REPLAY_WITH_SAME_APPROVAL = REFUSED
    ```

    Distinta de `PreConsumptionRefusal` porque aqui o comando atômico
    chegou ao banco. É o desfecho do replay (`ALREADY_CONSUMED`), da
    aprovação vencida, da revogada e do binding divergente — e o motivo
    é o vocabulário fechado que a própria E4.9.9.a definiu, não um
    paralelo inventado aqui.
    """

    approval_id: uuid.UUID
    operation: DestructiveOperation
    reason: ApprovalUsageRefusalReason

    def __post_init__(self) -> None:
        _validar_uuid("approval_id", self.approval_id)
        if not isinstance(self.operation, DestructiveOperation):
            raise TypeError("operation deve ser um DestructiveOperation")
        if not isinstance(self.reason, ApprovalUsageRefusalReason):
            raise TypeError(
                f"reason deve ser um ApprovalUsageRefusalReason, recebido "
                f"{type(self.reason).__name__}"
            )


@dataclass(frozen=True)
class TargetNotAttempted:
    """Nenhuma tentativa material começou para este alvo.

    ```text
    NO_MATERIAL_ATTEMPT -> NO_ERASURE_RECORD
    ```

    Não há campo de recibo aqui, e a ausência é o mecanismo: um alvo não
    tentado não tem onde guardar um `erasure_record_id`, então nenhum
    relatório pode alegar recibo sobre tentativa que não houve.
    """

    position: int
    subject_coid: uuid.UUID
    reason: MaterialAttemptRefusalReason
    observed_at: datetime

    def __post_init__(self) -> None:
        _validar_posicao(self.position)
        _validar_uuid("subject_coid", self.subject_coid)
        if not isinstance(self.reason, MaterialAttemptRefusalReason):
            raise TypeError(
                f"reason deve ser um MaterialAttemptRefusalReason, recebido "
                f"{type(self.reason).__name__}"
            )
        validar_instante_ciente("observed_at", self.observed_at)


@dataclass(frozen=True)
class TargetAttempted:
    """Uma tentativa material ocorreu, foi observada e gerou **um** recibo.

    ```text
    OBSERVED_ATTEMPT -> EXACTLY_ONE_ERASURE_RECORD
    ```

    `erasure_record_id` é obrigatório e sem default. Torná-lo opcional
    permitiria representar tentativa observada sem recibo — que é
    precisamente o estado que esta fatia existe para tornar
    inconstruível.
    """

    position: int
    subject_coid: uuid.UUID
    target_class: ErasureTargetClass
    outcome: ErasureOutcome
    erasure_record_id: uuid.UUID
    attempted_at: datetime
    completed_at: datetime

    def __post_init__(self) -> None:
        _validar_posicao(self.position)
        _validar_uuid("subject_coid", self.subject_coid)
        if not isinstance(self.target_class, ErasureTargetClass):
            raise TypeError("target_class deve ser um ErasureTargetClass")
        if self.target_class not in CLASSES_DE_CONTEUDO:
            raise ValueError(
                f"{self.target_class.value} não é conteúdo apagável — não há "
                "tentativa material sobre metadado cognitivo"
            )
        if not isinstance(self.outcome, ErasureOutcome):
            raise TypeError(
                f"outcome deve ser um ErasureOutcome, recebido "
                f"{type(self.outcome).__name__} — a fonte única é a da E4.9.5"
            )
        _validar_uuid("erasure_record_id", self.erasure_record_id)
        validar_instante_ciente("attempted_at", self.attempted_at)
        validar_instante_ciente("completed_at", self.completed_at)
        if self.completed_at < self.attempted_at:
            raise ValueError("completed_at anterior a attempted_at")


TargetExecutionOutcome = TargetNotAttempted | TargetAttempted
"""União fechada do desfecho por alvo — sem `bool`, sem `None`.

Um booleano não distinguiria *não tentado* de *tentado e falhado*, e
essa é exatamente a distinção que decide se existe recibo.
"""


@dataclass(frozen=True)
class DestructiveExecutionReport:
    """A aprovação foi consumida e o lote foi processado.

    ```text
    CONSUMPTION_COMMITTED_BEFORE_EFFECT = REQUIRED
    ```

    Existir este objeto significa que o consumo **commitou**. Ele não
    significa que todo alvo foi apagado: `targets` distingue, posição a
    posição, o que foi tentado e observado do que não foi tentado.
    """

    approval_id: uuid.UUID
    operation: DestructiveOperation
    consumed_at: datetime
    targets: tuple[TargetExecutionOutcome, ...]

    def __post_init__(self) -> None:
        _validar_uuid("approval_id", self.approval_id)
        if not isinstance(self.operation, DestructiveOperation):
            raise TypeError("operation deve ser um DestructiveOperation")
        validar_instante_ciente("consumed_at", self.consumed_at)

        if not isinstance(self.targets, tuple):
            raise TypeError(
                f"targets deve ser tuple[TargetExecutionOutcome, ...], recebido "
                f"{type(self.targets).__name__} — `set` perderia a ordem aprovada"
            )
        if not self.targets:
            raise ValueError(
                "relatório de execução exige ao menos um alvo — consumir "
                "aprovação e não processar nada não é desfecho representável"
            )

        sujeitos: set[uuid.UUID] = set()
        recibos: set[uuid.UUID] = set()
        for indice, alvo in enumerate(self.targets):
            if not isinstance(alvo, TargetNotAttempted | TargetAttempted):
                raise TypeError(
                    f"targets[{indice}] deve ser TargetNotAttempted ou "
                    f"TargetAttempted, recebido {type(alvo).__name__}"
                )
            if alvo.position != indice:
                raise ValueError(
                    f"targets[{indice}] declara position={alvo.position} — a "
                    "posição é a do lote aprovado e não é reordenada"
                )
            if alvo.subject_coid in sujeitos:
                raise ValueError(
                    f"sujeito repetido no relatório: {alvo.subject_coid} — cada "
                    "alvo do lote aprovado é distinto"
                )
            sujeitos.add(alvo.subject_coid)
            if isinstance(alvo, TargetAttempted):
                if alvo.erasure_record_id in recibos:
                    raise ValueError(
                        f"recibo repetido: {alvo.erasure_record_id} — um recibo "
                        "registra exatamente uma tentativa observada"
                    )
                recibos.add(alvo.erasure_record_id)

    @property
    def attempts_observed(self) -> int:
        """Quantos alvos tiveram tentativa material observada."""
        return sum(1 for alvo in self.targets if isinstance(alvo, TargetAttempted))

    @property
    def receipts_persisted(self) -> tuple[uuid.UUID, ...]:
        """Os recibos efetivamente gravados, na ordem do lote."""
        return tuple(
            alvo.erasure_record_id for alvo in self.targets if isinstance(alvo, TargetAttempted)
        )

    @property
    def not_attempted(self) -> int:
        """Quantos alvos não tiveram tentativa material alguma."""
        return sum(1 for alvo in self.targets if isinstance(alvo, TargetNotAttempted))


DestructiveExecutionResult = (
    PreConsumptionRefusal | ApprovalConsumptionRefusal | DestructiveExecutionReport
)
"""União **fechada** dos desfechos da execução destrutiva.

```text
PreConsumptionRefusal      nada foi escrito, aprovação segue ativa
ApprovalConsumptionRefusal consumo tentado e recusado, sem efeito
DestructiveExecutionReport consumo commitado, lote processado
```

O quarto desfecho — estado material desconhecido após exceção da porta —
**não** está aqui de propósito. Ele é exceção tipada, não valor: um
resultado que o chamador pudesse ignorar por engano faria o caso mais
grave passar como se fosse rotina.
"""


@dataclass(frozen=True)
class PartialExecutionEvidence:
    """Quanto do lote já era fato quando a porta deixou o estado ambíguo.

    Carregada pela exceção de estado desconhecido. Preserva o que **foi
    confirmado** antes da ambiguidade — nunca uma inferência sobre o
    alvo em que ela ocorreu.

    ```text
    EXCEPTION != OBSERVED_OUTCOME
    TIMEOUT   != PROOF_OF_NO_EFFECT
    ```
    """

    approval_id: uuid.UUID
    failed_position: int
    subject_coid: uuid.UUID
    attempts_observed: int
    receipts_persisted: int
    targets_not_attempted: int = field(default=0)

    def __post_init__(self) -> None:
        _validar_uuid("approval_id", self.approval_id)
        _validar_posicao(self.failed_position)
        _validar_uuid("subject_coid", self.subject_coid)
        for nome in ("attempts_observed", "receipts_persisted", "targets_not_attempted"):
            valor = getattr(self, nome)
            if isinstance(valor, bool) or not isinstance(valor, int):
                raise TypeError(f"{nome} deve ser int, recebido {type(valor).__name__}")
            if valor < 0:
                raise ValueError(f"{nome} não pode ser negativo")
        if self.receipts_persisted > self.attempts_observed:
            raise ValueError(
                "recibos persistidos excedem tentativas observadas — cada recibo "
                "registra exatamente uma tentativa"
            )


@dataclass(frozen=True)
class GovernanceProvenance:
    """As quatro fontes de governança que o recibo cita — **não opcionais**.

    ```text
    OPTIONAL_IN_E4_3 != OPTIONAL_HERE
    NARROWING_LIVES_IN_THE_TYPE, NOT_IN_A_BOOLEAN
    ```

    `GovernanceResolution` declara os quatro campos como opcionais, e um
    predicado booleano que apenas *verificasse* a presença deixaria o
    tipo ainda opcional na hora de montar o recibo — o que só se
    resolveria com `cast` ou `type: ignore`, ambos proibidos.

    Esta classe é o estreitamento: ou ela existe, com os quatro valores
    presentes, ou a composição recusa antes do efeito. Nada é completado
    com default, e nenhum identificador é convertido: `matched_rule_id`
    atravessa como **texto opaco**, byte a byte.
    """

    policy_id: uuid.UUID
    policy_key: str
    policy_version: int
    matched_rule_id: str

    def __post_init__(self) -> None:
        _validar_uuid("policy_id", self.policy_id)
        for nome in ("policy_key", "matched_rule_id"):
            valor = getattr(self, nome)
            if not isinstance(valor, str):
                raise TypeError(f"{nome} deve ser str, recebido {type(valor).__name__}")
            if not valor.strip():
                raise ValueError(f"{nome} não pode ser vazio ou apenas espaços")
        if isinstance(self.policy_version, bool) or not isinstance(self.policy_version, int):
            raise TypeError(
                f"policy_version deve ser int, recebido {type(self.policy_version).__name__}"
            )
        if self.policy_version < 1:
            raise ValueError("policy_version deve ser >= 1")
