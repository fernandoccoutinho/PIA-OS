"""
As três matrizes concretas de conformidade (`E4.10`).

```text
GOVERNANCE    ação observada  × permissão declarada
ACCESSIBILITY aresta exata    × transição permitida
RETENTION     elegibilidade   × avaliação exigida
```

Cada linha da matriz do plano tem teste próprio, e as linhas que
**não** são violação são medidas com o mesmo rigor das que são: um
avaliador que só acertasse as violações produziria falso positivo em
tudo o que é legítimo.
"""

import uuid
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
from app.memory.models.governance_enums import CognitiveOperation, GovernanceEffect
from app.memory.models.retention_enums import RetentionScopeKind
from app.memory.models.target_resolution_enums import LegacyProtectionState
from app.memory.schemas.accessibility import AccessibilityRule
from app.memory.schemas.governance import GovernanceRule
from app.memory.schemas.retention import RetentionRule
from app.memory.services.compliance_evaluator import (
    AccessibilityStateObservation,
    ComplianceSubject,
    EvaluatedPolicy,
    GovernedOperationObservation,
    RetentionAgeObservation,
    avaliar_conformidade,
)

AGORA = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
SUJEITO = uuid.UUID("00000000-0000-0000-0000-0000000ce001")
DOMINIO = uuid.UUID("00000000-0000-0000-0000-0000000ce002")
OUTRO_DOMINIO = uuid.UUID("00000000-0000-0000-0000-0000000ce003")
POLICY_ID = uuid.UUID("00000000-0000-0000-0000-0000000ce004")


# ----------------------------------------------------------------------
# Construtores
# ----------------------------------------------------------------------


def politica(
    kind: PolicyKind,
    regras: tuple[object, ...],
    *,
    versao: int = 3,
    inicio: datetime | None = None,
    fim: datetime | None = None,
) -> EvaluatedPolicy:
    return EvaluatedPolicy(
        kind=kind,
        policy_id=POLICY_ID,
        policy_key=f"{kind.value}.principal",
        policy_version=versao,
        effective_from=inicio or AGORA - timedelta(days=30),
        effective_until=fim,
        rules=regras,  # type: ignore[arg-type]
    )


def sujeito(kind: ComplianceSubjectKind, *, dominio: uuid.UUID | None = DOMINIO):
    return ComplianceSubject(kind=kind, subject_coid=SUJEITO, domain_id=dominio)


def regra_gov(
    identificador: str,
    efeito: GovernanceEffect,
    *,
    operacoes: frozenset | None = None,
    dominios: frozenset | None = None,
    atores: frozenset | None = None,
) -> GovernanceRule:
    return GovernanceRule(
        rule_id=identificador,
        effect=efeito,
        operations=operacoes if operacoes is not None else frozenset({CognitiveOperation.READ}),
        domain_ids=dominios if dominios is not None else frozenset(),
        actor_refs=atores if atores is not None else frozenset(),
        purposes=frozenset(),
    )


def regra_acc(
    identificador: str, efeito: GovernanceEffect, origem: str, destino: str
) -> AccessibilityRule:
    return AccessibilityRule(
        rule_id=identificador,
        effect=efeito,
        source_states=frozenset({origem}),
        target_states=frozenset({destino}),
    )


def regra_ret(identificador: str, dias: int, *, dominios: frozenset | None = None):
    if dominios is None:
        return RetentionRule(
            rule_id=identificador,
            scope_kind=RetentionScopeKind.ALL_LOCAL_PATRIMONY,
            minimum_age_days=dias,
        )
    return RetentionRule(
        rule_id=identificador,
        scope_kind=RetentionScopeKind.MEMORY_DOMAIN_SET,
        minimum_age_days=dias,
        domain_ids=dominios,
    )


def op(estado: ObservedOperationState, **overrides: object) -> GovernedOperationObservation:
    base: dict[str, object] = {
        "operation": CognitiveOperation.READ,
        "observed_state": estado,
        "actor_ref": "ator:ana",
        "purpose": "purpose:leitura",
        "domain_ids": (DOMINIO,),
    }
    base.update(overrides)
    return GovernedOperationObservation(**base)  # type: ignore[arg-type]


def avaliar(politica_avaliada, observacao, *, kind, instante=AGORA, dominio=DOMINIO):
    return avaliar_conformidade(
        subject=sujeito(kind, dominio=dominio),
        policy=politica_avaliada,
        observation=observacao,
        evaluated_at=instante,
    )


# ----------------------------------------------------------------------
# Contrato da assinatura
# ----------------------------------------------------------------------


def test_e01_o_relogio_e_injetado_e_obrigatorio():
    """`CLOCK_INJECTED = REQUIRED` — um default seria `now()` disfarçado."""
    with pytest.raises(TypeError):
        avaliar_conformidade(  # type: ignore[call-arg]
            subject=sujeito(ComplianceSubjectKind.GOVERNED_OPERATION),
            policy=politica(PolicyKind.GOVERNANCE, (regra_gov("r1", GovernanceEffect.ADMIT),)),
            observation=op(ObservedOperationState.EXECUTED),
        )


def test_e02_instante_ingenuo_e_recusado():
    with pytest.raises(ValueError, match="timezone-aware"):
        avaliar(
            politica(PolicyKind.GOVERNANCE, (regra_gov("r1", GovernanceEffect.ADMIT),)),
            op(ObservedOperationState.EXECUTED),
            kind=ComplianceSubjectKind.GOVERNED_OPERATION,
            instante=datetime(2026, 8, 19, 12, 0),
        )


@pytest.mark.parametrize(
    ("kind_politica", "kind_sujeito"),
    [
        (PolicyKind.GOVERNANCE, ComplianceSubjectKind.ACCESSIBILITY_TRANSITION),
        (PolicyKind.ACCESSIBILITY, ComplianceSubjectKind.RETENTION_CANDIDATE),
        (PolicyKind.RETENTION, ComplianceSubjectKind.GOVERNED_OPERATION),
    ],
)
def test_e03_sujeito_incompativel_com_a_politica_e_recusado(kind_politica, kind_sujeito):
    with pytest.raises(ValueError, match="avalia sujeito"):
        avaliar(
            politica(kind_politica, ()),
            op(ObservedOperationState.EXECUTED),
            kind=kind_sujeito,
        )


def test_e04_observacao_incompativel_com_a_politica_e_recusada():
    with pytest.raises(TypeError, match="exige AccessibilityStateObservation"):
        avaliar(
            politica(PolicyKind.ACCESSIBILITY, ()),
            op(ObservedOperationState.EXECUTED),
            kind=ComplianceSubjectKind.ACCESSIBILITY_TRANSITION,
        )


def test_e05_familias_de_regra_nao_se_misturam():
    """Uma política de acessibilidade com regra de governança avaliaria
    dimensões que a E4.7 deliberadamente manteve fora dela."""
    with pytest.raises(TypeError, match="admite apenas AccessibilityRule"):
        politica(PolicyKind.ACCESSIBILITY, (regra_gov("r1", GovernanceEffect.ADMIT),))


def test_e06_rule_id_repetido_e_recusado():
    """Com duplicata, a ordem de declaração passaria a mudar o resultado."""
    with pytest.raises(ValueError, match="rule_id repetido"):
        politica(
            PolicyKind.GOVERNANCE,
            (regra_gov("r1", GovernanceEffect.ADMIT), regra_gov("r1", GovernanceEffect.DENY)),
        )


def test_e07_janela_invertida_e_recusada():
    with pytest.raises(ValueError, match="janela vazia ou invertida"):
        politica(
            PolicyKind.GOVERNANCE,
            (),
            inicio=AGORA,
            fim=AGORA - timedelta(days=1),
        )


def test_e08_retencao_exige_dominio_do_sujeito():
    with pytest.raises(ValueError, match="exige domain_id"):
        sujeito(ComplianceSubjectKind.RETENTION_CANDIDATE, dominio=None)


@pytest.mark.parametrize("colecao", [list, set])
def test_e09_regras_exigem_tupla(colecao):
    with pytest.raises(TypeError, match="rules deve ser tuple"):
        politica(PolicyKind.GOVERNANCE, colecao([regra_gov("r1", GovernanceEffect.ADMIT)]))


def test_e10_entrada_nao_tipada_e_recusada():
    with pytest.raises(TypeError, match="subject deve ser"):
        avaliar_conformidade(
            subject={"coid": SUJEITO},  # type: ignore[arg-type]
            policy=politica(PolicyKind.GOVERNANCE, ()),
            observation=op(ObservedOperationState.EXECUTED),
            evaluated_at=AGORA,
        )


# ----------------------------------------------------------------------
# Janela de vigência — comum às três famílias
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("instante", "janela"),
    [
        (AGORA - timedelta(days=60), PolicyWindowState.BEFORE_WINDOW),
        (AGORA + timedelta(days=60), PolicyWindowState.AFTER_WINDOW),
    ],
)
def test_e11_politica_fora_da_janela_nao_se_aplica(instante, janela):
    resultado = avaliar(
        politica(
            PolicyKind.GOVERNANCE,
            (regra_gov("r1", GovernanceEffect.DENY),),
            fim=AGORA + timedelta(days=30),
        ),
        op(ObservedOperationState.EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
        instante=instante,
    )
    assert resultado.outcome is ComplianceOutcome.POLICY_NOT_APPLICABLE
    assert resultado.evidence.policy_window is janela
    assert resultado.findings == ()


def test_e12_a_janela_tem_fim_exclusivo():
    """Início inclusivo, fim exclusivo — idêntico à E4.9.9.c."""
    fim = AGORA + timedelta(days=1)
    politica_avaliada = politica(
        PolicyKind.GOVERNANCE, (regra_gov("r1", GovernanceEffect.ADMIT),), fim=fim
    )
    dentro = avaliar(
        politica_avaliada,
        op(ObservedOperationState.EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
        instante=fim - timedelta(seconds=1),
    )
    fora = avaliar(
        politica_avaliada,
        op(ObservedOperationState.EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
        instante=fim,
    )
    assert dentro.outcome is ComplianceOutcome.COMPLIANT
    assert fora.outcome is ComplianceOutcome.POLICY_NOT_APPLICABLE


# ----------------------------------------------------------------------
# Matriz GOVERNANCE
# ----------------------------------------------------------------------


def test_e13_deny_mais_executado_e_violacao():
    resultado = avaliar(
        politica(PolicyKind.GOVERNANCE, (regra_gov("r-nega", GovernanceEffect.DENY),)),
        op(ObservedOperationState.EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.outcome is ComplianceOutcome.VIOLATION_CONFIRMED
    assert resultado.violation_codes == (ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_AGAINST_DENY,)
    assert resultado.findings[0].matched_rule_ids == ("r-nega",)
    assert resultado.findings[0].severity is ErrorSeverity.ERROR


def test_e14_deny_mais_nao_executado_e_conforme():
    resultado = avaliar(
        politica(PolicyKind.GOVERNANCE, (regra_gov("r-nega", GovernanceEffect.DENY),)),
        op(ObservedOperationState.NOT_EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.outcome is ComplianceOutcome.COMPLIANT
    assert resultado.evidence.applicable_rule_ids == ("r-nega",)


@pytest.mark.parametrize(
    "estado", [ObservedOperationState.EXECUTED, ObservedOperationState.NOT_EXECUTED]
)
def test_e15_admit_e_conforme_nos_dois_estados(estado):
    """**Admissão é permissão, não obrigação de executar.**

    Tratar o não uso de uma permissão como desvio transformaria a
    política num agendador.
    """
    resultado = avaliar(
        politica(PolicyKind.GOVERNANCE, (regra_gov("r-admite", GovernanceEffect.ADMIT),)),
        op(estado),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.outcome is ComplianceOutcome.COMPLIANT


def test_e16_deny_prevalece_sobre_admit():
    """`DENY_OVERRIDES` — restrição que some porque outra regra permite
    não é restrição."""
    resultado = avaliar(
        politica(
            PolicyKind.GOVERNANCE,
            (
                regra_gov("r-admite", GovernanceEffect.ADMIT),
                regra_gov("r-nega", GovernanceEffect.DENY),
            ),
        ),
        op(ObservedOperationState.EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.outcome is ComplianceOutcome.VIOLATION_CONFIRMED
    assert resultado.findings[0].matched_rule_ids == ("r-nega",)


def test_e17_executado_sem_regra_aplicavel_e_codigo_proprio():
    """Executar sob política vigente sem regra é fato observável — e não
    vira negação retroativa."""
    resultado = avaliar(
        politica(
            PolicyKind.GOVERNANCE,
            (regra_gov("r-outra", GovernanceEffect.DENY, dominios=frozenset({OUTRO_DOMINIO})),),
        ),
        op(ObservedOperationState.EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.violation_codes == (ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_WITHOUT_RULE,)
    assert resultado.findings[0].severity is ErrorSeverity.WARNING
    assert resultado.findings[0].matched_rule_ids == ()


def test_e18_nao_executado_sem_regra_e_politica_nao_aplicavel():
    resultado = avaliar(
        politica(
            PolicyKind.GOVERNANCE,
            (regra_gov("r-outra", GovernanceEffect.DENY, dominios=frozenset({OUTRO_DOMINIO})),),
        ),
        op(ObservedOperationState.NOT_EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.outcome is ComplianceOutcome.POLICY_NOT_APPLICABLE
    assert resultado.evidence.applicable_rule_ids == ()


def test_e19_algum_deny_com_nao_observado_e_insuficiencia():
    """Onde alguma regra nega, a observação DECIDE — e falta."""
    resultado = avaliar(
        politica(PolicyKind.GOVERNANCE, (regra_gov("r-nega", GovernanceEffect.DENY),)),
        op(ObservedOperationState.NOT_OBSERVED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.outcome is ComplianceOutcome.INSUFFICIENT_INFORMATION
    assert resultado.evidence.missing_observations == (MissingObservation.OBSERVED_OPERATION_STATE,)
    assert resultado.findings == ()


def test_e19_1_somente_admit_com_nao_observado_e_conforme():
    """`MISSING_OBSERVATION_MATTERS_ONLY_WHERE_IT_CHANGES_THE_RESULT`.

    Com todas as regras aplicáveis admitindo, os dois estados possíveis
    são conformes: executado é conforme e não executado também. A
    observação que falta não decide nada, e pedi-la seria exigir um dado
    que não muda o desfecho.
    """
    resultado = avaliar(
        politica(
            PolicyKind.GOVERNANCE,
            (
                regra_gov("r-admite-1", GovernanceEffect.ADMIT),
                regra_gov("r-admite-2", GovernanceEffect.ADMIT),
            ),
        ),
        op(ObservedOperationState.NOT_OBSERVED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.outcome is ComplianceOutcome.COMPLIANT
    assert resultado.evidence.applicable_rule_ids == ("r-admite-1", "r-admite-2")
    assert resultado.evidence.missing_observations == ()
    assert resultado.findings == ()


def test_e19_2_deny_entre_admits_com_nao_observado_e_insuficiencia():
    """`DENY_OVERRIDES` também decide se a observação faz falta."""
    resultado = avaliar(
        politica(
            PolicyKind.GOVERNANCE,
            (
                regra_gov("r-admite", GovernanceEffect.ADMIT),
                regra_gov("r-nega", GovernanceEffect.DENY),
            ),
        ),
        op(ObservedOperationState.NOT_OBSERVED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.outcome is ComplianceOutcome.INSUFFICIENT_INFORMATION
    assert resultado.evidence.missing_observations == (MissingObservation.OBSERVED_OPERATION_STATE,)


def test_e19_3_sem_regra_com_nao_observado_e_insuficiencia():
    """Sem regra aplicável a observação decide entre `GOV-002` e
    `POLICY_NOT_APPLICABLE` — logo, faz falta."""
    resultado = avaliar(
        politica(
            PolicyKind.GOVERNANCE,
            (regra_gov("r-outra", GovernanceEffect.DENY, dominios=frozenset({OUTRO_DOMINIO})),),
        ),
        op(ObservedOperationState.NOT_OBSERVED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.outcome is ComplianceOutcome.INSUFFICIENT_INFORMATION
    assert resultado.evidence.missing_observations == (MissingObservation.OBSERVED_OPERATION_STATE,)
    assert resultado.evidence.applicable_rule_ids == ()


def test_e19_4_lote_vazio_com_nao_observado_e_insuficiencia():
    resultado = avaliar(
        politica(PolicyKind.GOVERNANCE, ()),
        op(ObservedOperationState.NOT_OBSERVED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.outcome is ComplianceOutcome.INSUFFICIENT_INFORMATION


def test_e20_governanca_com_lote_vazio_de_regras():
    resultado = avaliar(
        politica(PolicyKind.GOVERNANCE, ()),
        op(ObservedOperationState.NOT_EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.outcome is ComplianceOutcome.POLICY_NOT_APPLICABLE


# ----------------------------------------------------------------------
# Matriz ACCESSIBILITY
# ----------------------------------------------------------------------


def acc(destino: str, **overrides: object) -> AccessibilityStateObservation:
    base: dict[str, object] = {
        "current_state": destino,
        "declared_source": "active",
        "causal_evidence": CausalEvidencePresence.NOT_OBSERVED,
    }
    base.update(overrides)
    return AccessibilityStateObservation(**base)  # type: ignore[arg-type]


def test_e21_aresta_com_deny_e_violacao():
    resultado = avaliar(
        politica(
            PolicyKind.ACCESSIBILITY,
            (regra_acc("r-nega", GovernanceEffect.DENY, "active", "inaccessible"),),
        ),
        acc("inaccessible"),
        kind=ComplianceSubjectKind.ACCESSIBILITY_TRANSITION,
    )
    assert resultado.violation_codes == (ComplianceCode.ACCESSIBILITY_TRANSITION_AGAINST_DENY,)
    assert resultado.findings[0].matched_rule_ids == ("r-nega",)


def test_e22_aresta_com_allow_e_conforme():
    resultado = avaliar(
        politica(
            PolicyKind.ACCESSIBILITY,
            (regra_acc("r-permite", GovernanceEffect.ADMIT, "active", "latent"),),
        ),
        acc("latent"),
        kind=ComplianceSubjectKind.ACCESSIBILITY_TRANSITION,
    )
    assert resultado.outcome is ComplianceOutcome.COMPLIANT
    assert resultado.evidence.applicable_rule_ids == ("r-permite",)


def test_e23_a_aresta_e_exata_e_nao_apenas_o_destino():
    """A regra restringe *de onde* se veio; avaliar só o destino perderia
    exatamente isso."""
    politica_avaliada = politica(
        PolicyKind.ACCESSIBILITY,
        (regra_acc("r-permite", GovernanceEffect.ADMIT, "active", "latent"),),
    )
    de_active = avaliar(
        politica_avaliada, acc("latent"), kind=ComplianceSubjectKind.ACCESSIBILITY_TRANSITION
    )
    de_inaccessible = avaliar(
        politica_avaliada,
        acc("latent", declared_source="inaccessible"),
        kind=ComplianceSubjectKind.ACCESSIBILITY_TRANSITION,
    )
    assert de_active.outcome is ComplianceOutcome.COMPLIANT
    assert de_inaccessible.violation_codes == (
        ComplianceCode.ACCESSIBILITY_TRANSITION_WITHOUT_RULE,
    )


def test_e24_deny_prevalece_na_acessibilidade():
    resultado = avaliar(
        politica(
            PolicyKind.ACCESSIBILITY,
            (
                regra_acc("r-permite", GovernanceEffect.ADMIT, "active", "latent"),
                regra_acc("r-nega", GovernanceEffect.DENY, "active", "latent"),
            ),
        ),
        acc("latent"),
        kind=ComplianceSubjectKind.ACCESSIBILITY_TRANSITION,
    )
    assert resultado.violation_codes == (ComplianceCode.ACCESSIBILITY_TRANSITION_AGAINST_DENY,)


def test_e25_origem_ausente_e_insuficiencia():
    """`declared_source=None` nunca produz conformidade."""
    resultado = avaliar(
        politica(
            PolicyKind.ACCESSIBILITY,
            (regra_acc("r-permite", GovernanceEffect.ADMIT, "active", "latent"),),
        ),
        acc("latent", declared_source=None),
        kind=ComplianceSubjectKind.ACCESSIBILITY_TRANSITION,
    )
    assert resultado.outcome is ComplianceOutcome.INSUFFICIENT_INFORMATION
    assert resultado.evidence.missing_observations == (MissingObservation.DECLARED_SOURCE_STATE,)


def test_e26_extincao_sem_evidencia_observada_e_insuficiencia():
    resultado = avaliar(
        politica(
            PolicyKind.ACCESSIBILITY,
            (regra_acc("r", GovernanceEffect.ADMIT, "active", "causally_extinct"),),
        ),
        acc("causally_extinct", causal_evidence=CausalEvidencePresence.NOT_OBSERVED),
        kind=ComplianceSubjectKind.ACCESSIBILITY_TRANSITION,
    )
    assert resultado.outcome is ComplianceOutcome.INSUFFICIENT_INFORMATION
    assert resultado.evidence.missing_observations == (MissingObservation.CAUSAL_EVIDENCE,)


def test_e27_extincao_com_evidencia_ausente_e_violacao_critica():
    """`ABSENT` é fato observado — alguém procurou e não havia."""
    resultado = avaliar(
        politica(
            PolicyKind.ACCESSIBILITY,
            (regra_acc("r", GovernanceEffect.ADMIT, "active", "causally_extinct"),),
        ),
        acc("causally_extinct", causal_evidence=CausalEvidencePresence.ABSENT),
        kind=ComplianceSubjectKind.ACCESSIBILITY_TRANSITION,
    )
    assert resultado.violation_codes == (ComplianceCode.ACCESSIBILITY_EXTINCTION_WITHOUT_EVIDENCE,)
    assert resultado.findings[0].severity is ErrorSeverity.CRITICAL


def test_e28_extincao_com_evidencia_presente_segue_para_a_aresta():
    resultado = avaliar(
        politica(
            PolicyKind.ACCESSIBILITY,
            (regra_acc("r", GovernanceEffect.ADMIT, "active", "causally_extinct"),),
        ),
        acc("causally_extinct", causal_evidence=CausalEvidencePresence.PRESENT),
        kind=ComplianceSubjectKind.ACCESSIBILITY_TRANSITION,
    )
    assert resultado.outcome is ComplianceOutcome.COMPLIANT


def test_e29_origem_e_evidencia_ausentes_acumulam_faltantes():
    resultado = avaliar(
        politica(PolicyKind.ACCESSIBILITY, ()),
        acc("causally_extinct", declared_source=None),
        kind=ComplianceSubjectKind.ACCESSIBILITY_TRANSITION,
    )
    assert resultado.evidence.missing_observations == (
        MissingObservation.DECLARED_SOURCE_STATE,
        MissingObservation.CAUSAL_EVIDENCE,
    )


def test_e30_token_fora_do_vocabulario_da_e3_e_recusado():
    with pytest.raises(ValueError, match="fora do vocabulário da E3"):
        acc("arquivado")


def test_e31_origem_fora_do_vocabulario_e_recusada():
    with pytest.raises(ValueError, match="fora do vocabulário da E3"):
        acc("latent", declared_source="ARCHIVED")


# ----------------------------------------------------------------------
# Matriz RETENTION
# ----------------------------------------------------------------------


def ret(**overrides: object) -> RetentionAgeObservation:
    base: dict[str, object] = {
        "anchor_at": AGORA - timedelta(days=400),
        "legacy_protection_state": LegacyProtectionState.NOT_PROTECTED,
        "assessment_information": AssessmentInformationState.NOT_OBSERVED,
    }
    base.update(overrides)
    return RetentionAgeObservation(**base)  # type: ignore[arg-type]


def test_e32_ancora_ausente_e_insuficiencia():
    resultado = avaliar(
        politica(PolicyKind.RETENTION, (regra_ret("r-30", 30),)),
        ret(anchor_at=None),
        kind=ComplianceSubjectKind.RETENTION_CANDIDATE,
    )
    assert resultado.outcome is ComplianceOutcome.INSUFFICIENT_INFORMATION
    assert resultado.evidence.missing_observations == (MissingObservation.ANCHOR_TIMESTAMP,)


def test_e33_fora_de_escopo_e_politica_nao_aplicavel():
    resultado = avaliar(
        politica(
            PolicyKind.RETENTION,
            (regra_ret("r-30", 30, dominios=frozenset({OUTRO_DOMINIO})),),
        ),
        ret(),
        kind=ComplianceSubjectKind.RETENTION_CANDIDATE,
    )
    assert resultado.outcome is ComplianceOutcome.POLICY_NOT_APPLICABLE


def test_e34_legado_protegido_e_conforme():
    resultado = avaliar(
        politica(PolicyKind.RETENTION, (regra_ret("r-30", 30),)),
        ret(legacy_protection_state=LegacyProtectionState.PROTECTED),
        kind=ComplianceSubjectKind.RETENTION_CANDIDATE,
    )
    assert resultado.outcome is ComplianceOutcome.COMPLIANT


def test_e35_ainda_nao_vencido_e_conforme():
    """`AGE < MINIMUM_AGE` é preservação em curso — nada a exigir."""
    resultado = avaliar(
        politica(PolicyKind.RETENTION, (regra_ret("r-365", 365),)),
        ret(anchor_at=AGORA - timedelta(days=10)),
        kind=ComplianceSubjectKind.RETENTION_CANDIDATE,
    )
    assert resultado.outcome is ComplianceOutcome.COMPLIANT
    assert resultado.evidence.applicable_rule_ids == ("r-365",)


def test_e36_elegivel_com_avaliacao_presente_e_conforme():
    """`AGE >= MINIMUM_AGE` **não** é violação por permanência."""
    resultado = avaliar(
        politica(PolicyKind.RETENTION, (regra_ret("r-30", 30),)),
        ret(assessment_information=AssessmentInformationState.PRESENT),
        kind=ComplianceSubjectKind.RETENTION_CANDIDATE,
    )
    assert resultado.outcome is ComplianceOutcome.COMPLIANT
    assert resultado.findings == ()


def test_e37_elegivel_com_avaliacao_ausente_e_violacao():
    """O código significa avaliação exigida e confirmadamente ausente."""
    resultado = avaliar(
        politica(PolicyKind.RETENTION, (regra_ret("r-30", 30),)),
        ret(assessment_information=AssessmentInformationState.ABSENT),
        kind=ComplianceSubjectKind.RETENTION_CANDIDATE,
    )
    assert resultado.violation_codes == (ComplianceCode.RETENTION_ASSESSMENT_INFORMATION_ABSENT,)
    assert resultado.findings[0].matched_rule_ids == ("r-30",)
    assert resultado.findings[0].severity is ErrorSeverity.WARNING


def test_e38_elegivel_sem_observar_a_avaliacao_e_insuficiencia():
    resultado = avaliar(
        politica(PolicyKind.RETENTION, (regra_ret("r-30", 30),)),
        ret(assessment_information=AssessmentInformationState.NOT_OBSERVED),
        kind=ComplianceSubjectKind.RETENTION_CANDIDATE,
    )
    assert resultado.outcome is ComplianceOutcome.INSUFFICIENT_INFORMATION
    assert resultado.evidence.missing_observations == (MissingObservation.ASSESSMENT_INFORMATION,)


def test_e39_o_calculo_de_elegibilidade_nao_e_reimplementado():
    """A regra do MÁXIMO dos vencimentos vem de `avaliar_retencao`.

    Duas regras aplicáveis, 30 e 365 dias, com 100 dias de idade: a
    leitura conservadora ainda preserva. Reimplementar aqui com o mínimo
    daria conforme por outro caminho — e criaria duas respostas para a
    mesma pergunta.
    """
    resultado = avaliar(
        politica(PolicyKind.RETENTION, (regra_ret("r-30", 30), regra_ret("r-365", 365))),
        ret(anchor_at=AGORA - timedelta(days=100)),
        kind=ComplianceSubjectKind.RETENTION_CANDIDATE,
    )
    assert resultado.outcome is ComplianceOutcome.COMPLIANT
    assert resultado.evidence.applicable_rule_ids == ("r-30", "r-365")


def test_e40_retencao_sem_regras_e_politica_nao_aplicavel():
    resultado = avaliar(
        politica(PolicyKind.RETENTION, ()),
        ret(),
        kind=ComplianceSubjectKind.RETENTION_CANDIDATE,
    )
    assert resultado.outcome is ComplianceOutcome.POLICY_NOT_APPLICABLE


# ----------------------------------------------------------------------
# Determinismo, versão e ausência de efeito
# ----------------------------------------------------------------------


def test_e41_a_avaliacao_e_deterministica():
    """Mesma entrada, mesma saída — igualdade estrutural."""
    argumentos = (
        politica(PolicyKind.GOVERNANCE, (regra_gov("r", GovernanceEffect.DENY),)),
        op(ObservedOperationState.EXECUTED),
    )
    primeiro = avaliar(*argumentos, kind=ComplianceSubjectKind.GOVERNED_OPERATION)
    segundo = avaliar(*argumentos, kind=ComplianceSubjectKind.GOVERNED_OPERATION)
    assert primeiro == segundo


def test_e42_a_versao_avaliada_e_preservada_no_resultado():
    resultado = avaliar(
        politica(PolicyKind.GOVERNANCE, (regra_gov("r", GovernanceEffect.DENY),), versao=7),
        op(ObservedOperationState.EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert resultado.policy_version == 7
    assert resultado.findings[0].policy_version == 7


def test_e43_versoes_diferentes_da_mesma_politica_dao_resultados_distintos():
    """A versão posterior existir não altera o diagnóstico da anterior."""
    antiga = avaliar(
        politica(PolicyKind.GOVERNANCE, (regra_gov("r", GovernanceEffect.DENY),), versao=1),
        op(ObservedOperationState.EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    nova = avaliar(
        politica(PolicyKind.GOVERNANCE, (regra_gov("r", GovernanceEffect.ADMIT),), versao=2),
        op(ObservedOperationState.EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    assert antiga.outcome is ComplianceOutcome.VIOLATION_CONFIRMED
    assert antiga.policy_version == 1
    assert nova.outcome is ComplianceOutcome.COMPLIANT
    assert nova.policy_version == 2


def test_e44_todo_finding_cita_o_sujeito_e_o_instante_da_avaliacao():
    resultado = avaliar(
        politica(PolicyKind.GOVERNANCE, (regra_gov("r", GovernanceEffect.DENY),)),
        op(ObservedOperationState.EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    finding = resultado.findings[0]
    assert finding.subject_ref == resultado.subject_ref
    assert finding.policy_ref == resultado.policy_ref
    assert finding.evaluated_at == resultado.evaluated_at


def test_e45_a_avaliacao_nao_altera_a_politica_nem_a_observacao():
    """Função pura: as entradas saem idênticas."""
    politica_avaliada = politica(PolicyKind.GOVERNANCE, (regra_gov("r", GovernanceEffect.DENY),))
    observacao = op(ObservedOperationState.EXECUTED)
    antes = (politica_avaliada, observacao)
    avaliar(politica_avaliada, observacao, kind=ComplianceSubjectKind.GOVERNED_OPERATION)
    assert (politica_avaliada, observacao) == antes


def test_e46_o_resultado_nao_transporta_o_conteudo_das_regras():
    """Identificadores opacos, jamais as regras."""
    resultado = avaliar(
        politica(PolicyKind.GOVERNANCE, (regra_gov("r-nega", GovernanceEffect.DENY),)),
        op(ObservedOperationState.EXECUTED),
        kind=ComplianceSubjectKind.GOVERNED_OPERATION,
    )
    texto = repr(resultado)
    assert "GovernanceRule" not in texto
    assert "operations" not in texto
    assert "r-nega" in texto


# ----------------------------------------------------------------------
# Tipos exatos nas entradas — `STRING_EQUIVALENT != ENUM_MEMBER`
# ----------------------------------------------------------------------
#
# Cada ramo é alcançado pelo construtor PÚBLICO com o tipo errado. Sem
# estes casos, um `TypeError` nunca exercitado poderia estar quebrado
# sem que ninguém soubesse.


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("kind", "governed_operation"),
        ("subject_coid", str(SUJEITO)),
        ("domain_id", str(DOMINIO)),
    ],
)
def test_e47_o_sujeito_recusa_tipo_errado(campo, valor):
    base: dict[str, object] = {
        "kind": ComplianceSubjectKind.GOVERNED_OPERATION,
        "subject_coid": SUJEITO,
        "domain_id": DOMINIO,
    }
    base[campo] = valor
    with pytest.raises(TypeError):
        ComplianceSubject(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("campo", "valor", "erro"),
    [
        ("kind", "governance", TypeError),
        ("policy_id", str(POLICY_ID), TypeError),
        ("policy_key", "  ", ValueError),
        ("policy_version", "3", TypeError),
        ("policy_version", True, TypeError),
        ("policy_version", 0, ValueError),
        ("effective_from", "2026-08-19", TypeError),
    ],
)
def test_e48_a_politica_avaliada_recusa_valor_invalido(campo, valor, erro):
    base: dict[str, object] = {
        "kind": PolicyKind.GOVERNANCE,
        "policy_id": POLICY_ID,
        "policy_key": "gov.principal",
        "policy_version": 3,
        "effective_from": AGORA - timedelta(days=30),
        "effective_until": None,
        "rules": (),
    }
    base[campo] = valor
    with pytest.raises(erro):
        EvaluatedPolicy(**base)  # type: ignore[arg-type]


def test_e49_janela_final_ingenua_e_recusada():
    with pytest.raises(ValueError, match="timezone-aware"):
        politica(PolicyKind.GOVERNANCE, (), fim=datetime(2030, 1, 1))


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("operation", "read"),
        ("observed_state", "executed"),
        ("actor_ref", 1),
        ("purpose", 1),
        ("domain_ids", [DOMINIO]),
    ],
)
def test_e50_a_observacao_de_operacao_recusa_tipo_errado(campo, valor):
    with pytest.raises(TypeError):
        op(ObservedOperationState.EXECUTED, **{campo: valor})


def test_e51_dominio_de_outro_tipo_na_observacao_e_recusado():
    with pytest.raises(TypeError, match=r"domain_ids\[0\]"):
        op(ObservedOperationState.EXECUTED, domain_ids=(str(DOMINIO),))


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("current_state", 1), ("declared_source", 1), ("causal_evidence", "present")],
)
def test_e52_a_observacao_de_acessibilidade_recusa_tipo_errado(campo, valor):
    with pytest.raises(TypeError):
        acc("latent", **{campo: valor})


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("anchor_at", "2026-08-19"),
        ("legacy_protection_state", "not_protected"),
        ("assessment_information", "present"),
    ],
)
def test_e53_a_observacao_de_retencao_recusa_tipo_errado(campo, valor):
    with pytest.raises(TypeError):
        ret(**{campo: valor})


def test_e54_ancora_ingenua_e_recusada():
    with pytest.raises(ValueError, match="timezone-aware"):
        ret(anchor_at=datetime(2020, 1, 1))


def test_e55_politica_nao_tipada_e_recusada():
    with pytest.raises(TypeError, match="policy deve ser"):
        avaliar_conformidade(
            subject=sujeito(ComplianceSubjectKind.GOVERNED_OPERATION),
            policy={"kind": "governance"},  # type: ignore[arg-type]
            observation=op(ObservedOperationState.EXECUTED),
            evaluated_at=AGORA,
        )


def test_e56_a_segunda_camada_de_dominio_recusa_estado_impossivel():
    """`SECOND_LAYER_REACHED_BY_CONTROLLED_SUBCLASS`.

    O construtor de `ComplianceSubject` já recusa retenção sem domínio.
    A segunda camada no avaliador existe para que uma futura
    flexibilização daquele contrato não passe em silêncio — e é
    alcançada por subclasse controlada, que é construção legítima, não
    adulteração de estado.
    """

    class SujeitoSemDominio(ComplianceSubject):
        def __post_init__(self) -> None:  # noqa: D105
            return

    with pytest.raises(ValueError, match="sem domain_id"):
        avaliar_conformidade(
            subject=SujeitoSemDominio(
                kind=ComplianceSubjectKind.RETENTION_CANDIDATE,
                subject_coid=SUJEITO,
                domain_id=None,
            ),
            policy=politica(PolicyKind.RETENTION, (regra_ret("r-30", 30),)),
            observation=ret(),
            evaluated_at=AGORA,
        )
