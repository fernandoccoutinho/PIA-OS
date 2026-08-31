"""
Contratos tipados da fronteira de efeito destrutivo (`E4.9.9.b`).

```text
REFERENCE           != RESOLVED_TARGET
RESOLUTION          != DELETION_AUTHORITY
APPROVAL            != CONSUMPTION
CONSUMPTION         != EFFECT
EFFECT              != ERASURE_RECORD
NO_MATERIAL_ATTEMPT -> NO_ERASURE_RECORD
```

Esta fatia materializa **contratos inertes**. Não existe adaptador,
executor, chamada externa, re-resolução, comparação com snapshot, consumo
de `ApprovalRecord` ou escritor de recibo.

## Quatro desfechos, três no enum

```text
NOT_STARTED | SUCCEEDED | FAILED | PARTIAL
```

`SUCCEEDED`, `FAILED` e `PARTIAL` vêm de `ErasureOutcome`, fonte única
desde a E4.9.5 — duplicá-los criaria duas verdades sobre o que foi
observado.

`NOT_STARTED` fica **fora** do enum de propósito: entrar ali o tornaria
elegível a recibo, e recibo descreve tentativa material.

## Confidencialidade composta

O request contém o descritor, e o descritor contém `transient_locator`.
Delegar `descriptor!r` vazaria o localizador — é o defeito A5 que a
cadeia 82 mediu em nove campos. Todo `__repr__` aqui é escrito, nunca
delegado ingenuamente.

```text
UNRESTRICTED_PUBLIC_STR = MAY_CONTAIN_SENSITIVE_VALUE
DIRECT_REDACTION != COMPOSITE_REDACTION
```

O **resultado** nunca transporta localizador nem capacidade.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.memory.models.approval_enums import DestructiveOperation
from app.memory.models.erasure_effect_enums import (
    EffectAttemptStage,
    MaterialAttemptRefusalReason,
)
from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.memory.schemas.erasure_target import (
    CLASSES_DE_CONTEUDO,
    TEXTO_OCULTO,
    ErasureTargetDescriptor,
    validar_instante_ciente,
    validar_texto_opaco,
)

DESCRITOR_OCULTO = "<erasure_target_descriptor:redacted>"
"""O que `repr()` mostra no lugar do descritor incorporado.

`ErasureTargetDescriptor` redige o próprio localizador, mas a requisição
**não delega** mesmo assim: um campo novo no descritor, ou uma alteração
no `__repr__` dele, mudaria o que esta classe expõe sem que ninguém aqui
decidisse. A redação explícita torna a composição uma decisão local.
"""


def _validar_uuid(nome: str, valor: object) -> uuid.UUID:
    if not isinstance(valor, uuid.UUID):
        raise TypeError(f"{nome} deve ser UUID, recebido {type(valor).__name__}")
    return valor


@dataclass(frozen=True)
class ConsumedApprovalEvidence:
    """Evidência **tipada** de que a aprovação já foi consumida.

    ```text
    TYPED_CONSUMPTION_EVIDENCE != DATABASE_PROOF
    ```

    Construir esta instância em Python **não** prova que o banco confirmou
    consumo algum. É a mesma disciplina de `VerifiedDeletionCapability.
    verified` na E4.9.7 e de `IdentityEvidence` na E4.9.8: o objeto
    registra o que outro observou, e quem observa é outro.

    Nesta fatia **ninguém a produz**. `ApprovalRecordRepository` não é
    importado aqui, e a E4.9.9.d só poderá criá-la depois do
    `consume_once` bem-sucedido.

    ## O mínimo necessário, e nada além

    ```text
    approval_id · operation · tenant_id · workspace_id
    principal_ref · consumed_at
    ```

    **Não** transporta nonce, credencial, fator de autenticação, token nem
    o envelope completo. O adaptador precisa saber *que* houve consumo e
    *sob qual escopo*, não reconstruir a aprovação — e cada campo a mais
    seria material sensível atravessando uma fronteira externa.

    Todos obrigatórios, sem default. Um default faria a omissão parecer
    evidência, que é a forma exata do `verified = True` acidental fechado
    pela E4.9.7.4.
    """

    approval_id: uuid.UUID
    operation: DestructiveOperation
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    principal_ref: str = field(repr=False)
    consumed_at: datetime

    def __post_init__(self) -> None:
        _validar_uuid("approval_id", self.approval_id)
        if not isinstance(self.operation, DestructiveOperation):
            raise TypeError(
                f"operation deve ser um DestructiveOperation, recebido "
                f"{type(self.operation).__name__} — string equivalente não é membro"
            )
        _validar_uuid("tenant_id", self.tenant_id)
        _validar_uuid("workspace_id", self.workspace_id)
        validar_texto_opaco("principal_ref", self.principal_ref)
        validar_instante_ciente("consumed_at", self.consumed_at)

    def __repr__(self) -> str:
        return (
            f"ConsumedApprovalEvidence(approval_id={self.approval_id!r}, "
            f"operation={self.operation.value!r}, "
            f"tenant_id={self.tenant_id!r}, "
            f"workspace_id={self.workspace_id!r}, "
            f"principal_ref={TEXTO_OCULTO}, "
            f"consumed_at={self.consumed_at!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class ErasureEffectRequest:
    """O que se pede ao adaptador: um alvo fresco e a prova de autorização.

    ```text
    DESCRIPTOR + CONSUMED_APPROVAL -> ATTEMPT
    ```

    ## O que este construtor valida

    Operação aprovada tipada, capacidade **verificada**, coerência de
    tenant, workspace e principal com o `ControlScope` do descritor,
    classe de conteúdo apagável, e todos os tipos e instantes.

    ## O que ele deliberadamente NÃO valida

    ```text
    APPLICATION_LEVEL_CAPABILITY_OPERATION_MAPPING = FORBIDDEN
    CAPABILITY_OPERATION_SEMANTICS = ADAPTER_BOUNDARY
    ```

    **Não** compara `DestructiveOperation` com `capability.operation`.

    A razão é material, e o desenho inicial desta fatia estava errado.
    `capability.operation` é **texto opaco do provedor** — o repositório
    mostra valores como `"delete_object"` —, e não existe contrato
    canônico que diga a que operação aprovada cada um corresponde.
    Escrever uma matriz local seria inventar semântica de provedor, e o
    custo do erro é assimétrico: uma correspondência errada poderia
    deixar passar apagamento **definitivo** com capacidade que só
    autorizava lixeira.

    Quem conhece o provedor é o adaptador. É ele que confirma
    compatibilidade e, **antes de qualquer efeito**, devolve
    `OPERATION_NOT_SUPPORTED` ou `CAPABILITY_REFUSED_BEFORE_ATTEMPT`.

    Também não re-resolve o alvo nem compara com o snapshot aprovado —
    isso é E4.9.9.d, e alegar aqui seria capacidade acima da camada.
    """

    descriptor: ErasureTargetDescriptor = field(repr=False)
    authorization: ConsumedApprovalEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, ErasureTargetDescriptor):
            raise TypeError(
                f"descriptor deve ser um ErasureTargetDescriptor, recebido "
                f"{type(self.descriptor).__name__}"
            )
        if not isinstance(self.authorization, ConsumedApprovalEvidence):
            raise TypeError(
                f"authorization deve ser um ConsumedApprovalEvidence, recebido "
                f"{type(self.authorization).__name__}"
            )

        if self.descriptor.target_class not in CLASSES_DE_CONTEUDO:
            raise ValueError(
                f"{self.descriptor.target_class.value} não é conteúdo apagável — "
                "metadado cognitivo e referência não resolvida não chegam à "
                "fronteira de efeito"
            )

        if not self.descriptor.capability.verified:
            raise ValueError(
                "capacidade não verificada — a fronteira de efeito exige "
                "capacidade que alguém observou, e não a presença do campo"
            )

        escopo = self.descriptor.control_scope
        if escopo.tenant_id != self.authorization.tenant_id:
            raise ValueError("tenant do descritor diverge do tenant da aprovação consumida")
        if escopo.workspace_id != self.authorization.workspace_id:
            raise ValueError("workspace do descritor diverge do workspace da aprovação consumida")
        if escopo.control_principal_ref != self.authorization.principal_ref:
            raise ValueError(
                "principal de controle do alvo diverge do principal da aprovação "
                "consumida — sem modelo de delegação, os dois têm de coincidir"
            )

    def __repr__(self) -> str:
        """Nunca delega ao descritor.

        Ele redige o próprio localizador, mas um campo novo lá dentro
        mudaria o que esta classe expõe sem decisão local.
        """
        return (
            f"ErasureEffectRequest(descriptor={DESCRITOR_OCULTO}, "
            f"authorization={self.authorization!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class MaterialAttemptNotStarted:
    """Nenhuma tentativa material começou.

    ```text
    NOT_STARTED -> NO_ERASURE_RECORD
    ```

    Este resultado é prova de **ausência de tentativa**, e é por isso que
    nunca gera recibo: `ErasureRecord` registra o que uma tentativa
    material observou, e aqui não houve tentativa.

    Não carrega localizador, capacidade, descritor nem conteúdo — só o que
    identifica a aprovação, o sujeito e o motivo fechado.
    """

    approval_id: uuid.UUID
    subject_coid: uuid.UUID
    reason: MaterialAttemptRefusalReason
    observed_at: datetime

    @property
    def stage(self) -> EffectAttemptStage:
        """Constante da classe — nunca argumento do chamador.

        ```text
        DISJOINT_RESULT_TYPE = SOURCE_OF_TRUTH
        STAGE = DERIVED_TAG_ONLY
        ```

        Se fosse campo, alguém poderia construir um
        `MaterialAttemptNotStarted` marcado como observado, e a etiqueta
        contradiria o tipo. A verdade é a classe; isto só a acompanha.
        """
        return EffectAttemptStage.NOT_STARTED

    def __post_init__(self) -> None:
        _validar_uuid("approval_id", self.approval_id)
        _validar_uuid("subject_coid", self.subject_coid)
        if not isinstance(self.reason, MaterialAttemptRefusalReason):
            raise TypeError(
                f"reason deve ser um MaterialAttemptRefusalReason, recebido "
                f"{type(self.reason).__name__} — texto livre não é motivo"
            )
        validar_instante_ciente("observed_at", self.observed_at)


@dataclass(frozen=True)
class ObservedAttemptResult:
    """Uma tentativa material **ocorreu** e foi observada.

    ```text
    EFFECT != ERASURE_RECORD
    ```

    Este objeto é o que o adaptador observou. Escrever recibo a partir
    dele é da E4.9.9.d, e continua sem writer.

    ## Sobre `SUCCEEDED`

    Significa o que a E4.9.2 congelou: o adaptador **confirmou todo o
    escopo controlado**. Em provedor externo, não é prova metafísica de
    que todos os bytes desapareceram de toda réplica, backup ou cache — e
    o EDR registra esse limite em vez de deixá-lo implícito.

    ## Matriz de coerência

    ```text
    completed_at >= attempted_at
    SUCCEEDED         -> failure_code IS NONE
    FAILED | PARTIAL  -> failure_code obrigatório e não vazio
    ```

    `SUCCEEDED` com código de falha, ou `FAILED` sem ele, seriam estados
    impossíveis materializados.
    """

    approval_id: uuid.UUID
    subject_coid: uuid.UUID
    target_class: ErasureTargetClass
    outcome: ErasureOutcome
    executor_ref: str = field(repr=False)
    attempted_at: datetime
    completed_at: datetime
    failure_code: str | None = field(default=None, repr=False)

    @property
    def stage(self) -> EffectAttemptStage:
        """Constante da classe — ver `MaterialAttemptNotStarted.stage`."""
        return EffectAttemptStage.MATERIAL_ATTEMPT_OBSERVED

    def __post_init__(self) -> None:
        _validar_uuid("approval_id", self.approval_id)
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
        validar_texto_opaco("executor_ref", self.executor_ref)
        validar_instante_ciente("attempted_at", self.attempted_at)
        validar_instante_ciente("completed_at", self.completed_at)
        if self.completed_at < self.attempted_at:
            raise ValueError(
                "completed_at anterior a attempted_at — uma tentativa não termina "
                "antes de começar"
            )

        if self.outcome is ErasureOutcome.SUCCEEDED:
            if self.failure_code is not None:
                raise ValueError(
                    "succeeded não carrega failure_code — sucesso com código de "
                    "falha é estado impossível"
                )
        elif self.failure_code is None:
            raise ValueError(
                f"{self.outcome.value} exige failure_code — uma falha que não diz "
                "o que falhou é irrecorrível"
            )
        else:
            validar_texto_opaco("failure_code", self.failure_code)

    def __repr__(self) -> str:
        return (
            f"ObservedAttemptResult(approval_id={self.approval_id!r}, "
            f"subject_coid={self.subject_coid!r}, "
            f"target_class={self.target_class.value!r}, "
            f"outcome={self.outcome.value!r}, "
            f"executor_ref={TEXTO_OCULTO}, "
            f"attempted_at={self.attempted_at!r}, "
            f"completed_at={self.completed_at!r}, "
            f"failure_code={TEXTO_OCULTO if self.failure_code else None!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


ErasureEffectResult = MaterialAttemptNotStarted | ObservedAttemptResult
"""União **fechada** dos desfechos da fronteira de efeito.

```text
ErasureEffectResult = MaterialAttemptNotStarted | ObservedAttemptResult
```

Sem `bool`, `None`, dicionário livre ou objeto com combinações
inconsistentes. Quatro desfechos semânticos, e somente quatro:

```text
NOT_STARTED | SUCCEEDED | FAILED | PARTIAL
```

Um `bool` não distinguiria `NOT_STARTED` de `FAILED`, e essa é
precisamente a distinção que decide se existe recibo.
"""
