"""
Invariantes dos contratos de experiência validada (`E4.11`).

```text
CORRECT_FACTORY_OUTPUT != SAFE_PUBLIC_RESULT_CONSTRUCTOR
```

O construtor **direto** de cada value object é exercitado, não apenas o
caminho feliz do repositório. Um invariante que só vive na fábrica é
contornável por quem chama a classe.
"""

import uuid
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.memory.models.validated_experience_enums import (
    CriterionOriginKind,
    EvidenceKind,
    ExperienceSubjectKind,
    ValidatorKind,
)
from app.memory.schemas.validated_experience import (
    MAX_TOKEN_LENGTH,
    AttributedValidator,
    CriterionReference,
    EvidenceReference,
    ExperienceSubjectRef,
    ObservedOutcome,
    OriginAttribution,
    ValidatedExperienceAppend,
    validar_token_de_resultado,
)

AGORA = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)
SUJEITO = uuid.UUID("00000000-0000-0000-0000-0000000ae001")
EVIDENCIA_A = uuid.UUID("00000000-0000-0000-0000-0000000ae002")
EVIDENCIA_B = uuid.UUID("00000000-0000-0000-0000-0000000ae003")
ORIGEM = uuid.UUID("00000000-0000-0000-0000-0000000ae004")
EXPERIENCIA = uuid.UUID("00000000-0000-0000-0000-0000000ae005")

MARCADOR = "SEGREDO-VALIDADOR-7c1a"


def _evidencia(**overrides: object) -> EvidenceReference:
    base: dict[str, object] = {"kind": EvidenceKind.CAUSAL_EVENT, "ref": EVIDENCIA_A}
    base.update(overrides)
    return EvidenceReference(**base)  # type: ignore[arg-type]


def _resultado(**overrides: object) -> ObservedOutcome:
    base: dict[str, object] = {
        "outcome_token": "produced",
        "observed_at": AGORA,
        "primary_evidence_ref": _evidencia(),
    }
    base.update(overrides)
    return ObservedOutcome(**base)  # type: ignore[arg-type]


def _validador(**overrides: object) -> AttributedValidator:
    base: dict[str, object] = {
        "validator_kind": ValidatorKind.HUMAN,
        "validator_ref": "humano:ana",
    }
    base.update(overrides)
    return AttributedValidator(**base)  # type: ignore[arg-type]


def _criterio(**overrides: object) -> CriterionReference:
    base: dict[str, object] = {
        "criterion_key": "crit.transformacao.fidelidade",
        "criterion_version": 3,
        "criterion_origin": CriterionOriginKind.PUBLISHED,
    }
    base.update(overrides)
    return CriterionReference(**base)  # type: ignore[arg-type]


def _append(**overrides: object) -> ValidatedExperienceAppend:
    base: dict[str, object] = {
        "experience_id": EXPERIENCIA,
        "subject_ref": ExperienceSubjectRef(kind=ExperienceSubjectKind.CAUSAL_EVENT, ref=SUJEITO),
        "outcome_observed": _resultado(),
        "validated_by": _validador(),
        "criterion_ref": _criterio(),
        "evidence_refs": (_evidencia(),),
        "validated_at": AGORA,
        "origin": OriginAttribution(origin_ref=ORIGEM),
    }
    base.update(overrides)
    return ValidatedExperienceAppend(**base)  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Vocabulários — o que NÃO existe é a garantia
# ----------------------------------------------------------------------


def test_u01_nenhum_vocabulario_tem_membro_coringa():
    for enumeracao in (
        ExperienceSubjectKind,
        ValidatorKind,
        EvidenceKind,
        CriterionOriginKind,
    ):
        nomes = {membro.name for membro in enumeracao}
        assert not nomes & {"UNKNOWN", "OTHER", "ERROR", "UNSPECIFIED", "NONE"}


def test_u02_nenhum_vocabulario_expressa_grau_ou_julgamento():
    """`NO_SCORE · NO_CONFIDENCE · NO_WEIGHT` — nem como membro de enum."""
    proibidos = {"HIGH", "LOW", "MEDIUM", "STRONG", "WEAK", "SUCCESS", "FAILURE"}
    for enumeracao in (ExperienceSubjectKind, ValidatorKind, EvidenceKind, CriterionOriginKind):
        assert not {membro.name for membro in enumeracao} & proibidos


def test_u03_o_sujeito_distingue_objeto_de_evento():
    """`SAME_UUID_DIFFERENT_UNIVERSE` — o discriminador é indispensável."""
    assert {membro.value for membro in ExperienceSubjectKind} == {
        "cognitive_object",
        "causal_event",
    }


# ----------------------------------------------------------------------
# Token de resultado — gramática fechada
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "token", ["produced", "not_produced", "diverged", "a", "x1.y2-z3_w4", "a" * MAX_TOKEN_LENGTH]
)
def test_u04_a_gramatica_aceita_token_bem_formado(token):
    assert validar_token_de_resultado("outcome_token", token) == token


@pytest.mark.parametrize(
    "token",
    [
        "Produced",
        "o resultado foi produzido",
        "produced!",
        "produção",
        "_produced",
        "1produced",
        "produced-",
        "produced..x",
        "",
        "a" * (MAX_TOKEN_LENGTH + 1),
    ],
)
def test_u05_a_gramatica_recusa_texto_livre(token):
    """Um campo que aceita frase vira campo de julgamento."""
    with pytest.raises(ValueError):
        validar_token_de_resultado("outcome_token", token)


def test_u06_o_token_nao_e_normalizado():
    """Devolve o valor original — sem `strip`, sem `casefold`."""
    assert validar_token_de_resultado("t", "a.b-c_d") == "a.b-c_d"


def test_u07_token_nao_textual_e_recusado():
    with pytest.raises(TypeError, match="deve ser str"):
        validar_token_de_resultado("outcome_token", 1)


def test_u08_nao_existe_enum_universal_de_resultado():
    """O token é lido contra o critério; congelar uma taxonomia aqui a
    imporia a experiências que ainda não existem."""
    import app.memory.models.validated_experience_enums as vocabularios

    assert not hasattr(vocabularios, "ObservedOutcomeKind")
    assert not hasattr(vocabularios, "ValidatedOutcomeToken")


# ----------------------------------------------------------------------
# EvidenceReference
# ----------------------------------------------------------------------


def test_u09_a_evidencia_nao_tem_onde_guardar_localizador():
    """`UUID_HAS_NOWHERE_TO_PUT_A_URL` — garantia do tipo, não de vigilância."""
    campos = set(EvidenceReference.__dataclass_fields__)
    assert campos == {"kind", "ref"}
    assert EvidenceReference.__dataclass_fields__["ref"].type in ("uuid.UUID", uuid.UUID)


@pytest.mark.parametrize(
    "valor",
    [
        "file:///etc/passwd",
        "https://exemplo/segredo",
        "/home/user/transcript.txt",
        str(EVIDENCIA_A),
    ],
)
def test_u10_a_evidencia_recusa_qualquer_texto(valor):
    """Inclusive um UUID em texto: `STRING_EQUIVALENT != UUID`."""
    with pytest.raises(TypeError, match="ref deve ser UUID"):
        _evidencia(ref=valor)


def test_u11_a_evidencia_recusa_kind_textual():
    with pytest.raises(TypeError, match="EvidenceKind"):
        _evidencia(kind="causal_event")


def test_u12_a_ordenacao_da_evidencia_e_deterministica():
    assert _evidencia().sort_key() == ("causal_event", str(EVIDENCIA_A))


# ----------------------------------------------------------------------
# ObservedOutcome
# ----------------------------------------------------------------------


def test_u13_o_resultado_nao_tem_campo_de_score_nem_conteudo():
    campos = set(ObservedOutcome.__dataclass_fields__)
    assert campos == {"outcome_token", "observed_at", "primary_evidence_ref"}
    assert not campos & {"score", "confidence", "weight", "content", "recommendation"}


def test_u14_o_instante_observado_e_canonicalizado():
    deslocado = AGORA.astimezone(timezone(timedelta(hours=-3)))
    assert _resultado(observed_at=deslocado) == _resultado()


def test_u15_instante_ingenuo_e_recusado():
    with pytest.raises(ValueError, match="timezone-aware"):
        _resultado(observed_at=datetime(2026, 8, 19, 14, 0))


def test_u16_a_evidencia_primaria_e_tipada():
    with pytest.raises(TypeError, match="primary_evidence_ref"):
        _resultado(primary_evidence_ref=str(EVIDENCIA_A))


# ----------------------------------------------------------------------
# AttributedValidator — atribuição, nunca autenticação
# ----------------------------------------------------------------------


def test_u17_o_validador_nao_tem_campo_de_autenticacao():
    """`ATTRIBUTED = YES · AUTHENTICATED = NO`."""
    campos = set(AttributedValidator.__dataclass_fields__)
    assert campos == {"validator_kind", "validator_ref"}
    assert not campos & {"authenticated", "verified", "signature", "token", "credential"}


def test_u18_a_referencia_do_validador_nao_vaza_em_repr():
    validador = _validador(validator_ref=f"humano:{MARCADOR}")
    for texto in (repr(validador), str(validador)):
        assert MARCADOR not in texto
        assert "human" in texto


def test_u19_o_validador_recusa_caractere_de_controle():
    with pytest.raises(ValueError, match="caractere de controle"):
        _validador(validator_ref="humano:\nana")


def test_u20_o_validador_recusa_referencia_vazia():
    with pytest.raises(ValueError, match="vazio ou apenas espaços"):
        _validador(validator_ref="   ")


def test_u21_o_validador_recusa_kind_textual():
    with pytest.raises(TypeError, match="ValidatorKind"):
        _validador(validator_kind="human")


# ----------------------------------------------------------------------
# CriterionReference
# ----------------------------------------------------------------------


def test_u22_o_criterio_exige_chave_versao_e_origem():
    campos = set(CriterionReference.__dataclass_fields__)
    assert campos == {"criterion_key", "criterion_version", "criterion_origin"}


def test_u23_a_versao_do_criterio_nao_tem_default():
    """Versão implícita significaria 'a mais recente', e a mais recente muda."""
    with pytest.raises(TypeError):
        CriterionReference(  # type: ignore[call-arg]
            criterion_key="crit.x", criterion_origin=CriterionOriginKind.PUBLISHED
        )


@pytest.mark.parametrize(
    ("campo", "valor", "erro"),
    [
        ("criterion_key", "  ", ValueError),
        ("criterion_key", 1, TypeError),
        ("criterion_version", "3", TypeError),
        ("criterion_version", True, TypeError),
        ("criterion_version", 0, ValueError),
        ("criterion_origin", "published", TypeError),
    ],
)
def test_u24_o_criterio_recusa_valor_invalido(campo, valor, erro):
    with pytest.raises(erro):
        _criterio(**{campo: valor})


# ----------------------------------------------------------------------
# OriginAttribution
# ----------------------------------------------------------------------


def test_u25_a_origem_nao_persiste_localidade():
    """`ORIGIN_LOCALITY_PERSISTED = NO` — 'local' é relativo a quem lê."""
    campos = set(OriginAttribution.__dataclass_fields__)
    assert campos == {"origin_ref"}
    assert not campos & {"is_local", "local", "installation_is_local", "authenticated"}


def test_u26_a_origem_recusa_texto():
    with pytest.raises(TypeError, match="origin_ref deve ser UUID"):
        OriginAttribution(origin_ref=str(ORIGEM))


# ----------------------------------------------------------------------
# ValidatedExperienceAppend — o vínculo em seis partes
# ----------------------------------------------------------------------


def test_u27_o_append_reune_o_vinculo_completo():
    campos = set(ValidatedExperienceAppend.__dataclass_fields__)
    assert {
        "subject_ref",
        "outcome_observed",
        "validated_by",
        "criterion_ref",
        "evidence_refs",
        "validated_at",
    } <= campos


def test_u28_a_identidade_entra_no_contrato_de_append():
    """A idempotência é por identidade; o chamador precisa fornecê-la."""
    assert "experience_id" in ValidatedExperienceAppend.__dataclass_fields__
    assert _append().experience_id == EXPERIENCIA


@pytest.mark.parametrize(
    "campo",
    [
        "experience_id",
        "subject_ref",
        "outcome_observed",
        "validated_by",
        "criterion_ref",
        "evidence_refs",
        "validated_at",
        "origin",
    ],
)
def test_u29_nenhum_campo_do_append_tem_default(campo):
    import dataclasses

    definicao = ValidatedExperienceAppend.__dataclass_fields__[campo]
    assert definicao.default is dataclasses.MISSING
    assert definicao.default_factory is dataclasses.MISSING


def test_u30_evidencia_vazia_e_recusada():
    """`EXPERIENCE -> EVIDENCE -> VALIDATION` — sem lastro não há validação."""
    with pytest.raises(ValueError, match="não pode ser vazia"):
        _append(evidence_refs=())


@pytest.mark.parametrize("colecao", [list, set])
def test_u31_evidencia_exige_tupla(colecao):
    with pytest.raises(TypeError, match="tuple"):
        _append(evidence_refs=colecao([_evidencia()]))


def test_u32_evidencia_repetida_e_recusada():
    with pytest.raises(ValueError, match="repetida"):
        _append(evidence_refs=(_evidencia(), _evidencia()))


def test_u33_evidencia_fora_de_ordem_canonica_e_recusada():
    primeira = _evidencia(kind=EvidenceKind.CAUSAL_EVENT, ref=EVIDENCIA_A)
    segunda = _evidencia(kind=EvidenceKind.PROVENANCE_RECORD, ref=EVIDENCIA_B)
    with pytest.raises(ValueError, match="ordem canônica"):
        _append(
            evidence_refs=(segunda, primeira),
            outcome_observed=_resultado(primary_evidence_ref=primeira),
        )


def test_u34_evidencia_em_ordem_canonica_e_aceita():
    primeira = _evidencia(kind=EvidenceKind.CAUSAL_EVENT, ref=EVIDENCIA_A)
    segunda = _evidencia(kind=EvidenceKind.PROVENANCE_RECORD, ref=EVIDENCIA_B)
    entrada = _append(evidence_refs=(primeira, segunda))
    assert entrada.evidence_refs == (primeira, segunda)


def test_u35_a_evidencia_primaria_precisa_estar_no_lastro():
    """Sem isso, o resultado citaria um artefato fora do lastro declarado."""
    fora = _evidencia(kind=EvidenceKind.PROVENANCE_RECORD, ref=EVIDENCIA_B)
    with pytest.raises(ValueError, match="não está em evidence_refs"):
        _append(outcome_observed=_resultado(primary_evidence_ref=fora))


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("experience_id", str(EXPERIENCIA)),
        ("subject_ref", "sujeito"),
        ("outcome_observed", "produced"),
        ("validated_by", "ana"),
        ("criterion_ref", "crit.x"),
        ("origin", str(ORIGEM)),
        ("validated_at", "2026-08-19"),
    ],
)
def test_u36_o_append_recusa_tipo_errado(campo, valor):
    with pytest.raises(TypeError):
        _append(**{campo: valor})


def test_u37_instante_de_validacao_ingenuo_e_recusado():
    with pytest.raises(ValueError, match="timezone-aware"):
        _append(validated_at=datetime(2026, 8, 19, 14, 0))


def test_u38_o_append_e_congelado():
    with pytest.raises(FrozenInstanceError):
        _append().validated_at = AGORA  # type: ignore[misc]


def test_u39_replace_no_append_revalida():
    """`dataclasses.replace` passa pelo `__post_init__` — não é bypass."""
    with pytest.raises(ValueError, match="não pode ser vazia"):
        replace(_append(), evidence_refs=())


def test_u40_o_append_e_deterministico_por_igualdade_estrutural():
    assert _append() == _append()


# ----------------------------------------------------------------------
# Ausência de aprendizado — medida no contrato
# ----------------------------------------------------------------------


def test_u41_nenhum_contrato_tem_campo_de_inferencia():
    """`NO_SCORE · NO_GENERALIZATION · NO_RECOMMENDATION`."""
    proibidos = {
        "score",
        "confidence",
        "weight",
        "rank",
        "ranking",
        "priority",
        "recommendation",
        "generalization",
        "proves",
        "prediction",
    }
    for classe in (
        ExperienceSubjectRef,
        EvidenceReference,
        ObservedOutcome,
        AttributedValidator,
        CriterionReference,
        OriginAttribution,
        ValidatedExperienceAppend,
    ):
        assert not set(classe.__dataclass_fields__) & proibidos, classe.__name__


def test_u42_nenhum_contrato_tem_campo_de_conteudo():
    proibidos = {"content", "payload", "transcript", "body", "text", "locator", "url", "path"}
    for classe in (
        EvidenceReference,
        ObservedOutcome,
        AttributedValidator,
        ValidatedExperienceAppend,
    ):
        assert not set(classe.__dataclass_fields__) & proibidos, classe.__name__


def test_u43_nenhuma_representacao_expoe_material_sensivel():
    entrada = _append(validated_by=_validador(validator_ref=f"agente:{MARCADOR}"))
    for texto in (repr(entrada), str(entrada)):
        assert MARCADOR not in texto
        for proibido in ("file://", "https://", "capability", "transcript"):
            assert proibido not in texto


def test_u44_o_sujeito_recusa_tipo_errado():
    with pytest.raises(TypeError, match="ExperienceSubjectKind"):
        ExperienceSubjectRef(kind="causal_event", ref=SUJEITO)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ref deve ser UUID"):
        ExperienceSubjectRef(kind=ExperienceSubjectKind.CAUSAL_EVENT, ref=str(SUJEITO))


def test_u45_referencia_opaca_longa_demais_e_recusada():
    from app.memory.schemas.validated_experience import MAX_REF_LENGTH

    with pytest.raises(ValueError, match="excede"):
        _validador(validator_ref="a" * (MAX_REF_LENGTH + 1))


def test_u46_item_de_evidencia_de_outro_tipo_e_recusado():
    with pytest.raises(TypeError, match=r"evidence_refs\[0\]"):
        _append(evidence_refs=(str(EVIDENCIA_A),))


def test_u47_validacao_anterior_a_observacao_e_recusada_no_dominio():
    """`DB_CHECK_CONSTRAINT != DOMAIN_BOUNDARY_VALIDATION`."""
    with pytest.raises(ValueError, match="observed_at posterior"):
        _append(
            outcome_observed=_resultado(observed_at=AGORA + timedelta(seconds=1)),
            validated_at=AGORA,
        )
