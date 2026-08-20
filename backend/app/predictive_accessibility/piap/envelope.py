"""
Envelope protocolar PIAP e sua serialização canônica (`E5.a`).

```text
PIAP = VERSIONED_PROVENANCE_PRESERVING_PROTOCOL_ENVELOPE
PIAP_TRANSPORTS_CONTEXT_CLAIMS_EVIDENCE_AND_CONTRACT_METADATA = TRUE
PIAP_INTERPRETS_PREDICTIVE_SCIENCE = FALSE
PIAP_DECIDES_EPISTEMIC_STATE_OR_ROUTE = FALSE
PIAP_ENVELOPE != AI_HANDOFF_ENVELOPE
```

## O que este envelope carrega, e o que não carrega

Carrega **referências** a contexto, alegação, evidência e autoridade, com
proveniência, versão e tempo. Não carrega o conteúdo referido, nem
medida científica, nem estado epistêmico, nem rota, nem execução.

`ClaimSubject` transporta alvo, sinal e horizonte porque são metadados de
transporte declarados por `D1`. Nenhum deles recebe valor estimado.

```text
TRANSPORTED_METADATA != SCIENTIFIC_MEASUREMENT
```

Também não carrega papel de IA, modo de automação, pausa ou destino de
repasse — esse é o envelope de handoff multi-IA, que pertence à `E7` e é
outro objeto com nome parecido.

## Nada é transformado em silêncio

Tokens, referências opacas, escopo e coleções são **validados**, nunca
normalizados. Ordem canônica e ausência de duplicata são exigidas de quem
constrói; a camada rejeita em vez de reordenar.

```text
SILENT_NORMALIZATION = FORBIDDEN
SILENT_REORDER_OR_DEDUP = FORBIDDEN
```

## Sem taxonomia inventada de fonte

`ProvenanceKind` é value object de token opaco, não `StrEnum`. Não existe
taxonomia autorizada de tipos de fonte, e congelar uma aqui imporia uma
ontologia a fontes que ainda não existem — o mesmo raciocínio que a E4.11
usou para não congelar um enum de resultados observados.
"""

import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TypeVar

from app.predictive_accessibility.errors.exceptions import (
    PiapContractViolationError,
    PiapUnsupportedVersionError,
)
from app.predictive_accessibility.piap.authority import (
    ApprovalBinding,
    AuthorityContext,
    BoundObjectRef,
    canonizar_instante,
    validar_inteiro_positivo,
    validar_referencia_opaca,
)
from app.predictive_accessibility.piap.enums import (
    AuthorityStatus,
    BoundObjectKind,
    PiapContractVersion,
    TemporalAvailability,
)
from app.predictive_accessibility.piap.version import require_supported_version

MAX_TOKEN_LENGTH = 64
"""Mesmo limite de token já medido em `E4.11`."""

GRAMATICA_DO_TOKEN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
"""Gramática **fechada**, idêntica à de `validated_experience` na E4.11.

Minúsculas ASCII, dígitos e três separadores. Sem espaço, sem maiúscula,
sem acento, sem pontuação de frase — porque um campo que aceita frase
vira campo de julgamento, e alvo e sinal são identificadores, não
descrições.

```text
CLOSED_GRAMMAR != FREE_TEXT
```
"""

COMPRIMENTO_SHA256_HEX = 64
GRAMATICA_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
"""Exatamente 64 caracteres hexadecimais minúsculos.

Maiúsculas são recusadas em vez de rebaixadas: aceitar as duas formas e
converter uma delas seria normalização silenciosa, e dois envelopes com
o mesmo hash escrito de formas diferentes deixariam de ser
distinguíveis na origem.
"""


def validar_token(nome: str, valor: object) -> str:
    """Token da gramática fechada, devolvido sem transformação."""
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser str, recebido {type(valor).__name__}")
    if not valor:
        raise ValueError(f"{nome} não pode ser vazio")
    if len(valor) > MAX_TOKEN_LENGTH:
        raise ValueError(f"{nome} excede {MAX_TOKEN_LENGTH} caracteres")
    if not GRAMATICA_DO_TOKEN.fullmatch(valor):
        raise ValueError(
            f"{nome} {valor!r} está fora da gramática fechada — este campo é "
            "identificador, não frase"
        )
    return valor


def validar_sha256_hex(nome: str, valor: object) -> str:
    """Digest SHA-256 em hexadecimal minúsculo, exatos 64 caracteres."""
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser str, recebido {type(valor).__name__}")
    if not GRAMATICA_SHA256_HEX.fullmatch(valor):
        raise ValueError(
            f"{nome} deve ter exatamente {COMPRIMENTO_SHA256_HEX} caracteres "
            "hexadecimais minúsculos"
        )
    return valor


@dataclass(frozen=True)
class ProvenanceKind:
    """Tipo de fonte, como **token opaco validado** — não como taxonomia.

    ```text
    CLOSED_VOCABULARY != INVENTED_TAXONOMY
    ```

    O token só significa alguma coisa lido contra a fonte que o declara.
    Congelar um enum aqui decidiria, por antecipação, quais fontes o
    PIA-OS pode transportar.
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", validar_token("ProvenanceKind.value", self.value))


@dataclass(frozen=True)
class SourceReference:
    """Identifica a FONTE sem embutir o objeto de origem.

    Precedente medido: `EvidenceReference` da E4.11 carrega `kind` e
    `ref`, e nunca o objeto referido. É a forma de
    `PIAP_DUPLICATES_THE_APPROVED_OBJECT = FALSE`.
    """

    kind: ProvenanceKind
    ref: uuid.UUID
    source_version: int
    content_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ProvenanceKind):
            raise TypeError(f"kind deve ser ProvenanceKind, recebido {type(self.kind).__name__}")
        if not isinstance(self.ref, uuid.UUID):
            raise TypeError(f"ref deve ser uuid.UUID, recebido {type(self.ref).__name__}")
        object.__setattr__(
            self, "source_version", validar_inteiro_positivo("source_version", self.source_version)
        )
        if self.content_sha256 is not None:
            object.__setattr__(
                self, "content_sha256", validar_sha256_hex("content_sha256", self.content_sha256)
            )

    @property
    def sort_key(self) -> tuple[str, str, int, str]:
        """Chave de ordenação canônica, total e estável.

        Existe para que a ordem de `payload_refs` seja verificável pelo
        chamador antes de construir, e não imposta em silêncio depois.
        """
        return (self.kind.value, str(self.ref), self.source_version, self.content_sha256 or "")


@dataclass(frozen=True)
class Horizon:
    """Horizonte e instante de referência, que viajam juntos.

    Separá-los permitiria o par incoerente — um horizonte sem o instante
    a que se refere não diz nada.
    """

    delta: timedelta
    reference_time: datetime
    availability: TemporalAvailability

    def __post_init__(self) -> None:
        if not isinstance(self.delta, timedelta):
            raise TypeError(f"delta deve ser timedelta, recebido {type(self.delta).__name__}")
        if self.delta <= timedelta(0):
            raise ValueError("delta deve ser positivo: horizonte nulo ou negativo não é horizonte")
        object.__setattr__(
            self, "reference_time", canonizar_instante("reference_time", self.reference_time)
        )
        if not isinstance(self.availability, TemporalAvailability):
            raise TypeError(
                f"availability deve ser TemporalAvailability, recebido "
                f"{type(self.availability).__name__}"
            )


@dataclass(frozen=True)
class ClaimSubject:
    """Sobre o que a alegação transportada é.

    Alvo e sinal são identificadores da gramática fechada. Nenhum deles
    recebe valor estimado: são metadados de transporte.
    """

    target: str
    signal: str
    horizon: Horizon

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", validar_token("target", self.target))
        object.__setattr__(self, "signal", validar_token("signal", self.signal))
        if not isinstance(self.horizon, Horizon):
            raise TypeError(f"horizon deve ser Horizon, recebido {type(self.horizon).__name__}")


@dataclass(frozen=True)
class ProvenanceRecord:
    """Proveniência preservada, nunca reescrita.

    ```text
    K_HISTORY_PRESERVES_PROVENANCE = TRUE
    ```

    `policy_ref` é redigido no `repr` pelo mesmo motivo de
    `approval_reference`: uma referência de política se apresenta de uma
    forma em log e de outra numa interface.
    """

    origin: SourceReference
    recorded_at: datetime
    jurisdiction: str | None = None
    policy_ref: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.origin, SourceReference):
            raise TypeError(
                f"origin deve ser SourceReference, recebido {type(self.origin).__name__}"
            )
        object.__setattr__(self, "recorded_at", canonizar_instante("recorded_at", self.recorded_at))
        if self.jurisdiction is not None:
            object.__setattr__(
                self, "jurisdiction", validar_referencia_opaca("jurisdiction", self.jurisdiction)
            )
        if self.policy_ref is not None:
            object.__setattr__(
                self, "policy_ref", validar_referencia_opaca("policy_ref", self.policy_ref)
            )


@dataclass(frozen=True)
class PiapEnvelope:
    """O envelope versionado que atravessa a fronteira E4 -> E5.

    Invariantes cruzados:

    ```text
    reference_time <= sealed_at
    recorded_at <= sealed_at
    payload_refs sem duplicata e em ordem canônica por sort_key
    contract_version na allowlist
    ```

    Os dois primeiros existem porque um envelope selado antes do instante
    que ele declara descreveria um futuro que ninguém observou.
    """

    contract_version: PiapContractVersion
    subject: ClaimSubject
    provenance: ProvenanceRecord
    authority: AuthorityContext
    payload_refs: tuple[SourceReference, ...]
    sealed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "contract_version", require_supported_version(self.contract_version)
        )
        if not isinstance(self.subject, ClaimSubject):
            raise TypeError(
                f"subject deve ser ClaimSubject, recebido {type(self.subject).__name__}"
            )
        if not isinstance(self.provenance, ProvenanceRecord):
            raise TypeError(
                f"provenance deve ser ProvenanceRecord, recebido {type(self.provenance).__name__}"
            )
        if not isinstance(self.authority, AuthorityContext):
            raise TypeError(
                f"authority deve ser AuthorityContext, recebido {type(self.authority).__name__}"
            )
        if not isinstance(self.payload_refs, tuple):
            raise TypeError(
                f"payload_refs deve ser tuple, recebido {type(self.payload_refs).__name__}"
            )
        for i, referencia in enumerate(self.payload_refs):
            if not isinstance(referencia, SourceReference):
                raise TypeError(
                    f"payload_refs[{i}] deve ser SourceReference, recebido "
                    f"{type(referencia).__name__}"
                )
        chaves = [r.sort_key for r in self.payload_refs]
        if len(set(chaves)) != len(chaves):
            raise ValueError("payload_refs contém referência duplicada")
        if chaves != sorted(chaves):
            raise ValueError(
                "payload_refs deve chegar em ordem canônica por sort_key; a camada "
                "rejeita em vez de reordenar"
            )
        object.__setattr__(self, "sealed_at", canonizar_instante("sealed_at", self.sealed_at))
        if self.subject.horizon.reference_time > self.sealed_at:
            raise ValueError(
                "reference_time não pode ser posterior a sealed_at: o envelope "
                "descreveria um instante ainda não observado"
            )
        if self.provenance.recorded_at > self.sealed_at:
            raise ValueError("recorded_at não pode ser posterior a sealed_at")


# --- serialização canônica -------------------------------------------------
#
# ```text
# SERIALIZATION = canonical UTF-8 JSON bytes
# JSON_KEYS = sorted ; JSON_SEPARATORS = compact
# DATETIME = UTC ISO-8601 ; TIMEDELTA = integer microseconds
# UNKNOWN_FIELD = ERROR ; DUPLICATE_JSON_KEY = ERROR
# ```
#
# A serialização não usa `asdict`: `asdict` percorre a árvore sem
# conhecer a forma esperada, e a desserialização precisaria adivinhar o
# que cada dicionário era. Cada nível é escrito e lido contra um conjunto
# **literal** de chaves.


def _instante_para_json(valor: datetime) -> str:
    """UTC ISO-8601 canônico, com sufixo `Z`."""
    return valor.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _instante_de_json(nome: str, valor: object) -> datetime:
    if not isinstance(valor, str) or not valor.endswith("Z"):
        raise PiapContractViolationError(
            f"{nome} deve ser instante UTC ISO-8601 terminado em 'Z', recebido {valor!r}"
        )
    try:
        analisado = datetime.fromisoformat(valor[:-1] + "+00:00")
    except ValueError as erro:
        raise PiapContractViolationError(f"{nome} não é ISO-8601 válido: {valor!r}") from erro
    return analisado.astimezone(UTC)


def _chaves_exatas(nome: str, bruto: object, esperadas: frozenset[str]) -> Mapping[str, object]:
    """Exige objeto JSON com exatamente as chaves esperadas.

    Campo ausente e campo extra recebem o mesmo tratamento: erro. Nada é
    defaultado nem descartado para o payload caber.
    """
    if not isinstance(bruto, Mapping):
        raise PiapContractViolationError(
            f"{nome} deve ser objeto JSON, recebido {type(bruto).__name__}"
        )
    presentes = frozenset(bruto)
    if presentes != esperadas:
        faltando = sorted(esperadas - presentes)
        extras = sorted(presentes - esperadas)
        raise PiapContractViolationError(
            f"{nome} fora do contrato — faltando: {faltando}; extras: {extras}"
        )
    return bruto


def _sem_chave_duplicada(pares: list[tuple[str, object]]) -> dict[str, object]:
    """`object_pairs_hook` que recusa chave JSON repetida.

    O `json` da biblioteca padrão mantém a última ocorrência e descarta
    as anteriores em silêncio — exatamente o descarte silencioso que o
    contrato proíbe.
    """
    visto: dict[str, object] = {}
    for chave, valor in pares:
        if chave in visto:
            raise PiapContractViolationError(f"chave JSON duplicada: {chave!r}")
        visto[chave] = valor
    return visto


def _texto(nome: str, valor: object) -> str:
    if not isinstance(valor, str):
        raise PiapContractViolationError(f"{nome} deve ser string, recebido {type(valor).__name__}")
    return valor


def _inteiro(nome: str, valor: object) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise PiapContractViolationError(
            f"{nome} deve ser inteiro, recebido {type(valor).__name__}"
        )
    return valor


def _uuid(nome: str, valor: object) -> uuid.UUID:
    try:
        return uuid.UUID(_texto(nome, valor))
    except ValueError as erro:
        raise PiapContractViolationError(f"{nome} não é UUID canônico: {valor!r}") from erro


MembroT = TypeVar("MembroT", bound=StrEnum)


def _membro(nome: str, valor: object, enum: type[MembroT]) -> MembroT:
    try:
        return enum(_texto(nome, valor))
    except ValueError as erro:
        raise PiapContractViolationError(
            f"{nome} fora do vocabulário de {enum.__name__}: {valor!r}"
        ) from erro


_CHAVES_SOURCE_REFERENCE = frozenset({"content_sha256", "kind", "ref", "source_version"})
_CHAVES_HORIZON = frozenset({"availability", "delta_microseconds", "reference_time"})
_CHAVES_SUBJECT = frozenset({"horizon", "signal", "target"})
_CHAVES_PROVENANCE = frozenset({"jurisdiction", "origin", "policy_ref", "recorded_at"})
_CHAVES_BOUND_TO = frozenset({"kind", "ref"})
_CHAVES_APPROVAL = frozenset(
    {
        "approval_expiry",
        "approval_jurisdiction",
        "approval_reference",
        "approval_scope",
        "approval_version",
        "bound_to",
    }
)
_CHAVES_AUTHORITY = frozenset({"approval", "status"})
_CHAVES_ENVELOPE = frozenset(
    {"authority", "contract_version", "payload_refs", "provenance", "sealed_at", "subject"}
)


def _source_reference_para_json(valor: SourceReference) -> dict[str, object]:
    return {
        "content_sha256": valor.content_sha256,
        "kind": valor.kind.value,
        "ref": str(valor.ref),
        "source_version": valor.source_version,
    }


def _source_reference_de_json(nome: str, bruto: object) -> SourceReference:
    dados = _chaves_exatas(nome, bruto, _CHAVES_SOURCE_REFERENCE)
    hash_conteudo = dados["content_sha256"]
    return SourceReference(
        kind=ProvenanceKind(_texto(f"{nome}.kind", dados["kind"])),
        ref=_uuid(f"{nome}.ref", dados["ref"]),
        source_version=_inteiro(f"{nome}.source_version", dados["source_version"]),
        content_sha256=(
            None if hash_conteudo is None else _texto(f"{nome}.content_sha256", hash_conteudo)
        ),
    )


def serialize_piap_envelope(envelope: PiapEnvelope) -> bytes:
    """Bytes JSON UTF-8 canônicos, determinísticos para o mesmo envelope."""
    if not isinstance(envelope, PiapEnvelope):
        raise TypeError(f"envelope deve ser PiapEnvelope, recebido {type(envelope).__name__}")
    aprovacao = envelope.authority.approval
    documento: dict[str, object] = {
        "authority": {
            "approval": (
                None
                if aprovacao is None
                else {
                    "approval_expiry": (
                        None
                        if aprovacao.approval_expiry is None
                        else _instante_para_json(aprovacao.approval_expiry)
                    ),
                    "approval_jurisdiction": aprovacao.approval_jurisdiction,
                    "approval_reference": aprovacao.approval_reference,
                    "approval_scope": list(aprovacao.approval_scope),
                    "approval_version": aprovacao.approval_version,
                    "bound_to": {
                        "kind": aprovacao.bound_to.kind.value,
                        "ref": str(aprovacao.bound_to.ref),
                    },
                }
            ),
            "status": envelope.authority.status.value,
        },
        "contract_version": envelope.contract_version.value,
        "payload_refs": [_source_reference_para_json(r) for r in envelope.payload_refs],
        "provenance": {
            "jurisdiction": envelope.provenance.jurisdiction,
            "origin": _source_reference_para_json(envelope.provenance.origin),
            "policy_ref": envelope.provenance.policy_ref,
            "recorded_at": _instante_para_json(envelope.provenance.recorded_at),
        },
        "sealed_at": _instante_para_json(envelope.sealed_at),
        "subject": {
            "horizon": {
                "availability": envelope.subject.horizon.availability.value,
                "delta_microseconds": int(
                    envelope.subject.horizon.delta / timedelta(microseconds=1)
                ),
                "reference_time": _instante_para_json(envelope.subject.horizon.reference_time),
            },
            "signal": envelope.subject.signal,
            "target": envelope.subject.target,
        },
    }
    return json.dumps(
        documento,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def deserialize_piap_envelope(payload: bytes) -> PiapEnvelope:
    """Reconstrói o envelope a partir dos bytes canônicos.

    Falha fechada em versão desconhecida, campo ausente, campo extra,
    chave JSON duplicada, tipo errado ou JSON malformado. Nenhum campo é
    descartado, defaultado ou normalizado para o payload caber.
    """
    if not isinstance(payload, bytes | bytearray):
        raise TypeError(f"payload deve ser bytes, recebido {type(payload).__name__}")
    try:
        bruto = json.loads(bytes(payload).decode("utf-8"), object_pairs_hook=_sem_chave_duplicada)
    except UnicodeDecodeError as erro:
        raise PiapContractViolationError("payload não é UTF-8 válido") from erro
    except json.JSONDecodeError as erro:
        raise PiapContractViolationError(f"payload não é JSON válido: {erro.msg}") from erro

    dados = _chaves_exatas("envelope", bruto, _CHAVES_ENVELOPE)

    texto_versao = _texto("contract_version", dados["contract_version"])
    try:
        versao = PiapContractVersion(texto_versao)
    except ValueError as erro:
        raise PiapUnsupportedVersionError(
            f"versão de contrato PIAP desconhecida: {texto_versao!r}"
        ) from erro
    versao = require_supported_version(versao)

    autoridade = _chaves_exatas("authority", dados["authority"], _CHAVES_AUTHORITY)
    aprovacao_bruta = autoridade["approval"]
    if aprovacao_bruta is None:
        aprovacao: ApprovalBinding | None = None
    else:
        campos = _chaves_exatas("authority.approval", aprovacao_bruta, _CHAVES_APPROVAL)
        vinculo = _chaves_exatas(
            "authority.approval.bound_to", campos["bound_to"], _CHAVES_BOUND_TO
        )
        escopo_bruto = campos["approval_scope"]
        if not isinstance(escopo_bruto, Sequence) or isinstance(escopo_bruto, str):
            raise PiapContractViolationError("authority.approval.approval_scope deve ser lista")
        expiracao = campos["approval_expiry"]
        jurisdicao = campos["approval_jurisdiction"]
        aprovacao = ApprovalBinding(
            approval_reference=_texto(
                "authority.approval.approval_reference", campos["approval_reference"]
            ),
            approval_version=_inteiro(
                "authority.approval.approval_version", campos["approval_version"]
            ),
            approval_scope=tuple(
                _texto(f"authority.approval.approval_scope[{i}]", v)
                for i, v in enumerate(escopo_bruto)
            ),
            approval_expiry=(
                None
                if expiracao is None
                else _instante_de_json("authority.approval.approval_expiry", expiracao)
            ),
            approval_jurisdiction=(
                None
                if jurisdicao is None
                else _texto("authority.approval.approval_jurisdiction", jurisdicao)
            ),
            bound_to=BoundObjectRef(
                kind=_membro("authority.approval.bound_to.kind", vinculo["kind"], BoundObjectKind),
                ref=_uuid("authority.approval.bound_to.ref", vinculo["ref"]),
            ),
        )

    contexto = AuthorityContext(
        status=_membro("authority.status", autoridade["status"], AuthorityStatus),
        approval=aprovacao,
    )

    proveniencia_bruta = _chaves_exatas("provenance", dados["provenance"], _CHAVES_PROVENANCE)
    jurisdicao_proveniencia = proveniencia_bruta["jurisdiction"]
    politica = proveniencia_bruta["policy_ref"]
    proveniencia = ProvenanceRecord(
        origin=_source_reference_de_json("provenance.origin", proveniencia_bruta["origin"]),
        recorded_at=_instante_de_json("provenance.recorded_at", proveniencia_bruta["recorded_at"]),
        jurisdiction=(
            None
            if jurisdicao_proveniencia is None
            else _texto("provenance.jurisdiction", jurisdicao_proveniencia)
        ),
        policy_ref=None if politica is None else _texto("provenance.policy_ref", politica),
    )

    assunto = _chaves_exatas("subject", dados["subject"], _CHAVES_SUBJECT)
    horizonte_bruto = _chaves_exatas("subject.horizon", assunto["horizon"], _CHAVES_HORIZON)
    horizonte = Horizon(
        delta=timedelta(
            microseconds=_inteiro(
                "subject.horizon.delta_microseconds", horizonte_bruto["delta_microseconds"]
            )
        ),
        reference_time=_instante_de_json(
            "subject.horizon.reference_time", horizonte_bruto["reference_time"]
        ),
        availability=_membro(
            "subject.horizon.availability", horizonte_bruto["availability"], TemporalAvailability
        ),
    )
    subject = ClaimSubject(
        target=_texto("subject.target", assunto["target"]),
        signal=_texto("subject.signal", assunto["signal"]),
        horizon=horizonte,
    )

    referencias_brutas = dados["payload_refs"]
    if not isinstance(referencias_brutas, Sequence) or isinstance(referencias_brutas, str):
        raise PiapContractViolationError("payload_refs deve ser lista")

    return PiapEnvelope(
        contract_version=versao,
        subject=subject,
        provenance=proveniencia,
        authority=contexto,
        payload_refs=tuple(
            _source_reference_de_json(f"payload_refs[{i}]", r)
            for i, r in enumerate(referencias_brutas)
        ),
        sealed_at=_instante_de_json("sealed_at", dados["sealed_at"]),
    )
