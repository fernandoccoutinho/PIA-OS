"""
Contrato dos value objects do envelope PIAP (`E5.a`).

```text
NEW_CONTRACT_TEST — nenhum destes testes existia antes; nenhum "falhava"
ABSENT != FAILING_BEHAVIOUR
```
"""

import ast
import dataclasses
import pathlib
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.predictive_accessibility.piap import capacity as capacity_module
from app.predictive_accessibility.piap.authority import (
    ApprovalBinding,
    AuthorityContext,
    BoundObjectRef,
)
from app.predictive_accessibility.piap.capacity import (
    MAX_APPROVAL_SCOPE_ITEMS,
    MAX_PAYLOAD_REFERENCES,
    MAX_PIAP_INPUT_BYTES,
    MAX_PIAP_VERSION_NUMBER,
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
)

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_T1 = datetime(2026, 1, 2, tzinfo=UTC)
_HASH = "a" * 64


def _fonte(seq: int = 1, *, kind: str = "policy.registry", hash_conteudo: str | None = _HASH):
    return SourceReference(
        kind=ProvenanceKind(kind),
        ref=uuid.UUID(int=seq),
        source_version=1,
        content_sha256=hash_conteudo,
    )


def _horizonte(reference_time: datetime = _T0) -> Horizon:
    return Horizon(
        delta=timedelta(hours=6),
        reference_time=reference_time,
        availability=TemporalAvailability.AVAILABLE_AT_REFERENCE_TIME,
    )


def _assunto(reference_time: datetime = _T0) -> ClaimSubject:
    return ClaimSubject(
        target="grid.load", signal="demand.peak", horizon=_horizonte(reference_time)
    )


def _proveniencia(recorded_at: datetime = _T0) -> ProvenanceRecord:
    return ProvenanceRecord(origin=_fonte(), recorded_at=recorded_at, jurisdiction="br")


def _vinculo() -> BoundObjectRef:
    return BoundObjectRef(kind=BoundObjectKind.PROPOSED_BOUND, ref=uuid.UUID(int=99))


def _aprovacao(**kwargs) -> ApprovalBinding:
    base = {
        "approval_reference": "APR-0001",
        "approval_version": 2,
        "approval_scope": ("bound.read", "bound.write"),
        "approval_expiry": datetime(2026, 6, 1, tzinfo=UTC),
        "approval_jurisdiction": "br",
        "bound_to": _vinculo(),
    }
    base.update(kwargs)
    return ApprovalBinding(**base)


def _envelope(**kwargs) -> PiapEnvelope:
    base = {
        "contract_version": PiapContractVersion.V1_0,
        "subject": _assunto(),
        "provenance": _proveniencia(),
        "authority": AuthorityContext(
            status=AuthorityStatus.ASSERTED_AUTHORIZED, approval=_aprovacao()
        ),
        "payload_refs": (_fonte(1),),
        "sealed_at": _T1,
    }
    base.update(kwargs)
    return PiapEnvelope(**base)


# --- construção válida -----------------------------------------------------


def test_envelope_valido_constroi() -> None:
    envelope = _envelope()
    assert envelope.contract_version is PiapContractVersion.V1_0
    assert envelope.subject.target == "grid.load"
    assert envelope.authority.status is AuthorityStatus.ASSERTED_AUTHORIZED


def test_todos_os_value_objects_sao_frozen() -> None:
    for classe in (
        ProvenanceKind,
        SourceReference,
        Horizon,
        ClaimSubject,
        ProvenanceRecord,
        PiapEnvelope,
        BoundObjectRef,
        ApprovalBinding,
        AuthorityContext,
    ):
        assert classe.__dataclass_params__.frozen, classe.__name__


def test_imutabilidade_profunda_atribuicao_recusada() -> None:
    envelope = _envelope()
    with pytest.raises(dataclasses.FrozenInstanceError):
        envelope.sealed_at = _T0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        envelope.subject.horizon.delta = timedelta(days=1)  # type: ignore[misc]


def test_colecoes_publicas_sao_tuple() -> None:
    envelope = _envelope()
    assert isinstance(envelope.payload_refs, tuple)
    assert envelope.authority.approval is not None
    assert isinstance(envelope.authority.approval.approval_scope, tuple)


# --- tokens e gramática ----------------------------------------------------


@pytest.mark.parametrize("valor", ["Grid.Load", "grid load", "grid..load", "_grid", "grid-", "ré"])
def test_token_fora_da_gramatica_rejeita(valor: str) -> None:
    with pytest.raises(ValueError):
        ClaimSubject(target=valor, signal="demand.peak", horizon=_horizonte())


def test_token_nao_e_transformado() -> None:
    assunto = ClaimSubject(target="grid.load", signal="demand.peak", horizon=_horizonte())
    assert assunto.target == "grid.load"


def test_token_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        ClaimSubject(target=1, signal="a", horizon=_horizonte())  # type: ignore[arg-type]


# --- hash ------------------------------------------------------------------


@pytest.mark.parametrize("valor", ["A" * 64, "a" * 63, "a" * 65, "g" * 64, ""])
def test_content_sha256_invalido_rejeita(valor: str) -> None:
    with pytest.raises(ValueError):
        _fonte(hash_conteudo=valor)


def test_content_sha256_ausente_e_legitimo() -> None:
    assert _fonte(hash_conteudo=None).content_sha256 is None


# --- inteiros e bool -------------------------------------------------------


def test_bool_recusado_onde_int_e_exigido() -> None:
    with pytest.raises(TypeError):
        SourceReference(
            kind=ProvenanceKind("a.b"),
            ref=uuid.UUID(int=1),
            source_version=True,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        _aprovacao(approval_version=True)


def test_versao_menor_que_um_rejeita() -> None:
    with pytest.raises(ValueError):
        _aprovacao(approval_version=0)


# --- tempo -----------------------------------------------------------------


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("reference_time", datetime(2026, 1, 1)),
        ("recorded_at", datetime(2026, 1, 1)),
    ],
)
def test_datetime_ingenuo_rejeita(campo: str, valor: datetime) -> None:
    with pytest.raises(ValueError):
        if campo == "reference_time":
            Horizon(
                delta=timedelta(hours=1),
                reference_time=valor,
                availability=TemporalAvailability.UNKNOWN,
            )
        else:
            ProvenanceRecord(origin=_fonte(), recorded_at=valor)


def test_sealed_at_ingenuo_rejeita() -> None:
    with pytest.raises(ValueError):
        _envelope(sealed_at=datetime(2026, 1, 2))


def test_instantes_equivalentes_convergem_ao_mesmo_utc() -> None:
    em_utc = _horizonte(datetime(2026, 1, 1, 12, tzinfo=UTC))
    em_outro_fuso = _horizonte(datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=-3))))
    assert em_utc == em_outro_fuso
    assert em_outro_fuso.reference_time.tzinfo is UTC


def test_microssegundos_preservados() -> None:
    instante = datetime(2026, 1, 1, 0, 0, 0, 123456, tzinfo=UTC)
    assert _horizonte(instante).reference_time.microsecond == 123456


def test_delta_nao_positivo_rejeita() -> None:
    for delta in (timedelta(0), timedelta(seconds=-1)):
        with pytest.raises(ValueError):
            Horizon(
                delta=delta,
                reference_time=_T0,
                availability=TemporalAvailability.UNKNOWN,
            )


# --- invariantes cruzados --------------------------------------------------


def test_reference_time_posterior_a_sealed_at_rejeita() -> None:
    with pytest.raises(ValueError, match="reference_time"):
        _envelope(subject=_assunto(datetime(2026, 2, 1, tzinfo=UTC)))


def test_recorded_at_posterior_a_sealed_at_rejeita() -> None:
    with pytest.raises(ValueError, match="recorded_at"):
        _envelope(provenance=_proveniencia(datetime(2026, 2, 1, tzinfo=UTC)))


def test_payload_refs_duplicada_rejeita() -> None:
    with pytest.raises(ValueError, match="duplicada"):
        _envelope(payload_refs=(_fonte(1), _fonte(1)))


def test_payload_refs_fora_de_ordem_rejeita_sem_reordenar() -> None:
    fora_de_ordem = (_fonte(2, kind="sensor.feed"), _fonte(1, kind="policy.registry"))
    with pytest.raises(ValueError, match="ordem canônica"):
        _envelope(payload_refs=fora_de_ordem)


def test_payload_refs_em_ordem_canonica_aceita() -> None:
    ordenadas = tuple(
        sorted(
            (_fonte(2, kind="sensor.feed"), _fonte(1, kind="policy.registry")),
            key=lambda r: r.sort_key,
        )
    )
    assert _envelope(payload_refs=ordenadas).payload_refs == ordenadas


def test_payload_refs_vazio_e_legitimo() -> None:
    assert _envelope(payload_refs=()).payload_refs == ()


def test_tipos_errados_nos_campos_compostos() -> None:
    with pytest.raises(TypeError):
        _envelope(subject="grid.load")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        _envelope(provenance=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        _envelope(authority=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        _envelope(payload_refs=[_fonte(1)])  # type: ignore[arg-type]


# --- repr redigido ---------------------------------------------------------


def test_policy_ref_redigido_no_repr() -> None:
    proveniencia = ProvenanceRecord(
        origin=_fonte(), recorded_at=_T0, policy_ref="segredo-de-politica"
    )
    assert "segredo-de-politica" not in repr(proveniencia)


def test_referencia_opaca_com_caractere_de_controle_rejeita() -> None:
    with pytest.raises(ValueError):
        ProvenanceRecord(origin=_fonte(), recorded_at=_T0, jurisdiction="br\u0000x")


# --- validadores: cada recusa tem um teste --------------------------------
#
# Um validador cujo caminho de recusa nunca corre é um validador que
# ninguém verificou.


def test_referencia_opaca_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        ProvenanceRecord(origin=_fonte(), recorded_at=_T0, jurisdiction=1)  # type: ignore[arg-type]


def test_referencia_opaca_vazia_rejeita() -> None:
    with pytest.raises(ValueError, match="vazio"):
        ProvenanceRecord(origin=_fonte(), recorded_at=_T0, jurisdiction="   ")


def test_referencia_opaca_longa_demais_rejeita() -> None:
    with pytest.raises(ValueError, match="excede"):
        ProvenanceRecord(origin=_fonte(), recorded_at=_T0, jurisdiction="x" * 256)


def test_token_vazio_rejeita() -> None:
    with pytest.raises(ValueError, match="vazio"):
        ClaimSubject(target="", signal="demand.peak", horizon=_horizonte())


def test_token_longo_demais_rejeita() -> None:
    with pytest.raises(ValueError, match="excede"):
        ClaimSubject(target="a" * 65, signal="demand.peak", horizon=_horizonte())


def test_hash_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        _fonte(hash_conteudo=123)  # type: ignore[arg-type]


def test_instante_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        ProvenanceRecord(origin=_fonte(), recorded_at="2026-01-01")  # type: ignore[arg-type]


def test_kind_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        SourceReference(kind="policy.registry", ref=uuid.UUID(int=1), source_version=1)  # type: ignore[arg-type]


def test_ref_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        SourceReference(kind=ProvenanceKind("a.b"), ref="nao-e-uuid", source_version=1)  # type: ignore[arg-type]


def test_delta_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        Horizon(
            delta=3600,  # type: ignore[arg-type]
            reference_time=_T0,
            availability=TemporalAvailability.UNKNOWN,
        )


def test_availability_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        Horizon(delta=timedelta(hours=1), reference_time=_T0, availability="talvez")  # type: ignore[arg-type]


def test_horizon_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        ClaimSubject(target="grid.load", signal="demand.peak", horizon=object())  # type: ignore[arg-type]


def test_origin_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        ProvenanceRecord(origin=object(), recorded_at=_T0)  # type: ignore[arg-type]


def test_payload_ref_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError, match="payload_refs"):
        _envelope(payload_refs=(object(),))  # type: ignore[arg-type]


def test_bound_object_ref_com_tipos_errados() -> None:
    with pytest.raises(TypeError):
        BoundObjectRef(kind="proposed_bound", ref=uuid.UUID(int=1))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        BoundObjectRef(kind=BoundObjectKind.PROPOSED_BOUND, ref="x")  # type: ignore[arg-type]


def test_authority_context_com_tipos_errados() -> None:
    with pytest.raises(TypeError):
        AuthorityContext(status="autorizado")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        AuthorityContext(
            status=AuthorityStatus.ASSERTED_AUTHORIZED,
            approval=object(),  # type: ignore[arg-type]
        )


def test_bound_to_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        _aprovacao(bound_to=object())


def test_expiracao_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        _aprovacao(approval_expiry="2026-06-01")


# --- capacidade: cardinalidade de payload_refs na construção direta -------
#
# ```text
# PUBLIC_FUNCTION_MUST_BE_SAFE_WHEN_CALLED_INTERNALLY = TRUE
# ```
#
# O teto não vale só na fronteira de bytes. Quem monta o envelope em memória,
# sem passar pelo desserializador, encontra a mesma recusa — senão o limite
# seria uma propriedade do transporte, não do contrato.


def _referencias(n: int) -> tuple[SourceReference, ...]:
    """`n` referências distintas, já em ordem canônica por `sort_key`."""
    brutas = tuple(_fonte(i + 1) for i in range(n))
    return tuple(sorted(brutas, key=lambda r: r.sort_key))


def test_cap_refs_no_teto_e_aceito() -> None:
    envelope = _envelope(payload_refs=_referencias(MAX_PAYLOAD_REFERENCES))
    assert len(envelope.payload_refs) == MAX_PAYLOAD_REFERENCES


def test_cap_refs_acima_do_teto_rejeita() -> None:
    with pytest.raises(ValueError, match="MAX_PAYLOAD_REFERENCES"):
        _envelope(payload_refs=_referencias(MAX_PAYLOAD_REFERENCES + 1))


def test_cap_refs_conta_antes_de_validar_cada_item() -> None:
    """A contagem precede a validação de tipo item a item.

    Uma tupla grande DEMAIS cujo último item é de tipo errado deve reprovar
    pela cardinalidade, com `ValueError`, e não pelo item, com `TypeError`.
    Inverter a ordem troca a exceção e reprova este teste.
    """
    grande_e_invalida = _referencias(MAX_PAYLOAD_REFERENCES) + (object(),)
    with pytest.raises(ValueError, match="MAX_PAYLOAD_REFERENCES"):
        _envelope(payload_refs=grande_e_invalida)


def test_cap_refs_vazio_continua_aceito() -> None:
    """Envelope sem referências é legítimo; o teto é superior, não inferior."""
    assert _envelope(payload_refs=()).payload_refs == ()


def test_cap_refs_ordem_e_duplicata_continuam_exigidas_abaixo_do_teto() -> None:
    """O teto novo não substituiu nenhuma guarda antiga."""
    fora_de_ordem = tuple(reversed(_referencias(3)))
    with pytest.raises(ValueError, match="ordem canônica"):
        _envelope(payload_refs=fora_de_ordem)
    with pytest.raises(ValueError, match="duplicada"):
        _envelope(payload_refs=(_fonte(1), _fonte(1)))


def test_cap_versao_de_fonte_acima_do_teto_rejeita() -> None:
    with pytest.raises(ValueError, match="MAX_PIAP_VERSION_NUMBER"):
        SourceReference(
            kind=ProvenanceKind("policy.registry"),
            ref=uuid.UUID(int=1),
            source_version=MAX_PIAP_VERSION_NUMBER + 1,
            content_sha256=_HASH,
        )


def test_cap_versao_de_fonte_no_teto_e_aceita() -> None:
    fonte = SourceReference(
        kind=ProvenanceKind("policy.registry"),
        ref=uuid.UUID(int=1),
        source_version=MAX_PIAP_VERSION_NUMBER,
        content_sha256=_HASH,
    )
    assert fonte.source_version == MAX_PIAP_VERSION_NUMBER


def test_cap_constantes_tem_os_quatro_valores_normativos() -> None:
    assert MAX_PIAP_INPUT_BYTES == 262_144
    assert MAX_PAYLOAD_REFERENCES == 256
    assert MAX_APPROVAL_SCOPE_ITEMS == 32
    assert MAX_PIAP_VERSION_NUMBER == 2_147_483_647


def test_cap_modulo_de_capacidade_e_puro() -> None:
    """Sem I/O, sem dependência externa e sem estado mutável.

    Um teto reatribuível em runtime não é teto. A prova é estrutural, por AST,
    e não pela ausência de sintomas.
    """
    arvore = ast.parse(pathlib.Path(capacity_module.__file__).read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        assert not isinstance(no, ast.Import | ast.ImportFrom), "capacity.py não importa nada"
        assert not isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    atribuicoes = [n for n in arvore.body if isinstance(n, ast.Assign)]
    nomes = {a.targets[0].id for a in atribuicoes if isinstance(a.targets[0], ast.Name)}
    assert nomes == {
        "MAX_PIAP_INPUT_BYTES",
        "MAX_PAYLOAD_REFERENCES",
        "MAX_APPROVAL_SCOPE_ITEMS",
        "MAX_PIAP_VERSION_NUMBER",
        "__all__",
    }
