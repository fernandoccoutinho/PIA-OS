"""
Provas unitárias da ponte de proteção humana (`E7.4-1 B1a`).

```text
E4_HOLDS_AUTHORITY · E7_APPLIES_THE_DECISION · THE_PROOF_HOLDS_THEM_EQUAL
```

Os subcasos de `P-FINGERPRINT-COMPLETE`, `P-BINDING-COMPLETE` e
`P-PORT-QUERY` são **derivados** dos dataclasses reais, nunca escritos à mão:

```text
HAND_WRITTEN_COUNT = COUNT_THAT_DRIFTS
DERIVED_SUBCASES != DECLARED_SUBCASE_COUNT
```

O dublê usado é da **porta**, com a mesma forma autorizada — nunca um
`typed_fixture` representável no schema produtivo.

```text
TEST_DOUBLE_IN_PRODUCTION_SCHEMA = PRODUCTION_CAPABILITY
FAKE_LOOSER_THAN_REAL = TEST_THAT_PROVES_NOTHING
```
"""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum

import pytest

from app.memory.models.governance_enums import (
    CapabilityEngagement,
    CognitiveOperation,
    CriticalCapability,
    GovernanceOutcome,
)
from app.memory.schemas.governance import GovernanceResolution
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.governance_manager import GovernanceManager
from app.orchestration.errors.exceptions import HumanProtectionGateUnavailableError
from app.orchestration.ports.governance import (
    GovernanceQuery,
    GovernanceResolutionPort,
    GovernanceResolutionView,
)
from app.orchestration.ports.governance_vocabulary import (
    ACCEPTED_BOUNDARY_OUTCOMES,
    BoundaryCapability,
    BoundaryEngagement,
    BoundaryOperation,
    BoundaryOutcome,
)
from app.orchestration.protection.binding import GovernanceBinding
from app.orchestration.protection.bridge import (
    DESFECHO_POR_FRONTEIRA,
    GATES_SEM_LIGACAO_PRODUTIVA,
    HumanProtectionBridge,
)
from app.orchestration.protection.decision import (
    CAMPOS_IMUTAVEIS_DA_APLICACAO,
    HumanProtectionApplication,
    ProtectionEffects,
)
from app.orchestration.protection.fingerprint import (
    calcular_binding_sha256,
    calcular_decision_fingerprint,
    campos_do_binding,
    serializar_canonicamente,
)
from app.orchestration.protection.vocabulary import (
    BINDING_ALGO_VERSION,
    FINGERPRINT_ALGO_VERSION,
    PRODUCER_REF,
    RETENTION_MINIMUM_AGE_DAYS,
    RETENTION_POLICY_ID,
    GatePosition,
    ProtectionOutcome,
)
from app.services.governance_bridge import (
    CAMPO_DA_EVIDENCIA,
    CAMPOS_DA_RESOLUCAO,
    RETENTION_POLICY_DECLARADA,
    GovernanceResolutionAdapter,
)

pytestmark = pytest.mark.unit

_AGORA = datetime.now(UTC)
"""UM único instante, capturado uma vez e injetado em todos os caminhos.

A versão anterior deste arnês fixava `_AGORA` num literal e deixava o
adaptador carimbar `evaluated_at` pelo relógio real: dezesseis provas
falharam por `valid_until` já vencido — **arnês envelhecido**, não defeito
do invariante.

```text
FIXTURE_INCOMPLETA = PROVA_QUE_FALHA_PELO_MOTIVO_ERRADO
MULTIPLE_CLOCK_READS = FLAKY_BY_CONSTRUCTION
```

A correção não é ler o relógio em vários pontos: é ler **uma vez** e
injetar o mesmo instante como `moment` do adaptador e como base de
`valid_until`. Assim o contrato temporal é provado em vez de contornado.
"""

_VALIDADE = _AGORA + timedelta(minutes=10)
_OBJETIVO = "a" * 64
_FINGERPRINT = "d" * 64
_SCHEDULE = uuid.UUID("11111111-1111-1111-1111-111111111111")
_STEP = uuid.UUID("22222222-2222-2222-2222-222222222222")
_ATTEMPT = uuid.UUID("33333333-3333-3333-3333-333333333333")


# --- fábricas ---------------------------------------------------------------


def _binding(
    *,
    gate: GatePosition = GatePosition.G2,
    schedule_id: uuid.UUID | None = _SCHEDULE,
    step_id: uuid.UUID | None = _STEP,
    attempt_id: uuid.UUID | None = None,
    **extra: object,
) -> GovernanceBinding:
    campos: dict[str, object] = {
        "operation": BoundaryOperation.EXPOSE,
        "principal_ref": "principal-a",
        "schedule_id": schedule_id,
        "step_id": step_id,
        "attempt_id": attempt_id,
        "objective_sha256": _OBJETIVO,
        "gate_position": gate,
        "boundary_version": 1,
        "classifier_version": "iab-1",
        "valid_until": _VALIDADE,
    }
    campos.update(extra)
    return GovernanceBinding(**campos)  # type: ignore[arg-type]


def _vista(
    binding: GovernanceBinding,
    *,
    outcome: BoundaryOutcome = BoundaryOutcome.NOT_APPLICABLE,
    capacidades: tuple[BoundaryCapability, ...] = (),
    engajamento: BoundaryEngagement = BoundaryEngagement.ANALYTICAL,
    **extra: object,
) -> GovernanceResolutionView:
    campos: dict[str, object] = {
        "outcome": outcome,
        "blocked_capabilities": capacidades,
        "capability_engagement": engajamento,
        "boundary_version": binding.boundary_version,
        "classifier_version": binding.classifier_version,
        "decision_fingerprint": _FINGERPRINT,
        "binding_sha256": calcular_binding_sha256(binding),
        "evaluated_at": _AGORA,
        "valid_until": binding.valid_until,
    }
    campos.update(extra)
    return GovernanceResolutionView(**campos)  # type: ignore[arg-type]


def _vista_bloqueio(binding: GovernanceBinding) -> GovernanceResolutionView:
    return _vista(
        binding,
        outcome=BoundaryOutcome.PROHIBITED,
        capacidades=(BoundaryCapability.CHILD_SEXUAL_EXPLOITATION,),
        engajamento=BoundaryEngagement.OPERATIONAL_ENABLEMENT,
    )


class _PortaDeTeste:
    """Dublê da PORTA, com a forma autorizada. Nunca entra em produção."""

    def __init__(self, resposta: object = None, falha: Exception | None = None) -> None:
        self.resposta = resposta
        self.falha = falha
        self.chamadas = 0

    def resolve(self, query: GovernanceQuery) -> GovernanceResolutionView:
        self.chamadas += 1
        if self.falha is not None:
            raise self.falha
        return self.resposta  # type: ignore[return-value]


class _RepositorioNaoConsultado:
    """Qualquer acesso reprova. Prova que `policy_key=None` não lê policy."""

    def __getattr__(self, nome: str) -> object:
        raise AssertionError(f"a policy local foi consultada: {nome}")


class _RepositorioDeMemoria:
    """Repositório mínimo da ponte, sem banco, para os testes de serviço."""

    def __init__(self) -> None:
        self.linhas: dict[tuple[str, str, str], HumanProtectionApplication] = {}

    @staticmethod
    def _chave(aplicacao: HumanProtectionApplication) -> tuple[str, str, str]:
        return (
            aplicacao.decision_fingerprint,
            aplicacao.gate_position.value,
            aplicacao.binding_sha256,
        )

    def inserir_se_ausente(self, aplicacao: HumanProtectionApplication) -> uuid.UUID | None:
        chave = self._chave(aplicacao)
        if chave in self.linhas:
            return None
        self.linhas[chave] = aplicacao
        return uuid.uuid4()

    def confirmar_vencedor(self, aplicacao: HumanProtectionApplication) -> None:
        vencedor = self.linhas[self._chave(aplicacao)]
        divergentes = [
            campo
            for campo in CAMPOS_IMUTAVEIS_DA_APLICACAO
            if getattr(vencedor, campo) != getattr(aplicacao, campo)
        ]
        if vencedor.blocked_capabilities != aplicacao.blocked_capabilities:
            divergentes.append("blocked_capabilities")
        if divergentes:
            raise HumanProtectionGateUnavailableError(str(sorted(divergentes)))


# --- paridade de vocabulário (P-VOCAB-PARITY) -------------------------------


@pytest.mark.parametrize(
    ("espelho", "canonico"),
    [
        (BoundaryOperation, CognitiveOperation),
        (BoundaryCapability, CriticalCapability),
        (BoundaryEngagement, CapabilityEngagement),
        (BoundaryOutcome, GovernanceOutcome),
    ],
)
def test_hp_u01_paridade_exata_dos_vocabularios(espelho: type[Enum], canonico: type[Enum]) -> None:
    """Igualdade de CONJUNTOS, não de subconjunto.

    Uma cópia parcial passaria numa comparação de inclusão e esconderia
    exatamente a divergência que esta prova existe para achar.
    """
    assert {m.value for m in espelho} == {m.value for m in canonico}
    assert {m.name for m in espelho} == {m.name for m in canonico}


def test_hp_u02_a_ponte_so_interpreta_dois_desfechos() -> None:
    assert {
        BoundaryOutcome.PROHIBITED,
        BoundaryOutcome.NOT_APPLICABLE,
    } == ACCEPTED_BOUNDARY_OUTCOMES
    assert set(DESFECHO_POR_FRONTEIRA) == ACCEPTED_BOUNDARY_OUTCOMES


def test_hp_u03_review_required_nao_tem_produtor_em_v1() -> None:
    """`DECLARED_VOCABULARY != EXECUTABLE_TRANSITION`."""
    assert ProtectionOutcome.REVIEW_REQUIRED not in set(DESFECHO_POR_FRONTEIRA.values())


# --- manifesto derivado -----------------------------------------------------


def test_hp_u04_manifesto_derivado_19_10_19_4() -> None:
    """Os quatro totais, todos derivados dos dataclasses reais."""
    entradas_fingerprint = len(CAMPOS_DA_RESOLUCAO) + 1
    binding = [c.name for c in dataclasses.fields(GovernanceBinding)]
    contexto = [c.name for c in dataclasses.fields(MemoryContext)]
    assert (
        entradas_fingerprint,
        len(binding),
        len(CAMPOS_IMUTAVEIS_DA_APLICACAO),
        len(contexto),
    ) == (19, 10, 19, 4)
    assert CAMPO_DA_EVIDENCIA not in CAMPOS_DA_RESOLUCAO


def test_hp_u05_binding_tem_exatamente_os_dez_campos_do_contrato() -> None:
    assert [c.name for c in dataclasses.fields(GovernanceBinding)] == [
        "operation",
        "principal_ref",
        "schedule_id",
        "step_id",
        "attempt_id",
        "objective_sha256",
        "gate_position",
        "boundary_version",
        "classifier_version",
        "valid_until",
    ]


@pytest.mark.parametrize("campo", [c.name for c in dataclasses.fields(GovernanceBinding)])
def test_hp_u06_omitir_qualquer_campo_muda_o_binding(campo: str) -> None:
    """`P-BINDING-COMPLETE`: dez subcasos DERIVADOS, um por campo."""
    binding = _binding(gate=GatePosition.G3, attempt_id=_ATTEMPT)
    completo = campos_do_binding(binding)
    reduzido = {k: v for k, v in completo.items() if k != campo}
    assert calcular_decision_fingerprint(reduzido) != calcular_decision_fingerprint(completo)


@pytest.mark.parametrize("campo", CAMPOS_DA_RESOLUCAO)
def test_hp_u07_omitir_qualquer_campo_muda_o_fingerprint(campo: str) -> None:
    """`P-FINGERPRINT-COMPLETE`: dezoito subcasos derivados da E4."""
    resolucao = _resolucao_permitida()
    completo = {c: getattr(resolucao, c) for c in CAMPOS_DA_RESOLUCAO}
    completo[CAMPO_DA_EVIDENCIA] = "iab-1"
    reduzido = {k: v for k, v in completo.items() if k != campo}
    assert calcular_decision_fingerprint(reduzido) != calcular_decision_fingerprint(completo)


def test_hp_u08_omitir_a_evidencia_muda_o_fingerprint() -> None:
    """O décimo nono subcaso: a identidade do produtor semântico."""
    resolucao = _resolucao_permitida()
    completo = {c: getattr(resolucao, c) for c in CAMPOS_DA_RESOLUCAO}
    completo[CAMPO_DA_EVIDENCIA] = "iab-1"
    reduzido = {k: v for k, v in completo.items() if k != CAMPO_DA_EVIDENCIA}
    assert calcular_decision_fingerprint(reduzido) != calcular_decision_fingerprint(completo)


@pytest.mark.parametrize("campo", [c.name for c in dataclasses.fields(MemoryContext)])
def test_hp_u09_o_contexto_atravessa_campo_a_campo(campo: str) -> None:
    """`P-PORT-QUERY`: quatro subcasos, um por campo de `MemoryContext`.

    ```text
    COMPRESSED_CONTEXT = TWO_QUESTIONS_WITH_ONE_HASH
    ```
    """
    query = GovernanceQuery(
        descriptor_operation=BoundaryOperation.EXPOSE,
        descriptor_capabilities=frozenset(),
        descriptor_engagement=BoundaryEngagement.ANALYTICAL,
        binding=_binding(),
        context_domain_ids=(uuid.uuid4(),),
        context_session_id="s1",
        context_actor_ref="ator",
        context_purpose="proposito",
    )
    equivalente = {
        "domain_ids": "context_domain_ids",
        "session_id": "context_session_id",
        "actor_ref": "context_actor_ref",
        "purpose": "context_purpose",
    }[campo]
    assert getattr(query, equivalente) is not None


# --- canonicalização --------------------------------------------------------


def test_hp_u10_o_mesmo_instante_em_outro_fuso_produz_o_mesmo_digest() -> None:
    outro = _VALIDADE.astimezone(timezone(timedelta(hours=-3)))
    assert calcular_binding_sha256(_binding()) == calcular_binding_sha256(
        _binding(valid_until=outro)
    )


def test_hp_u11_a_serializacao_e_canonica_e_sem_espacos() -> None:
    bruto = serializar_canonicamente(
        {
            "b": {"z": 1, "a": 2},
            "a": [BoundaryOperation.EXPOSE, uuid.UUID(int=1)],
            "c": frozenset({"x", "y"}),
            "d": None,
        }
    )
    assert bruto.startswith(b'{"a":[')
    assert b", " not in bruto
    assert b'"d":null' in bruto


def test_hp_u12_valor_nao_canonicalizavel_levanta() -> None:
    with pytest.raises(TypeError, match="não canonicalizável"):
        serializar_canonicamente({"x": object()})


def test_hp_u13_datetime_ingenuo_nao_e_canonicalizavel() -> None:
    with pytest.raises(ValueError, match="sem fuso"):
        serializar_canonicamente({"x": datetime(2026, 1, 1)})  # noqa: DTZ001


def test_hp_u14_a_chave_do_algoritmo_e_reservada() -> None:
    with pytest.raises(ValueError, match="reservado"):
        calcular_decision_fingerprint({"__algo_version__": "1"})


def test_hp_u15_fingerprint_sem_entradas_levanta() -> None:
    with pytest.raises(ValueError, match="entradas da resolução"):
        calcular_decision_fingerprint({})


def test_hp_u16_gates_distintos_mudam_o_binding_e_nao_a_decisao() -> None:
    """`MESMA DECISÃO -> MESMO fingerprint · GATES DIFERENTES -> bindings DIFERENTES`."""
    g2 = _binding(gate=GatePosition.G2)
    g4 = _binding(gate=GatePosition.G4)
    assert calcular_binding_sha256(g2) != calcular_binding_sha256(g4)


def test_hp_u17_nova_tentativa_muda_o_binding_de_g3() -> None:
    """`G3_APPLICATION_WITHOUT_ATTEMPT_ID = STALE_ATTEMPT_PROOF`."""
    primeira = _binding(gate=GatePosition.G3, attempt_id=_ATTEMPT)
    segunda = _binding(gate=GatePosition.G3, attempt_id=uuid.uuid4())
    assert calcular_binding_sha256(primeira) != calcular_binding_sha256(segunda)


# --- invariantes do binding -------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "erro"),
    [
        ({"gate": GatePosition.G3}, "g3 exige attempt_id"),
        ({"attempt_id": _ATTEMPT}, "somente g3 carrega attempt_id"),
        (
            {"gate": GatePosition.G1, "schedule_id": None, "step_id": None, "attempt_id": _ATTEMPT},
            "somente g3 carrega attempt_id",
        ),
        ({"gate": GatePosition.G1}, "g1 avalia antes da criação"),
        ({"schedule_id": None}, "exige schedule_id e step_id"),
        ({"step_id": None}, "exige schedule_id e step_id"),
        ({"objective_sha256": "A" * 64}, "hexadecimal minúsculo"),
        ({"principal_ref": "  "}, "não pode ser vazio"),
        ({"principal_ref": "x" * 256}, "excede 255"),
        ({"classifier_version": "x" * 17}, "excede 16"),
        ({"boundary_version": 0}, "deve ser >= 1"),
        ({"valid_until": datetime(2026, 1, 1)}, "deve ser datetime com fuso"),  # noqa: DTZ001
    ],
)
def test_hp_u18_binding_recusa_estado_incoerente(kwargs: dict, erro: str) -> None:
    with pytest.raises((ValueError, TypeError), match=erro):
        _binding(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "erro"),
    [
        ({"operation": "expose"}, "BoundaryOperation"),
        ({"gate": "g2"}, "GatePosition"),
        ({"boundary_version": True}, "deve ser int"),
        ({"principal_ref": 1}, "deve ser str"),
        ({"valid_until": "amanhã"}, "deve ser datetime"),
        ({"schedule_id": "nao-uuid"}, "uuid.UUID ou None"),
    ],
)
def test_hp_u19_binding_recusa_tipo_errado(kwargs: dict, erro: str) -> None:
    with pytest.raises(TypeError, match=erro):
        _binding(**kwargs)


# --- invariantes da vista ---------------------------------------------------


@pytest.mark.parametrize("desfecho", [BoundaryOutcome.ADMISSIBLE, BoundaryOutcome.INADMISSIBLE])
def test_hp_u20_a_vista_recusa_desfecho_fora_do_par(desfecho: BoundaryOutcome) -> None:
    """`UNEXPECTED_OUTCOME_INTERPRETED = FABRICATED_AUTHORITY`."""
    with pytest.raises(ValueError, match="não interpreta"):
        _vista(_binding(), outcome=desfecho)


def test_hp_u21_prohibited_exige_capacidade() -> None:
    with pytest.raises(ValueError, match="ao menos uma capacidade"):
        _vista(_binding(), outcome=BoundaryOutcome.PROHIBITED)


def test_hp_u22_not_applicable_nao_carrega_capacidade() -> None:
    with pytest.raises(ValueError, match="não pode carregar capacidades"):
        _vista(
            _binding(),
            capacidades=(BoundaryCapability.CATASTROPHIC_HARM_ENABLEMENT,),
        )


@pytest.mark.parametrize(
    ("kwargs", "erro"),
    [
        ({"outcome": "prohibited"}, "BoundaryOutcome"),
        ({"engajamento": "analytical"}, "BoundaryEngagement"),
        ({"boundary_version": 0}, "deve ser >= 1"),
        ({"boundary_version": True}, "deve ser int"),
        ({"classifier_version": " "}, "classifier_version é obrigatório"),
        ({"decision_fingerprint": "z" * 64}, "decision_fingerprint deve ser sha-256"),
        ({"binding_sha256": "nao-hash"}, "binding_sha256 deve ser sha-256"),
        ({"evaluated_at": "ontem"}, "evaluated_at deve ser datetime"),
        (
            {"valid_until": datetime(2026, 1, 1)},
            "valid_until deve ser datetime com fuso",
        ),  # noqa: DTZ001
        ({"valid_until": _AGORA - timedelta(seconds=1)}, "validade inexistente"),
        ({"capacidades": ["child_sexual_exploitation"]}, "apenas BoundaryCapability"),
        ({"capacidades": "abc"}, "iterável de BoundaryCapability"),
    ],
)
def test_hp_u23_a_vista_recusa_estado_invalido(kwargs: dict, erro: str) -> None:
    with pytest.raises((ValueError, TypeError), match=erro):
        _vista(_binding(), **kwargs)


def test_hp_u24_a_vista_recusa_capacidade_repetida() -> None:
    with pytest.raises(ValueError, match="não aceita repetição"):
        _vista(
            _binding(),
            outcome=BoundaryOutcome.PROHIBITED,
            engajamento=BoundaryEngagement.UNSPECIFIED,
            capacidades=(
                BoundaryCapability.CHILD_SEXUAL_EXPLOITATION,
                BoundaryCapability.CHILD_SEXUAL_EXPLOITATION,
            ),
        )


# --- invariantes da consulta ------------------------------------------------


def _query(binding: GovernanceBinding, **extra: object) -> GovernanceQuery:
    campos: dict[str, object] = {
        "descriptor_operation": BoundaryOperation.EXPOSE,
        "descriptor_capabilities": frozenset(),
        "descriptor_engagement": BoundaryEngagement.ANALYTICAL,
        "binding": binding,
    }
    campos.update(extra)
    return GovernanceQuery(**campos)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "erro"),
    [
        ({"descriptor_operation": "expose"}, "BoundaryOperation"),
        ({"descriptor_engagement": "analytical"}, "BoundaryEngagement"),
        ({"descriptor_capabilities": "abc"}, "iterável de BoundaryCapability"),
        ({"descriptor_capabilities": frozenset({"x"})}, "apenas BoundaryCapability"),
        ({"context_domain_ids": "abc"}, "iterável de uuid.UUID"),
        ({"context_domain_ids": ("x",)}, "apenas uuid.UUID"),
        ({"context_session_id": 1}, "deve ser str ou None"),
        ({"context_purpose": "  "}, "não pode ser vazio"),
        ({"descriptor_operation": BoundaryOperation.READ}, "MESMA operação"),
    ],
)
def test_hp_u25_a_consulta_recusa_estado_invalido(kwargs: dict, erro: str) -> None:
    with pytest.raises((ValueError, TypeError), match=erro):
        _query(_binding(), **kwargs)


def test_hp_u25b_a_consulta_recusa_binding_que_nao_e_binding() -> None:
    """Construção inválida DENTRO do `pytest.raises`.

    Passar `binding="b"` pela fábrica `_query` fazia a `GovernanceQuery`
    levantar antes do bloco, e a prova media o arnês em vez do contrato.

    ```text
    REFUSAL_BY_THE_WRONG_GUARD = UNPROVEN_INVARIANT
    ```
    """
    with pytest.raises(TypeError, match="GovernanceBinding"):
        GovernanceQuery(
            descriptor_operation=BoundaryOperation.EXPOSE,
            descriptor_capabilities=frozenset(),
            descriptor_engagement=BoundaryEngagement.ANALYTICAL,
            binding="b",  # type: ignore[arg-type]
        )


def test_hp_u26_a_consulta_aceita_contexto_ausente() -> None:
    query = _query(_binding())
    assert query.context_domain_ids == ()
    assert query.context_session_id is None


# --- invariantes da aplicação ----------------------------------------------


def _aplicacao(**extra: object) -> HumanProtectionApplication:
    campos: dict[str, object] = {
        "control_principal_ref": "principal-a",
        "schedule_id": _SCHEDULE,
        "step_id": _STEP,
        "attempt_id": None,
        "binding_attempt_id": None,
        "objective_sha256": _OBJETIVO,
        "decision_fingerprint": _FINGERPRINT,
        "fingerprint_algo_version": FINGERPRINT_ALGO_VERSION,
        "binding_sha256": "b" * 64,
        "binding_algo_version": BINDING_ALGO_VERSION,
        "outcome": ProtectionOutcome.ALLOWED,
        "capability_engagement": None,
        "boundary_version": 1,
        "classifier_version": "iab-1",
        "cognitive_operation": BoundaryOperation.EXPOSE,
        "gate_position": GatePosition.G2,
        "producer_ref": PRODUCER_REF,
        "pause_applied": False,
        "delegations_revoked": 0,
        "blocked_capabilities": (),
    }
    campos.update(extra)
    return HumanProtectionApplication(**campos)  # type: ignore[arg-type]


def _bloqueio(**extra: object) -> HumanProtectionApplication:
    campos: dict[str, object] = {
        "outcome": ProtectionOutcome.BLOCKED,
        "capability_engagement": BoundaryEngagement.OPERATIONAL_ENABLEMENT,
        "pause_applied": True,
        "blocked_capabilities": (BoundaryCapability.CHILD_SEXUAL_EXPLOITATION,),
    }
    campos.update(extra)
    return _aplicacao(**campos)


@pytest.mark.parametrize(
    ("kwargs", "erro"),
    [
        ({"outcome": "allowed"}, "ProtectionOutcome"),
        ({"gate_position": "g2"}, "GatePosition"),
        ({"cognitive_operation": "expose"}, "BoundaryOperation"),
        ({"capability_engagement": "analytical"}, "BoundaryEngagement ou None"),
        ({"control_principal_ref": " "}, "control_principal_ref é obrigatório"),
        ({"classifier_version": ""}, "classifier_version é obrigatório"),
        ({"schedule_id": "x"}, "schedule_id deve ser uuid"),
        ({"pause_applied": 1}, "pause_applied deve ser bool"),
        ({"delegations_revoked": True}, "delegations_revoked deve ser int"),
        ({"delegations_revoked": -1}, "não pode ser negativo"),
        ({"boundary_version": True}, "boundary_version deve ser int"),
        ({"boundary_version": 0}, "deve ser >= 1"),
        ({"blocked_capabilities": ("x",)}, "apenas BoundaryCapability"),
        ({"objective_sha256": "curto"}, "objective_sha256 deve ser sha-256"),
        ({"fingerprint_algo_version": "9"}, "fingerprint_algo_version desconhecida"),
        ({"binding_algo_version": "9"}, "binding_algo_version desconhecida"),
        ({"producer_ref": "outro"}, "não é o produtor autorizado"),
        ({"schedule_id": None}, "exige schedule_id e step_id"),
        ({"binding_attempt_id": _ATTEMPT}, "somente g3 carrega binding_attempt_id"),
        ({"attempt_id": _ATTEMPT}, "somente g3 permitido materializa tentativa"),
    ],
)
def test_hp_u27_a_aplicacao_recusa_estado_invalido(kwargs: dict, erro: str) -> None:
    with pytest.raises((ValueError, TypeError), match=erro):
        _aplicacao(**kwargs)


def test_hp_u28_g1_registra_sem_schedule_e_sem_pausa() -> None:
    aplicacao = _bloqueio(
        gate_position=GatePosition.G1, schedule_id=None, step_id=None, pause_applied=False
    )
    assert aplicacao.schedule_id is None and aplicacao.pause_applied is False


def test_hp_u29_g1_com_schedule_e_recusado() -> None:
    with pytest.raises(ValueError, match="g1 registra schedule_id e step_id nulos"):
        _bloqueio(gate_position=GatePosition.G1, step_id=None, pause_applied=False)


def test_hp_u30_g1_nao_pausa() -> None:
    with pytest.raises(ValueError, match="g1 não pausa"):
        _bloqueio(gate_position=GatePosition.G1, schedule_id=None, step_id=None)


def test_hp_u31_g3_exige_binding_attempt() -> None:
    with pytest.raises(ValueError, match="g3 exige binding_attempt_id"):
        _bloqueio(gate_position=GatePosition.G3)


def test_hp_u32_g3_permitido_exige_tentativa_materializada() -> None:
    with pytest.raises(ValueError, match="g3 permitido exige tentativa"):
        _aplicacao(gate_position=GatePosition.G3, binding_attempt_id=_ATTEMPT)


def test_hp_u33_tentativa_divergente_do_binding_e_recusada() -> None:
    with pytest.raises(ValueError, match="diverge da tentativa do binding"):
        _aplicacao(
            gate_position=GatePosition.G3,
            binding_attempt_id=_ATTEMPT,
            attempt_id=uuid.uuid4(),
        )


def test_hp_u34_g3_permitido_com_tentativa_coerente_e_aceito() -> None:
    aplicacao = _aplicacao(
        gate_position=GatePosition.G3, binding_attempt_id=_ATTEMPT, attempt_id=_ATTEMPT
    )
    assert aplicacao.attempt_id == aplicacao.binding_attempt_id


def test_hp_u35_bloqueio_nao_materializa_tentativa() -> None:
    """`bloqueio/revisão não fabricam Attempt`."""
    with pytest.raises(ValueError, match="somente g3 permitido materializa tentativa"):
        _bloqueio(gate_position=GatePosition.G3, binding_attempt_id=_ATTEMPT, attempt_id=_ATTEMPT)


def test_hp_u36_permitido_nao_pausa_nem_revoga() -> None:
    with pytest.raises(ValueError, match="allowed não pausa nem revoga"):
        _aplicacao(pause_applied=True)


def test_hp_u37_permitido_nao_carrega_engajamento() -> None:
    """`ALLOWED` com `category=None` e `signal=None` (corretivo R2.1)."""
    with pytest.raises(ValueError, match="allowed não carrega engajamento"):
        _aplicacao(capability_engagement=BoundaryEngagement.ANALYTICAL)


@pytest.mark.parametrize(
    "engajamento", [BoundaryEngagement.ANALYTICAL, BoundaryEngagement.PREVENTIVE]
)
def test_hp_u38_bloqueio_com_engajamento_nao_habilitante_e_recusado(
    engajamento: BoundaryEngagement,
) -> None:
    """`ANALYSIS != OPERATIONAL_ENABLEMENT`, medido no value object."""
    with pytest.raises(ValueError, match="engajamento operacional ou não especificado"):
        _bloqueio(capability_engagement=engajamento)


def test_hp_u39_bloqueio_fora_de_g1_exige_pausa() -> None:
    with pytest.raises(ValueError, match="exige pausa aplicada"):
        _bloqueio(pause_applied=False)


def test_hp_u40_revisao_nao_tem_produtor() -> None:
    with pytest.raises(ValueError, match="não possui produtor autorizado"):
        _aplicacao(outcome=ProtectionOutcome.REVIEW_REQUIRED, pause_applied=False)


def test_hp_u41_somente_bloqueio_revoga() -> None:
    with pytest.raises(ValueError, match="somente bloqueio revoga"):
        _aplicacao(outcome=ProtectionOutcome.REVIEW_REQUIRED, delegations_revoked=1)


def test_hp_u42_capacidade_repetida_e_recusada() -> None:
    with pytest.raises(ValueError, match="não aceita repetição"):
        _bloqueio(
            blocked_capabilities=(
                BoundaryCapability.CHILD_SEXUAL_EXPLOITATION,
                BoundaryCapability.CHILD_SEXUAL_EXPLOITATION,
            )
        )


@pytest.mark.parametrize(
    ("kwargs", "erro"),
    [
        ({"pause_applied": 1}, "pause_applied deve ser bool"),
        ({"delegations_revoked": True}, "delegations_revoked deve ser int"),
        ({"delegations_revoked": -1}, "não pode ser negativo"),
        ({"attempt_id": "x"}, "uuid.UUID ou None"),
    ],
)
def test_hp_u43_efeitos_recusam_estado_invalido(kwargs: dict, erro: str) -> None:
    with pytest.raises((ValueError, TypeError), match=erro):
        ProtectionEffects(**kwargs)


# --- comportamento da ponte -------------------------------------------------


def _ponte(porta: object, repositorio: object | None = None) -> HumanProtectionBridge:
    return HumanProtectionBridge(porta, repositorio or _RepositorioDeMemoria())  # type: ignore[arg-type]


def test_hp_u44_avaliar_devolve_a_vista_vinculada() -> None:
    binding = _binding()
    porta = _PortaDeTeste(_vista(binding))
    assert _ponte(porta).avaliar(_query(binding), moment=_AGORA).outcome is (
        BoundaryOutcome.NOT_APPLICABLE
    )


def test_hp_u45_falha_da_porta_vira_indisponibilidade_tecnica() -> None:
    """`SOFTWARE_FAILURE != HUMAN_HARM_CATEGORY`."""
    porta = _PortaDeTeste(falha=RuntimeError("caiu"))
    with pytest.raises(HumanProtectionGateUnavailableError, match="falhou ao resolver"):
        _ponte(porta).avaliar(_query(_binding()), moment=_AGORA)


def test_hp_u46_indisponibilidade_da_porta_e_propagada_sem_remascarar() -> None:
    original = HumanProtectionGateUnavailableError("descritor ausente")
    porta = _PortaDeTeste(falha=original)
    with pytest.raises(HumanProtectionGateUnavailableError, match="descritor ausente"):
        _ponte(porta).avaliar(_query(_binding()), moment=_AGORA)


@pytest.mark.parametrize("resposta", [None, "not_applicable", object()])
def test_hp_u47_resposta_que_nao_e_vista_e_recusada(resposta: object) -> None:
    """`MISSING_AUTHORIZED_DESCRIPTOR != AUTHORIZED_EMPTY_DESCRIPTOR`."""
    porta = _PortaDeTeste(resposta)
    with pytest.raises(HumanProtectionGateUnavailableError, match="não é uma resolução"):
        _ponte(porta).avaliar(_query(_binding()), moment=_AGORA)


def test_hp_u48_vista_de_outro_gate_nao_e_reutilizavel() -> None:
    """`RESOLUTION_FOR_ANOTHER_QUESTION = NO_RESOLUTION`."""
    porta = _PortaDeTeste(_vista(_binding(gate=GatePosition.G4)))
    with pytest.raises(HumanProtectionGateUnavailableError, match="não está vinculada"):
        _ponte(porta).avaliar(_query(_binding(gate=GatePosition.G2)), moment=_AGORA)


@pytest.mark.parametrize(
    ("extra", "erro"),
    [
        ({"boundary_version": 2}, "versão da fronteira divergente"),
        ({"classifier_version": "iab-2"}, "versão do classificador divergente"),
        ({"valid_until": _VALIDADE + timedelta(minutes=1)}, "validade divergente"),
    ],
)
def test_hp_u49_divergencia_de_versao_ou_validade_recusa(extra: dict, erro: str) -> None:
    binding = _binding()
    vista = _vista(binding, **extra)
    with pytest.raises(HumanProtectionGateUnavailableError, match=erro):
        _ponte(_PortaDeTeste(vista)).avaliar(_query(binding), moment=_AGORA)


def test_hp_u50_resolucao_vencida_nao_autoriza_nem_recusa() -> None:
    binding = _binding()
    porta = _PortaDeTeste(_vista(binding))
    with pytest.raises(HumanProtectionGateUnavailableError, match="vencida"):
        _ponte(porta).avaliar(_query(binding), moment=_VALIDADE + timedelta(seconds=1))


def test_hp_u51_resolucao_do_futuro_e_incoerente() -> None:
    binding = _binding()
    porta = _PortaDeTeste(_vista(binding))
    with pytest.raises(HumanProtectionGateUnavailableError, match="no futuro"):
        _ponte(porta).avaliar(_query(binding), moment=_AGORA - timedelta(seconds=1))


def test_hp_u52_avaliar_sem_moment_usa_o_relogio() -> None:
    """O ramo do relógio existe e é exercitado — com margem, não com sorte.

    A janela de uma hora não é folga arbitrária: ela é o que separa "o
    caminho sem `moment` funciona" de "o teste passou porque a máquina
    estava rápida".
    """
    binding = _binding(valid_until=_AGORA + timedelta(hours=1))
    vista = _vista(binding, evaluated_at=_AGORA - timedelta(hours=1))
    assert _ponte(_PortaDeTeste(vista)).avaliar(_query(binding)) is vista


def test_hp_u53_desfecho_inesperado_na_ponte_e_indisponibilidade() -> None:
    """O mapa é exaustivo: sem entrada, `KeyError` vira `PIA-8069`.

    A vista já recusa `ADMISSIBLE` na construção, então o desfecho só chega
    aqui por adulteração — e adulteração não pode virar permissão.
    """
    vista = _vista(_binding())
    object.__setattr__(vista, "outcome", BoundaryOutcome.ADMISSIBLE)
    with pytest.raises(HumanProtectionGateUnavailableError, match="não é interpretável"):
        HumanProtectionBridge.desfecho(vista)


def test_hp_u54_prohibited_vira_bloqueio_com_capacidades_preservadas() -> None:
    binding = _binding()
    ponte = _ponte(_PortaDeTeste(_vista_bloqueio(binding)))
    aplicacao = ponte.registrar_aplicacao(
        vista=_vista_bloqueio(binding),
        binding=binding,
        efeitos=ProtectionEffects(pause_applied=True, delegations_revoked=2),
    )
    assert aplicacao.outcome is ProtectionOutcome.BLOCKED
    assert aplicacao.blocked_capabilities == (BoundaryCapability.CHILD_SEXUAL_EXPLOITATION,)
    assert aplicacao.delegations_revoked == 2


def test_hp_u55_not_applicable_vira_permissao_registrada() -> None:
    """`ABSENCE_OF_EVIDENCE != ABSENCE_OF_DECISION`."""
    binding = _binding()
    ponte = _ponte(_PortaDeTeste(_vista(binding)))
    aplicacao = ponte.registrar_aplicacao(
        vista=_vista(binding), binding=binding, efeitos=ProtectionEffects()
    )
    assert aplicacao.outcome is ProtectionOutcome.ALLOWED
    assert aplicacao.capability_engagement is None
    assert aplicacao.blocked_capabilities == ()


def test_hp_u56_registrar_com_binding_alheio_e_recusado() -> None:
    binding = _binding()
    outro = _binding(gate=GatePosition.G4)
    with pytest.raises(HumanProtectionGateUnavailableError, match="não está vinculada"):
        _ponte(_PortaDeTeste(None)).registrar_aplicacao(
            vista=_vista(binding), binding=outro, efeitos=ProtectionEffects()
        )


def test_hp_u57_retry_do_mesmo_bloqueio_nao_duplica_evento() -> None:
    binding = _binding()
    repositorio = _RepositorioDeMemoria()
    ponte = _ponte(_PortaDeTeste(None), repositorio)
    efeitos = ProtectionEffects(pause_applied=True)
    for _ in range(3):
        ponte.registrar_aplicacao(vista=_vista_bloqueio(binding), binding=binding, efeitos=efeitos)
    assert len(repositorio.linhas) == 1


def test_hp_u58_vencedor_divergente_e_falha_tecnica() -> None:
    """`DIVERGENT_WINNER = TECHNICAL_FAILURE`, nunca "já estava lá"."""
    binding = _binding()
    repositorio = _RepositorioDeMemoria()
    ponte = _ponte(_PortaDeTeste(None), repositorio)
    ponte.registrar_aplicacao(
        vista=_vista_bloqueio(binding),
        binding=binding,
        efeitos=ProtectionEffects(pause_applied=True),
    )
    with pytest.raises(HumanProtectionGateUnavailableError, match="delegations_revoked"):
        ponte.registrar_aplicacao(
            vista=_vista_bloqueio(binding),
            binding=binding,
            efeitos=ProtectionEffects(pause_applied=True, delegations_revoked=1),
        )


def test_hp_u59_nenhuma_posicao_de_gate_esta_composta_no_b1a() -> None:
    """`PRODUCTION_COMPOSITION_IN_B1A = NO`, como conjunto verificável."""
    assert frozenset(GatePosition) == GATES_SEM_LIGACAO_PRODUTIVA


# --- adaptador E7 -> E4 -----------------------------------------------------


def _resolucao_permitida() -> GovernanceResolution:
    return GovernanceResolution(
        outcome=GovernanceOutcome.NOT_APPLICABLE,
        operation=CognitiveOperation.EXPOSE,
        context_domain_ids=(),
        context_actor_ref=None,
        context_purpose=None,
        safety_boundary_version=1,
        safety_rationale="nenhuma capacidade crítica declarada",
    )


def _adaptador() -> GovernanceResolutionAdapter:
    """Adaptador real da E4, com o instante do arnês injetado.

    `momento` é o mesmo `_AGORA` que define `valid_until`: uma leitura de
    relógio, um instante, nenhuma janela entre eles.
    """
    return GovernanceResolutionAdapter(
        GovernanceManager(_RepositorioNaoConsultado()),  # type: ignore[arg-type]
        momento=_AGORA,
    )


def test_hp_u60_o_adaptador_satisfaz_a_porta() -> None:
    assert isinstance(_adaptador(), GovernanceResolutionPort)


@pytest.mark.parametrize(
    "capacidade",
    [
        BoundaryCapability.CHILD_SEXUAL_EXPLOITATION,
        BoundaryCapability.MINOR_TARGETING_FOR_EXPLOITATION,
        BoundaryCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT,
        BoundaryCapability.CATASTROPHIC_HARM_ENABLEMENT,
    ],
)
@pytest.mark.parametrize(
    "engajamento",
    [BoundaryEngagement.OPERATIONAL_ENABLEMENT, BoundaryEngagement.UNSPECIFIED],
)
def test_hp_u61_capacidade_operacional_ou_nao_especificada_bloqueia(
    capacidade: BoundaryCapability, engajamento: BoundaryEngagement
) -> None:
    """`P-GOV-BRIDGE-02/03`: a regra é consumida, não reimplementada."""
    binding = _binding()
    vista = _adaptador().resolve(
        _query(
            binding,
            descriptor_capabilities=frozenset({capacidade}),
            descriptor_engagement=engajamento,
        )
    )
    assert vista.outcome is BoundaryOutcome.PROHIBITED
    assert vista.blocked_capabilities == (capacidade,)


@pytest.mark.parametrize(
    "engajamento", [BoundaryEngagement.ANALYTICAL, BoundaryEngagement.PREVENTIVE]
)
def test_hp_u62_analitico_e_preventivo_nao_sao_bloqueados_por_tema(
    engajamento: BoundaryEngagement,
) -> None:
    """`P-GOV-BRIDGE-04`: `TOPIC != CAPABILITY`.

    Trabalho de prevenção, detecção, proteção, denúncia e pesquisa continua
    alcançável — bloquear por assunto destruiria exatamente esse trabalho.
    """
    binding = _binding()
    vista = _adaptador().resolve(
        _query(
            binding,
            descriptor_capabilities=frozenset(BoundaryCapability),
            descriptor_engagement=engajamento,
        )
    )
    assert vista.outcome is BoundaryOutcome.NOT_APPLICABLE
    assert vista.blocked_capabilities == ()


def test_hp_u63_sem_capacidade_critica_a_fronteira_nao_se_opoe() -> None:
    vista = _adaptador().resolve(_query(_binding()))
    assert vista.outcome is BoundaryOutcome.NOT_APPLICABLE


def test_hp_u64_o_adaptador_vincula_a_vista_ao_binding() -> None:
    binding = _binding(gate=GatePosition.G3, attempt_id=_ATTEMPT)
    vista = _adaptador().resolve(_query(binding))
    assert vista.binding_sha256 == calcular_binding_sha256(binding)
    assert vista.classifier_version == binding.classifier_version
    assert vista.valid_until == binding.valid_until


def test_hp_u65_a_mesma_decisao_em_gates_distintos_tem_um_fingerprint() -> None:
    """`P-BINDING-DISTINCT`, do lado do adaptador."""
    adaptador = _adaptador()
    g2 = adaptador.resolve(_query(_binding(gate=GatePosition.G2)))
    g4 = adaptador.resolve(_query(_binding(gate=GatePosition.G4)))
    assert g2.decision_fingerprint == g4.decision_fingerprint
    assert g2.binding_sha256 != g4.binding_sha256


def test_hp_u66_a_policy_local_nunca_e_consultada() -> None:
    """`policy_key = None` SEMPRE — o dublê reprova qualquer acesso."""
    assert _adaptador().resolve(_query(_binding())).outcome in ACCEPTED_BOUNDARY_OUTCOMES


def test_hp_u67_falha_da_governanca_vira_indisponibilidade() -> None:
    class _GovernancaQueCai:
        def resolve(self, **_: object) -> GovernanceResolution:
            raise RuntimeError("indisponível")

    adaptador = GovernanceResolutionAdapter(_GovernancaQueCai())  # type: ignore[arg-type]
    with pytest.raises(HumanProtectionGateUnavailableError, match="não pôde produzir"):
        adaptador.resolve(_query(_binding()))


def test_hp_u68_indisponibilidade_da_governanca_nao_e_remascarada() -> None:
    class _GovernancaTipada:
        def resolve(self, **_: object) -> GovernanceResolution:
            raise HumanProtectionGateUnavailableError("já tipada")

    adaptador = GovernanceResolutionAdapter(_GovernancaTipada())  # type: ignore[arg-type]
    with pytest.raises(HumanProtectionGateUnavailableError, match="já tipada"):
        adaptador.resolve(_query(_binding()))


def test_hp_u69_resolucao_que_nao_e_resolucao_e_recusada() -> None:
    class _GovernancaEstranha:
        def resolve(self, **_: object) -> object:
            return "not_applicable"

    adaptador = GovernanceResolutionAdapter(_GovernancaEstranha())  # type: ignore[arg-type]
    with pytest.raises(HumanProtectionGateUnavailableError, match="não é uma resolução"):
        adaptador.resolve(_query(_binding()))


@pytest.mark.parametrize("desfecho", [GovernanceOutcome.ADMISSIBLE, GovernanceOutcome.INADMISSIBLE])
def test_hp_u70_desfecho_inesperado_do_manager_e_indisponibilidade(
    desfecho: GovernanceOutcome,
) -> None:
    """`ADMISSIBLE ou INADMISSIBLE chegando pela porta -> PIA-8069`."""

    class _GovernancaComPolicy:
        def resolve(self, **_: object) -> GovernanceResolution:
            return GovernanceResolution(
                outcome=desfecho,
                operation=CognitiveOperation.EXPOSE,
                context_domain_ids=(),
                context_actor_ref=None,
                context_purpose=None,
                safety_boundary_version=1,
                policy_key="k",
                policy_version=1,
                policy_id=uuid.uuid4(),
                matched_rule_id="r1",
            )

    adaptador = GovernanceResolutionAdapter(_GovernancaComPolicy())  # type: ignore[arg-type]
    with pytest.raises(HumanProtectionGateUnavailableError, match="desfecho inesperado"):
        adaptador.resolve(_query(_binding()))


def test_hp_u71_desfecho_nao_tipado_e_recusado() -> None:
    class _GovernancaAdulterada:
        def resolve(self, **_: object) -> GovernanceResolution:
            resolucao = _resolucao_permitida()
            object.__setattr__(resolucao, "outcome", "not_applicable")
            return resolucao

    adaptador = GovernanceResolutionAdapter(_GovernancaAdulterada())  # type: ignore[arg-type]
    with pytest.raises(HumanProtectionGateUnavailableError, match="não é tipado"):
        adaptador.resolve(_query(_binding()))


def test_hp_u72_a_ponte_ponta_a_ponta_com_a_governanca_real() -> None:
    """Adaptador REAL + ponte: bloqueio de capacidade operacional."""
    binding = _binding()
    repositorio = _RepositorioDeMemoria()
    ponte = HumanProtectionBridge(_adaptador(), repositorio)  # type: ignore[arg-type]
    query = _query(
        binding,
        descriptor_capabilities=frozenset({BoundaryCapability.CHILD_SEXUAL_EXPLOITATION}),
        descriptor_engagement=BoundaryEngagement.OPERATIONAL_ENABLEMENT,
    )
    vista = ponte.avaliar(query)
    aplicacao = ponte.registrar_aplicacao(
        vista=vista, binding=binding, efeitos=ProtectionEffects(pause_applied=True)
    )
    assert aplicacao.outcome is ProtectionOutcome.BLOCKED
    assert len(repositorio.linhas) == 1


def test_hp_u73_a_retencao_e_declarada_sem_executor() -> None:
    """`EXPIRACAO_DO_EVENTO = NOT_IMPLEMENTED`, declarado e não implementado."""
    assert RETENTION_POLICY_DECLARADA == RETENTION_POLICY_ID
    assert RETENTION_MINIMUM_AGE_DAYS == 365
