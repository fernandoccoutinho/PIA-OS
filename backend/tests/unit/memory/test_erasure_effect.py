"""
Testes da fronteira de efeito destrutivo (`E4.9.9.b`).

```text
APPROVAL   != CONSUMPTION
CONSUMPTION != EFFECT
EFFECT      != ERASURE_RECORD
NO_MATERIAL_ATTEMPT -> NO_ERASURE_RECORD
```
"""

import dataclasses
import inspect
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.memory.models.approval_enums import (
    DestructiveOperation,
    InputChannel,
    VoiceReviewState,
)
from app.memory.models.erasure_effect_enums import (
    EffectAttemptStage,
    MaterialAttemptRefusalReason,
)
from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.memory.models.target_resolution_enums import (
    LegacyProtectionState,
    ReferenceOrigin,
)
from app.memory.ports.erasure_effect import ErasureEffectPort
from app.memory.schemas.erasure_effect import (
    ConsumedApprovalEvidence,
    ErasureEffectRequest,
    ErasureEffectResult,
    MaterialAttemptNotStarted,
    ObservedAttemptResult,
)
from app.memory.schemas.erasure_target import (
    ControlScope,
    CustodyNamespace,
    ErasureTargetDescriptor,
    ReferenceProvenance,
    VerifiedDeletionCapability,
)

TENANT = uuid.UUID("00000000-0000-0000-0000-0000000ee001")
WORKSPACE = uuid.UUID("00000000-0000-0000-0000-0000000ee002")
SUJEITO = uuid.UUID("00000000-0000-0000-0000-0000000ee003")
APROVACAO = uuid.UUID("00000000-0000-0000-0000-0000000ee004")
PRINCIPAL = "principal:humano-1"
LOCALIZADOR = "s3://bucket-privado/objeto-exato"
QUANDO = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
DEPOIS = QUANDO + timedelta(seconds=5)

MARCADOR = "MARCADOR-SENSIVEL-E499B-nao-deve-vazar"


def _executavel(modulo: object) -> str:
    """Código sem docstrings — as deste módulo nomeiam o que ele NÃO faz."""
    import ast

    arvore = ast.parse(inspect.getsource(modulo))
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if isinstance(corpo, list):
            novo = [
                filho
                for filho in corpo
                if not (
                    isinstance(filho, ast.Expr)
                    and isinstance(filho.value, ast.Constant)
                    and isinstance(filho.value.value, str)
                )
            ] or [ast.Pass()]
            setattr(no, "body", novo)  # noqa: B010
    return ast.unparse(arvore)


def _construir(alvo: object, **kwargs: object) -> object:
    """Construção dinâmica para entradas deliberadamente inválidas."""
    return alvo(**kwargs)  # type: ignore[operator]


def descritor(**over: object) -> ErasureTargetDescriptor:
    base: dict[str, object] = {
        "target_class": ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        "subject_coid": SUJEITO,
        "control_scope": ControlScope(WORKSPACE, TENANT, PRINCIPAL),
        "custody_namespace": CustodyNamespace("pia-storage", "workspace/w1"),
        "capability": VerifiedDeletionCapability("delete_object", "workspace/w1/*", True),
        "resolved_at": QUANDO,
        "origin": ReferenceProvenance(ReferenceOrigin.PAYLOAD_REF),
        "legacy_protection_state": LegacyProtectionState.NOT_PROTECTED,
        "transient_locator": LOCALIZADOR,
    }
    base.update(over)
    feito = _construir(ErasureTargetDescriptor, **base)
    assert isinstance(feito, ErasureTargetDescriptor)
    return feito


def evidencia(**over: object) -> ConsumedApprovalEvidence:
    base: dict[str, object] = {
        "approval_id": APROVACAO,
        "operation": DestructiveOperation.PERMANENT_ERASURE,
        "tenant_id": TENANT,
        "workspace_id": WORKSPACE,
        "principal_ref": PRINCIPAL,
        "consumed_at": QUANDO,
    }
    base.update(over)
    feito = _construir(ConsumedApprovalEvidence, **base)
    assert isinstance(feito, ConsumedApprovalEvidence)
    return feito


def requisicao(**over: object) -> ErasureEffectRequest:
    base: dict[str, object] = {
        "descriptor": descritor(),
        "authorization": evidencia(),
    }
    base.update(over)
    feito = _construir(ErasureEffectRequest, **base)
    assert isinstance(feito, ErasureEffectRequest)
    return feito


def observado(**over: object) -> ObservedAttemptResult:
    base: dict[str, object] = {
        "approval_id": APROVACAO,
        "subject_coid": SUJEITO,
        "target_class": ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        "outcome": ErasureOutcome.SUCCEEDED,
        "executor_ref": "exec:local-artifact-store",
        "attempted_at": QUANDO,
        "completed_at": DEPOIS,
    }
    base.update(over)
    feito = _construir(ObservedAttemptResult, **base)
    assert isinstance(feito, ObservedAttemptResult)
    return feito


def nao_iniciada(**over: object) -> MaterialAttemptNotStarted:
    base: dict[str, object] = {
        "approval_id": APROVACAO,
        "subject_coid": SUJEITO,
        "reason": MaterialAttemptRefusalReason.ADAPTER_UNAVAILABLE,
        "observed_at": QUANDO,
    }
    base.update(over)
    feito = _construir(MaterialAttemptNotStarted, **base)
    assert isinstance(feito, MaterialAttemptNotStarted)
    return feito


# ======================================================================
# Vocabulários
# ======================================================================


def test_u01_motivos_de_nao_tentativa_sao_quatro_e_fechados():
    assert [m.value for m in MaterialAttemptRefusalReason] == [
        "adapter_unavailable",
        "operation_not_supported",
        "capability_refused_before_attempt",
        "provider_precondition_refused",
    ]
    for proibido in ("UNKNOWN", "OTHER", "GENERIC", "ERROR", "FALLBACK", "DEFAULT"):
        assert proibido not in MaterialAttemptRefusalReason.__members__


def test_u02_nenhum_motivo_duplica_recusa_de_etapa_anterior():
    """Resolução e aprovação são etapas que já terminaram aqui."""
    from app.memory.models.approval_lifecycle_enums import ApprovalUsageRefusalReason
    from app.memory.models.target_resolution_enums import (
        TargetResolutionRefusalReason,
    )

    efeito = {m.value for m in MaterialAttemptRefusalReason}
    assert efeito.isdisjoint({m.value for m in TargetResolutionRefusalReason})
    assert efeito.isdisjoint({m.value for m in ApprovalUsageRefusalReason})


def test_u03_erasure_outcome_nao_foi_duplicado():
    """`ErasureOutcome` da E4.9.5 é a fonte única dos três observados."""
    from enum import EnumMeta

    import app.memory.models.erasure_effect_enums as modulo

    for nome in dir(modulo):
        obj = getattr(modulo, nome)
        if isinstance(obj, EnumMeta) and obj.__module__ == modulo.__name__:
            valores = {m.value for m in obj}
            assert not valores & {"succeeded", "failed", "partial"}, nome


def test_u04_not_started_esta_fora_de_erasure_outcome():
    """`NOT_STARTED -> NO_ERASURE_RECORD`.

    Entrar no enum de desfecho o tornaria elegível a recibo, e recibo
    descreve tentativa material.
    """
    assert "not_started" not in {m.value for m in ErasureOutcome}
    assert "NOT_STARTED" not in ErasureOutcome.__members__


def test_u05_quatro_desfechos_semanticos():
    semanticos = {EffectAttemptStage.NOT_STARTED.value} | {m.value for m in ErasureOutcome}
    assert semanticos == {"not_started", "succeeded", "failed", "partial"}


# ======================================================================
# `stage` é etiqueta derivada, nunca argumento
# ======================================================================


@pytest.mark.parametrize(
    ("classe", "esperado"),
    [
        (MaterialAttemptNotStarted, EffectAttemptStage.NOT_STARTED),
        (ObservedAttemptResult, EffectAttemptStage.MATERIAL_ATTEMPT_OBSERVED),
    ],
)
def test_u06_stage_nao_e_campo_nem_parametro(classe, esperado):
    """`DISJOINT_RESULT_TYPE = SOURCE_OF_TRUTH` · `STAGE = DERIVED_TAG_ONLY`.

    Se `stage` fosse campo, seria possível construir uma não-tentativa
    marcada como observada, e a etiqueta competiria com o tipo pela
    verdade.
    """
    assert "stage" not in {c.name for c in dataclasses.fields(classe)}
    assert "stage" not in inspect.signature(classe).parameters
    assert isinstance(inspect.getattr_static(classe, "stage"), property)


def test_u07_stage_e_constante_da_classe():
    assert nao_iniciada().stage is EffectAttemptStage.NOT_STARTED
    assert observado().stage is EffectAttemptStage.MATERIAL_ATTEMPT_OBSERVED


def test_u08_stage_nao_pode_ser_passado_nem_atribuido():
    with pytest.raises(TypeError):
        nao_iniciada(stage=EffectAttemptStage.MATERIAL_ATTEMPT_OBSERVED)
    with pytest.raises(dataclasses.FrozenInstanceError):
        nao_iniciada().__setattr__(  # noqa: PLC2801
            "stage", EffectAttemptStage.MATERIAL_ATTEMPT_OBSERVED
        )


# ======================================================================
# Evidência de consumo
# ======================================================================


def test_u09_evidencia_nao_transporta_material_proibido():
    """`TYPED_CONSUMPTION_EVIDENCE != DATABASE_PROOF`."""
    campos = {c.name for c in dataclasses.fields(ConsumedApprovalEvidence)}
    assert campos == {
        "approval_id",
        "operation",
        "tenant_id",
        "workspace_id",
        "principal_ref",
        "consumed_at",
    }
    for proibido in (
        "nonce",
        "token",
        "credential",
        "secret",
        "envelope",
        "proposal",
        "assurance_level",
        "signature",
        "biometric",
    ):
        assert proibido not in campos


def test_u10_todos_os_campos_da_evidencia_sao_obrigatorios():
    for parametro in inspect.signature(ConsumedApprovalEvidence).parameters.values():
        assert parametro.default is inspect.Parameter.empty, parametro.name


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("approval_id", str(APROVACAO)),
        ("operation", "permanent_erasure"),
        ("operation", None),
        ("tenant_id", 42),
        ("workspace_id", "w"),
        ("consumed_at", datetime(2026, 8, 18, 12, 0)),
    ],
)
def test_u11_evidencia_recusa_tipo_equivalente(campo, valor):
    with pytest.raises((TypeError, ValueError)):
        evidencia(**{campo: valor})


def test_u12_construir_evidencia_nao_prova_consumo():
    """Nesta fatia ninguém a produz; a E4.9.9.d o fará após o banco."""
    import app.memory.schemas.erasure_effect as modulo

    executavel = _executavel(modulo)
    assert "ApprovalRecordRepository" not in executavel
    assert "consume_once" not in executavel
    assert "append_observed" not in executavel


# ======================================================================
# Requisição de efeito
# ======================================================================


def test_u13_requisicao_valida_constroi():
    r = requisicao()
    assert r.descriptor.subject_coid == SUJEITO
    assert r.authorization.approval_id == APROVACAO


@pytest.mark.parametrize(
    "classe",
    [
        ErasureTargetClass.COGNITIVE_METADATA_RECORD,
        ErasureTargetClass.UNRESOLVED_OPAQUE_REFERENCE,
    ],
)
def test_u14_classe_nao_apagavel_nao_chega_a_fronteira(classe):
    with pytest.raises(ValueError, match="não é conteúdo apagável"):
        requisicao(descriptor=descritor(target_class=classe))


def test_u15_capacidade_nao_verificada_e_recusada_antes_da_fronteira():
    """Medido: a recusa acontece na camada do **descritor**, não aqui.

    `ErasureTargetDescriptor` já exige `verified is True` desde a
    E4.9.7.4 — "capacidade presumida é a forma silenciosa do confused
    deputy". Logo, um descritor válido nunca chega à fronteira de efeito
    com capacidade não verificada.

    ```text
    UNVERIFIED_CAPABILITY = REJECTED_AT_DESCRIPTOR
    ```

    A verificação no `ErasureEffectRequest` permanece como segunda
    camada — se a E4.9.7 relaxar a exigência, a fronteira de efeito não
    herda o relaxamento em silêncio —, e este teste documenta qual
    camada recusa hoje, em vez de alegar uma prova que a outra dá.
    """
    with pytest.raises(ValueError, match="VERIFICADA"):
        descritor(capability=VerifiedDeletionCapability("delete_object", "w/*", False))

    r = requisicao()
    assert r.descriptor.capability.verified is True


@pytest.mark.parametrize(
    ("campo", "trecho"),
    [
        ("tenant_id", "tenant do descritor"),
        ("workspace_id", "workspace do descritor"),
    ],
)
def test_u16_escopo_divergente_recusado(campo, trecho):
    with pytest.raises(ValueError, match=trecho):
        requisicao(authorization=evidencia(**{campo: uuid.uuid4()}))


def test_u17_principal_divergente_recusado():
    with pytest.raises(ValueError, match="principal de controle"):
        requisicao(authorization=evidencia(principal_ref="principal:outro"))


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("descriptor", "descritor"), ("authorization", {"approval_id": APROVACAO})],
)
def test_u18_requisicao_exige_tipos_reais(campo, valor):
    with pytest.raises(TypeError):
        requisicao(**{campo: valor})


# --- a correção material: sem inferência de semântica de provedor -------


def test_u19_nenhuma_inferencia_entre_operacao_e_capacidade():
    """`APPLICATION_LEVEL_CAPABILITY_OPERATION_MAPPING = FORBIDDEN`.

    `capability.operation` é **texto opaco do provedor**, e não existe
    contrato canônico que o traduza para `DestructiveOperation`. Uma
    matriz local inventaria semântica de provedor, e o custo do erro é
    assimétrico: poderia deixar passar apagamento definitivo com
    capacidade que só autorizava lixeira.

    ```text
    CAPABILITY_OPERATION_SEMANTICS = ADAPTER_BOUNDARY
    ```

    Esta é a prova por **comportamento**: qualquer texto de capacidade
    construído com as demais invariantes satisfeitas é aceito, para as
    duas operações aprovadas. A fronteira não opina.
    """
    for operacao in DestructiveOperation:
        for texto in (
            "delete_object",
            "move_to_trash",
            "permanent_erasure",
            "purge",
            "s3:DeleteObject",
            "qualquer-coisa-do-provedor",
        ):
            r = requisicao(
                descriptor=descritor(
                    capability=VerifiedDeletionCapability(texto, "workspace/w1/*", True)
                ),
                authorization=evidencia(operation=operacao),
            )
            assert r.descriptor.capability.operation == texto
            assert r.authorization.operation is operacao


def test_u20_o_modulo_nao_contem_matriz_de_capacidade():
    """Prova estrutural, complementar à de comportamento em `u19`.

    Nenhuma comparação, igualdade, substring ou dicionário que traduza
    `capability.operation` para operação aprovada.
    """
    import ast

    import app.memory.schemas.erasure_effect as modulo

    arvore = ast.parse(inspect.getsource(modulo))
    corpo = _executavel(modulo)

    # nenhuma leitura de `capability.operation` no código executável
    atributos = [
        no for no in ast.walk(arvore) if isinstance(no, ast.Attribute) and no.attr == "operation"
    ]
    lidos_da_capacidade = [
        no
        for no in atributos
        if isinstance(no.value, ast.Attribute) and no.value.attr == "capability"
    ]
    assert lidos_da_capacidade == []

    for forma in (
        "OPERACAO_DE_CAPACIDADE",
        "CAPABILITY_OPERATION_MAP",
        ".startswith(",
        ".endswith(",
        "in capability",
    ):
        assert forma not in corpo, forma


def test_u21_a_recusa_de_operacao_pertence_ao_adaptador():
    """Os dois motivos existem para o adaptador devolver antes do efeito."""
    assert MaterialAttemptRefusalReason.OPERATION_NOT_SUPPORTED
    assert MaterialAttemptRefusalReason.CAPABILITY_REFUSED_BEFORE_ATTEMPT
    n = nao_iniciada(reason=MaterialAttemptRefusalReason.OPERATION_NOT_SUPPORTED)
    assert n.stage is EffectAttemptStage.NOT_STARTED


# ======================================================================
# Resultados
# ======================================================================


@pytest.mark.parametrize("motivo", list(MaterialAttemptRefusalReason))
def test_u22_nao_tentativa_constroi_com_qualquer_motivo(motivo):
    assert nao_iniciada(reason=motivo).reason is motivo


def test_u23_nao_tentativa_recusa_texto_livre_como_motivo():
    with pytest.raises(TypeError, match="MaterialAttemptRefusalReason"):
        nao_iniciada(reason="adapter_unavailable")


def test_u24_nao_tentativa_nao_carrega_alvo_material():
    campos = {c.name for c in dataclasses.fields(MaterialAttemptNotStarted)}
    for proibido in ("transient_locator", "capability", "descriptor", "executor_ref"):
        assert proibido not in campos


@pytest.mark.parametrize(
    ("outcome", "codigo", "valido"),
    [
        (ErasureOutcome.SUCCEEDED, None, True),
        (ErasureOutcome.SUCCEEDED, "E-01", False),
        (ErasureOutcome.FAILED, "E-01", True),
        (ErasureOutcome.FAILED, None, False),
        (ErasureOutcome.PARTIAL, "E-02", True),
        (ErasureOutcome.PARTIAL, None, False),
    ],
)
def test_u25_matriz_outcome_failure_code(outcome, codigo, valido):
    """A matriz completa — seis combinações, três impossíveis."""
    if valido:
        r = observado(outcome=outcome, failure_code=codigo)
        assert r.outcome is outcome
        assert r.failure_code == codigo
    else:
        with pytest.raises(ValueError):
            observado(outcome=outcome, failure_code=codigo)


def test_u26_failure_code_vazio_e_recusado():
    for vazio in ("", "   ", "\t"):
        with pytest.raises(ValueError):
            observado(outcome=ErasureOutcome.FAILED, failure_code=vazio)


def test_u27_ordem_temporal_exigida():
    with pytest.raises(ValueError, match="anterior a attempted_at"):
        observado(attempted_at=DEPOIS, completed_at=QUANDO)
    assert observado(attempted_at=QUANDO, completed_at=QUANDO)


@pytest.mark.parametrize("campo", ["attempted_at", "completed_at"])
def test_u28_instantes_exigem_timezone(campo):
    with pytest.raises(ValueError, match="timezone-aware"):
        observado(**{campo: datetime(2026, 8, 18, 12, 0)})


def test_u29_resultado_observado_nao_carrega_localizador_nem_capacidade():
    campos = {c.name for c in dataclasses.fields(ObservedAttemptResult)}
    for proibido in (
        "transient_locator",
        "capability",
        "descriptor",
        "content",
        "payload",
        "credential",
    ):
        assert proibido not in campos


def test_u30_uniao_e_fechada_e_disjunta():
    """Sem `bool`, `None` ou dicionário livre."""
    import typing

    membros = set(typing.get_args(ErasureEffectResult))
    assert membros == {MaterialAttemptNotStarted, ObservedAttemptResult}
    assert not isinstance(nao_iniciada(), ObservedAttemptResult)
    assert not isinstance(observado(), MaterialAttemptNotStarted)


def test_u31_bool_nao_serve_como_desfecho():
    """`NOT_STARTED` e `FAILED` seriam ambos `False`."""
    n = nao_iniciada()
    f = observado(outcome=ErasureOutcome.FAILED, failure_code="E-01")
    assert n.stage is not f.stage
    assert type(n) is not type(f)


# ======================================================================
# Imutabilidade e igualdade
# ======================================================================


@pytest.mark.parametrize("fabrica", [evidencia, requisicao, observado, nao_iniciada])
def test_u32_todos_os_contratos_sao_congelados(fabrica):
    with pytest.raises(dataclasses.FrozenInstanceError):
        fabrica().__setattr__("approval_id", uuid.uuid4())  # noqa: PLC2801


def test_u33_igualdade_estrutural():
    assert observado() == observado()
    assert observado() != observado(outcome=ErasureOutcome.FAILED, failure_code="E")
    assert nao_iniciada() == nao_iniciada()
    assert nao_iniciada() != nao_iniciada(
        reason=MaterialAttemptRefusalReason.OPERATION_NOT_SUPPORTED
    )


def test_u34_replace_revalida():
    with pytest.raises(ValueError):
        dataclasses.replace(observado(), failure_code="E-01")
    with pytest.raises(TypeError):
        dataclasses.replace(nao_iniciada(), reason="adapter_unavailable")
    trocado = dataclasses.replace(
        nao_iniciada(), reason=MaterialAttemptRefusalReason.PROVIDER_PRECONDITION_REFUSED
    )
    assert trocado.reason is MaterialAttemptRefusalReason.PROVIDER_PRECONDITION_REFUSED


def test_u35_nenhuma_colecao_mutavel_publica():
    for objeto in (evidencia(), requisicao(), observado(), nao_iniciada()):
        for valor in vars(objeto).values():
            assert not isinstance(valor, list | dict | set), type(valor)


# ======================================================================
# Confidencialidade — direta e composta
# ======================================================================


def _sem_marcador(objeto: object, canal: str) -> None:
    assert MARCADOR not in repr(objeto), f"{canal}: repr"
    assert MARCADOR not in str(objeto), f"{canal}: str"
    assert MARCADOR not in f"{objeto}", f"{canal}: f-string"


def test_u36_nenhum_canal_textual_revela_o_marcador():
    """Composição completa com marcador **real**, não nomes de campo."""
    escopo = ControlScope(WORKSPACE, TENANT, MARCADOR)
    d = descritor(
        control_scope=escopo,
        custody_namespace=CustodyNamespace(MARCADOR, MARCADOR),
        capability=VerifiedDeletionCapability(MARCADOR, MARCADOR, True),
        transient_locator=f"s3://bucket/{MARCADOR}",
        version_etag=MARCADOR,
    )
    ev = evidencia(principal_ref=MARCADOR)
    _sem_marcador(ev, "ConsumedApprovalEvidence.principal_ref")
    _sem_marcador(
        ErasureEffectRequest(descriptor=d, authorization=evidencia(principal_ref=MARCADOR)),
        "ErasureEffectRequest (5 canais compostos)",
    )
    _sem_marcador(observado(executor_ref=MARCADOR), "ObservedAttemptResult.executor_ref")
    _sem_marcador(
        observado(outcome=ErasureOutcome.FAILED, failure_code=MARCADOR),
        "ObservedAttemptResult.failure_code",
    )


def test_u37_a_requisicao_nao_delega_ao_descritor():
    """O descritor redige o próprio localizador — mas a delegação não é a prova.

    Um campo novo lá dentro mudaria o que esta classe expõe sem decisão
    local. `s` fixa a redação explícita na AST.
    """
    from app.memory.schemas.erasure_effect import DESCRITOR_OCULTO

    r = requisicao()
    assert DESCRITOR_OCULTO in repr(r)
    assert LOCALIZADOR not in repr(r)


def test_u38_os_valores_continuam_acessiveis():
    """Redigir a representação não pode inutilizar o contrato."""
    assert evidencia(principal_ref=MARCADOR).principal_ref == MARCADOR
    assert observado(executor_ref=MARCADOR).executor_ref == MARCADOR
    assert requisicao().descriptor.transient_locator == LOCALIZADOR


def test_u39_excecoes_controladas_nao_vazam_conteudo():
    with pytest.raises((TypeError, ValueError)) as capturado:
        requisicao(
            descriptor=descritor(
                transient_locator=f"s3://bucket/{MARCADOR}",
                capability=VerifiedDeletionCapability("x", "y", False),
            )
        )
    assert MARCADOR not in str(capturado.value)


def test_u40_nenhum_serializer_ou_logger_nas_dataclasses():
    for classe in (
        ConsumedApprovalEvidence,
        ErasureEffectRequest,
        MaterialAttemptNotStarted,
        ObservedAttemptResult,
    ):
        for proibido in ("to_dict", "model_dump", "asdict", "json", "log"):
            assert not hasattr(classe, proibido), f"{classe.__name__}.{proibido}"


# ======================================================================
# Protocol
# ======================================================================


class _FakeAdapter:
    """Fake **puro** — sem filesystem, rede ou banco."""

    def __init__(self, resultado: ErasureEffectResult) -> None:
        self._resultado = resultado
        self.chamadas: int = 0

    def attempt_effect(self, request: ErasureEffectRequest) -> ErasureEffectResult:
        self.chamadas += 1
        return self._resultado


def test_u41_fake_correto_satisfaz_o_protocol():
    fake = _FakeAdapter(nao_iniciada())
    porta: ErasureEffectPort = fake
    resultado = porta.attempt_effect(requisicao())
    assert isinstance(resultado, MaterialAttemptNotStarted)
    assert fake.chamadas == 1


def test_u42_o_protocol_devolve_os_dois_lados_da_uniao():
    for resultado in (nao_iniciada(), observado()):
        porta: ErasureEffectPort = _FakeAdapter(resultado)
        assert porta.attempt_effect(requisicao()) is resultado


def test_u43_runtime_checkable_mede_presenca_e_nao_assinatura():
    """`RUNTIME_CHECKABLE != SIGNATURE_PROOF`.

    `isinstance` contra um `Protocol` verifica apenas a presença do
    membro. Quem prova a assinatura é o mypy, sobre a atribuição estática
    de `u41`.
    """

    class _AssinaturaErrada:
        def attempt_effect(self, a: int, b: int) -> int:  # noqa: ARG002
            return 0

    assert isinstance(_AssinaturaErrada(), ErasureEffectPort)
    assert isinstance(_FakeAdapter(nao_iniciada()), ErasureEffectPort)

    class _SemMetodo:
        pass

    assert not isinstance(_SemMetodo(), ErasureEffectPort)


def test_u44_a_porta_tem_um_unico_metodo():
    metodos = [
        nome
        for nome in dir(ErasureEffectPort)
        if not nome.startswith("_") and callable(getattr(ErasureEffectPort, nome, None))
    ]
    assert metodos == ["attempt_effect"]


def test_u45_nenhum_tipo_de_persistencia_atravessa_a_assinatura():
    """Sem `Session`, UoW, repositório, callback ou logger."""
    assinatura = inspect.signature(ErasureEffectPort.attempt_effect)
    parametros = [p for nome, p in assinatura.parameters.items() if nome != "self"]
    assert len(parametros) == 1
    assert parametros[0].annotation is ErasureEffectRequest
    fonte = inspect.getsource(ErasureEffectPort)
    for proibido in ("Session", "UnitOfWork", "Repository", "Logger", "Callable"):
        assert proibido not in fonte.split('"""')[-1], proibido


def test_u46_a_porta_de_efeito_nao_resolve_nem_escreve_recibo():
    """`RESOLUTION != DELETION_AUTHORITY` · `EFFECT != ERASURE_RECORD`."""
    for proibido in ("resolve", "resolve_target", "append_observed", "write_record"):
        assert not hasattr(ErasureEffectPort, proibido)


@pytest.mark.parametrize(
    ("canal", "revisao"),
    [
        (InputChannel.TEXT, VoiceReviewState.NOT_APPLICABLE),
        (InputChannel.VOICE, VoiceReviewState.REVIEWED_AND_CONFIRMED),
    ],
)
def test_u47_texto_e_voz_nao_alteram_o_contrato_da_porta(canal, revisao):
    """O canal pertence à proveniência da aprovação, não à fronteira de efeito.

    Nenhum campo de canal existe aqui — e é isso que garante paridade: não
    há como a fronteira tratar voz de modo diferente.
    """
    campos: set[str] = set()
    for classe in (
        ConsumedApprovalEvidence,
        ErasureEffectRequest,
        MaterialAttemptNotStarted,
        ObservedAttemptResult,
    ):
        campos |= {c.name for c in dataclasses.fields(classe)}
    assert "channel" not in campos
    assert "voice_review" not in campos
    assert canal.value and revisao.value  # os dois existem e não mudam nada aqui


# ======================================================================
# Fronteiras descobertas pela exigência de 100%
# ======================================================================


def test_u48_requisicao_recusa_classe_e_capacidade_pela_propria_camada():
    """A segunda camada existe e é exercida diretamente.

    O descritor já recusa classe não apagável e capacidade não
    verificada. Estas verificações permanecem no `ErasureEffectRequest`
    como segunda camada — se a E4.9.7 relaxar, a fronteira de efeito não
    herda o relaxamento em silêncio.

    Alcançá-las exige um objeto que satisfaça o protocolo estrutural do
    descritor sem passar por seu construtor; o teste usa uma subclasse
    controlada, que é construção **legítima**, não bypass.
    """

    @dataclasses.dataclass(frozen=True)
    class _DescritorRelaxado(ErasureTargetDescriptor):
        """Subclasse que NÃO reexecuta a validação da classe base."""

        def __post_init__(self) -> None:  # noqa: D105
            return

    relaxado = _DescritorRelaxado(
        target_class=ErasureTargetClass.COGNITIVE_METADATA_RECORD,
        subject_coid=SUJEITO,
        control_scope=ControlScope(WORKSPACE, TENANT, PRINCIPAL),
        custody_namespace=CustodyNamespace("pia-storage", "workspace/w1"),
        capability=VerifiedDeletionCapability("delete_object", "workspace/w1/*", True),
        resolved_at=QUANDO,
        origin=ReferenceProvenance(ReferenceOrigin.PAYLOAD_REF),
        legacy_protection_state=LegacyProtectionState.NOT_PROTECTED,
        transient_locator=LOCALIZADOR,
    )
    with pytest.raises(ValueError, match="não é conteúdo apagável"):
        requisicao(descriptor=relaxado)

    sem_verificacao = _DescritorRelaxado(
        target_class=ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        subject_coid=SUJEITO,
        control_scope=ControlScope(WORKSPACE, TENANT, PRINCIPAL),
        custody_namespace=CustodyNamespace("pia-storage", "workspace/w1"),
        capability=VerifiedDeletionCapability("delete_object", "workspace/w1/*", False),
        resolved_at=QUANDO,
        origin=ReferenceProvenance(ReferenceOrigin.PAYLOAD_REF),
        legacy_protection_state=LegacyProtectionState.NOT_PROTECTED,
        transient_locator=LOCALIZADOR,
    )
    with pytest.raises(ValueError, match="capacidade não verificada"):
        requisicao(descriptor=sem_verificacao)


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("target_class", "pia_managed_artifact", "ErasureTargetClass"),
        ("target_class", ErasureTargetClass.COGNITIVE_METADATA_RECORD, "conteúdo apagável"),
        ("outcome", "succeeded", "ErasureOutcome"),
    ],
)
def test_u49_resultado_observado_exige_tipos_reais(campo, valor, trecho):
    with pytest.raises((TypeError, ValueError), match=trecho):
        observado(**{campo: valor})


def test_u50_o_protocol_e_declaracao_e_nao_implementacao():
    """O corpo do método é elipse — o port não executa nada."""
    import ast

    fonte = inspect.getsource(ErasureEffectPort)
    (metodo,) = [
        no
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.FunctionDef) and no.name == "attempt_effect"
    ]
    # docstring + elipse: o corpo executável é apenas a elipse
    executaveis = [
        no
        for no in metodo.body
        if not (
            isinstance(no, ast.Expr)
            and isinstance(no.value, ast.Constant)
            and isinstance(no.value.value, str)
        )
    ]
    assert len(executaveis) == 1
    assert isinstance(executaveis[0], ast.Expr)
    assert isinstance(executaveis[0].value, ast.Constant)
    assert executaveis[0].value.value is Ellipsis


def test_u51_o_corpo_da_porta_nao_faz_nada():
    """Prova por **execução**, não só por AST.

    Chamar o método não vinculado do `Protocol` executa seu corpo — a
    elipse — e devolve `None`. É a diferença entre "o port declara
    fronteira" e "o port implementa efeito": se algum dia o corpo passar a
    fazer algo, este teste deixa de valer.

    ```text
    PORT = DECLARED_BOUNDARY
    PORT != IMPLEMENTATION
    ```
    """
    fake = _FakeAdapter(nao_iniciada())
    assert ErasureEffectPort.attempt_effect(fake, requisicao()) is None
    # e o fake, chamado pela interface, devolve o resultado de verdade
    assert fake.attempt_effect(requisicao()) is not None
