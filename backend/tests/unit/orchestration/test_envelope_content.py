"""
`ENVELOPE_CONTENT` e o hash canônico — provas de determinismo (`E7.1`).

```text
SEALED_AT_IN_CONTENT_HASH = FALSE
CONTENT_DETERMINISM = TRUE
CONTENT_CHANGED -> hash distinto
```

O hash de referência é literal e verificado num **subprocesso** com
`PYTHONHASHSEED` diferente: determinismo alegado dentro do mesmo processo
não é determinismo, é coincidência de ambiente.
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from app.orchestration.schemas.envelope import (
    ENVELOPE_CONTENT_FIELDS,
    ENVELOPE_VERSION,
    SEAL_RECEIPT_ONLY_FIELDS,
    ContextRef,
    EnvelopeContent,
    ScheduleDraft,
    StepDraft,
    canonical_constraints,
    parse_context_refs,
)

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[3]

_SCHEDULE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_STEP_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
_HASH_A = "a" * 64
_HASH_B = "b" * 64

GOLDEN_CONTENT_SHA256 = "06b1e5e2544acaeff9c896cb323b43c42d833a1d2a6c2804211d40837a866444"
"""Valor de referência, recalculado abaixo e comparado em subprocesso.

Fixar o literal transforma "o hash é estável" numa afirmação falsificável:
qualquer mudança acidental na serialização canônica reprova aqui, não
silenciosamente na próxima entrega.
"""


def _conteudo(**alteracoes: object) -> EnvelopeContent:
    campos: dict[str, object] = {
        "envelope_version": ENVELOPE_VERSION,
        "schedule_id": _SCHEDULE_ID,
        "step_id": _STEP_ID,
        "role": "reviewer",
        "instruction_ref": "instr://revisao-1",
        "context_refs": (ContextRef(uri="art://a", sha256=_HASH_A, bytes=10),),
        "expected_output_contract": "contract://parecer-v1",
        "constraints": (
            ("idioma", "pt-BR"),
            ("limite", "2000"),
        ),
    }
    campos.update(alteracoes)
    return EnvelopeContent(**campos)  # type: ignore[arg-type]


# --- campos congelados -----------------------------------------------------


def test_e71c01_o_conteudo_tem_exatamente_os_oito_campos_do_mai() -> None:
    assert set(_conteudo().as_canonical_mapping()) == ENVELOPE_CONTENT_FIELDS
    assert len(ENVELOPE_CONTENT_FIELDS) == 8


def test_e71c02_campos_do_recibo_nunca_aparecem_no_conteudo() -> None:
    """`sealed_at`, `attempt_id` e `sealer_ref` vivem a jusante (§21)."""
    canonico = _conteudo().canonical_json()
    for campo in SEAL_RECEIPT_ONLY_FIELDS:
        assert campo not in canonico
    assert not (ENVELOPE_CONTENT_FIELDS & SEAL_RECEIPT_ONLY_FIELDS)


def test_e71c03_o_hash_bate_com_o_valor_de_referencia() -> None:
    assert _conteudo().content_sha256() == GOLDEN_CONTENT_SHA256


def test_e71c04_o_hash_e_estavel_entre_processos_com_outro_hashseed() -> None:
    """Roda em subprocesso com `PYTHONHASHSEED` distinto e sem cache."""
    programa = (
        "import uuid;"
        "from app.orchestration.schemas.envelope import ContextRef, EnvelopeContent;"
        "print(EnvelopeContent("
        "envelope_version='1',"
        f"schedule_id=uuid.UUID('{_SCHEDULE_ID}'),"
        f"step_id=uuid.UUID('{_STEP_ID}'),"
        "role='reviewer',"
        "instruction_ref='instr://revisao-1',"
        f"context_refs=(ContextRef(uri='art://a', sha256='{_HASH_A}', bytes=10),),"
        "expected_output_contract='contract://parecer-v1',"
        "constraints=(('idioma','pt-BR'),('limite','2000'))"
        ").content_sha256())"
    )
    ambiente = dict(os.environ)
    ambiente["PYTHONHASHSEED"] = "12345"
    ambiente["PYTHONPATH"] = str(BACKEND)
    ambiente.setdefault("ENVIRONMENT", "testing")
    resultado = subprocess.run(
        [sys.executable, "-B", "-c", programa],
        cwd=BACKEND,
        env=ambiente,
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == GOLDEN_CONTENT_SHA256


def test_e71c05_o_hash_nao_depende_do_relogio() -> None:
    """Duas montagens separadas por tempo produzem o mesmo hash.

    A prova de fato é a ausência de leitura de relógio: nenhum campo do
    conteúdo é temporal, e por isso repetir a montagem não pode divergir.
    """
    primeiro = _conteudo().content_sha256()
    segundo = _conteudo().content_sha256()
    assert primeiro == segundo
    assert "sealed_at" not in _conteudo().canonical_json()


# --- sensibilidade campo a campo -------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("envelope_version", "2"),
        ("schedule_id", uuid.UUID("33333333-3333-4333-8333-333333333333")),
        ("step_id", uuid.UUID("44444444-4444-4444-8444-444444444444")),
        ("role", "auditor"),
        ("instruction_ref", "instr://revisao-2"),
        ("context_refs", (ContextRef(uri="art://a", sha256=_HASH_B, bytes=10),)),
        ("expected_output_contract", "contract://parecer-v2"),
        ("constraints", (("idioma", "en-US"), ("limite", "2000"))),
    ],
)
def test_e71c06_alterar_qualquer_campo_altera_o_hash(campo: str, valor: object) -> None:
    assert _conteudo(**{campo: valor}).content_sha256() != GOLDEN_CONTENT_SHA256


def test_e71c07_alterar_apenas_bytes_ou_uri_da_referencia_altera_o_hash() -> None:
    base = _conteudo().content_sha256()
    outro_bytes = _conteudo(
        context_refs=(ContextRef(uri="art://a", sha256=_HASH_A, bytes=11),)
    ).content_sha256()
    outra_uri = _conteudo(
        context_refs=(ContextRef(uri="art://b", sha256=_HASH_A, bytes=10),)
    ).content_sha256()
    assert len({base, outro_bytes, outra_uri}) == 3


def test_e71c08_a_ordem_das_referencias_e_conteudo() -> None:
    """Ordem de `context_refs` não é normalizada: ela é a declaração."""
    uma = _conteudo(
        context_refs=(
            ContextRef(uri="art://a", sha256=_HASH_A, bytes=1),
            ContextRef(uri="art://b", sha256=_HASH_B, bytes=2),
        )
    )
    outra = _conteudo(
        context_refs=(
            ContextRef(uri="art://b", sha256=_HASH_B, bytes=2),
            ContextRef(uri="art://a", sha256=_HASH_A, bytes=1),
        )
    )
    assert uma.content_sha256() != outra.content_sha256()


def test_e71c09_a_ordem_de_digitacao_das_restricoes_nao_altera_o_hash() -> None:
    """Restrições são mapa: canonicalizadas na entrada, não no hash."""
    direta = _conteudo(constraints=(("idioma", "pt-BR"), ("limite", "2000")))
    invertida = _conteudo(constraints=(("limite", "2000"), ("idioma", "pt-BR")))
    mapa = _conteudo(constraints={"limite": "2000", "idioma": "pt-BR"})
    assert direta.content_sha256() == invertida.content_sha256() == mapa.content_sha256()


def test_e71c10_o_json_canonico_e_compacto_e_ordenado() -> None:
    canonico = _conteudo().canonical_json()
    assert ", " not in canonico and '": ' not in canonico
    chaves = list(json.loads(canonico))
    assert chaves == sorted(chaves)


# --- recusa antes da persistência ------------------------------------------


@pytest.mark.parametrize(
    "sha256",
    ["", "abc", _HASH_A.upper(), "g" * 64, "a" * 63, "a" * 65, " " + "a" * 63],
)
def test_e71c11_context_ref_sem_sha256_valido_e_recusado(sha256: str) -> None:
    with pytest.raises(ValueError, match="sha256"):
        ContextRef(uri="art://a", sha256=sha256, bytes=1)


def test_e71c12_context_ref_recusa_uri_vazia_e_bytes_invalido() -> None:
    with pytest.raises(ValueError, match="uri"):
        ContextRef(uri="   ", sha256=_HASH_A, bytes=1)
    with pytest.raises(ValueError, match="bytes"):
        ContextRef(uri="art://a", sha256=_HASH_A, bytes=-1)
    with pytest.raises(ValueError, match="bytes"):
        ContextRef(uri="art://a", sha256=_HASH_A, bytes=True)
    with pytest.raises(ValueError, match="bytes"):
        ContextRef(uri="art://a", sha256=_HASH_A, bytes="10")  # type: ignore[arg-type]


def test_e71c13_referencia_com_chave_a_mais_ou_a_menos_e_recusada() -> None:
    with pytest.raises(ValueError, match="context_ref exige exatamente"):
        parse_context_refs([{"uri": "art://a", "sha256": _HASH_A}])
    with pytest.raises(ValueError, match="context_ref exige exatamente"):
        parse_context_refs([{"uri": "art://a", "sha256": _HASH_A, "bytes": 1, "inline": "x"}])


def test_e71c14_conteudo_embutido_sem_hash_nao_tem_como_ser_declarado() -> None:
    """`INLINE_CONTENT_WITHOUT_HASH = FORBIDDEN` por construção."""
    with pytest.raises(ValueError):
        parse_context_refs([{"uri": "art://a", "sha256": "", "bytes": 0}])
    with pytest.raises(ValueError, match="objeto"):
        parse_context_refs(["conteúdo cru"])


def test_e71c15_restricoes_recusam_duplicata_e_tipo_errado() -> None:
    with pytest.raises(ValueError, match="duplicada"):
        canonical_constraints((("a", "1"), ("a", "2")))
    with pytest.raises(ValueError, match="constraint value"):
        canonical_constraints({"a": 1})
    with pytest.raises(ValueError, match="constraint key"):
        canonical_constraints({"  ": "1"})


def test_e71c16_rascunhos_validam_na_construcao() -> None:
    with pytest.raises(ValueError, match="role"):
        StepDraft(role="", instruction_ref="i", expected_output_contract="c")
    with pytest.raises(ValueError, match="sem etapas"):
        ScheduleDraft(title="t", steps=())
    with pytest.raises(ValueError, match="StepDraft"):
        ScheduleDraft(title="t", steps=("não é etapa",))  # type: ignore[arg-type]


def test_e71c17_o_conteudo_e_congelado_e_hashavel() -> None:
    conteudo = _conteudo()
    with pytest.raises(AttributeError):
        conteudo.role = "outro"  # type: ignore[misc]
    assert hash(conteudo) == hash(_conteudo())
