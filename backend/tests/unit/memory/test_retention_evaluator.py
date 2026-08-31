"""
Testes do avaliador de retenção (`E4.9.9.c`).

```text
ASSESSMENT_ELIGIBILITY != DELETION_DECISION
EVALUATION             != DISPOSITION
NO_POLICY              != ELIGIBLE
CLOCK_INJECTED         = REQUIRED
LEGACY_PROTECTION_OVERRIDES_RETENTION_ELIGIBILITY
```
"""

import dataclasses
import inspect
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.memory.models.retention_assessment_enums import RetentionAssessmentDecision
from app.memory.models.retention_enums import (
    RetentionAnchor,
    RetentionExpiryAction,
    RetentionScopeKind,
)
from app.memory.models.target_resolution_enums import LegacyProtectionState
from app.memory.schemas.retention import RetentionRule
from app.memory.services.retention_evaluator import (
    RetentionAssessment,
    RetentionCandidate,
    avaliar_retencao,
)

DOMINIO = uuid.UUID("00000000-0000-0000-0000-00000000ff01")
OUTRO_DOMINIO = uuid.UUID("00000000-0000-0000-0000-00000000ff02")
SUJEITO = uuid.UUID("00000000-0000-0000-0000-00000000ff03")

NASCIMENTO = datetime(2026, 1, 1, tzinfo=UTC)
VIGENCIA = datetime(2025, 1, 1, tzinfo=UTC)
AOS_60_DIAS = NASCIMENTO + timedelta(days=60)
AOS_400_DIAS = NASCIMENTO + timedelta(days=400)


def candidato(**over: object) -> RetentionCandidate:
    base: dict[str, object] = {
        "subject_coid": SUJEITO,
        "domain_id": DOMINIO,
        "created_at": NASCIMENTO,
        "legacy_protection_state": LegacyProtectionState.NOT_PROTECTED,
    }
    base.update(over)
    return RetentionCandidate(**base)  # type: ignore[arg-type]


def regra(
    rule_id: str,
    dias: int,
    *,
    escopo: RetentionScopeKind = RetentionScopeKind.MEMORY_DOMAIN_SET,
    dominios: frozenset[uuid.UUID] | None = None,
) -> RetentionRule:
    return RetentionRule(
        rule_id=rule_id,
        scope_kind=escopo,
        minimum_age_days=dias,
        domain_ids=(
            frozenset()
            if escopo is RetentionScopeKind.ALL_LOCAL_PATRIMONY
            else (dominios if dominios is not None else frozenset({DOMINIO}))
        ),
    )


def avaliar(**over: object) -> RetentionAssessment:
    base: dict[str, object] = {
        "candidate": candidato(),
        "rules": (regra("curta", 30), regra("longa", 365)),
        "policy_effective_from": VIGENCIA,
        "policy_effective_until": None,
        "evaluated_at": AOS_60_DIAS,
    }
    base.update(over)
    return avaliar_retencao(**base)  # type: ignore[arg-type]


# ======================================================================
# Vocabulário
# ======================================================================


def test_u01_cinco_decisoes_e_nenhuma_de_disposicao():
    assert [m.value for m in RetentionAssessmentDecision] == [
        "policy_not_effective",
        "out_of_scope",
        "preserve_legacy_protected",
        "not_yet_due",
        "assess_and_inform",
    ]
    for proibido in (
        "DELETE",
        "ERASE",
        "PURGE",
        "MOVE_TO_TRASH",
        "DISPOSE",
        "SCHEDULE",
        "EXPIRED",
        "UNKNOWN",
        "OTHER",
    ):
        assert proibido not in RetentionAssessmentDecision.__members__


def test_u02_a_acao_de_expiracao_continua_com_um_unico_membro():
    """`ASSESS_AND_INFORM != DELETE`.

    A unicidade de `RetentionExpiryAction` desde a E4.9.6 é a prova de
    que vencimento nunca dispôs de nada. Esta fatia não pode ampliá-la.
    """
    assert [m.value for m in RetentionExpiryAction] == ["assess_and_inform"]
    assert [m.value for m in RetentionAnchor] == ["created_at"]


# ======================================================================
# Precedência — os cinco degraus, na ordem
# ======================================================================


@pytest.mark.parametrize(
    ("inicio", "fim", "quando"),
    [
        (datetime(2027, 1, 1, tzinfo=UTC), None, AOS_60_DIAS),
        (VIGENCIA, datetime(2026, 2, 1, tzinfo=UTC), AOS_60_DIAS),
    ],
)
def test_u03_policy_nao_vigente_vem_primeiro(inicio, fim, quando):
    r = avaliar(policy_effective_from=inicio, policy_effective_until=fim, evaluated_at=quando)
    assert r.decision is RetentionAssessmentDecision.POLICY_NOT_EFFECTIVE
    assert r.applicable_rule_ids == ()
    assert r.effective_due_at is None


def test_u04_janela_e_inicio_inclusivo_e_fim_exclusivo():
    """`[effective_from, effective_until)`."""
    inicio = datetime(2026, 3, 1, tzinfo=UTC)
    fim = datetime(2026, 4, 1, tzinfo=UTC)
    dentro = avaliar(policy_effective_from=inicio, policy_effective_until=fim, evaluated_at=inicio)
    assert dentro.decision is not RetentionAssessmentDecision.POLICY_NOT_EFFECTIVE

    no_fim = avaliar(policy_effective_from=inicio, policy_effective_until=fim, evaluated_at=fim)
    assert no_fim.decision is RetentionAssessmentDecision.POLICY_NOT_EFFECTIVE

    antes = avaliar(
        policy_effective_from=inicio,
        policy_effective_until=fim,
        evaluated_at=inicio - timedelta(microseconds=1),
    )
    assert antes.decision is RetentionAssessmentDecision.POLICY_NOT_EFFECTIVE


def test_u05_fora_de_escopo_vem_antes_do_prazo():
    r = avaliar(rules=(regra("outro", 1, dominios=frozenset({OUTRO_DOMINIO})),))
    assert r.decision is RetentionAssessmentDecision.OUT_OF_SCOPE
    assert r.applicable_rule_ids == ()
    assert r.effective_due_at is None


def test_u06_ausencia_de_regra_nao_e_elegibilidade():
    """`NO_POLICY != ELIGIBLE`."""
    r = avaliar(rules=(), evaluated_at=AOS_400_DIAS)
    assert r.decision is RetentionAssessmentDecision.OUT_OF_SCOPE
    assert r.decision is not RetentionAssessmentDecision.ASSESS_AND_INFORM


def test_u07_fora_de_escopo_nao_e_ainda_nao_venceu():
    """Colapsá-los sugeriria que um dia vencerá — o que seria falso."""
    fora = avaliar(rules=(regra("outro", 1, dominios=frozenset({OUTRO_DOMINIO})),))
    nao_venceu = avaliar()
    assert fora.decision is not nao_venceu.decision
    assert fora.next_due_at is None
    assert nao_venceu.next_due_at is not None


def test_u08_legado_protegido_vence_o_prazo_cumprido():
    """`LEGACY_PROTECTION_OVERRIDES_RETENTION_ELIGIBILITY`.

    Prazo cumprido não revoga escolha do titular.
    """
    r = avaliar(
        candidate=candidato(legacy_protection_state=LegacyProtectionState.PROTECTED),
        evaluated_at=AOS_400_DIAS,
    )
    assert r.decision is RetentionAssessmentDecision.PRESERVE_LEGACY_PROTECTED
    assert r.due_rule_ids == ("curta", "longa"), "as duas venceram, e mesmo assim"
    assert r.next_due_at is None


def test_u09_legado_protegido_tambem_antes_do_prazo():
    r = avaliar(candidate=candidato(legacy_protection_state=LegacyProtectionState.PROTECTED))
    assert r.decision is RetentionAssessmentDecision.PRESERVE_LEGACY_PROTECTED


def test_u10_protegido_fora_de_escopo_continua_fora_de_escopo():
    """A ordem importa: escopo é anterior à proteção."""
    r = avaliar(
        candidate=candidato(legacy_protection_state=LegacyProtectionState.PROTECTED),
        rules=(regra("outro", 1, dominios=frozenset({OUTRO_DOMINIO})),),
    )
    assert r.decision is RetentionAssessmentDecision.OUT_OF_SCOPE


def test_u11_protegido_sob_policy_nao_vigente_e_policy_not_effective():
    r = avaliar(
        candidate=candidato(legacy_protection_state=LegacyProtectionState.PROTECTED),
        policy_effective_from=datetime(2027, 1, 1, tzinfo=UTC),
    )
    assert r.decision is RetentionAssessmentDecision.POLICY_NOT_EFFECTIVE


# ======================================================================
# O máximo, e não o mínimo
# ======================================================================


def test_u12_a_regra_curta_nao_neutraliza_a_longa():
    """`effective_due_at = MAX(due_at)`.

    Com o mínimo, uma regra de 30 dias tornaria avaliável um item que
    outra política vigente ainda pede para preservar por 365.
    """
    r = avaliar()
    assert r.decision is RetentionAssessmentDecision.NOT_YET_DUE
    assert r.applicable_rule_ids == ("curta", "longa")
    assert r.due_rule_ids == ("curta",), "a curta venceu INDIVIDUALMENTE"
    assert r.effective_due_at == NASCIMENTO + timedelta(days=365)
    assert r.next_due_at == r.effective_due_at


def test_u13_elegivel_somente_apos_o_maior_prazo():
    limite = NASCIMENTO + timedelta(days=365)
    antes = avaliar(evaluated_at=limite - timedelta(microseconds=1))
    assert antes.decision is RetentionAssessmentDecision.NOT_YET_DUE
    exato = avaliar(evaluated_at=limite)
    assert exato.decision is RetentionAssessmentDecision.ASSESS_AND_INFORM
    depois = avaliar(evaluated_at=AOS_400_DIAS)
    assert depois.decision is RetentionAssessmentDecision.ASSESS_AND_INFORM


def test_u14_ordem_das_regras_nao_altera_o_resultado():
    direta = avaliar(rules=(regra("curta", 30), regra("longa", 365)))
    inversa = avaliar(rules=(regra("longa", 365), regra("curta", 30)))
    assert direta.decision is inversa.decision
    assert direta.effective_due_at == inversa.effective_due_at
    assert set(direta.applicable_rule_ids) == set(inversa.applicable_rule_ids)


def test_u15_tres_regras_com_prazos_distintos():
    r = avaliar(
        rules=(regra("a", 10), regra("b", 100), regra("c", 1000)),
        evaluated_at=NASCIMENTO + timedelta(days=500),
    )
    assert r.decision is RetentionAssessmentDecision.NOT_YET_DUE
    assert r.due_rule_ids == ("a", "b")
    assert r.effective_due_at == NASCIMENTO + timedelta(days=1000)


def test_u16_escopo_global_alcanca_qualquer_dominio():
    r = avaliar(
        candidate=candidato(domain_id=OUTRO_DOMINIO),
        rules=(regra("global", 30, escopo=RetentionScopeKind.ALL_LOCAL_PATRIMONY),),
        evaluated_at=AOS_60_DIAS,
    )
    assert r.decision is RetentionAssessmentDecision.ASSESS_AND_INFORM
    assert r.applicable_rule_ids == ("global",)


def test_u17_toda_decisao_cita_seu_fundamento():
    """`EVERY_DECISION_CITES_ITS_BASIS`."""
    for r in (
        avaliar(),
        avaliar(evaluated_at=AOS_400_DIAS),
        avaliar(candidate=candidato(legacy_protection_state=LegacyProtectionState.PROTECTED)),
    ):
        assert r.applicable_rule_ids
        assert r.effective_due_at is not None


# ======================================================================
# Pureza
# ======================================================================


def test_u18_o_instante_e_obrigatorio_e_sem_default():
    """`CLOCK_INJECTED = REQUIRED` — um default seria `now()` disfarçado."""
    assinatura = inspect.signature(avaliar_retencao)
    for nome in (
        "candidate",
        "rules",
        "policy_effective_from",
        "policy_effective_until",
        "evaluated_at",
    ):
        assert assinatura.parameters[nome].kind is inspect.Parameter.KEYWORD_ONLY
    assert assinatura.parameters["evaluated_at"].default is inspect.Parameter.empty


def test_u19_mesma_entrada_produz_mesma_saida():
    assert avaliar() == avaliar()
    assert avaliar(evaluated_at=AOS_400_DIAS) == avaliar(evaluated_at=AOS_400_DIAS)


def test_u20_nenhum_relogio_interno():
    import ast

    import app.memory.services.retention_evaluator as modulo

    arvore = ast.parse(inspect.getsource(modulo))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Attribute):
            assert no.attr not in {"now", "utcnow", "today"}, no.attr


def test_u21_a_avaliacao_nao_muta_a_entrada():
    c = candidato()
    regras = (regra("curta", 30), regra("longa", 365))
    antes = (dataclasses.asdict(c), tuple(r.rule_id for r in regras))
    avaliar(candidate=c, rules=regras)
    assert (dataclasses.asdict(c), tuple(r.rule_id for r in regras)) == antes


# ======================================================================
# Invariantes de tipo e de resultado
# ======================================================================


def test_u22_candidato_exige_protecao_sem_default():
    campo = next(
        c for c in dataclasses.fields(RetentionCandidate) if c.name == "legacy_protection_state"
    )
    assert campo.default is dataclasses.MISSING
    assert campo.default_factory is dataclasses.MISSING
    with pytest.raises(TypeError):
        RetentionCandidate(  # type: ignore[call-arg]
            subject_coid=SUJEITO, domain_id=DOMINIO, created_at=NASCIMENTO
        )


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("subject_coid", "coid"),
        ("domain_id", 1),
        ("created_at", datetime(2026, 1, 1)),
        ("legacy_protection_state", "protected"),
    ],
)
def test_u23_candidato_recusa_tipo_equivalente(campo, valor):
    with pytest.raises((TypeError, ValueError)):
        candidato(**{campo: valor})


def test_u24_item_nao_e_avaliado_antes_de_existir():
    with pytest.raises(ValueError, match="posterior a evaluated_at"):
        avaliar(candidate=candidato(created_at=AOS_400_DIAS))


def test_u25_janela_invertida_ou_vazia_e_recusada():
    for fim in (VIGENCIA, VIGENCIA - timedelta(days=1)):
        with pytest.raises(ValueError, match="posterior a policy_effective_from"):
            avaliar(policy_effective_until=fim)


@pytest.mark.parametrize(
    "campo", ["policy_effective_from", "policy_effective_until", "evaluated_at"]
)
def test_u26_instantes_exigem_timezone(campo):
    with pytest.raises(ValueError, match="timezone-aware"):
        avaliar(**{campo: datetime(2026, 6, 1)})


def test_u27_regras_exigem_tupla_e_tipo_real():
    with pytest.raises(TypeError, match="tuple"):
        avaliar(rules=[regra("curta", 30)])
    with pytest.raises(TypeError, match="RetentionRule"):
        avaliar(rules=("curta",))


def test_u28_next_due_at_so_existe_em_not_yet_due():
    for decisao, resultado in (
        (RetentionAssessmentDecision.NOT_YET_DUE, avaliar()),
        (RetentionAssessmentDecision.ASSESS_AND_INFORM, avaliar(evaluated_at=AOS_400_DIAS)),
        (RetentionAssessmentDecision.OUT_OF_SCOPE, avaliar(rules=())),
    ):
        assert resultado.decision is decisao
        if decisao is RetentionAssessmentDecision.NOT_YET_DUE:
            assert resultado.next_due_at == resultado.effective_due_at
        else:
            assert resultado.next_due_at is None


def test_u29_resultado_incoerente_e_recusado_no_construtor():
    # ATUALIZADO NA E4.9.9.c.1: a matriz recusa este objeto por FALTAR
    # `effective_due_at`, antes de olhar `next_due_at`. O caso do
    # `next_due_at` indevido em `assess_and_inform` passou a ser exercido
    # com o objeto no mais completo, em `u38`.
    with pytest.raises(ValueError, match="exige effective_due_at"):
        RetentionAssessment(
            decision=RetentionAssessmentDecision.ASSESS_AND_INFORM,
            subject_coid=SUJEITO,
            evaluated_at=AOS_60_DIAS,
            applicable_rule_ids=("a",),
            next_due_at=AOS_400_DIAS,
        )
    with pytest.raises(ValueError, match="exige effective_due_at"):
        RetentionAssessment(
            decision=RetentionAssessmentDecision.NOT_YET_DUE,
            subject_coid=SUJEITO,
            evaluated_at=AOS_60_DIAS,
            applicable_rule_ids=("a",),
        )
    with pytest.raises(ValueError, match="não é aplicável"):
        RetentionAssessment(
            decision=RetentionAssessmentDecision.NOT_YET_DUE,
            subject_coid=SUJEITO,
            evaluated_at=AOS_60_DIAS,
            applicable_rule_ids=("a", "b"),
            due_rule_ids=("c",),
            effective_due_at=AOS_400_DIAS,
            next_due_at=AOS_400_DIAS,
        )


def test_u30_resultado_e_congelado_e_sem_colecao_mutavel():
    r = avaliar()
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.__setattr__("decision", RetentionAssessmentDecision.ASSESS_AND_INFORM)  # noqa: PLC2801
    for valor in vars(r).values():
        assert not isinstance(valor, list | dict | set)


def test_u31_o_resultado_nao_carrega_conteudo_nem_localizador():
    campos = {c.name for c in dataclasses.fields(RetentionAssessment)}
    campos |= {c.name for c in dataclasses.fields(RetentionCandidate)}
    for proibido in (
        "content",
        "payload",
        "transient_locator",
        "capability",
        "credential",
        "executor_ref",
        "principal_ref",
    ):
        assert proibido not in campos


def test_u32_a_avaliacao_nao_forma_aprovacao_nem_recibo():
    """`EVALUATION != DISPOSITION`."""
    import app.memory.services.retention_evaluator as modulo

    fonte = inspect.getsource(modulo)
    for proibido in (
        "DestructiveApprovalProposal",
        "DestructiveApprovalEnvelope",
        "ApprovalRecord",
        "ErasureRecord",
        "ErasureEffectPort",
        "append_observed",
    ):
        assert proibido not in fonte


# ======================================================================
# Fronteiras de tipo — construtor direto, não só a fábrica
# ======================================================================


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("decision", "not_yet_due", "RetentionAssessmentDecision"),
        ("subject_coid", "coid", "UUID"),
        ("evaluated_at", datetime(2026, 6, 1), "timezone-aware"),
        ("evaluated_at", "2026-06-01", "datetime"),
        ("applicable_rule_ids", ["a"], "tuple"),
        ("due_rule_ids", ["a"], "tuple"),
    ],
)
def test_u33_resultado_recusa_tipo_no_construtor_direto(campo, valor, trecho):
    """A lição repetida desde a E4.2.1: invariante que só vive na fábrica
    é contornável pelo construtor direto."""
    base: dict[str, object] = {
        "decision": RetentionAssessmentDecision.OUT_OF_SCOPE,
        "subject_coid": SUJEITO,
        "evaluated_at": AOS_60_DIAS,
    }
    base[campo] = valor
    with pytest.raises((TypeError, ValueError), match=trecho):
        RetentionAssessment(**base)  # type: ignore[arg-type]


def test_u34_avaliador_recusa_candidato_de_outro_tipo():
    with pytest.raises(TypeError, match="RetentionCandidate"):
        avaliar(candidate={"subject_coid": SUJEITO})


def test_u35_effective_due_at_e_next_due_at_exigem_timezone():
    for campo in ("effective_due_at", "next_due_at"):
        with pytest.raises(ValueError, match="timezone-aware"):
            RetentionAssessment(
                decision=RetentionAssessmentDecision.NOT_YET_DUE,
                subject_coid=SUJEITO,
                evaluated_at=AOS_60_DIAS,
                applicable_rule_ids=("a",),
                **{campo: datetime(2026, 6, 1)},  # type: ignore[arg-type]
            )


# ======================================================================
# E4.9.9.c.1 — os dois defeitos que a auditoria encontrou
#
# ```text
# COLLECTION_TYPE_CHECK != CANONICAL_COLLECTION_VALIDATION
# UNIQUE_RULE_ID_REQUIRED_BEFORE_DICTIONARY_INDEXING
# CORRECT_FACTORY_OUTPUT != SAFE_PUBLIC_RESULT_CONSTRUCTOR
# PUBLIC_RESULT_CONSTRUCTOR_ENFORCES_DECISION_MATRIX
# ```
# ======================================================================


def _duplicada(dias: int) -> RetentionRule:
    """Duas regras com o MESMO `rule_id` e prazos diferentes."""
    return regra("MESMO_ID", dias)


def test_u36_duplicata_de_rule_id_e_recusada_na_ordem_longa_curta():
    with pytest.raises(ValueError, match="duplicado"):
        avaliar(rules=(_duplicada(365), _duplicada(30)))


def test_u37_duplicata_e_recusada_identicamente_na_ordem_inversa():
    """As duas ordens falham com o **mesmo** erro, antes de qualquer prazo.

    O defeito da cadeia 92: o avaliador indexa vencimentos por `rule_id`,
    e com duplicata o dicionário sobrescrevia uma entrada — a ordem de
    declaração passava a mudar a decisão.

    ```text
    (365, 30) -> ASSESS_AND_INFORM
    (30, 365) -> NOT_YET_DUE
    ```

    Meu `u14` alegava que a ordem não altera o resultado, e usava
    `rule_id` DISTINTOS — nunca construiu o caso que quebrava.

    ```text
    TESTED_CASE != TESTED_PROPERTY
    ```
    """
    with pytest.raises(ValueError) as longa_curta:
        avaliar(rules=(_duplicada(365), _duplicada(30)))
    with pytest.raises(ValueError) as curta_longa:
        avaliar(rules=(_duplicada(30), _duplicada(365)))
    assert str(longa_curta.value) == str(curta_longa.value)
    assert "duplicado" in str(curta_longa.value)


def test_u38_o_validador_canonico_e_reutilizado_e_nao_reimplementado():
    """`validar_regras_retencao` é o contrato único desde a E4.9.6.2."""
    import ast
    import inspect

    import app.memory.services.retention_evaluator as modulo

    fonte = inspect.getsource(modulo)
    chamadas = {
        no.func.id
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
    }
    assert "validar_regras_retencao" in chamadas
    assert "validar_identificador_opaco" in chamadas
    # nenhuma reimplementação local de unicidade sobre as REGRAS
    assert "rule_ids_vistos" not in fonte
    assert "duplicado na mesma versão" not in fonte


def test_u39_colecao_vazia_continua_out_of_scope():
    """`EMPTY_RULES → OUT_OF_SCOPE` — o validador canônico exige regra.

    Ausência de regra nunca vira elegibilidade nem erro.
    """
    r = avaliar(rules=(), evaluated_at=AOS_400_DIAS)
    assert r.decision is RetentionAssessmentDecision.OUT_OF_SCOPE


def test_u40_colecao_valida_preserva_a_ordem_declarada():
    """O validador canônico devolve a mesma tupla, sem reordenar."""
    r = avaliar(rules=(regra("z", 30), regra("a", 365)))
    assert r.applicable_rule_ids == ("z", "a")


def test_u41_o_caminho_nominal_de_30_365_continua_identico():
    """A correção não pode alterar o comportamento já auditado."""
    r = avaliar()
    assert r.decision is RetentionAssessmentDecision.NOT_YET_DUE
    assert r.applicable_rule_ids == ("curta", "longa")
    assert r.due_rule_ids == ("curta",)
    assert r.effective_due_at == NASCIMENTO + timedelta(days=365)
    assert r.next_due_at == r.effective_due_at


# --- a matriz das cinco decisões, no construtor público ------------------


def _resultado(**over: object) -> RetentionAssessment:
    base: dict[str, object] = {
        "decision": RetentionAssessmentDecision.OUT_OF_SCOPE,
        "subject_coid": SUJEITO,
        "evaluated_at": AOS_60_DIAS,
    }
    base.update(over)
    return RetentionAssessment(**base)  # type: ignore[arg-type]


PASSADO = NASCIMENTO
FUTURO = AOS_400_DIAS


@pytest.mark.parametrize(
    "coerente",
    [
        {"decision": RetentionAssessmentDecision.POLICY_NOT_EFFECTIVE},
        {"decision": RetentionAssessmentDecision.OUT_OF_SCOPE},
        {
            "decision": RetentionAssessmentDecision.PRESERVE_LEGACY_PROTECTED,
            "applicable_rule_ids": ("r",),
            "effective_due_at": FUTURO,
        },
        {
            "decision": RetentionAssessmentDecision.PRESERVE_LEGACY_PROTECTED,
            "applicable_rule_ids": ("r",),
            "due_rule_ids": ("r",),
            "effective_due_at": PASSADO,
        },
        {
            "decision": RetentionAssessmentDecision.NOT_YET_DUE,
            "applicable_rule_ids": ("r",),
            "effective_due_at": FUTURO,
            "next_due_at": FUTURO,
        },
        {
            "decision": RetentionAssessmentDecision.ASSESS_AND_INFORM,
            "applicable_rule_ids": ("a", "b"),
            "due_rule_ids": ("a", "b"),
            "effective_due_at": PASSADO,
        },
    ],
)
def test_u42_cada_decisao_aceita_sua_forma_coerente(coerente):
    assert _resultado(**coerente)


def test_u43_protecao_de_legado_nao_impoe_relacao_temporal():
    """Item protegido pode estar **antes ou depois** do prazo.

    A proteção vale nos dois casos, e exigir uma relação temporal aqui
    inventaria uma regra que a E4.9.8.3 não estabeleceu.
    """
    for prazo in (PASSADO, FUTURO):
        assert _resultado(
            decision=RetentionAssessmentDecision.PRESERVE_LEGACY_PROTECTED,
            applicable_rule_ids=("r",),
            due_rule_ids=("r",) if prazo is PASSADO else (),
            effective_due_at=prazo,
        )


@pytest.mark.parametrize(
    ("rotulo", "impossivel", "trecho"),
    [
        (
            "assess sem fundamento",
            {"decision": RetentionAssessmentDecision.ASSESS_AND_INFORM},
            "exige applicable_rule_ids",
        ),
        (
            "out_of_scope com fundamento",
            {"applicable_rule_ids": ("r",)},
            "não cita regra",
        ),
        (
            "out_of_scope com prazo",
            {"effective_due_at": PASSADO},
            "não carrega prazo",
        ),
        (
            "policy_not_effective com prazo",
            {
                "decision": RetentionAssessmentDecision.POLICY_NOT_EFFECTIVE,
                "effective_due_at": PASSADO,
            },
            "não carrega prazo",
        ),
        (
            "preserve sem prazo efetivo",
            {
                "decision": RetentionAssessmentDecision.PRESERVE_LEGACY_PROTECTED,
                "applicable_rule_ids": ("r",),
            },
            "exige effective_due_at",
        ),
        (
            "preserve com next_due_at",
            {
                "decision": RetentionAssessmentDecision.PRESERVE_LEGACY_PROTECTED,
                "applicable_rule_ids": ("r",),
                "effective_due_at": FUTURO,
                "next_due_at": FUTURO,
            },
            "não carrega next_due_at",
        ),
        (
            "not_yet_due com prazo no passado",
            {
                "decision": RetentionAssessmentDecision.NOT_YET_DUE,
                "applicable_rule_ids": ("r",),
                "effective_due_at": PASSADO,
                "next_due_at": PASSADO,
            },
            "posterior a evaluated_at",
        ),
        (
            "assess com prazo no futuro",
            {
                "decision": RetentionAssessmentDecision.ASSESS_AND_INFORM,
                "applicable_rule_ids": ("r",),
                "due_rule_ids": ("r",),
                "effective_due_at": FUTURO,
            },
            "não posterior a",
        ),
        (
            "assess com due != applicable",
            {
                "decision": RetentionAssessmentDecision.ASSESS_AND_INFORM,
                "applicable_rule_ids": ("a", "b"),
                "due_rule_ids": ("a",),
                "effective_due_at": PASSADO,
            },
            "igual a applicable_rule_ids",
        ),
        (
            "assess com next_due_at",
            {
                "decision": RetentionAssessmentDecision.ASSESS_AND_INFORM,
                "applicable_rule_ids": ("a",),
                "due_rule_ids": ("a",),
                "effective_due_at": PASSADO,
                "next_due_at": FUTURO,
            },
            "não carrega next_due_at",
        ),
    ],
)
def test_u44_cada_celula_proibida_falha_no_construtor_direto(rotulo, impossivel, trecho):
    """Cada célula proibida da matriz falha pelo construtor **direto**."""
    with pytest.raises(ValueError, match=trecho):
        _resultado(**impossivel)


@pytest.mark.parametrize("campo", ["applicable_rule_ids", "due_rule_ids"])
@pytest.mark.parametrize("valor", [(123,), ("",), ("   ",), ("\u200b",), (None,)])
def test_u45_ids_devem_ser_texto_opaco_valido(campo, valor):
    base: dict[str, object] = {
        "decision": RetentionAssessmentDecision.PRESERVE_LEGACY_PROTECTED,
        "applicable_rule_ids": ("r",),
        "effective_due_at": FUTURO,
    }
    if campo == "due_rule_ids":
        base["due_rule_ids"] = valor
        base["applicable_rule_ids"] = ("r", *[v for v in valor if isinstance(v, str)])
    else:
        base[campo] = valor
    with pytest.raises((TypeError, ValueError)):
        _resultado(**base)


@pytest.mark.parametrize("campo", ["applicable_rule_ids", "due_rule_ids"])
def test_u46_ids_duplicados_sao_recusados_nas_duas_tuplas(campo):
    base: dict[str, object] = {
        "decision": RetentionAssessmentDecision.ASSESS_AND_INFORM,
        "applicable_rule_ids": ("r",),
        "due_rule_ids": ("r",),
        "effective_due_at": PASSADO,
    }
    base[campo] = ("r", "r")
    if campo == "applicable_rule_ids":
        base["due_rule_ids"] = ("r", "r")
    with pytest.raises(ValueError, match="duplicado"):
        _resultado(**base)


def test_u47_replace_revalida_a_matriz():
    valido = _resultado(
        decision=RetentionAssessmentDecision.NOT_YET_DUE,
        applicable_rule_ids=("r",),
        effective_due_at=FUTURO,
        next_due_at=FUTURO,
    )
    with pytest.raises(ValueError, match="não carrega next_due_at"):
        dataclasses.replace(valido, decision=RetentionAssessmentDecision.ASSESS_AND_INFORM)
    with pytest.raises(ValueError, match="duplicado"):
        dataclasses.replace(valido, applicable_rule_ids=("r", "r"))
    with pytest.raises(ValueError, match="posterior a evaluated_at"):
        dataclasses.replace(valido, effective_due_at=PASSADO, next_due_at=PASSADO)


def test_u48_not_yet_due_exige_next_due_at_igual_ao_prazo_efetivo():
    """Informar um vencimento diferente do efetivo desorientaria quem lê."""
    with pytest.raises(ValueError, match="igual a effective_due_at"):
        _resultado(
            decision=RetentionAssessmentDecision.NOT_YET_DUE,
            applicable_rule_ids=("r",),
            effective_due_at=FUTURO,
            next_due_at=FUTURO + timedelta(days=1),
        )
    with pytest.raises(ValueError, match="igual a effective_due_at"):
        _resultado(
            decision=RetentionAssessmentDecision.NOT_YET_DUE,
            applicable_rule_ids=("r",),
            effective_due_at=FUTURO,
        )
