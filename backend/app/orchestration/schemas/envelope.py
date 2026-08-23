"""
`ENVELOPE_CONTENT`, seus invariantes e o hash canônico (`MAI-001 R1` §3).

```text
ENVELOPE_CONTENT = {envelope_version, schedule_id, step_id, role,
  instruction_ref, context_refs[{uri, sha256, bytes}],
  expected_output_contract, constraints}
ENVELOPE_CONTENT_SHA256 = sha256(json canônico de ENVELOPE_CONTENT)
SEAL_RECEIPT = {content_sha256, sealed_at, attempt_id, sealer_ref}

SEALED_AT_IN_CONTENT_HASH = FALSE      CONTENT_DETERMINISM = TRUE
SAME_CONTENT + MULTIPLE_ATTEMPTS -> mesmo hash, recibos distintos
CONTENT_CHANGED -> hash distinto
```

A regra temporal do §21 é o motivo de `sealed_at`, `attempt_id` e
`sealer_ref` viverem no recibo: nenhum composto pode depender de
componente produzido a jusante dele. Um hash que inclui o instante do
selamento não é determinístico por conteúdo — é um carimbo.

```text
INLINE_CONTENT_WITHOUT_HASH = FORBIDDEN
```

Toda referência de contexto declara `{uri, sha256, bytes}`. Conteúdo
embutido sem hash é recusado **antes** da persistência, não corrigido na
leitura: uma linha inválida numa base que outros hashes referenciam é
permanente.

Este módulo não importa SQLAlchemy, FastAPI nem qualquer camada de
persistência. É contrato puro, e a guarda estática mede isso.
"""

import hashlib
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

ENVELOPE_VERSION = "1"
"""Versão do contrato de envelope produzida por esta entrega.

Fica gravada na tentativa, não no recibo: é o insumo que produziu aquele
hash, e uma versão futura precisa ser legível ao lado do valor antigo.
"""

ENVELOPE_CONTENT_FIELDS: frozenset[str] = frozenset(
    {
        "envelope_version",
        "schedule_id",
        "step_id",
        "role",
        "instruction_ref",
        "context_refs",
        "expected_output_contract",
        "constraints",
    }
)
"""Os oito campos congelados no MAI §3. Ampliar exige emenda ao MAI."""

SEAL_RECEIPT_ONLY_FIELDS: frozenset[str] = frozenset({"sealed_at", "attempt_id", "sealer_ref"})
"""Campos que **nunca** entram no conteúdo. Guarda estática e teste medem."""

CONTEXT_REF_FIELDS: tuple[str, ...] = ("uri", "sha256", "bytes")
"""Ordem declarada do `ARTIFACT_REF` (§8). O JSON canônico ordena por chave."""

MAX_REF_LENGTH = 255
MAX_ROLE_LENGTH = 64
MAX_TITLE_LENGTH = 200
MAX_URI_LENGTH = 1024
MAX_CONSTRAINT_KEY_LENGTH = 64
MAX_CONSTRAINT_VALUE_LENGTH = 255
MAX_ENVELOPE_VERSION_LENGTH = 16

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
"""Hexadecimal minúsculo de 64 caracteres. Sem normalização.

Aceitar maiúsculas e baixá-las faria duas grafias do mesmo artefato
produzirem o mesmo conteúdo por conta de uma conversão silenciosa. O
contrato exige a forma canônica desde a entrada.
"""


def _texto_obrigatorio(valor: object, campo: str, limite: int) -> str:
    if not isinstance(valor, str):
        raise ValueError(f"{campo} deve ser str, recebido {type(valor).__name__}")
    if not valor.strip():
        raise ValueError(f"{campo} não pode ser vazio ou apenas espaços")
    if len(valor) > limite:
        raise ValueError(f"{campo} excede {limite} caracteres")
    return valor


@dataclass(frozen=True)
class ContextRef:
    """`ARTIFACT_REF = {uri_ou_id, sha256, bytes}` (MAI §8).

    Congelado e validado no construtor. O `bytes` é o tamanho declarado do
    artefato, não o conteúdo — a E7 referencia, não transporta.
    """

    uri: str
    sha256: str
    bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "uri", _texto_obrigatorio(self.uri, "uri", MAX_URI_LENGTH))
        if not isinstance(self.sha256, str) or not SHA256_PATTERN.match(self.sha256):
            raise ValueError(
                "context_ref exige sha256 hexadecimal minúsculo de 64 caracteres; "
                f"recebido {self.sha256!r}"
            )
        if isinstance(self.bytes, bool) or not isinstance(self.bytes, int):
            raise ValueError(f"bytes deve ser int, recebido {type(self.bytes).__name__}")
        if self.bytes < 0:
            raise ValueError("bytes não pode ser negativo")

    def as_content(self) -> dict[str, object]:
        return {"uri": self.uri, "sha256": self.sha256, "bytes": self.bytes}


def parse_context_refs(valor: object) -> tuple[ContextRef, ...]:
    """Reconstrói referências a partir da forma persistida, sem tolerância.

    Uma linha fora do contrato levanta aqui, na fronteira de leitura, em
    vez de virar um envelope silenciosamente diferente do que foi gravado.
    """
    if valor is None or isinstance(valor, str | bytes) or not isinstance(valor, Sequence):
        raise ValueError("context_refs deve ser uma sequência de objetos")
    referencias: list[ContextRef] = []
    for item in valor:
        if isinstance(item, ContextRef):
            referencias.append(item)
            continue
        if not isinstance(item, Mapping):
            raise ValueError("cada context_ref deve ser um objeto")
        if set(item) != set(CONTEXT_REF_FIELDS):
            raise ValueError(
                f"context_ref exige exatamente {sorted(CONTEXT_REF_FIELDS)}; "
                f"recebido {sorted(item)}"
            )
        referencias.append(ContextRef(uri=item["uri"], sha256=item["sha256"], bytes=item["bytes"]))
    return tuple(referencias)


ConstraintPairs = tuple[tuple[str, str], ...]


def canonical_constraints(valor: object) -> ConstraintPairs:
    """Mapa de restrições em pares ordenados por chave.

    Ordenar na escrita e não na leitura é o precedente da E6.2: duas
    declarações com o mesmo conjunto têm a mesma forma persistida, então o
    hash não depende da ordem em que alguém digitou. Chave duplicada é
    recusada em vez de resolvida — resolver escolheria um vencedor.
    """
    if valor is None:
        return ()
    itens: list[tuple[object, object]]
    if isinstance(valor, Mapping):
        itens = list(valor.items())
    elif isinstance(valor, str | bytes) or not isinstance(valor, Sequence):
        raise ValueError("constraints deve ser um mapa ou uma sequência de pares")
    else:
        itens = []
        for par in valor:
            if isinstance(par, str | bytes) or not isinstance(par, Sequence) or len(par) != 2:
                raise ValueError("cada restrição deve ser um par (chave, valor)")
            itens.append((par[0], par[1]))
    pares: list[tuple[str, str]] = []
    vistas: set[str] = set()
    for chave, conteudo in itens:
        texto_chave = _texto_obrigatorio(chave, "constraint key", MAX_CONSTRAINT_KEY_LENGTH)
        texto_valor = _texto_obrigatorio(conteudo, "constraint value", MAX_CONSTRAINT_VALUE_LENGTH)
        if texto_chave in vistas:
            raise ValueError(f"restrição duplicada: {texto_chave!r}")
        vistas.add(texto_chave)
        pares.append((texto_chave, texto_valor))
    return tuple(sorted(pares))


def constraints_as_mapping(pares: ConstraintPairs) -> dict[str, str]:
    return {chave: valor for chave, valor in pares}


@dataclass(frozen=True)
class StepDraft:
    """Etapa declarada pelo chamador, antes de existir no banco.

    `constraints` aceita mapa ou pares e é canonicalizada no construtor;
    a anotação declara isso em vez de mentir que só admite a forma final.
    """

    role: str
    instruction_ref: str
    expected_output_contract: str
    context_refs: tuple[ContextRef, ...] = ()
    constraints: ConstraintPairs | Mapping[str, str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", _texto_obrigatorio(self.role, "role", MAX_ROLE_LENGTH))
        object.__setattr__(
            self,
            "instruction_ref",
            _texto_obrigatorio(self.instruction_ref, "instruction_ref", MAX_REF_LENGTH),
        )
        object.__setattr__(
            self,
            "expected_output_contract",
            _texto_obrigatorio(
                self.expected_output_contract, "expected_output_contract", MAX_REF_LENGTH
            ),
        )
        object.__setattr__(self, "context_refs", parse_context_refs(self.context_refs))
        object.__setattr__(self, "constraints", canonical_constraints(self.constraints))


@dataclass(frozen=True)
class ScheduleDraft:
    """Trabalho declarado: título, modo de execução e etapas em ordem.

    A ordem das etapas é conteúdo, não apresentação: ela é a composição
    (§4). Reordenar é redeclarar o trabalho.
    """

    title: str
    steps: tuple[StepDraft, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _texto_obrigatorio(self.title, "title", MAX_TITLE_LENGTH))
        if not isinstance(self.steps, tuple):
            object.__setattr__(self, "steps", tuple(self.steps))
        if not self.steps:
            raise ValueError("um Schedule sem etapas não descreve trabalho algum")
        for etapa in self.steps:
            if not isinstance(etapa, StepDraft):
                raise ValueError("cada etapa deve ser um StepDraft")


@dataclass(frozen=True)
class EnvelopeContent:
    """Os oito campos congelados, e nada além deles.

    ```text
    NO_COMPOSITE_DEPENDS_ON_DOWNSTREAM_COMPONENT
    ```
    """

    envelope_version: str
    schedule_id: uuid.UUID
    step_id: uuid.UUID
    role: str
    instruction_ref: str
    context_refs: tuple[ContextRef, ...]
    expected_output_contract: str
    constraints: ConstraintPairs

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "envelope_version",
            _texto_obrigatorio(
                self.envelope_version, "envelope_version", MAX_ENVELOPE_VERSION_LENGTH
            ),
        )
        for campo in ("schedule_id", "step_id"):
            if not isinstance(getattr(self, campo), uuid.UUID):
                raise ValueError(f"{campo} deve ser uuid.UUID")
        object.__setattr__(self, "role", _texto_obrigatorio(self.role, "role", MAX_ROLE_LENGTH))
        object.__setattr__(
            self,
            "instruction_ref",
            _texto_obrigatorio(self.instruction_ref, "instruction_ref", MAX_REF_LENGTH),
        )
        object.__setattr__(
            self,
            "expected_output_contract",
            _texto_obrigatorio(
                self.expected_output_contract, "expected_output_contract", MAX_REF_LENGTH
            ),
        )
        object.__setattr__(self, "context_refs", parse_context_refs(self.context_refs))
        object.__setattr__(self, "constraints", canonical_constraints(self.constraints))

    def as_canonical_mapping(self) -> dict[str, Any]:
        """Forma serializável do conteúdo — exatamente os oito campos."""
        return {
            "envelope_version": self.envelope_version,
            "schedule_id": str(self.schedule_id),
            "step_id": str(self.step_id),
            "role": self.role,
            "instruction_ref": self.instruction_ref,
            "context_refs": [referencia.as_content() for referencia in self.context_refs],
            "expected_output_contract": self.expected_output_contract,
            "constraints": constraints_as_mapping(self.constraints),
        }

    def canonical_json(self) -> str:
        """JSON canônico: chaves ordenadas, sem espaço, sem escape de não-ASCII.

        `sort_keys=True` é o que retira a ordem de inserção do resultado —
        sem ele, o hash dependeria da ordem em que o dicionário foi
        montado, que é detalhe de implementação e não conteúdo.
        """
        return json.dumps(
            self.as_canonical_mapping(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def content_sha256(self) -> str:
        """`ENVELOPE_CONTENT_SHA256`. Não lê relógio, ambiente nem banco."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
