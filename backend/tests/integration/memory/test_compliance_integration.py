"""
Conformidade contra políticas **reais** e versionadas (`E4.10`).

```text
READ_ONLY_EVALUATION = REQUIRED
ZERO_WRITES · ZERO_COMMITS
```

O que só o PostgreSQL real prova: que a avaliação lê a versão exata que
o repositório entrega, que a versão posterior existir não altera o
diagnóstico da anterior, e que **nada** é escrito — medido por censo de
linhas antes e depois, em todas as tabelas do domínio de memória.

Nenhum finding é persistido, e nenhuma tabela existe para persisti-lo.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.memory.models.accessibility_policy import AccessibilityPolicy
from app.memory.models.compliance_enums import (
    AssessmentInformationState,
    ComplianceCode,
    ComplianceOutcome,
    ComplianceSubjectKind,
    ObservedOperationState,
    PolicyKind,
)
from app.memory.models.governance_enums import CognitiveOperation, GovernanceEffect
from app.memory.models.governance_policy import GovernancePolicy
from app.memory.models.retention_enums import RetentionScopeKind
from app.memory.models.target_resolution_enums import LegacyProtectionState
from app.memory.repositories.accessibility_policy_repository import (
    AccessibilityPolicyRepository,
)
from app.memory.repositories.governance_policy_repository import GovernancePolicyRepository
from app.memory.repositories.retention_policy_repository import RetentionPolicyRepository
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
SUJEITO = uuid.UUID("00000000-0000-0000-0000-0000000c1001")
DOMINIO = uuid.UUID("00000000-0000-0000-0000-0000000c1002")

TABELAS = (
    "governance_policies",
    "accessibility_policies",
    "retention_policies",
    "approval_records",
    "erasure_records",
)


def _disponivel() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _disponivel(),
    reason="PostgreSQL real indisponível — a leitura versionada exige banco.",
)


@pytest.fixture(autouse=True)
def _limpar():
    migrations.upgrade("head")
    _truncar()
    yield
    _truncar()


def _truncar() -> None:
    with engine.begin() as conn:
        for tabela in TABELAS:
            conn.execute(sa.text(f"TRUNCATE {tabela} CASCADE"))


def _censo() -> dict[str, int]:
    """Contagem de linhas em todas as tabelas do domínio."""
    with Session(engine) as sessao:
        return {
            tabela: sessao.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar_one()
            for tabela in TABELAS
        }


def _tabelas_existentes() -> set[str]:
    with Session(engine) as sessao:
        return {
            linha[0]
            for linha in sessao.execute(
                sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }


# ----------------------------------------------------------------------
# Semeadura de políticas reais
# ----------------------------------------------------------------------


def _semear_governanca(versao: int, efeito: GovernanceEffect):  # noqa: ANN202
    with Session(engine) as sessao:
        registro = GovernancePolicyRepository(sessao).add_policy(
            policy_key="gov.compliance",
            version=versao,
            rules=(
                GovernanceRule(
                    rule_id=f"r-{versao}",
                    effect=efeito,
                    operations=frozenset({CognitiveOperation.READ}),
                ),
            ),
            effective_from=AGORA - timedelta(days=30),
        )
        sessao.commit()
        return registro.id


def _ler_governanca(versao: int) -> EvaluatedPolicy:
    """Lê a versão exata pelo repositório e monta a política avaliada."""
    with Session(engine) as sessao:
        registro = GovernancePolicyRepository(sessao).get_version("gov.compliance", versao)
        assert registro is not None
        # `deserialize_rules` é o contrato CANÔNICO do modelo desde a
        # E4.3, e é ele que converte a linha em regra tipada. Reconstruir
        # as regras à mão aqui faria o teste medir a minha
        # desserialização em vez da do projeto — e a E4.10 não é dona
        # desse contrato.
        #
        # MEDIDO: as três famílias divergem no que o repositório
        # devolve. Governança e acessibilidade guardam JSON e expõem
        # `deserialize_rules`; retenção já devolve regra tipada pelo
        # `RetentionRulesType`. A conversão pertence a quem lê.
        regras = GovernancePolicy.deserialize_rules(registro.rules)
        return EvaluatedPolicy(
            kind=PolicyKind.GOVERNANCE,
            policy_id=registro.id,
            policy_key=registro.policy_key,
            policy_version=registro.version,
            effective_from=registro.effective_from,
            effective_until=registro.effective_until,
            rules=regras,
        )


def _operacao(estado: ObservedOperationState) -> GovernedOperationObservation:
    return GovernedOperationObservation(
        operation=CognitiveOperation.READ,
        observed_state=estado,
        actor_ref="ator:ana",
        purpose="purpose:leitura",
        domain_ids=(DOMINIO,),
    )


def _sujeito(kind: ComplianceSubjectKind) -> ComplianceSubject:
    return ComplianceSubject(kind=kind, subject_coid=SUJEITO, domain_id=DOMINIO)


# ----------------------------------------------------------------------
# A prova central — leitura versionada, zero escrita
# ----------------------------------------------------------------------


def test_i01_avalia_contra_a_versao_lida_do_banco():
    _semear_governanca(1, GovernanceEffect.DENY)
    resultado = avaliar_conformidade(
        subject=_sujeito(ComplianceSubjectKind.GOVERNED_OPERATION),
        policy=_ler_governanca(1),
        observation=_operacao(ObservedOperationState.EXECUTED),
        evaluated_at=AGORA,
    )
    assert resultado.outcome is ComplianceOutcome.VIOLATION_CONFIRMED
    assert resultado.policy_version == 1
    assert resultado.violation_codes == (ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_AGAINST_DENY,)


def test_i02_a_avaliacao_nao_escreve_nada():
    """`ZERO_WRITES` — censo de linhas antes e depois, todas as tabelas."""
    _semear_governanca(1, GovernanceEffect.DENY)
    antes = _censo()
    for estado in ObservedOperationState:
        avaliar_conformidade(
            subject=_sujeito(ComplianceSubjectKind.GOVERNED_OPERATION),
            policy=_ler_governanca(1),
            observation=_operacao(estado),
            evaluated_at=AGORA,
        )
    assert _censo() == antes


def test_i03_a_versao_posterior_nao_altera_o_diagnostico_da_anterior():
    """`PRESERVE_THE_EXACT_VERSION_EVALUATED`.

    A v1 nega e a v2 admite. Avaliar a v1 depois que a v2 existe tem de
    produzir exatamente o mesmo diagnóstico de antes — senão o
    relatório descreveria uma política que ninguém aplicou.
    """
    _semear_governanca(1, GovernanceEffect.DENY)
    antes = avaliar_conformidade(
        subject=_sujeito(ComplianceSubjectKind.GOVERNED_OPERATION),
        policy=_ler_governanca(1),
        observation=_operacao(ObservedOperationState.EXECUTED),
        evaluated_at=AGORA,
    )

    _semear_governanca(2, GovernanceEffect.ADMIT)
    depois = avaliar_conformidade(
        subject=_sujeito(ComplianceSubjectKind.GOVERNED_OPERATION),
        policy=_ler_governanca(1),
        observation=_operacao(ObservedOperationState.EXECUTED),
        evaluated_at=AGORA,
    )
    nova = avaliar_conformidade(
        subject=_sujeito(ComplianceSubjectKind.GOVERNED_OPERATION),
        policy=_ler_governanca(2),
        observation=_operacao(ObservedOperationState.EXECUTED),
        evaluated_at=AGORA,
    )

    assert depois == antes
    assert nova.outcome is ComplianceOutcome.COMPLIANT
    assert nova.policy_version == 2


def test_i04_a_versao_vigente_e_a_avaliada_podem_divergir():
    """`effective_version_at` diz qual vigora; a avaliação usa a pedida."""
    _semear_governanca(1, GovernanceEffect.DENY)
    _semear_governanca(2, GovernanceEffect.ADMIT)
    with Session(engine) as sessao:
        vigente = GovernancePolicyRepository(sessao).effective_version_at("gov.compliance", AGORA)
    assert vigente is not None
    resultado = avaliar_conformidade(
        subject=_sujeito(ComplianceSubjectKind.GOVERNED_OPERATION),
        policy=_ler_governanca(1),
        observation=_operacao(ObservedOperationState.EXECUTED),
        evaluated_at=AGORA,
    )
    assert resultado.policy_version == 1
    assert vigente.version >= 1


# ----------------------------------------------------------------------
# Acessibilidade e retenção contra registros reais
# ----------------------------------------------------------------------


def test_i05_acessibilidade_avaliada_contra_policy_persistida():
    with Session(engine) as sessao:
        registro = AccessibilityPolicyRepository(sessao).add_policy(
            policy_key="acc.compliance",
            version=1,
            governance_policy_key="gov.compliance",
            rules=(
                AccessibilityRule(
                    rule_id="acc-1",
                    effect=GovernanceEffect.DENY,
                    source_states=frozenset({"active"}),
                    target_states=frozenset({"inaccessible"}),
                ),
            ),
            effective_from=AGORA - timedelta(days=30),
        )
        sessao.commit()
        politica = EvaluatedPolicy(
            kind=PolicyKind.ACCESSIBILITY,
            policy_id=registro.id,
            policy_key=registro.policy_key,
            policy_version=registro.version,
            effective_from=registro.effective_from,
            effective_until=registro.effective_until,
            rules=AccessibilityPolicy.deserialize_rules(registro.rules),
        )

    antes = _censo()
    resultado = avaliar_conformidade(
        subject=_sujeito(ComplianceSubjectKind.ACCESSIBILITY_TRANSITION),
        policy=politica,
        observation=AccessibilityStateObservation(
            current_state="inaccessible", declared_source="active"
        ),
        evaluated_at=AGORA,
    )
    assert resultado.violation_codes == (ComplianceCode.ACCESSIBILITY_TRANSITION_AGAINST_DENY,)
    assert _censo() == antes


def test_i06_retencao_avaliada_contra_policy_persistida():
    regra = RetentionRule(
        rule_id="ret-30",
        scope_kind=RetentionScopeKind.ALL_LOCAL_PATRIMONY,
        minimum_age_days=30,
    )
    with Session(engine) as sessao:
        registro = RetentionPolicyRepository(sessao).add_policy(
            policy_key="ret.compliance",
            version=1,
            governance_policy_key="gov.compliance",
            rules=(regra,),
            effective_from=AGORA - timedelta(days=30),
        )
        sessao.commit()
        politica = EvaluatedPolicy(
            kind=PolicyKind.RETENTION,
            policy_id=registro.id,
            policy_key=registro.policy_key,
            policy_version=registro.version,
            effective_from=registro.effective_from,
            effective_until=registro.effective_until,
            rules=(regra,),
        )

    antes = _censo()
    ausente = avaliar_conformidade(
        subject=_sujeito(ComplianceSubjectKind.RETENTION_CANDIDATE),
        policy=politica,
        observation=RetentionAgeObservation(
            anchor_at=AGORA - timedelta(days=400),
            legacy_protection_state=LegacyProtectionState.NOT_PROTECTED,
            assessment_information=AssessmentInformationState.ABSENT,
        ),
        evaluated_at=AGORA,
    )
    presente = avaliar_conformidade(
        subject=_sujeito(ComplianceSubjectKind.RETENTION_CANDIDATE),
        policy=politica,
        observation=RetentionAgeObservation(
            anchor_at=AGORA - timedelta(days=400),
            legacy_protection_state=LegacyProtectionState.NOT_PROTECTED,
            assessment_information=AssessmentInformationState.PRESENT,
        ),
        evaluated_at=AGORA,
    )

    assert ausente.violation_codes == (ComplianceCode.RETENTION_ASSESSMENT_INFORMATION_ABSENT,)
    assert presente.outcome is ComplianceOutcome.COMPLIANT
    assert _censo() == antes


# ----------------------------------------------------------------------
# Ausência de persistência do próprio diagnóstico
# ----------------------------------------------------------------------


def test_i07_nenhuma_tabela_de_compliance_existe():
    """`ComplianceFinding` é transitório por contrato congelado."""
    tabelas = _tabelas_existentes()
    assert not {t for t in tabelas if "compliance" in t.lower()}


def test_i08_a_cabeca_do_alembic_continua_a_da_cadeia_94():
    """`MIGRATION = NONE` — a E4.10 não sucede a migration da E4.9.9.d."""
    assert migrations.head_revision() == "e5b21c9704af"
    assert migrations.current_revision() == "e5b21c9704af"


def test_i09_o_diagnostico_nao_sobrevive_a_avaliacao():
    """O relatório existe em memória e não deixa rastro no banco."""
    _semear_governanca(1, GovernanceEffect.DENY)
    antes = _censo()
    resultado = avaliar_conformidade(
        subject=_sujeito(ComplianceSubjectKind.GOVERNED_OPERATION),
        policy=_ler_governanca(1),
        observation=_operacao(ObservedOperationState.EXECUTED),
        evaluated_at=AGORA,
    )
    assert resultado.findings
    assert _censo() == antes
    with Session(engine) as sessao:
        encontrados = sessao.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE column_name LIKE '%compliance%'"
            )
        ).scalar_one()
    assert encontrados == 0


def test_i10_a_avaliacao_nao_altera_a_policy_lida():
    """A política persistida sai da avaliação byte a byte igual."""
    _semear_governanca(1, GovernanceEffect.DENY)
    with Session(engine) as sessao:
        antes = GovernancePolicyRepository(sessao).get_version("gov.compliance", 1)
        assert antes is not None
        instantaneo = (antes.policy_key, antes.version, list(antes.rules))

    avaliar_conformidade(
        subject=_sujeito(ComplianceSubjectKind.GOVERNED_OPERATION),
        policy=_ler_governanca(1),
        observation=_operacao(ObservedOperationState.EXECUTED),
        evaluated_at=AGORA,
    )

    with Session(engine) as sessao:
        depois = GovernancePolicyRepository(sessao).get_version("gov.compliance", 1)
        assert depois is not None
        assert (depois.policy_key, depois.version, list(depois.rules)) == instantaneo


def test_i11_o_diagnostico_e_reproduzivel_a_partir_da_mesma_versao():
    """Derivável de novo — é por isso que não precisa ser persistido."""
    _semear_governanca(1, GovernanceEffect.DENY)
    primeiro = avaliar_conformidade(
        subject=_sujeito(ComplianceSubjectKind.GOVERNED_OPERATION),
        policy=_ler_governanca(1),
        observation=_operacao(ObservedOperationState.EXECUTED),
        evaluated_at=AGORA,
    )
    segundo = avaliar_conformidade(
        subject=_sujeito(ComplianceSubjectKind.GOVERNED_OPERATION),
        policy=_ler_governanca(1),
        observation=_operacao(ObservedOperationState.EXECUTED),
        evaluated_at=AGORA,
    )
    assert primeiro == segundo
