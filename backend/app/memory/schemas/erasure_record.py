"""
Contratos internos do recibo de apagamento (`E4.9.5`).

**Nada aqui é exposto em API.** Não há endpoint, router ou serializer
público nesta fatia — e criar um exporia, como recurso consultável, o
registro de tudo que já foi destruído.

Dois contratos, com propósitos que não se confundem:

- `ErasureRecordAppend` — o que um futuro orquestrador precisa ter
  observado para poder registrar;
- `ErasureRecordView` — leitura imutável, para consulta local.

A validação aqui **precede** o banco e não o substitui. Os mesmos
invariantes existem como `CHECK` na tabela, porque a validação Python
só protege quem passa por ela, e este é o registro que mais convida a
escrita por fora.
"""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.memory.models.erasure_record import MAX_FAILURE_CODE_LENGTH, MAX_IDENTIFIER_LENGTH

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
"""Caracteres de controle, incluindo NUL, tab e quebras de linha.

Rejeitados em toda string opaca. Um identificador com quebra de linha
não é identificador — é texto, e texto é onde o conteúdo apagado
sobreviveria.
"""


def _validar_opaco(valor: str, campo: str, tamanho: int = MAX_IDENTIFIER_LENGTH) -> str:
    """Valida uma string opaca: não vazia, sem controle, dentro do teto.

    Não tenta inspecionar semanticamente se o valor é um segredo ou um
    localizador — isso seria heurística, e heurística que falha em
    silêncio é pior que ausência de checagem. O vocabulário é mantido
    mínimo por construção, não por adivinhação.
    """
    if not valor or not valor.strip():
        raise ValueError(f"{campo} não pode ser vazio ou apenas espaços")
    if _CONTROL_CHARS.search(valor):
        raise ValueError(f"{campo} não pode conter caracteres de controle")
    if len(valor) > tamanho:
        raise ValueError(f"{campo} excede o tamanho máximo de {tamanho} caracteres")
    return valor


def _exigir_aware(valor: datetime, campo: str) -> datetime:
    """Rejeita datetime naive.

    Um instante sem timezone não identifica um momento: "14:30" é
    ambíguo entre fusos, e um recibo cujo instante é ambíguo não serve
    para auditoria.
    """
    if valor.tzinfo is None or valor.tzinfo.utcoffset(valor) is None:
        raise ValueError(f"{campo} deve ser timezone-aware")
    return valor


class ErasureRecordAppend(BaseModel):
    """Entrada validada para registrar uma tentativa **já observada**.

    Não é uma proposta, não é um pedido e não agenda nada. Quem
    constrói isto está afirmando que a tentativa material ocorreu e
    que o desfecho foi observado.

    ```text
    NO_RECORD_BEFORE_OBSERVED_ATTEMPT
    ```

    Nenhum campo livre existe, e `effect_digest` **não** faz parte
    desta fatia: mecanismo e canonicalização continuam deferidos, e
    inventá-los aqui produziria um digest que ninguém sabe verificar.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_identifier: str
    target_class: ErasureTargetClass
    scope_token: str
    outcome: ErasureOutcome
    governance_policy_id: uuid.UUID
    governance_policy_key: str
    governance_policy_version: int
    governance_rule_id: str
    """Identificador **textual opaco** da regra (`E4.9.9.d`).

    ```text
    OPAQUE_RULE_REFERENCE != UUID
    ```

    Ver `ErasureRecord.governance_rule_id`: a fonte é
    `GovernanceResolution.matched_rule_id`, que é `str`. Exigir `UUID`
    aqui tornava o mapeamento fiel do recibo impossível sem fabricar
    identidade.
    """

    governance_resolution_ref: str
    approval_ref: str
    executor_ref: str
    attempted_at: datetime
    completed_at: datetime
    retention_policy_id: uuid.UUID | None = None
    retention_policy_key: str | None = None
    retention_policy_version: int | None = None
    failure_code: str | None = None

    @field_validator(
        "subject_identifier",
        "scope_token",
        "governance_policy_key",
        "governance_rule_id",
        "governance_resolution_ref",
        "approval_ref",
        "executor_ref",
    )
    @classmethod
    def _opacos_validos(cls, valor: str, info: object) -> str:
        campo = getattr(info, "field_name", "campo")
        return _validar_opaco(valor, campo)

    @field_validator("retention_policy_key")
    @classmethod
    def _retention_key_valida(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return _validar_opaco(valor, "retention_policy_key")

    @field_validator("failure_code")
    @classmethod
    def _failure_code_valido(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return _validar_opaco(valor, "failure_code", MAX_FAILURE_CODE_LENGTH)

    @field_validator("governance_policy_version")
    @classmethod
    def _versao_governanca_positiva(cls, valor: int) -> int:
        if valor < 1:
            raise ValueError("governance_policy_version deve ser >= 1")
        return valor

    @field_validator("retention_policy_version")
    @classmethod
    def _versao_retencao_positiva(cls, valor: int | None) -> int | None:
        if valor is not None and valor < 1:
            raise ValueError("retention_policy_version deve ser >= 1")
        return valor

    @field_validator("attempted_at", "completed_at")
    @classmethod
    def _instantes_aware(cls, valor: datetime, info: object) -> datetime:
        campo = getattr(info, "field_name", "campo")
        return _exigir_aware(valor, campo)

    @model_validator(mode="after")
    def _invariantes(self) -> "ErasureRecordAppend":
        if self.completed_at < self.attempted_at:
            raise ValueError("completed_at não pode ser anterior a attempted_at")

        trio = (
            self.retention_policy_id,
            self.retention_policy_key,
            self.retention_policy_version,
        )
        preenchidos = sum(1 for campo in trio if campo is not None)
        if preenchidos not in (0, 3):
            raise ValueError(
                "retention_policy_id, retention_policy_key e retention_policy_version "
                "devem ser todos nulos ou todos preenchidos — um trio parcial cita uma "
                "policy que não pode ser reencontrada"
            )

        if self.outcome is ErasureOutcome.SUCCEEDED and self.failure_code is not None:
            raise ValueError("failure_code é proibido quando outcome é SUCCEEDED")
        if self.outcome is not ErasureOutcome.SUCCEEDED and self.failure_code is None:
            raise ValueError(f"failure_code é obrigatório quando outcome é {self.outcome.value}")

        return self


class ErasureRecordView(BaseModel):
    """Leitura imutável de um recibo persistido.

    `frozen=True` por coerência com o registro: um recibo que pudesse
    ser mutado em memória convidaria a apresentar ao usuário algo
    diferente do que está no banco.
    """

    model_config = ConfigDict(frozen=True, from_attributes=True, extra="forbid")

    id: uuid.UUID
    subject_identifier: str
    target_class: ErasureTargetClass
    scope_token: str
    outcome: ErasureOutcome
    governance_policy_id: uuid.UUID
    governance_policy_key: str
    governance_policy_version: int
    governance_rule_id: str
    governance_resolution_ref: str
    approval_ref: str
    executor_ref: str
    attempted_at: datetime
    completed_at: datetime
    retention_policy_id: uuid.UUID | None
    retention_policy_key: str | None
    retention_policy_version: int | None
    failure_code: str | None
