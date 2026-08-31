"""
Invariantes dos contratos de conformidade (`E4.10`).

```text
CORRECT_FACTORY_OUTPUT != SAFE_PUBLIC_RESULT_CONSTRUCTOR
```

O construtor **direto** de cada value object é exercitado, não apenas o
caminho feliz do avaliador. Um invariante que só vive na fábrica é
contornável por quem chama a classe — lição que o programa pagou pela
última vez na E4.9.9.c.1.
"""

import uuid
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest

from app.core.error_codes import ErrorSeverity
from app.memory.models.compliance_enums import (
    AssessmentInformationState,
    CausalEvidencePresence,
    ComplianceCode,
    ComplianceOutcome,
    ComplianceSubjectKind,
    MissingObservation,
    ObservedOperationState,
    PolicyKind,
    PolicyWindowState,
)
from app.memory.schemas.compliance import (
    CODIGOS_POR_POLITICA,
    SUJEITO_POR_POLITICA,
    ComplianceFinding,
    ComplianceReport,
    ComplianceSubjectRef,
    PolicyReference,
    ReportEvidence,
)

INSTANTE = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
SUJEITO_A = uuid.UUID("00000000-0000-0000-0000-0000000ca001")
SUJEITO_B = uuid.UUID("00000000-0000-0000-0000-0000000ca002")
POLICY_ID = uuid.UUID("00000000-0000-0000-0000-0000000ca003")
DOMINIO = uuid.UUID("00000000-0000-0000-0000-0000000ca004")


def _politica(**overrides: object) -> PolicyReference:
    base: dict[str, object] = {
        "kind": PolicyKind.GOVERNANCE,
        "policy_id": POLICY_ID,
        "policy_key": "gov.leitura",
        "policy_version": 3,
    }
    base.update(overrides)
    return PolicyReference(**base)  # type: ignore[arg-type]


def _sujeito(**overrides: object) -> ComplianceSubjectRef:
    base: dict[str, object] = {
        "kind": ComplianceSubjectKind.GOVERNED_OPERATION,
        "subject_coid": SUJEITO_A,
        "domain_id": DOMINIO,
    }
    base.update(overrides)
    return ComplianceSubjectRef(**base)  # type: ignore[arg-type]


def _finding(**overrides: object) -> ComplianceFinding:
    base: dict[str, object] = {
        "code": ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_AGAINST_DENY,
        "severity": ErrorSeverity.ERROR,
        "subject_ref": _sujeito(),
        "policy_ref": _politica(),
        "policy_version": 3,
        "evaluated_at": INSTANTE,
        "matched_rule_ids": ("r-1",),
    }
    base.update(overrides)
    return ComplianceFinding(**base)  # type: ignore[arg-type]


def _evidencia(**overrides: object) -> ReportEvidence:
    base: dict[str, object] = {
        "policy_window": PolicyWindowState.EFFECTIVE,
        "applicable_rule_ids": ("r-1",),
        "missing_observations": (),
    }
    base.update(overrides)
    return ReportEvidence(**base)  # type: ignore[arg-type]


def _relatorio(**overrides: object) -> ComplianceReport:
    base: dict[str, object] = {
        "outcome": ComplianceOutcome.COMPLIANT,
        "subject_ref": _sujeito(),
        "policy_ref": _politica(),
        "policy_version": 3,
        "evaluated_at": INSTANTE,
        "evidence": _evidencia(),
        "findings": (),
    }
    base.update(overrides)
    return ComplianceReport(**base)  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Vocabulários
# ----------------------------------------------------------------------


def test_u01_o_desfecho_tem_exatamente_quatro_estados():
    assert {membro.value for membro in ComplianceOutcome} == {
        "compliant",
        "policy_not_applicable",
        "insufficient_information",
        "violation_confirmed",
    }


def test_u02_nenhum_vocabulario_tem_membro_coringa():
    """`UNKNOWN`/`OTHER`/`ERROR` absorveriam o caso que ninguém previu."""
    for enumeracao in (
        ComplianceOutcome,
        PolicyKind,
        ComplianceSubjectKind,
        ObservedOperationState,
        CausalEvidencePresence,
        AssessmentInformationState,
        PolicyWindowState,
        MissingObservation,
    ):
        nomes = {membro.name for membro in enumeracao}
        assert not nomes & {"UNKNOWN", "OTHER", "ERROR", "UNSPECIFIED", "NONE"}


def test_u03_os_codigos_ficam_fora_do_catalogo_de_excecoes():
    """`FINDING != EXCEPTION` — herdado literalmente da E3.10."""
    for membro in ComplianceCode:
        assert membro.value.startswith("COMPLIANCE-")
        assert not membro.value.startswith("PIA-")


def test_u04_a_correspondencia_politica_sujeito_e_biunivoca():
    assert set(SUJEITO_POR_POLITICA) == set(PolicyKind)
    assert set(SUJEITO_POR_POLITICA.values()) == set(ComplianceSubjectKind)
    assert len(set(SUJEITO_POR_POLITICA.values())) == len(PolicyKind)


def test_u05_todo_codigo_pertence_a_exatamente_uma_familia():
    todos = [codigo for familia in CODIGOS_POR_POLITICA.values() for codigo in familia]
    assert sorted(todos, key=lambda c: c.value) == sorted(ComplianceCode, key=lambda c: c.value)
    assert len(todos) == len(set(todos))


def test_u06_o_estado_observado_nao_reusa_o_efeito_da_policy():
    """`PRESCRIPTION != FACT` — enums disjuntos, sem valor em comum."""
    from app.memory.models.governance_enums import GovernanceEffect

    assert not {m.value for m in ObservedOperationState} & {m.value for m in GovernanceEffect}


@pytest.mark.parametrize(
    "enumeracao", [ObservedOperationState, CausalEvidencePresence, AssessmentInformationState]
)
def test_u07_toda_observacao_distingue_ausencia_de_nao_observacao(enumeracao):
    """Um booleano não separaria *não aconteceu* de *ninguém olhou*."""
    assert "NOT_OBSERVED" in {membro.name for membro in enumeracao}


# ----------------------------------------------------------------------
# PolicyReference
# ----------------------------------------------------------------------


def test_u08_a_politica_e_identificada_pelas_quatro_dimensoes():
    referencia = _politica()
    assert (referencia.kind, referencia.policy_id, referencia.policy_key) == (
        PolicyKind.GOVERNANCE,
        POLICY_ID,
        "gov.leitura",
    )
    assert referencia.policy_version == 3


def test_u09_a_versao_nao_tem_default():
    """Versão implícita significaria 'a mais recente', e a mais recente muda."""
    with pytest.raises(TypeError):
        PolicyReference(  # type: ignore[call-arg]
            kind=PolicyKind.GOVERNANCE, policy_id=POLICY_ID, policy_key="gov.leitura"
        )


@pytest.mark.parametrize(
    ("campo", "valor", "erro"),
    [
        ("kind", "governance", TypeError),
        ("policy_id", str(POLICY_ID), TypeError),
        ("policy_key", "   ", ValueError),
        ("policy_key", 1, TypeError),
        ("policy_version", "3", TypeError),
        ("policy_version", True, TypeError),
        ("policy_version", 0, ValueError),
    ],
)
def test_u10_a_referencia_recusa_valor_invalido(campo, valor, erro):
    with pytest.raises(erro):
        _politica(**{campo: valor})


def test_u11_a_referencia_e_congelada():
    with pytest.raises(FrozenInstanceError):
        _politica().policy_version = 4  # type: ignore[misc]


# ----------------------------------------------------------------------
# ComplianceSubjectRef
# ----------------------------------------------------------------------


def test_u12_o_sujeito_nao_tem_onde_guardar_conteudo():
    """`NO_LOCATOR · NO_CONTENT` — garantido por ausência de campo."""
    campos = set(ComplianceSubjectRef.__dataclass_fields__)
    assert campos == {"kind", "subject_coid", "domain_id"}


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("kind", "governed_operation"), ("subject_coid", "x"), ("domain_id", "y")],
)
def test_u13_o_sujeito_recusa_tipo_errado(campo, valor):
    with pytest.raises(TypeError):
        _sujeito(**{campo: valor})


def test_u14_o_dominio_e_opcional_no_sujeito_projetado():
    assert _sujeito(domain_id=None).domain_id is None


# ----------------------------------------------------------------------
# ComplianceFinding
# ----------------------------------------------------------------------


def test_u15_o_finding_carrega_a_identidade_completa_da_avaliacao():
    finding = _finding()
    assert finding.policy_version == finding.policy_ref.policy_version
    assert finding.evaluated_at == INSTANTE
    assert finding.subject_ref == _sujeito()


def test_u16_o_finding_nao_pode_citar_duas_versoes():
    with pytest.raises(ValueError, match="não pode citar duas versões"):
        _finding(policy_version=4)


def test_u17_o_finding_recusa_codigo_de_outra_familia():
    """Um código de acessibilidade num relatório de governança citaria
    uma regra que a política avaliada não tem."""
    with pytest.raises(ValueError, match="não pertence à família"):
        _finding(code=ComplianceCode.ACCESSIBILITY_TRANSITION_AGAINST_DENY)


def test_u18_o_finding_recusa_sujeito_incompativel():
    with pytest.raises(ValueError, match="incompatível com política"):
        _finding(subject_ref=_sujeito(kind=ComplianceSubjectKind.RETENTION_CANDIDATE))


def test_u19_o_instante_ingenuo_e_recusado():
    with pytest.raises(ValueError, match="timezone-aware"):
        _finding(evaluated_at=datetime(2026, 8, 19, 12, 0))


def test_u20_o_instante_e_canonicalizado_para_utc():
    """Dois instantes iguais em fusos diferentes dão o mesmo diagnóstico."""
    outro = INSTANTE.astimezone(UTC) + timedelta(0)
    deslocado = INSTANTE.replace(tzinfo=UTC).astimezone(
        __import__("datetime").timezone(timedelta(hours=-3))
    )
    assert _finding(evaluated_at=deslocado) == _finding(evaluated_at=outro)


def test_u21_codigo_textual_equivalente_nao_e_membro():
    with pytest.raises(TypeError, match="ComplianceCode"):
        _finding(code="COMPLIANCE-GOV-001")


def test_u22_severidade_de_outro_vocabulario_e_recusada():
    with pytest.raises(TypeError, match="ErrorSeverity"):
        _finding(severity="error")


@pytest.mark.parametrize("colecao", [list, set])
def test_u23_regras_casadas_exigem_tupla(colecao):
    with pytest.raises(TypeError, match="tuple"):
        _finding(matched_rule_ids=colecao(["r-1"]))


def test_u24_identificador_de_regra_vazio_e_recusado():
    with pytest.raises(ValueError, match="matched_rule_ids"):
        _finding(matched_rule_ids=("  ",))


def test_u25_a_ordenacao_do_finding_e_deterministica():
    assert _finding().sort_key() == (
        "COMPLIANCE-GOV-001",
        str(SUJEITO_A),
    )


def test_u26_o_finding_nao_tem_campo_de_conteudo():
    campos = set(ComplianceFinding.__dataclass_fields__)
    assert not campos & {"evidence", "payload", "content", "locator", "message"}


# ----------------------------------------------------------------------
# ReportEvidence
# ----------------------------------------------------------------------


def test_u27_a_observacao_faltante_e_vocabulario_fechado():
    with pytest.raises(TypeError, match="MissingObservation"):
        _evidencia(missing_observations=("anchor_timestamp",))


def test_u28_regra_aplicavel_repetida_e_recusada():
    with pytest.raises(ValueError, match="applicable_rule_ids repetido"):
        _evidencia(applicable_rule_ids=("r-1", "r-1"))


def test_u29_observacao_faltante_repetida_e_recusada():
    with pytest.raises(ValueError, match="missing_observations repetido"):
        _evidencia(
            missing_observations=(
                MissingObservation.ANCHOR_TIMESTAMP,
                MissingObservation.ANCHOR_TIMESTAMP,
            )
        )


def test_u30_a_janela_e_tipada():
    with pytest.raises(TypeError, match="PolicyWindowState"):
        _evidencia(policy_window="effective")


# ----------------------------------------------------------------------
# Invariantes do relatório — a matriz fechada
# ----------------------------------------------------------------------


def test_u31_compliant_exige_zero_findings():
    with pytest.raises(ValueError, match="não admite finding"):
        _relatorio(outcome=ComplianceOutcome.COMPLIANT, findings=(_finding(),))


def test_u32_compliant_exige_regra_avaliada():
    """Conformidade sem regra seria indistinguível de nada ter sido olhado."""
    with pytest.raises(ValueError, match="compliant exige applicable_rule_ids"):
        _relatorio(evidence=_evidencia(applicable_rule_ids=()))


def test_u33_policy_not_applicable_exige_zero_findings():
    with pytest.raises(ValueError, match="não admite finding"):
        _relatorio(
            outcome=ComplianceOutcome.POLICY_NOT_APPLICABLE,
            evidence=_evidencia(applicable_rule_ids=()),
            findings=(_finding(),),
        )


def test_u34_policy_not_applicable_exige_zero_regras_aplicaveis():
    """Se alguma regra alcança o sujeito, a política se aplica."""
    with pytest.raises(ValueError, match="não admite applicable_rule_ids"):
        _relatorio(outcome=ComplianceOutcome.POLICY_NOT_APPLICABLE)


def test_u35_insufficient_information_exige_o_que_falta():
    with pytest.raises(ValueError, match="exige missing_observations"):
        _relatorio(
            outcome=ComplianceOutcome.INSUFFICIENT_INFORMATION,
            evidence=_evidencia(applicable_rule_ids=()),
        )


def test_u36_insufficient_information_exige_zero_findings():
    with pytest.raises(ValueError, match="não admite finding"):
        _relatorio(
            outcome=ComplianceOutcome.INSUFFICIENT_INFORMATION,
            evidence=_evidencia(
                applicable_rule_ids=(),
                missing_observations=(MissingObservation.ANCHOR_TIMESTAMP,),
            ),
            findings=(_finding(),),
        )


@pytest.mark.parametrize(
    "desfecho", [ComplianceOutcome.COMPLIANT, ComplianceOutcome.POLICY_NOT_APPLICABLE]
)
def test_u37_nenhum_desfecho_decidido_admite_observacao_faltante(desfecho):
    """`INSUFFICIENT_INFORMATION` nunca vira `COMPLIANT`.

    O mesmo par de valores não satisfaz os dois desfechos: um exige
    `missing_observations` não vazio, o outro exige vazio.
    """
    with pytest.raises(ValueError, match="não admite missing_observations"):
        _relatorio(
            outcome=desfecho,
            evidence=_evidencia(
                applicable_rule_ids=(
                    () if desfecho is ComplianceOutcome.POLICY_NOT_APPLICABLE else ("r-1",)
                ),
                missing_observations=(MissingObservation.ANCHOR_TIMESTAMP,),
            ),
        )


def test_u38_violation_confirmed_exige_pelo_menos_um_finding():
    with pytest.raises(ValueError, match="exige ao menos um finding"):
        _relatorio(outcome=ComplianceOutcome.VIOLATION_CONFIRMED)


def test_u39_violation_confirmed_valido():
    relatorio = _relatorio(outcome=ComplianceOutcome.VIOLATION_CONFIRMED, findings=(_finding(),))
    assert relatorio.violation_codes == (ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_AGAINST_DENY,)


# ----------------------------------------------------------------------
# Vínculo exato de cada finding
# ----------------------------------------------------------------------


def test_u40_finding_de_outro_sujeito_e_recusado():
    with pytest.raises(ValueError, match="descreve outro sujeito"):
        _relatorio(
            outcome=ComplianceOutcome.VIOLATION_CONFIRMED,
            findings=(_finding(subject_ref=_sujeito(subject_coid=SUJEITO_B)),),
        )


def test_u41_finding_de_outra_politica_e_recusado():
    outra = _politica(policy_id=uuid.uuid4())
    with pytest.raises(ValueError, match="cita outra política"):
        _relatorio(
            outcome=ComplianceOutcome.VIOLATION_CONFIRMED,
            findings=(_finding(policy_ref=outra),),
        )


def test_u42_finding_de_outra_versao_e_recusado():
    """A versão é o que dá sentido ao diagnóstico."""
    outra = _politica(policy_version=4)
    with pytest.raises(ValueError, match="cita a versão"):
        _relatorio(
            outcome=ComplianceOutcome.VIOLATION_CONFIRMED,
            findings=(_finding(policy_ref=outra, policy_version=4),),
        )


def test_u43_finding_de_outro_instante_e_recusado():
    """Duas datas descrevem duas avaliações."""
    with pytest.raises(ValueError, match="instante diferente"):
        _relatorio(
            outcome=ComplianceOutcome.VIOLATION_CONFIRMED,
            findings=(_finding(evaluated_at=INSTANTE + timedelta(seconds=1)),),
        )


def test_u44_o_relatorio_recusa_versao_divergente_da_referencia():
    with pytest.raises(ValueError, match="policy_version diverge"):
        _relatorio(policy_version=4)


def test_u45_o_relatorio_recusa_sujeito_incompativel():
    with pytest.raises(ValueError, match="incompatível com política"):
        _relatorio(subject_ref=_sujeito(kind=ComplianceSubjectKind.RETENTION_CANDIDATE))


# ----------------------------------------------------------------------
# Ordem canônica e determinismo
# ----------------------------------------------------------------------


def test_u46_findings_fora_de_ordem_sao_recusados():
    primeiro = _finding(code=ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_AGAINST_DENY)
    segundo = _finding(
        code=ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_WITHOUT_RULE, matched_rule_ids=()
    )
    with pytest.raises(ValueError, match="fora da ordem canônica"):
        _relatorio(outcome=ComplianceOutcome.VIOLATION_CONFIRMED, findings=(segundo, primeiro))


def test_u47_findings_em_ordem_canonica_sao_aceitos():
    primeiro = _finding(code=ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_AGAINST_DENY)
    segundo = _finding(
        code=ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_WITHOUT_RULE, matched_rule_ids=()
    )
    relatorio = _relatorio(
        outcome=ComplianceOutcome.VIOLATION_CONFIRMED, findings=(primeiro, segundo)
    )
    assert relatorio.violation_codes == (primeiro.code, segundo.code)


def test_u48_finding_repetido_e_recusado():
    with pytest.raises(ValueError, match="finding repetido"):
        _relatorio(
            outcome=ComplianceOutcome.VIOLATION_CONFIRMED,
            findings=(_finding(), _finding()),
        )


def test_u49_o_relatorio_e_determinístico_por_igualdade_estrutural():
    assert _relatorio() == _relatorio()


def test_u50_colecao_mutavel_de_findings_e_recusada():
    with pytest.raises(TypeError, match="findings deve ser tuple"):
        _relatorio(findings=[])


def test_u51_finding_de_outro_tipo_e_recusado():
    with pytest.raises(TypeError, match=r"findings\[0\]"):
        _relatorio(outcome=ComplianceOutcome.VIOLATION_CONFIRMED, findings=("violado",))


def test_u52_replace_no_relatorio_revalida():
    """`dataclasses.replace` passa pelo `__post_init__` — não é bypass."""
    with pytest.raises(ValueError, match="exige ao menos um finding"):
        replace(_relatorio(), outcome=ComplianceOutcome.VIOLATION_CONFIRMED)


# ----------------------------------------------------------------------
# Tipos exatos e confidencialidade
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("outcome", "compliant"),
        ("subject_ref", "sujeito"),
        ("policy_ref", "politica"),
        ("evidence", {"policy_window": "effective"}),
        ("policy_version", "3"),
        ("policy_version", True),
    ],
)
def test_u53_o_relatorio_recusa_tipo_errado(campo, valor):
    with pytest.raises(TypeError):
        _relatorio(**{campo: valor})


def test_u54_o_relatorio_e_congelado():
    with pytest.raises(FrozenInstanceError):
        _relatorio().outcome = ComplianceOutcome.VIOLATION_CONFIRMED  # type: ignore[misc]


def test_u55_o_instante_ingenuo_do_relatorio_e_recusado():
    with pytest.raises(ValueError, match="timezone-aware"):
        _relatorio(evaluated_at=datetime(2026, 8, 19, 12, 0))


def test_u56_nenhuma_representacao_expoe_material_sensivel():
    """Redação medida em `repr` e `str`, com marcador real."""
    marcador = "SEGREDO-COMPLIANCE-91af"
    relatorio = _relatorio(
        outcome=ComplianceOutcome.VIOLATION_CONFIRMED,
        findings=(_finding(matched_rule_ids=(f"regra-{marcador}",)),),
    )
    # O identificador de regra é opaco e legítimo; o que não pode
    # aparecer é conteúdo, localizador ou capacidade — e não há campo.
    for texto in (repr(relatorio), str(relatorio)):
        for proibido in ("s3://", "file://", "capability", "payload", "transcript"):
            assert proibido not in texto


def test_u57_o_relatorio_nao_tem_score_nem_percentual():
    """A E3.10 congelou que '97% de conformidade' não significaria nada."""
    atributos = set(dir(ComplianceReport))
    assert not atributos & {"score", "percentage", "ratio", "compliance_level"}


def test_u58_o_relatorio_nao_persiste_nem_tem_identidade_cognitiva():
    campos = set(ComplianceReport.__dataclass_fields__)
    assert not campos & {"id", "coid", "clid", "lifecycle_state", "created_at"}
    assert not hasattr(ComplianceReport, "__tablename__")
    assert not hasattr(ComplianceFinding, "__tablename__")


# ----------------------------------------------------------------------
# Tipos exatos no construtor do finding e da evidência
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor", "erro"),
    [
        ("subject_ref", "sujeito", TypeError),
        ("policy_ref", "politica", TypeError),
        ("policy_version", "3", TypeError),
        ("policy_version", True, TypeError),
        ("evaluated_at", "2026-08-19", TypeError),
    ],
)
def test_u59_o_finding_recusa_tipo_errado(campo, valor, erro):
    with pytest.raises(erro):
        _finding(**{campo: valor})


@pytest.mark.parametrize("campo", ["applicable_rule_ids", "missing_observations"])
def test_u60_a_evidencia_exige_tupla(campo):
    with pytest.raises(TypeError, match="deve ser tuple"):
        _evidencia(**{campo: ["x"]})


def test_u61_violation_confirmed_admite_observacao_faltante_junto():
    """Insuficiência parcial não apaga violação já localizada.

    O ramo existe porque uma avaliação pode ter observado o bastante
    para confirmar uma violação e ainda assim não ter observado tudo —
    e o relatório precisa dizer as duas coisas sem que uma anule a
    outra.
    """
    relatorio = _relatorio(
        outcome=ComplianceOutcome.VIOLATION_CONFIRMED,
        evidence=_evidencia(missing_observations=(MissingObservation.CAUSAL_EVIDENCE,)),
        findings=(_finding(),),
    )
    assert relatorio.evidence.missing_observations == (MissingObservation.CAUSAL_EVIDENCE,)
    assert len(relatorio.findings) == 1


def test_u62_insufficient_information_valido_e_construtivel():
    """O desfecho existe e é representável — o ramo que retorna limpo."""
    relatorio = _relatorio(
        outcome=ComplianceOutcome.INSUFFICIENT_INFORMATION,
        evidence=_evidencia(
            applicable_rule_ids=(),
            missing_observations=(MissingObservation.ANCHOR_TIMESTAMP,),
        ),
    )
    assert relatorio.outcome is ComplianceOutcome.INSUFFICIENT_INFORMATION
    assert relatorio.findings == ()
    assert relatorio.violation_codes == ()
