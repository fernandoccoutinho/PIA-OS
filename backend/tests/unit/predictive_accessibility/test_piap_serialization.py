"""
Serialização canônica do envelope PIAP (`E5.a`).

```text
SERIALIZATION = canonical UTF-8 JSON bytes
UNKNOWN_FIELD = ERROR ; DUPLICATE_JSON_KEY = ERROR
SILENT_FIELD_DROP = FORBIDDEN
```
"""

import json
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.predictive_accessibility.errors.codes import PIA_8053_PIAP_CONTRACT_VIOLATION
from app.predictive_accessibility.errors.exceptions import (
    PiapContractViolationError,
    PiapUnsupportedVersionError,
)
from app.predictive_accessibility.piap.authority import (
    ApprovalBinding,
    AuthorityContext,
    BoundObjectRef,
)
from app.predictive_accessibility.piap.enums import (
    AuthorityStatus,
    BoundObjectKind,
    PiapContractVersion,
    TemporalAvailability,
)
from app.predictive_accessibility.piap.envelope import (
    ClaimSubject,
    Horizon,
    PiapEnvelope,
    ProvenanceKind,
    ProvenanceRecord,
    SourceReference,
    deserialize_piap_envelope,
    serialize_piap_envelope,
)

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_T1 = datetime(2026, 1, 2, tzinfo=UTC)


def _fonte(seq: int = 1, *, kind: str = "policy.registry", hash_conteudo: str | None = "a" * 64):
    return SourceReference(
        kind=ProvenanceKind(kind),
        ref=uuid.UUID(int=seq),
        source_version=3,
        content_sha256=hash_conteudo,
    )


def _envelope(**kwargs) -> PiapEnvelope:
    base = {
        "contract_version": PiapContractVersion.V1_0,
        "subject": ClaimSubject(
            target="grid.load",
            signal="demand.peak",
            horizon=Horizon(
                delta=timedelta(hours=6, microseconds=7),
                reference_time=_T0,
                availability=TemporalAvailability.AVAILABLE_AT_REFERENCE_TIME,
            ),
        ),
        "provenance": ProvenanceRecord(
            origin=_fonte(), recorded_at=_T0, jurisdiction="br", policy_ref="pol.a"
        ),
        "authority": AuthorityContext(
            status=AuthorityStatus.ASSERTED_AUTHORIZED,
            approval=ApprovalBinding(
                approval_reference="APR-0001",
                approval_version=2,
                approval_scope=("bound.read", "bound.write"),
                approval_expiry=datetime(2026, 6, 1, tzinfo=UTC),
                approval_jurisdiction="br",
                bound_to=BoundObjectRef(kind=BoundObjectKind.PROPOSED_BOUND, ref=uuid.UUID(int=99)),
            ),
        ),
        "payload_refs": tuple(
            sorted((_fonte(1), _fonte(2, kind="sensor.feed")), key=lambda r: r.sort_key)
        ),
        "sealed_at": _T1,
    }
    base.update(kwargs)
    return PiapEnvelope(**base)


def _sem_aprovacao() -> PiapEnvelope:
    return _envelope(
        authority=AuthorityContext(status=AuthorityStatus.UNKNOWN),
        provenance=ProvenanceRecord(origin=_fonte(), recorded_at=_T0),
    )


# --- round trip ------------------------------------------------------------


@pytest.mark.parametrize("construtor", [_envelope, _sem_aprovacao])
def test_round_trip_preserva_o_objeto(construtor) -> None:
    original = construtor()
    assert deserialize_piap_envelope(serialize_piap_envelope(original)) == original


def test_round_trip_de_bytes_e_deterministico() -> None:
    original = _envelope()
    primeiro = serialize_piap_envelope(original)
    segundo = serialize_piap_envelope(deserialize_piap_envelope(primeiro))
    assert primeiro == segundo
    assert serialize_piap_envelope(original) == primeiro


def test_round_trip_preserva_proveniencia_autoridade_e_referencias() -> None:
    original = _envelope()
    reconstruido = deserialize_piap_envelope(serialize_piap_envelope(original))
    assert reconstruido.provenance == original.provenance
    assert reconstruido.authority == original.authority
    assert reconstruido.payload_refs == original.payload_refs


def test_microssegundos_do_horizonte_sobrevivem_sem_float() -> None:
    reconstruido = deserialize_piap_envelope(serialize_piap_envelope(_envelope()))
    assert reconstruido.subject.horizon.delta == timedelta(hours=6, microseconds=7)
    documento = json.loads(serialize_piap_envelope(_envelope()))
    assert isinstance(documento["subject"]["horizon"]["delta_microseconds"], int)


def test_instante_em_outro_fuso_produz_os_mesmos_bytes() -> None:
    em_utc = _envelope(sealed_at=datetime(2026, 1, 2, 12, tzinfo=UTC))
    outro = _envelope(sealed_at=datetime(2026, 1, 2, 9, tzinfo=timezone(timedelta(hours=-3))))
    assert serialize_piap_envelope(em_utc) == serialize_piap_envelope(outro)


# --- forma canônica --------------------------------------------------------


def test_bytes_sao_utf8_json_com_chaves_ordenadas_e_compactas() -> None:
    bruto = serialize_piap_envelope(_envelope())
    assert isinstance(bruto, bytes)
    texto = bruto.decode("utf-8")
    assert ", " not in texto and '": ' not in texto
    documento = json.loads(texto)
    assert list(documento) == sorted(documento)


def test_instantes_saem_em_utc_com_sufixo_z() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    assert documento["sealed_at"].endswith("Z")
    assert documento["provenance"]["recorded_at"].endswith("Z")


# --- rejeições -------------------------------------------------------------


def test_campo_extra_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["extra"] = 1
    with pytest.raises(PiapContractViolationError, match="extras"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_campo_ausente_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    del documento["sealed_at"]
    with pytest.raises(PiapContractViolationError, match="faltando"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_campo_extra_aninhado_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["subject"]["horizon"]["extra"] = 1
    with pytest.raises(PiapContractViolationError, match="subject.horizon"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_chave_json_duplicada_rejeita() -> None:
    bruto = b'{"sealed_at":"x","sealed_at":"y"}'
    with pytest.raises(PiapContractViolationError, match="duplicada"):
        deserialize_piap_envelope(bruto)


def test_json_malformado_rejeita() -> None:
    with pytest.raises(PiapContractViolationError, match="JSON"):
        deserialize_piap_envelope(b"{")


def test_utf8_invalido_rejeita() -> None:
    with pytest.raises(PiapContractViolationError, match="UTF-8"):
        deserialize_piap_envelope(b"\xff\xfe")


def test_versao_desconhecida_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["contract_version"] = "9.9"
    with pytest.raises(PiapUnsupportedVersionError):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_tipo_errado_em_inteiro_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["subject"]["horizon"]["delta_microseconds"] = True
    with pytest.raises(PiapContractViolationError, match="inteiro"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_uuid_nao_canonico_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["provenance"]["origin"]["ref"] = "nao-e-uuid"
    with pytest.raises(PiapContractViolationError, match="UUID"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_membro_fora_do_vocabulario_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["authority"]["status"] = "talvez"
    with pytest.raises(PiapContractViolationError, match="vocabulário"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_instante_sem_sufixo_z_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["sealed_at"] = "2026-01-02T00:00:00+00:00"
    with pytest.raises(PiapContractViolationError, match="sealed_at"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_instante_malformado_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["sealed_at"] = "ontemZ"
    with pytest.raises(PiapContractViolationError, match="ISO-8601"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_lista_esperada_como_objeto_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["payload_refs"] = {"a": 1}
    with pytest.raises(PiapContractViolationError, match="payload_refs"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_escopo_como_string_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["authority"]["approval"]["approval_scope"] = "bound.read"
    with pytest.raises(PiapContractViolationError, match="approval_scope"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_payload_nao_bytes_e_type_error() -> None:
    with pytest.raises(TypeError):
        deserialize_piap_envelope("{}")  # type: ignore[arg-type]


def test_serializar_nao_envelope_e_type_error() -> None:
    with pytest.raises(TypeError):
        serialize_piap_envelope(object())  # type: ignore[arg-type]


def test_codigo_de_violacao_e_o_da_camada() -> None:
    with pytest.raises(PiapContractViolationError) as erro:
        deserialize_piap_envelope(b"{")
    assert erro.value.error_code is PIA_8053_PIAP_CONTRACT_VIOLATION
    assert erro.value.error_code.code == "PIA-8053"


def test_ordem_canonica_de_payload_refs_e_exigida_na_desserializacao() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["payload_refs"].reverse()
    with pytest.raises(ValueError, match="ordem canônica"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_texto_de_tipo_errado_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["subject"]["target"] = 7
    with pytest.raises(PiapContractViolationError, match="string"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))


def test_nivel_esperado_como_lista_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["subject"] = ["grid.load"]
    with pytest.raises(PiapContractViolationError, match="objeto JSON"):
        deserialize_piap_envelope(json.dumps(documento).encode("utf-8"))
