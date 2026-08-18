"""
Testes unitários dos contratos de resolução de alvo (`E4.9.7`).

O que estes testes protegem, acima de tudo: que resolver seja
observacional e que nenhum símbolo novo implique autoridade ou efeito.

```text
REFERENCE != RESOLVED_TARGET
TARGET_RESOLUTION != DELETION_AUTHORITY
```
"""

import uuid
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.memory.models.erasure_enums import ErasureTargetClass
from app.memory.models.target_resolution_enums import TargetResolutionRefusalReason
from app.memory.ports.erasure_target import ErasureTargetResolverPort
from app.memory.schemas.erasure_target import (
    CLASSES_DE_CONTEUDO,
    LOCALIZADOR_OCULTO,
    MAX_OPAQUE_LENGTH,
    NOMES_DE_CAMPO_PROIBIDOS,
    ControlScope,
    CustodyNamespace,
    ErasureTargetDescriptor,
    ErasureTargetReference,
    TargetResolutionRefusal,
    TargetResolutionResult,
    VerifiedDeletionCapability,
    validar_texto_opaco,
)

W1, T1, S1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
AGORA = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
LOCALIZADOR = "s3://bucket-privado/objeto-abc123"


def _chamar(alvo: object, metodo: str, **kwargs: object) -> object:
    """Chamada dinâmica para entradas deliberadamente inválidas.

    Uma função obtida por `getattr` não tem assinatura conhecida, então o
    argumento inválido é expresso sem `# type: ignore` — a disciplina que
    a E4.9.6.3 estabeleceu.
    """
    funcao: Callable[..., object] = getattr(alvo, metodo)
    return funcao(**kwargs)


def _construir(alvo: Callable[..., object], **kwargs: object) -> object:
    return alvo(**kwargs)


def _atribuir_campo(alvo: object, campo: str, valor: object) -> None:
    setattr(alvo, campo, valor)


def escopo(**overrides: object) -> ControlScope:
    base: dict[str, object] = {
        "workspace_id": W1,
        "tenant_id": T1,
        "control_principal_ref": "principal:controle-1",
    }
    base.update(overrides)
    construido = _construir(ControlScope, **base)
    assert isinstance(construido, ControlScope)
    return construido


def custodia(**overrides: object) -> CustodyNamespace:
    base: dict[str, object] = {"provider": "pia-storage", "namespace": "workspace/w1"}
    base.update(overrides)
    construido = _construir(CustodyNamespace, **base)
    assert isinstance(construido, CustodyNamespace)
    return construido


def capacidade(**overrides: object) -> VerifiedDeletionCapability:
    base: dict[str, object] = {
        "operation": "delete_object",
        "scope": "workspace/w1/*",
        "verified": True,
    }
    base.update(overrides)
    construida = _construir(VerifiedDeletionCapability, **base)
    assert isinstance(construida, VerifiedDeletionCapability)
    return construida


def descritor(**overrides: object) -> ErasureTargetDescriptor:
    base: dict[str, object] = {
        "target_class": ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        "subject_coid": S1,
        "control_scope": escopo(),
        "custody_namespace": custodia(),
        "capability": capacidade(),
        "resolved_at": AGORA,
        "origin": "payload_ref",
        "transient_locator": LOCALIZADOR,
    }
    base.update(overrides)
    construido = _construir(ErasureTargetDescriptor, **base)
    assert isinstance(construido, ErasureTargetDescriptor)
    return construido


def referencia(**overrides: object) -> ErasureTargetReference:
    base: dict[str, object] = {
        "subject_coid": S1,
        "opaque_reference": "payload://abc",
        "origin": "payload_ref",
        "control_scope": escopo(),
    }
    base.update(overrides)
    construida = _construir(ErasureTargetReference, **base)
    assert isinstance(construida, ErasureTargetReference)
    return construida


def recusa(**overrides: object) -> TargetResolutionRefusal:
    base: dict[str, object] = {
        "reason": TargetResolutionRefusalReason.UNRESOLVED_OPAQUE_REFERENCE,
        "subject_coid": S1,
        "origin": "payload_ref",
    }
    base.update(overrides)
    construida = _construir(TargetResolutionRefusal, **base)
    assert isinstance(construida, TargetResolutionRefusal)
    return construida


# ======================================================================
# Taxonomia
# ======================================================================


def test_u01_a_taxonomia_reutilizada_tem_exatamente_as_quatro_classes():
    """Nenhum enum novo de classe: o da E4.9.5 já é o canônico.

    Um segundo vocabulário com os mesmos quatro membros criaria duas
    fontes da verdade sobre classificação.
    """
    assert [c.value for c in ErasureTargetClass] == [
        "pia_managed_artifact",
        "authorized_connector_referent",
        "cognitive_metadata_record",
        "unresolved_opaque_reference",
    ]


def test_u02_somente_duas_classes_sao_conteudo():
    assert (
        frozenset(
            {
                ErasureTargetClass.PIA_MANAGED_ARTIFACT,
                ErasureTargetClass.AUTHORIZED_CONNECTOR_REFERENT,
            }
        )
        == CLASSES_DE_CONTEUDO
    )


def test_u03_motivos_de_recusa_sao_fechados_e_sem_generico():
    """`UNKNOWN`/`OTHER` seria o best effort proibido, com outro nome."""
    valores = [r.value for r in TargetResolutionRefusalReason]
    assert valores == [
        "unresolved_opaque_reference",
        "cognitive_metadata_is_not_content",
        "control_scope_mismatch",
        "deletion_capability_not_verified",
        "provider_namespace_out_of_scope",
        "stale_resolution",
    ]
    for proibido in ("UNKNOWN", "OTHER", "GENERIC", "FALLBACK", "PARTIAL"):
        assert proibido not in TargetResolutionRefusalReason.__members__


@pytest.mark.parametrize(
    "classe",
    [
        ErasureTargetClass.COGNITIVE_METADATA_RECORD,
        ErasureTargetClass.UNRESOLVED_OPAQUE_REFERENCE,
    ],
)
def test_u04_classe_que_nao_e_conteudo_nao_constroi_descritor(classe):
    """`METADATA REMOVAL != CONTENT ERASURE`."""
    with pytest.raises(ValueError, match="não é conteúdo apagável"):
        descritor(target_class=classe)


@pytest.mark.parametrize(
    "classe",
    [
        ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        ErasureTargetClass.AUTHORIZED_CONNECTOR_REFERENT,
    ],
)
def test_u05_as_duas_classes_de_conteudo_constroem(classe):
    assert descritor(target_class=classe).target_class is classe


def test_u06_classe_de_tipo_errado_recusada():
    with pytest.raises(TypeError, match="ErasureTargetClass"):
        descritor(target_class="pia_managed_artifact")


# ======================================================================
# Construção e invariantes
# ======================================================================


def test_u07_capacidade_nao_verificada_nao_vira_descritor():
    """Capacidade presumida é a forma silenciosa do confused deputy."""
    with pytest.raises(ValueError, match="VERIFICADA"):
        descritor(capability=capacidade(verified=False))


def test_u08_verified_exige_bool_verdadeiro():
    for valor in (1, 0, "sim", None):
        with pytest.raises(TypeError, match="verified deve ser bool"):
            capacidade(verified=valor)


@pytest.mark.parametrize("campo", ["opaque_reference", "origin"])
@pytest.mark.parametrize("valor", ["", "   ", "\t", 42, None, [], {}])
def test_u09_texto_opaco_vazio_ou_de_tipo_errado_recusado(campo, valor):
    with pytest.raises((TypeError, ValueError)):
        referencia(**{campo: valor})


@pytest.mark.parametrize(
    "invisivel",
    ["\u0000", "\u000a", "\u007f", "\u0085", "\u200b", "\u202e", "\u2028", "\u2029"],
)
def test_u10_invisiveis_unicode_recusados_no_texto_opaco(invisivel):
    with pytest.raises(ValueError, match="caracteres de controle"):
        referencia(opaque_reference=f"ref{invisivel}x")


@pytest.mark.parametrize(
    "valido",
    ["ação", "produção", "São_Paulo", "s3://bucket/coração", "ref com espaço"],
)
def test_u11_unicode_visivel_preservado_byte_a_byte(valido):
    """`VALIDATED OPAQUE VALUE != NORMALIZED VALUE`."""
    devolvido = validar_texto_opaco("origin", valido)
    assert devolvido is valido
    assert devolvido.encode("utf-8") == valido.encode("utf-8")


def test_u12_sequencias_unicode_distintas_nao_sao_fundidas():
    precomposta, decomposta = "a\u00e7\u00e3o", "ac\u0327a\u0303o"
    assert precomposta != decomposta
    assert validar_texto_opaco("origin", precomposta) == precomposta
    assert validar_texto_opaco("origin", decomposta) == decomposta


def test_u13_teto_de_tamanho_respeitado():
    assert validar_texto_opaco("origin", "x" * MAX_OPAQUE_LENGTH)
    with pytest.raises(ValueError, match="excede"):
        validar_texto_opaco("origin", "x" * (MAX_OPAQUE_LENGTH + 1))


@pytest.mark.parametrize("valor", [datetime(2026, 8, 18, 12, 0), "2026-08-18", 0, None])
def test_u14_resolved_at_ingenuo_ou_de_tipo_errado_recusado(valor):
    """Assumir fuso seria inventar um instante que ninguém declarou."""
    with pytest.raises((TypeError, ValueError)):
        descritor(resolved_at=valor)


@pytest.mark.parametrize("valor", ["nao-uuid", 42, None, str(S1)])
def test_u15_subject_coid_exige_uuid_real(valor):
    with pytest.raises(TypeError, match="subject_coid deve ser UUID"):
        descritor(subject_coid=valor)


def test_u16_escopo_e_custodia_exigem_os_tipos_proprios():
    with pytest.raises(TypeError, match="ControlScope"):
        descritor(control_scope={"workspace_id": W1})
    with pytest.raises(TypeError, match="CustodyNamespace"):
        descritor(custody_namespace="pia-storage")
    with pytest.raises(TypeError, match="VerifiedDeletionCapability"):
        descritor(capability="delete_object")


def test_u17_expected_namespace_e_opcional_mas_tipado():
    assert referencia().expected_namespace is None
    assert referencia(expected_namespace=custodia()).expected_namespace == custodia()
    with pytest.raises(TypeError, match="CustodyNamespace"):
        referencia(expected_namespace="pia-storage")


def test_u18_version_etag_e_opcional_mas_validado():
    assert descritor().version_etag is None
    assert descritor(version_etag='W/"abc"').version_etag == 'W/"abc"'
    with pytest.raises(ValueError):
        descritor(version_etag="   ")


def test_u19_invariantes_valem_no_construtor_direto():
    """Não apenas em factory — a lição repetida desde a E4.2.1."""
    with pytest.raises(ValueError):
        ErasureTargetDescriptor(
            target_class=ErasureTargetClass.COGNITIVE_METADATA_RECORD,
            subject_coid=S1,
            control_scope=escopo(),
            custody_namespace=custodia(),
            capability=capacidade(),
            resolved_at=AGORA,
            origin="payload_ref",
            transient_locator=LOCALIZADOR,
        )


# ======================================================================
# Imutabilidade
# ======================================================================


@pytest.mark.parametrize(
    "objeto_campo",
    [
        ("descritor", "origin"),
        ("descritor", "transient_locator"),
        ("descritor", "target_class"),
        ("referencia", "opaque_reference"),
        ("recusa", "reason"),
        ("escopo", "workspace_id"),
        ("custodia", "provider"),
        ("capacidade", "verified"),
    ],
)
def test_u20_todos_os_value_objects_sao_congelados(objeto_campo):
    nome, campo = objeto_campo
    fabrica = {
        "descritor": descritor,
        "referencia": referencia,
        "recusa": recusa,
        "escopo": escopo,
        "custodia": custodia,
        "capacidade": capacidade,
    }[nome]
    alvo = fabrica()
    with pytest.raises(FrozenInstanceError):
        _atribuir_campo(alvo, campo, "outro")


def test_u21_nenhuma_colecao_mutavel_publica():
    """Nenhum campo de conjunto — e é isso que fecha target expansion."""
    for alvo in (descritor(), referencia(), recusa()):
        for valor in vars(alvo).values():
            assert not isinstance(valor, list | dict | set), type(valor)


# ======================================================================
# Confidencialidade do localizador
# ======================================================================


def test_u22_repr_e_str_nao_revelam_o_localizador():
    """`MUST_NOT_APPEAR_IN_CLEAR_REPR_OR_STR`."""
    d = descritor()
    assert LOCALIZADOR not in repr(d)
    assert LOCALIZADOR not in str(d)
    assert LOCALIZADOR not in f"{d}"
    assert LOCALIZADOR not in "{}".format(d)  # noqa: UP032
    assert LOCALIZADOR_OCULTO in repr(d)


def test_u23_o_localizador_continua_acessivel_ao_titular_do_objeto():
    """Redigir a representação não é esconder o valor de quem o resolveu."""
    assert descritor().transient_locator == LOCALIZADOR


def test_u24_recusa_nao_carrega_localizador():
    r = recusa(diagnostic="referência não resolvida por adaptador autorizado")
    assert LOCALIZADOR not in repr(r)
    assert "transient_locator" not in {campo for campo in vars(r)}


def test_u25_nenhum_campo_de_credencial_nos_contratos():
    """Capacidade verificada é afirmação tipada, não a credencial."""
    for alvo in (descritor(), referencia(), recusa(), capacidade(), custodia(), escopo()):
        for campo in vars(alvo):
            assert campo.lower() not in NOMES_DE_CAMPO_PROIBIDOS, (type(alvo), campo)


def test_u26_nenhum_serializer_publico_no_descritor():
    """Sem `to_dict`/`model_dump` não há caminho fácil para vazar."""
    for proibido in ("to_dict", "model_dump", "json", "dict", "serialize", "as_dict"):
        assert not hasattr(descritor(), proibido), proibido


# ======================================================================
# Resultado discriminado
# ======================================================================


def test_u27_sucesso_e_recusa_sao_classes_disjuntas():
    """Nenhum objeto pode ser as duas coisas — não há campo de estado."""
    d, r = descritor(), recusa()
    assert isinstance(d, ErasureTargetDescriptor)
    assert not isinstance(d, TargetResolutionRefusal)
    assert isinstance(r, TargetResolutionRefusal)
    assert not isinstance(r, ErasureTargetDescriptor)


def test_u28_narrowing_estatico_sem_any_nem_cast():
    """O consumidor distingue por `isinstance` e o mypy acompanha."""

    def consumir(resultado: TargetResolutionResult) -> str:
        if isinstance(resultado, ErasureTargetDescriptor):
            return resultado.custody_namespace.provider
        return resultado.reason.value

    assert consumir(descritor()) == "pia-storage"
    assert consumir(recusa()) == "unresolved_opaque_reference"


def test_u29_nao_resolucao_nunca_e_none_false_dict_ou_excecao():
    r = recusa()
    assert r is not None
    assert r is not False
    assert not isinstance(r, dict | str)
    assert not isinstance(r, Exception)


def test_u30_recusa_preserva_a_classificacao_quando_houve():
    r = recusa(
        reason=TargetResolutionRefusalReason.COGNITIVE_METADATA_IS_NOT_CONTENT,
        classified_as=ErasureTargetClass.COGNITIVE_METADATA_RECORD,
    )
    assert r.classified_as is ErasureTargetClass.COGNITIVE_METADATA_RECORD
    assert recusa().classified_as is None


def test_u31_recusa_exige_motivo_do_vocabulario_fechado():
    with pytest.raises(TypeError, match="TargetResolutionRefusalReason"):
        recusa(reason="unresolved_opaque_reference")


# ======================================================================
# Porta observacional
# ======================================================================


class _ResolvedorObservacional:
    """Dublê que **conta** o que faria, e não faz nada.

    Não recebe sessão, repositório nem cliente, porque a assinatura da
    porta não os oferece — e é essa ausência que torna a contagem em
    zero uma prova, e não uma promessa.
    """

    def __init__(self) -> None:
        self.escritas = 0
        self.chamadas_externas = 0
        self.resolucoes = 0

    def resolve_target(self, reference: ErasureTargetReference) -> TargetResolutionResult:
        self.resolucoes += 1
        if reference.control_scope.workspace_id != W1:
            return TargetResolutionRefusal(
                reason=TargetResolutionRefusalReason.CONTROL_SCOPE_MISMATCH,
                subject_coid=reference.subject_coid,
                origin=reference.origin,
            )
        return descritor(subject_coid=reference.subject_coid, origin=reference.origin)


def test_u32_implementacao_estrutural_satisfaz_o_protocolo():
    assert isinstance(_ResolvedorObservacional(), ErasureTargetResolverPort)


def test_u33_atribuicao_estatica_da_porta_e_valida():
    """`RUNTIME_CHECKABLE != STATIC SIGNATURE COMPATIBILITY` (E4.7.1).

    `isinstance` confere só nomes de membros; esta atribuição é o que o
    mypy verifica.
    """
    porta: ErasureTargetResolverPort = _ResolvedorObservacional()
    resultado = porta.resolve_target(referencia())
    assert isinstance(resultado, ErasureTargetDescriptor)


def test_u34_resolucao_nao_produz_escrita_nem_chamada_externa():
    """`RESOLUTION_IS_OBSERVATIONAL = TRUE`."""
    dubl = _ResolvedorObservacional()
    porta: ErasureTargetResolverPort = dubl
    for _ in range(5):
        porta.resolve_target(referencia())
    assert dubl.resolucoes == 5
    assert dubl.escritas == 0
    assert dubl.chamadas_externas == 0


def test_u35_escopo_divergente_nao_vira_sucesso():
    """Fecha o cross-tenant no comportamento, não só no contrato."""
    porta: ErasureTargetResolverPort = _ResolvedorObservacional()
    resultado = porta.resolve_target(referencia(control_scope=escopo(workspace_id=uuid.uuid4())))
    assert isinstance(resultado, TargetResolutionRefusal)
    assert resultado.reason is TargetResolutionRefusalReason.CONTROL_SCOPE_MISMATCH


def test_u36_a_porta_nao_aceita_nem_devolve_objeto_de_efeito():
    """A assinatura é a garantia, e ela tem exatamente um parâmetro."""
    import inspect

    assinatura = inspect.signature(ErasureTargetResolverPort.resolve_target)
    assert list(assinatura.parameters) == ["self", "reference"]


def test_u37_referencia_legada_nao_e_promovida_a_localizador():
    """`payload_ref != ErasureTargetDescriptor` (E4.9.1 §9)."""
    ref = referencia(opaque_reference="payload://legado-123")
    resolvido = _ResolvedorObservacional().resolve_target(ref)
    assert isinstance(resolvido, ErasureTargetDescriptor)
    assert resolvido.transient_locator != ref.opaque_reference


def test_u38_um_descritor_representa_exatamente_um_alvo():
    """Sem curinga e sem expansão: não há onde escrever vários."""
    campos = set(vars(descritor()))
    for plural in ("targets", "locators", "subject_coids", "namespaces", "scopes"):
        assert plural not in campos


def test_u39_origem_e_rastreabilidade_nunca_autoridade():
    """Mudar a origem não altera nada sobre poder agir."""
    a = descritor(origin="payload_ref")
    b = descritor(origin="evidence_refs")
    assert a.capability == b.capability
    assert a.control_scope == b.control_scope
    assert a.target_class == b.target_class


def test_u40_descritor_carrega_a_identidade_contextual_completa():
    """Workspace, tenant, principal, provedor e namespace, todos presentes."""
    d = descritor()
    assert d.control_scope.workspace_id == W1
    assert d.control_scope.tenant_id == T1
    assert d.control_scope.control_principal_ref == "principal:controle-1"
    assert d.custody_namespace.provider == "pia-storage"
    assert d.custody_namespace.namespace == "workspace/w1"


# ======================================================================
# Cobertura das recusas de tipo restantes
#
# Descobertas pela exigência de 100%: cada uma é uma fronteira real que
# nenhum teste anterior tocava, não linha morta.
# ======================================================================


@pytest.mark.parametrize("campo", ["workspace_id", "tenant_id"])
@pytest.mark.parametrize("valor", ["nao-uuid", 42, None, b"x"])
def test_u41_escopo_exige_uuid_real_nos_dois_identificadores(campo, valor):
    with pytest.raises(TypeError, match=f"{campo} deve ser UUID"):
        escopo(**{campo: valor})


@pytest.mark.parametrize("valor", ["nao-uuid", 42, None])
def test_u42_referencia_exige_uuid_no_subject_coid(valor):
    with pytest.raises(TypeError, match="subject_coid deve ser UUID"):
        referencia(subject_coid=valor)


@pytest.mark.parametrize("valor", [{"workspace_id": W1}, "escopo", 42, None])
def test_u43_referencia_exige_control_scope_tipado(valor):
    with pytest.raises(TypeError, match="ControlScope"):
        referencia(control_scope=valor)


@pytest.mark.parametrize("valor", ["nao-uuid", 42, None])
def test_u44_recusa_exige_uuid_no_subject_coid(valor):
    with pytest.raises(TypeError, match="subject_coid deve ser UUID"):
        recusa(subject_coid=valor)


@pytest.mark.parametrize("valor", ["cognitive_metadata_record", 42, object()])
def test_u45_recusa_exige_classificacao_tipada_ou_none(valor):
    with pytest.raises(TypeError, match="ErasureTargetClass"):
        recusa(classified_as=valor)
