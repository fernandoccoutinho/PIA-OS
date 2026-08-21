"""
Serialização canônica do envelope PIAP (`E5.a`).

```text
SERIALIZATION = canonical UTF-8 JSON bytes
UNKNOWN_FIELD = ERROR ; DUPLICATE_JSON_KEY = ERROR
SILENT_FIELD_DROP = FORBIDDEN
```
"""

import ast
import json
import pathlib
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.predictive_accessibility.errors.codes import PIA_8053_PIAP_CONTRACT_VIOLATION
from app.predictive_accessibility.errors.exceptions import (
    PiapContractViolationError,
    PiapUnsupportedVersionError,
)
from app.predictive_accessibility.piap import envelope as envelope_module
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


def test_microssegundos_do_horizonte_sobrevivem_em_valor_pequeno() -> None:
    """Caso pequeno. **Não** prova ausência de float — ver os testes de B1.

    Este teste existe na cadeia 99 com o nome
    `test_microssegundos_do_horizonte_sobrevivem_sem_float`, e a auditoria
    mostrou que o nome afirmava mais do que o corpo media: seis horas e sete
    microssegundos cabem folgadamente na precisão exata do `float`, então o
    caso passava mesmo com a conversão defeituosa.

    ```text
    SMALL_FIXTURE_PASS != NO_FLOAT_PROOF
    ```

    O teste foi preservado, com o nome corrigido para dizer o que ele mede.
    """
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


def test_uuid_invalido_rejeita() -> None:
    """Renomeado: `"nao-e-uuid"` é UUID **inválido**, não UUID em forma não
    canônica. O nome da cadeia 99 afirmava o segundo caso e media o primeiro.
    Os casos realmente não canônicos estão em `test_uuid_valido_nao_canonico_rejeita`.
    """
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["provenance"]["origin"]["ref"] = "nao-e-uuid"
    with pytest.raises(PiapContractViolationError, match="UUID"):
        deserialize_piap_envelope(_canonizar(documento))


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


# ===========================================================================
# Corretivo da cadeia 100 — os quatro defeitos reprovados na auditoria da 99
# ===========================================================================
#
# Cada teste desta secao FALHA contra o parent 0a0574ac e PASSA no corretivo.
# Nenhum deles passa dos dois lados.
#
#     PARENT_FAILING_TEST != TEST_THAT_PASSES_ON_BOTH_SIDES


def _canonizar(documento: dict[str, object]) -> bytes:
    """Reescreve o documento na forma canônica de chave e separador.

    Existe para que os testes de UUID, versão e campo isolem o defeito que
    querem medir: sem isto, a nova verificação de bytes canônicos reprovaria
    antes, por um motivo diferente do que o teste pretende provar.
    """
    return json.dumps(documento, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _us_exatos(valor: timedelta) -> int:
    return ((valor.days * 86400) + valor.seconds) * 1_000_000 + valor.microseconds


# --- B1: timedelta sem float ----------------------------------------------


@pytest.mark.parametrize(
    "delta",
    [
        timedelta(days=200000, microseconds=1),
        timedelta.max,
        timedelta(microseconds=1),
        timedelta(days=999999999),
        timedelta(days=106751991, microseconds=999999),
    ],
)
def test_b1_round_trip_preserva_timedelta_em_qualquer_magnitude(delta: timedelta) -> None:
    """Contra o parent, os dois primeiros casos perdem microssegundos."""
    envelope = _envelope(
        subject=ClaimSubject(
            target="grid.load",
            signal="demand.peak",
            horizon=Horizon(
                delta=delta,
                reference_time=_T0,
                availability=TemporalAvailability.UNKNOWN,
            ),
        ),
        sealed_at=datetime(9999, 12, 30, tzinfo=UTC),
    )
    reconstruido = deserialize_piap_envelope(serialize_piap_envelope(envelope))
    assert reconstruido.subject.horizon.delta == delta


@pytest.mark.parametrize(
    "delta", [timedelta(days=200000, microseconds=1), timedelta.max, timedelta(days=999999999)]
)
def test_b1_microssegundos_codificados_sao_exatos(delta: timedelta) -> None:
    """Prova comportamental de ausência de float: o inteiro codificado é exato.

    `timedelta.max` codificado por float dava 86400000000000000000, um
    microssegundo **acima** do valor real — arredondamento para cima, não
    truncamento.
    """
    envelope = _envelope(
        subject=ClaimSubject(
            target="grid.load",
            signal="demand.peak",
            horizon=Horizon(
                delta=delta, reference_time=_T0, availability=TemporalAvailability.UNKNOWN
            ),
        ),
        sealed_at=datetime(9999, 12, 30, tzinfo=UTC),
    )
    documento = json.loads(serialize_piap_envelope(envelope))
    codificado = documento["subject"]["horizon"]["delta_microseconds"]
    assert isinstance(codificado, int)
    assert not isinstance(codificado, bool)
    assert codificado == _us_exatos(delta)


def test_b1_nenhuma_divisao_envolvendo_timedelta_no_codigo_executavel() -> None:
    """Prova estrutural por AST, não por busca textual.

    Busca textual acusaria a própria docstring de `_total_microssegundos`, que
    cita a expressão defeituosa justamente para explicar por que ela saiu. A
    AST vê apenas o código executável.
    """
    arvore = ast.parse(pathlib.Path(envelope_module.__file__).read_text(encoding="utf-8"))
    divisoes = [
        ast.unparse(no)
        for no in ast.walk(arvore)
        if isinstance(no, ast.BinOp) and isinstance(no.op, ast.Div | ast.FloorDiv)
    ]
    assert not [d for d in divisoes if "timedelta" in d or "delta" in d], divisoes


def test_b1_existe_conversao_inteira_dedicada() -> None:
    """O cálculo vive numa função própria, testável e sem ponto flutuante."""
    assert callable(envelope_module._total_microssegundos)
    assert envelope_module._total_microssegundos(timedelta.max) == _us_exatos(timedelta.max)
    assert isinstance(envelope_module._total_microssegundos(timedelta.max), int)


def test_b1_microssegundos_fora_do_dominio_de_timedelta_rejeita() -> None:
    """Fora do domínio é violação de contrato, não valor a ser aparado."""
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["subject"]["horizon"]["delta_microseconds"] = 10**30
    with pytest.raises(PiapContractViolationError, match="domínio de timedelta"):
        deserialize_piap_envelope(_canonizar(documento))


# --- M1: UUID válido em forma não canônica --------------------------------


@pytest.mark.parametrize(
    "nao_canonico",
    [
        "{00000000-0000-0000-0000-000000000001}",
        "00000000000000000000000000000001",
        "urn:uuid:00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-00000000000A",
        "00000000-0000-0000-0000-00000000000a".upper(),
    ],
)
def test_m1_uuid_valido_nao_canonico_rejeita(nao_canonico: str) -> None:
    """Contra o parent, todos estes eram aceitos e normalizados em silêncio."""
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["provenance"]["origin"]["ref"] = nao_canonico
    with pytest.raises(PiapContractViolationError, match="NÃO canônica"):
        deserialize_piap_envelope(_canonizar(documento))


def test_m1_uuid_canonico_continua_aceito() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["provenance"]["origin"]["ref"] = "00000000-0000-0000-0000-000000000001"
    reconstruido = deserialize_piap_envelope(_canonizar(documento))
    assert str(reconstruido.provenance.origin.ref) == "00000000-0000-0000-0000-000000000001"


def test_m1_uuid_nao_canonico_no_vinculo_de_aprovacao_rejeita() -> None:
    """A verificação vale em toda posição de UUID, não só na proveniência."""
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["authority"]["approval"]["bound_to"]["ref"] = "{00000000-0000-0000-0000-000000000063}"
    with pytest.raises(PiapContractViolationError, match="NÃO canônica"):
        deserialize_piap_envelope(_canonizar(documento))


# --- M2: bytes canônicos ---------------------------------------------------


def test_m2_json_indentado_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    indentado = json.dumps(documento, indent=2, sort_keys=True).encode("utf-8")
    with pytest.raises(PiapContractViolationError, match="forma canônica"):
        deserialize_piap_envelope(indentado)


def test_m2_chaves_fora_de_ordem_canonica_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    invertido = {chave: documento[chave] for chave in reversed(list(documento))}
    fora_de_ordem = json.dumps(invertido, separators=(",", ":")).encode("utf-8")
    assert fora_de_ordem != serialize_piap_envelope(_envelope())
    with pytest.raises(PiapContractViolationError, match="forma canônica"):
        deserialize_piap_envelope(fora_de_ordem)


def test_m2_separadores_nao_compactos_rejeita() -> None:
    documento = json.loads(serialize_piap_envelope(_envelope()))
    espacado = json.dumps(documento, sort_keys=True, separators=(", ", ": ")).encode("utf-8")
    with pytest.raises(PiapContractViolationError, match="forma canônica"):
        deserialize_piap_envelope(espacado)


def test_m2_instante_semanticamente_equivalente_nao_canonico_rejeita() -> None:
    """`...T00:00:00.000000Z` descreve o mesmo instante e não é a forma emitida."""
    canonico = serialize_piap_envelope(_envelope())
    equivalente = canonico.replace(b"2026-01-01T00:00:00Z", b"2026-01-01T00:00:00.000000Z")
    assert equivalente != canonico
    with pytest.raises(PiapContractViolationError, match="forma canônica"):
        deserialize_piap_envelope(equivalente)


def test_m2_escape_json_alternativo_rejeita() -> None:
    """`\\u0067` é `g`; o texto sobrevive à validação de campo e os bytes mudam."""
    canonico = serialize_piap_envelope(_envelope())
    escapado = canonico.replace(b'"target":"grid.load"', b'"target":"\\u0067rid.load"')
    assert escapado != canonico
    with pytest.raises(PiapContractViolationError, match="forma canônica"):
        deserialize_piap_envelope(escapado)


def test_m2_payload_canonico_continua_aceito() -> None:
    original = _envelope()
    canonico = serialize_piap_envelope(original)
    assert deserialize_piap_envelope(canonico) == original


def test_m2_precedencias_anteriores_sobrevivem_a_verificacao_de_canonicidade() -> None:
    """Versão, chave duplicada e JSON inválido continuam vindo ANTES."""
    documento = json.loads(serialize_piap_envelope(_envelope()))
    documento["contract_version"] = "9.9"
    with pytest.raises(PiapUnsupportedVersionError):
        deserialize_piap_envelope(json.dumps(documento, indent=4).encode("utf-8"))
    with pytest.raises(PiapContractViolationError, match="duplicada"):
        deserialize_piap_envelope(b'{"sealed_at":"x","sealed_at":"y"}')
    with pytest.raises(PiapContractViolationError, match="JSON"):
        deserialize_piap_envelope(b"{")


# --- m1: tipo público estrito ---------------------------------------------


def test_m1_tipo_somente_bytes_e_aceito() -> None:
    canonico = serialize_piap_envelope(_envelope())
    assert isinstance(deserialize_piap_envelope(canonico), PiapEnvelope)


@pytest.mark.parametrize(
    "conversor",
    [bytearray, memoryview, lambda b: b.decode("utf-8"), list],
    ids=["bytearray", "memoryview", "str", "list"],
)
def test_m1_tipos_nao_bytes_sao_type_error(conversor) -> None:
    """Contra o parent, `bytearray` era aceito e convertido em silêncio."""
    canonico = serialize_piap_envelope(_envelope())
    with pytest.raises(TypeError, match="payload deve ser bytes"):
        deserialize_piap_envelope(conversor(canonico))  # type: ignore[arg-type]


# --- capacidade na fronteira de bytes -------------------------------------
#
# ```text
# HTTP_LIMIT != PIAP_LIMIT
# CARDINALITY_CHECK_BEFORE_EXPENSIVE_OBJECT_ASSEMBLY = TRUE
# RAW_VALUE_ERROR_AT_PIAP_BOUNDARY = DEFECT
# ```
#
# Contra o parent, os quatro tetos NÃO existiam: 262.145 bytes, 257
# referências, 33 itens de escopo e a versão 2.147.483.648 eram todos aceitos,
# e um inteiro JSON de 4.301 dígitos escapava como `ValueError` cru.


def _refs_serializadas(n: int) -> list[dict]:
    """`n` referências em forma JSON canônica, já ordenadas."""
    fontes = tuple(sorted((_fonte(i + 1) for i in range(n)), key=lambda r: r.sort_key))
    return [envelope_module._source_reference_para_json(f) for f in fontes]


def _canonico(documento: dict) -> bytes:
    return json.dumps(documento, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _documento() -> dict:
    return json.loads(serialize_piap_envelope(_envelope()))


def test_cap_bytes_no_teto_alcanca_a_validacao_posterior() -> None:
    """Exatamente 262.144 bytes não é rejeitado POR TAMANHO.

    O payload é lixo, então ele falha adiante — e é justamente esse "adiante"
    que o teste mede: a mensagem não pode ser a do teto de bytes.
    """
    with pytest.raises(PiapContractViolationError) as erro:
        deserialize_piap_envelope(b"x" * MAX_PIAP_INPUT_BYTES)
    assert "MAX_PIAP_INPUT_BYTES" not in str(erro.value)


def test_cap_bytes_acima_do_teto_rejeita_antes_de_utf8_e_json(monkeypatch) -> None:
    """Um byte acima do teto, `json.loads` não pode nem ser chamado.

    A sonda substitui `json.loads` por uma função que registra a chamada.
    Provar a ordem por sonda é diferente de supô-la pelo texto do código.
    """
    chamadas: list[int] = []

    def loads_espiao(*args, **kwargs):  # pragma: no cover - não deve executar
        chamadas.append(1)
        raise AssertionError("json.loads foi chamado acima do teto de bytes")

    monkeypatch.setattr(envelope_module.json, "loads", loads_espiao)
    with pytest.raises(PiapContractViolationError, match="MAX_PIAP_INPUT_BYTES"):
        deserialize_piap_envelope(b"x" * (MAX_PIAP_INPUT_BYTES + 1))
    assert chamadas == []


def test_cap_bytes_mensagem_nomeia_observado_e_permitido() -> None:
    with pytest.raises(PiapContractViolationError) as erro:
        deserialize_piap_envelope(b"x" * (MAX_PIAP_INPUT_BYTES + 1))
    texto = str(erro.value)
    assert str(MAX_PIAP_INPUT_BYTES + 1) in texto
    assert str(MAX_PIAP_INPUT_BYTES) in texto


def test_cap_desserializacao_com_refs_no_teto_e_aceita() -> None:
    documento = _documento()
    documento["payload_refs"] = _refs_serializadas(MAX_PAYLOAD_REFERENCES)
    bytes_canonicos = _canonico(documento)
    assert len(bytes_canonicos) <= MAX_PIAP_INPUT_BYTES
    assert len(deserialize_piap_envelope(bytes_canonicos).payload_refs) == MAX_PAYLOAD_REFERENCES


def test_cap_desserializacao_com_refs_acima_do_teto_rejeita_por_cardinalidade() -> None:
    """Bytes DENTRO do teto e cardinalidade fora: quem reprova é a cardinalidade."""
    documento = _documento()
    documento["payload_refs"] = _refs_serializadas(MAX_PAYLOAD_REFERENCES + 1)
    bytes_canonicos = _canonico(documento)
    assert len(bytes_canonicos) <= MAX_PIAP_INPUT_BYTES
    with pytest.raises(PiapContractViolationError, match="MAX_PAYLOAD_REFERENCES"):
        deserialize_piap_envelope(bytes_canonicos)


def test_cap_desserializacao_com_escopo_no_teto_e_aceita() -> None:
    documento = _documento()
    escopo = sorted(f"bound.scope.{i:04d}" for i in range(MAX_APPROVAL_SCOPE_ITEMS))
    documento["authority"]["approval"]["approval_scope"] = escopo
    bytes_canonicos = _canonico(documento)
    assert len(bytes_canonicos) <= MAX_PIAP_INPUT_BYTES
    reconstruido = deserialize_piap_envelope(bytes_canonicos)
    assert reconstruido.authority.approval is not None
    assert len(reconstruido.authority.approval.approval_scope) == MAX_APPROVAL_SCOPE_ITEMS


def test_cap_desserializacao_com_escopo_acima_do_teto_rejeita_por_cardinalidade() -> None:
    documento = _documento()
    escopo = sorted(f"bound.scope.{i:04d}" for i in range(MAX_APPROVAL_SCOPE_ITEMS + 1))
    documento["authority"]["approval"]["approval_scope"] = escopo
    bytes_canonicos = _canonico(documento)
    assert len(bytes_canonicos) <= MAX_PIAP_INPUT_BYTES
    with pytest.raises(PiapContractViolationError, match="MAX_APPROVAL_SCOPE_ITEMS"):
        deserialize_piap_envelope(bytes_canonicos)


def _documento_nas_cardinalidades_maximas() -> tuple[dict, bytes]:
    """Documento com AS DUAS cardinalidades exatamente NO teto, e seus bytes.

    Serve aos dois testes abaixo: um infla os bytes um acima do teto, o outro
    para exatamente no teto. Assim os dois medem o MESMO documento, e a única
    variável entre eles é um byte.
    """
    documento = _documento()
    documento["payload_refs"] = _refs_serializadas(MAX_PAYLOAD_REFERENCES)
    documento["authority"]["approval"]["approval_scope"] = sorted(
        f"bound.scope.{i:04d}" for i in range(MAX_APPROVAL_SCOPE_ITEMS)
    )
    return documento, _canonico(documento)


def test_cap_bytes_vence_com_as_cardinalidades_dentro_dos_tetos() -> None:
    """Cardinalidades DENTRO dos tetos e bytes UM acima: reprova por bytes.

    Substitui `test_cap_tetos_sao_independentes_e_bytes_vence_quando_ambos_estouram`
    da candidata rejeitada `067d554e`, cujo corpo usava
    `MAX_PAYLOAD_REFERENCES + 1`. Com a cardinalidade também fora, a rejeição
    podia vir dela, e a guarda de bytes nunca era exercitada sozinha.

    ```text
    BOTH_LIMITS_EXCEEDED != BYTE_LIMIT_PROVEN
    ```

    O documento base é primeiro provado ACEITÁVEL. O único fato que muda entre
    aceitar e reprovar é o enchimento.
    """
    documento, base = _documento_nas_cardinalidades_maximas()

    assert len(documento["payload_refs"]) == MAX_PAYLOAD_REFERENCES
    assert len(documento["authority"]["approval"]["approval_scope"]) == MAX_APPROVAL_SCOPE_ITEMS
    assert len(base) < MAX_PIAP_INPUT_BYTES
    assert len(deserialize_piap_envelope(base).payload_refs) == MAX_PAYLOAD_REFERENCES

    enchimento = b" " * (MAX_PIAP_INPUT_BYTES + 1 - len(base))
    payload = base + enchimento
    assert len(payload) == MAX_PIAP_INPUT_BYTES + 1

    with pytest.raises(PiapContractViolationError, match="MAX_PIAP_INPUT_BYTES"):
        deserialize_piap_envelope(payload)


def test_cap_um_byte_abaixo_do_teto_a_recusa_ja_nao_e_por_tamanho() -> None:
    """Controle do teste acima: a fronteira é o byte, não o tamanho do documento.

    Mesmo documento, mesmo enchimento, um byte a menos. O teto de bytes deixa
    de valer e a recusa passa a vir da comparação canônica, que é o próximo
    ponto do caminho. Sem este controle, o teste acima seria compatível com
    "documento grande reprova por qualquer motivo".
    """
    _, base = _documento_nas_cardinalidades_maximas()
    payload = base + b" " * (MAX_PIAP_INPUT_BYTES - len(base))
    assert len(payload) == MAX_PIAP_INPUT_BYTES

    with pytest.raises(PiapContractViolationError) as erro:
        deserialize_piap_envelope(payload)
    assert "MAX_PIAP_INPUT_BYTES" not in str(erro.value)


def test_cap_versao_acima_do_teto_rejeita_na_desserializacao() -> None:
    for caminho in ("payload_refs", "authority"):
        documento = _documento()
        if caminho == "payload_refs":
            documento["payload_refs"][0]["source_version"] = MAX_PIAP_VERSION_NUMBER + 1
        else:
            documento["authority"]["approval"]["approval_version"] = MAX_PIAP_VERSION_NUMBER + 1
        with pytest.raises(PiapContractViolationError, match="MAX_PIAP_VERSION_NUMBER"):
            deserialize_piap_envelope(_canonico(documento))


def test_cap_versao_no_teto_e_aceita_na_desserializacao() -> None:
    documento = _documento()
    documento["payload_refs"][0]["source_version"] = MAX_PIAP_VERSION_NUMBER
    documento["authority"]["approval"]["approval_version"] = MAX_PIAP_VERSION_NUMBER
    reconstruido = deserialize_piap_envelope(_canonico(documento))
    assert reconstruido.payload_refs[0].source_version == MAX_PIAP_VERSION_NUMBER


def test_cap_inteiro_json_alem_da_capacidade_do_parser_e_erro_tipado() -> None:
    """4.301 dígitos: o parser recusa, e a recusa não pode vazar como `ValueError`.

    O payload fica MUITO abaixo de 256 KiB, então o teto de bytes não o pega.
    Contra o parent, este caminho escapava cru pela função pública.
    """
    canonico = serialize_piap_envelope(_envelope()).decode("utf-8")
    gigante = "9" * 4301
    texto = canonico.replace('"source_version":3', f'"source_version":{gigante}', 1)
    payload = texto.encode("utf-8")
    assert len(payload) < MAX_PIAP_INPUT_BYTES
    with pytest.raises(PiapContractViolationError, match="capacidade do parser"):
        deserialize_piap_envelope(payload)


def test_cap_serializacao_defensiva_de_inteiro_fora_da_capacidade_e_erro_tipado(
    monkeypatch,
) -> None:
    """O serializador também não deixa `ValueError` numérico escapar.

    O caminho é defensivo: a construção do envelope já barra a versão. A sonda
    força o `json.dumps` a falhar por número para provar que o `except` existe
    e é da camada certa.
    """

    def dumps_que_falha(*args, **kwargs):
        raise ValueError("Exceeds the limit (4300 digits) for integer string conversion")

    monkeypatch.setattr(envelope_module.json, "dumps", dumps_que_falha)
    with pytest.raises(PiapContractViolationError, match="JSON canônico"):
        serialize_piap_envelope(_envelope())


def test_cap_nenhuma_configuracao_global_de_digitos_e_alterada() -> None:
    """`sys.set_int_max_str_digits` não é CHAMADO em lugar nenhum do pacote.

    Aumentar o limite global do processo para fazer uma entrada caber é o
    oposto de validar a entrada.

    A guarda é por AST, não por texto: `capacity.py` explica no docstring por
    que não faz isso, e uma busca textual reprovaria a própria explicação.

    ```text
    MENTIONING_A_CALL != MAKING_A_CALL
    ```
    """
    pacote = pathlib.Path(envelope_module.__file__).parent.parent
    for arquivo in sorted(pacote.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call):
                alvo = no.func
                nome = alvo.attr if isinstance(alvo, ast.Attribute) else getattr(alvo, "id", "")
                assert nome != "set_int_max_str_digits", arquivo


def test_cap_nenhuma_cardinalidade_e_truncada_deduplicada_ou_reordenada() -> None:
    """Rejeitar não virou aparar: nada é silenciosamente ajustado para caber."""
    documento = _documento()
    documento["payload_refs"] = _refs_serializadas(MAX_PAYLOAD_REFERENCES + 1)
    with pytest.raises(PiapContractViolationError):
        deserialize_piap_envelope(_canonico(documento))

    documento = _documento()
    fora_de_ordem = list(reversed(_refs_serializadas(3)))
    documento["payload_refs"] = fora_de_ordem
    with pytest.raises(ValueError, match="ordem canônica"):
        deserialize_piap_envelope(_canonico(documento))

    documento = _documento()
    duplicada = _refs_serializadas(1)
    documento["payload_refs"] = duplicada + duplicada
    with pytest.raises(ValueError, match="duplicada"):
        deserialize_piap_envelope(_canonico(documento))


def test_cap_constantes_vem_de_fonte_unica_em_envelope() -> None:
    """`envelope.py` não redeclara teto nenhum."""
    fonte = pathlib.Path(envelope_module.__file__).read_text(encoding="utf-8")
    for nome in (
        "MAX_PIAP_INPUT_BYTES",
        "MAX_PAYLOAD_REFERENCES",
        "MAX_APPROVAL_SCOPE_ITEMS",
        "MAX_PIAP_VERSION_NUMBER",
    ):
        assert f"{nome} = " not in fonte
    assert envelope_module.MAX_PIAP_INPUT_BYTES is MAX_PIAP_INPUT_BYTES
    assert envelope_module.MAX_PAYLOAD_REFERENCES is MAX_PAYLOAD_REFERENCES


def test_cap_versao_zero_e_negativa_rejeitam_na_desserializacao() -> None:
    """O domínio fechado vale nos DOIS extremos também na fronteira de bytes.

    O piso não é herdado do value object: se fosse, a mensagem viria como
    `ValueError`, e o vocabulário da fronteira exige `PiapContractViolationError`.
    """
    for invalida in (0, -1):
        documento = _documento()
        documento["payload_refs"][0]["source_version"] = invalida
        with pytest.raises(PiapContractViolationError, match=">= 1"):
            deserialize_piap_envelope(_canonico(documento))
