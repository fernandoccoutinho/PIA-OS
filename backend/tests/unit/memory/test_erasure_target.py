"""
Testes unitários dos contratos de resolução de alvo (`E4.9.7`).

O que estes testes protegem, acima de tudo: que resolver seja
observacional e que nenhum símbolo novo implique autoridade ou efeito.

```text
REFERENCE != RESOLVED_TARGET
TARGET_RESOLUTION != DELETION_AUTHORITY
```
"""

import pathlib
import uuid
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.memory.models.erasure_enums import ErasureTargetClass
from app.memory.models.target_resolution_enums import (
    ORIGENS_PLURAIS,
    LegacyProtectionState,
    ReferenceOrigin,
    RefusalDimension,
    TargetResolutionRefusalReason,
)
from app.memory.ports.erasure_target import ErasureTargetResolverPort
from app.memory.schemas.erasure_target import (
    CLASSES_DE_CONTEUDO,
    LOCALIZADOR_OCULTO,
    MAX_OPAQUE_LENGTH,
    METACARACTERES_DE_EXPANSAO,
    NOMES_DE_CAMPO_PROIBIDOS,
    REFERENCIA_OCULTA,
    ControlScope,
    CustodyNamespace,
    ErasureTargetDescriptor,
    ErasureTargetReference,
    ReferenceProvenance,
    TargetResolutionRefusal,
    TargetResolutionResult,
    VerifiedDeletionCapability,
    validar_localizador_sem_expansao_literal,
    validar_texto_opaco,
)

W1, T1, S1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
AGORA = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
LOCALIZADOR = "s3://bucket-privado/objeto-abc123"
PROVENIENCIA = ReferenceProvenance(ReferenceOrigin.PAYLOAD_REF)
SEGREDO = "https://user:password@storage.example/object?token=secret"


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
        "origin": PROVENIENCIA,
        # E4.9.8.3 — escolha CONSCIENTE, não conveniência. As fábricas
        # default declaram NOT_PROTECTED, e os testes nominais u109+
        # exercitam PROTECTED explicitamente nos dois lados. Nenhum caso
        # depende do default para provar comportamento de proteção.
        "legacy_protection_state": LegacyProtectionState.NOT_PROTECTED,
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
        "origin": PROVENIENCIA,
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
        "origin": PROVENIENCIA,
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
        # E4.9.8.3 — indeterminação da proteção de legado é RECUSA, não
        # estado: por isso o motivo entra aqui e LegacyProtectionState
        # continua com exatamente dois membros.
        "legacy_protection_state_unresolved",
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
            origin=PROVENIENCIA,
            legacy_protection_state=LegacyProtectionState.NOT_PROTECTED,
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
    """ATUALIZADO NA E4.9.7.1 — `diagnostic` de texto livre foi removido.

    A versão da cadeia 80 passava um diagnóstico benigno e concluía que
    a recusa não vazava. A auditoria passou o localizador e o campo o
    aceitou, com a representação padrão revelando-o. Agora não há campo
    de texto livre onde ele pudesse caber.
    """
    r = recusa(observed_dimension=RefusalDimension.REFERENCE)
    assert LOCALIZADOR not in repr(r)
    assert LOCALIZADOR not in str(r)
    campos = set(vars(r))
    assert "transient_locator" not in campos
    assert "diagnostic" not in campos


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

    CUSTODIA_CANONICA = ("pia-storage", "workspace/w1")

    def resolve_target(self, reference: ErasureTargetReference) -> TargetResolutionResult:
        self.resolucoes += 1

        # ATUALIZADO NA E4.9.7.1. A versão da cadeia 80 comparava APENAS
        # `workspace_id`, e o EDR afirmava fechamento de cross-tenant e de
        # divergências de contexto mais amplas. A auditoria mediu: tenant,
        # principal, provedor e namespace divergentes devolviam descritor
        # de SUCESSO. Cada dimensão agora tem recusa própria, e cada uma
        # tem teste comportamental independente.
        escopo_divergente = {
            RefusalDimension.WORKSPACE: reference.control_scope.workspace_id != W1,
            RefusalDimension.TENANT: reference.control_scope.tenant_id != T1,
            RefusalDimension.CONTROL_PRINCIPAL: (
                reference.control_scope.control_principal_ref != "principal:controle-1"
            ),
        }
        for dimensao, divergiu in escopo_divergente.items():
            if divergiu:
                return TargetResolutionRefusal(
                    reason=TargetResolutionRefusalReason.CONTROL_SCOPE_MISMATCH,
                    subject_coid=reference.subject_coid,
                    origin=reference.origin,
                    observed_dimension=dimensao,
                )

        # `expected_namespace=None` continua legítimo: a maior parte das
        # referências da E3 não diz onde o conteúdo vive. Ausência NÃO
        # fabrica correspondência — apenas não há o que comparar.
        esperado = reference.expected_namespace
        if esperado is not None:
            provedor, namespace = self.CUSTODIA_CANONICA
            divergencia = {
                RefusalDimension.PROVIDER: esperado.provider != provedor,
                RefusalDimension.NAMESPACE: esperado.namespace != namespace,
            }
            for dimensao, divergiu in divergencia.items():
                if divergiu:
                    return TargetResolutionRefusal(
                        reason=(TargetResolutionRefusalReason.PROVIDER_NAMESPACE_OUT_OF_SCOPE),
                        subject_coid=reference.subject_coid,
                        origin=reference.origin,
                        observed_dimension=dimensao,
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
    """Prova CONTRATUAL de isolamento, não fechamento em runtime externo.

    Corrigido na E4.9.7.2. A cadeia 81 dizia "fecha o cross-tenant no
    comportamento" — o dublê é o contrato exercitado, não um resolvedor
    real, e não há adaptador nesta fatia.

    ```text
    CONTRACT_AND_FAKE_ISOLATION_PROOF = IMPLEMENTED
    EXTERNAL_RUNTIME_CROSS_TENANT_CLOSURE = DEFERRED
    ```
    """
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
    a = descritor(origin=PROVENIENCIA)
    b = descritor(origin=ReferenceProvenance(ReferenceOrigin.EVIDENCE_REFS))
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


# ======================================================================
# E4.9.7.1 — alvo exato, isolamento contextual e confidencialidade
#
# As oito evidências da auditoria da cadeia 80 viram regressão aqui.
# A1: um campo escalar não prova cardinalidade — a string cabia `*`.
# A2: o dublê comparava só workspace, e o EDR afirmava mais.
# A3: `repr` redigido não torna o objeto livre de segredo.
# ======================================================================


# --- A1: alvo exato ------------------------------------------------------


@pytest.mark.parametrize(
    "locator",
    [
        "s3://bucket/*",
        "s3://bucket/prefixo/*",
        "s3://bucket/[a-z].txt",
        "s3://bucket/{a,b}.txt",
        "pia://workspace/w1/*",
        "*",
    ],
)
def test_u46_localizador_com_expansao_recusado(locator):
    """`FIELD_COUNT = 1 DOES_NOT_PROVE TARGET_CARDINALITY = 1`."""
    with pytest.raises(ValueError, match="exatamente um alvo"):
        descritor(transient_locator=locator)


def test_u47_glob_de_um_caractere_recusado():
    """`?` designa um caractere qualquer — e também abre query."""
    with pytest.raises(ValueError, match="query nem fragmento"):
        descritor(transient_locator="s3://bucket/fi?e.txt")


@pytest.mark.parametrize("locator", ["s3://bucket/prefixo/", "pia://workspace/w1/", "s3://bucket/"])
def test_u48_prefixo_terminado_em_barra_recusado(locator):
    """Prefixo designa coleção, não objeto."""
    with pytest.raises(ValueError, match="coleção"):
        descritor(transient_locator=locator)


def test_u49_metacaracteres_sao_neutros_de_provedor():
    """Nenhum deles é sintaxe de um storage específico."""
    assert set(METACARACTERES_DE_EXPANSAO) == {"*", "[", "]", "{", "}"}


@pytest.mark.parametrize(
    "locator",
    [
        "s3://bucket-privado/objeto-abc123",
        "pia://workspace/w1/artefato-1",
        "gs://outro/objeto.bin",
        "arquivo,com,virgula.txt",
    ],
)
def test_u50_localizador_exato_aceito_sem_normalizacao(locator):
    devolvido = validar_localizador_sem_expansao_literal("transient_locator", locator)
    assert devolvido is locator
    assert devolvido.encode("utf-8") == locator.encode("utf-8")


def test_u51_localizador_com_unicode_portugues_preservado():
    locator = "s3://bucket/ação/produção-São_Paulo.txt"
    assert validar_localizador_sem_expansao_literal("transient_locator", locator) is locator
    assert descritor(transient_locator=locator).transient_locator == locator


def test_u52_a_capacidade_ainda_pode_expressar_escopo_amplo():
    """Distinção que o corretivo NÃO pode apagar.

    `capability.scope` descreve o que a conta **pode** — legitimamente
    um conjunto, como `workspace/w1/*`. O localizador descreve **um
    objeto**. Aplicar a mesma regra aos dois confundiria autoridade com
    alvo, que é o oposto do contrato.
    """
    d = descritor(capability=capacidade(scope="workspace/w1/*"))
    assert d.capability.scope == "workspace/w1/*"
    assert "*" not in d.transient_locator


# --- A3a: segredo no localizador ----------------------------------------


@pytest.mark.parametrize(
    "locator",
    [
        "https://user:password@storage.example/object",
        "https://u:p@host/obj",
        "https://apenas-usuario@host/obj",
        "s3://AKIAEXEMPLO:chave@bucket/objeto",
    ],
)
def test_u53_userinfo_recusado_como_credencial_embutida(locator):
    """`REDACTED_REPR != SECRET_FREE_OBJECT`."""
    with pytest.raises(ValueError, match="credencial"):
        descritor(transient_locator=locator)


@pytest.mark.parametrize(
    "locator",
    [
        "https://storage.example/object?token=secret",
        "https://storage.example/object?signature=abc",
        "https://storage.example/object?api_key=x&expires=1",
        "https://storage.example/object?credential=y",
        "https://storage.example/object#signature=abc",
        "s3://bucket/objeto?versionId=1",
    ],
)
def test_u54_query_e_fragmento_recusados(locator):
    """Parâmetro de capacidade não pertence ao localizador.

    A recusa é **estrutural** — toda query cai, não apenas as que
    contêm palavras conhecidas. É mais forte que vocabulário e não
    depende de adivinhar o nome do parâmetro de cada provedor. Versão
    tem campo próprio: `version_etag`.
    """
    with pytest.raises(ValueError, match="query nem fragmento"):
        descritor(transient_locator=locator)


def test_u55_a_url_assinada_do_reprodutor_e_recusada():
    """O caso exato medido pela auditoria da cadeia 80."""
    with pytest.raises(ValueError):
        descritor(
            transient_locator=(
                "https://user:password@storage.example/object" "?token=secret&signature=abc"
            )
        )


def test_u56_versao_continua_tendo_campo_proprio():
    """Se a versão tem onde ir, o localizador não precisa de query."""
    d = descritor(version_etag='W/"v2"')
    assert d.version_etag == 'W/"v2"'
    assert "?" not in d.transient_locator


# --- A3b: diagnóstico -----------------------------------------------------


def test_u57_diagnostico_de_texto_livre_nao_existe_mais():
    """`SAFE_DIAGNOSTIC != FREE_TEXT`.

    Na cadeia 80 este construtor aceitava o localizador. Agora o campo
    não existe, então não há onde ele caber.
    """
    with pytest.raises(TypeError):
        _construir(
            TargetResolutionRefusal,
            reason=TargetResolutionRefusalReason.UNRESOLVED_OPAQUE_REFERENCE,
            subject_coid=S1,
            origin=PROVENIENCIA,
            diagnostic=LOCALIZADOR,
        )


@pytest.mark.parametrize(
    "valor",
    [
        LOCALIZADOR,
        "https://user:password@storage.example/object?token=secret",
        "token=abc",
        "workspace",
    ],
)
def test_u58_contexto_seguro_nao_aceita_texto(valor):
    """Vocabulário fechado: nem o localizador, nem sequer o nome certo."""
    with pytest.raises(TypeError, match="RefusalDimension"):
        recusa(observed_dimension=valor)


def test_u59_dimensoes_de_recusa_sao_fechadas_e_sem_generico():
    assert [d.value for d in RefusalDimension] == [
        "workspace",
        "tenant",
        "control_principal",
        "provider",
        "namespace",
        "reference",
        "capability",
        "resolution_freshness",
    ]
    for proibido in ("UNKNOWN", "OTHER", "GENERIC", "FREE_TEXT", "DETAIL"):
        assert proibido not in RefusalDimension.__members__


@pytest.mark.parametrize("dimensao", list(RefusalDimension))
def test_u60_nenhuma_forma_de_recusa_revela_localizador(dimensao):
    r = recusa(observed_dimension=dimensao)
    assert LOCALIZADOR not in repr(r)
    assert LOCALIZADOR not in str(r)


@pytest.mark.parametrize("motivo", list(TargetResolutionRefusalReason))
def test_u61_repr_de_toda_recusa_e_seguro(motivo):
    r = recusa(reason=motivo, classified_as=ErasureTargetClass.COGNITIVE_METADATA_RECORD)
    for proibido in (LOCALIZADOR, "password", "token", "secret"):
        assert proibido not in repr(r)
        assert proibido not in str(r)


# --- A2: isolamento contextual, dimensão por dimensão --------------------


def test_u62_workspace_divergente_recusado():
    porta: ErasureTargetResolverPort = _ResolvedorObservacional()
    r = porta.resolve_target(referencia(control_scope=escopo(workspace_id=uuid.uuid4())))
    assert isinstance(r, TargetResolutionRefusal)
    assert r.reason is TargetResolutionRefusalReason.CONTROL_SCOPE_MISMATCH
    assert r.observed_dimension is RefusalDimension.WORKSPACE


def test_u63_tenant_divergente_recusado():
    """Na cadeia 80 este caso devolvia descritor de SUCESSO."""
    porta: ErasureTargetResolverPort = _ResolvedorObservacional()
    r = porta.resolve_target(referencia(control_scope=escopo(tenant_id=uuid.uuid4())))
    assert isinstance(r, TargetResolutionRefusal)
    assert r.reason is TargetResolutionRefusalReason.CONTROL_SCOPE_MISMATCH
    assert r.observed_dimension is RefusalDimension.TENANT


def test_u64_principal_de_controle_divergente_recusado():
    porta: ErasureTargetResolverPort = _ResolvedorObservacional()
    r = porta.resolve_target(
        referencia(control_scope=escopo(control_principal_ref="principal:outro"))
    )
    assert isinstance(r, TargetResolutionRefusal)
    assert r.reason is TargetResolutionRefusalReason.CONTROL_SCOPE_MISMATCH
    assert r.observed_dimension is RefusalDimension.CONTROL_PRINCIPAL


def test_u65_provedor_divergente_recusado():
    porta: ErasureTargetResolverPort = _ResolvedorObservacional()
    r = porta.resolve_target(referencia(expected_namespace=custodia(provider="outro")))
    assert isinstance(r, TargetResolutionRefusal)
    assert r.reason is TargetResolutionRefusalReason.PROVIDER_NAMESPACE_OUT_OF_SCOPE
    assert r.observed_dimension is RefusalDimension.PROVIDER


def test_u66_namespace_divergente_recusado():
    porta: ErasureTargetResolverPort = _ResolvedorObservacional()
    r = porta.resolve_target(referencia(expected_namespace=custodia(namespace="workspace/outro")))
    assert isinstance(r, TargetResolutionRefusal)
    assert r.reason is TargetResolutionRefusalReason.PROVIDER_NAMESPACE_OUT_OF_SCOPE
    assert r.observed_dimension is RefusalDimension.NAMESPACE


def test_u67_namespace_ausente_e_legitimo_e_nao_fabrica_correspondencia():
    """`expected_namespace=None` continua válido — não há o que comparar."""
    porta: ErasureTargetResolverPort = _ResolvedorObservacional()
    assert referencia().expected_namespace is None
    assert isinstance(porta.resolve_target(referencia()), ErasureTargetDescriptor)


def test_u68_namespace_coincidente_resolve():
    porta: ErasureTargetResolverPort = _ResolvedorObservacional()
    r = porta.resolve_target(
        referencia(expected_namespace=custodia(provider="pia-storage", namespace="workspace/w1"))
    )
    assert isinstance(r, ErasureTargetDescriptor)


def test_u69_isolamento_continua_sem_escrita_nem_chamada_externa():
    """As recusas novas não introduziram efeito colateral."""
    dubl = _ResolvedorObservacional()
    porta: ErasureTargetResolverPort = dubl
    for referencia_divergente in (
        referencia(control_scope=escopo(workspace_id=uuid.uuid4())),
        referencia(control_scope=escopo(tenant_id=uuid.uuid4())),
        referencia(expected_namespace=custodia(provider="outro")),
        referencia(),
    ):
        porta.resolve_target(referencia_divergente)
    assert dubl.resolucoes == 4
    assert dubl.escritas == 0
    assert dubl.chamadas_externas == 0


# ======================================================================
# E4.9.7.2 — origem tipada, referência sensível e fronteira de prova
#
# As cinco evidências do segundo reprodutor viram regressão aqui.
# A3c: `origin: str` era o novo canal livre — nome do campo != tipo.
# A3d: `opaque_reference` é entrada NECESSÁRIA e vazava na representação.
# A1:  restrição lexical não é prova de cardinalidade material.
# ======================================================================


# --- A3c: origem tipada ---------------------------------------------------


@pytest.mark.parametrize(
    "valor",
    [
        LOCALIZADOR,
        SEGREDO,
        "payload_ref",
        "evidence_refs",
        "",
        42,
        None,
        ReferenceOrigin.PAYLOAD_REF,
    ],
)
def test_u70_origem_recusa_texto_na_referencia(valor):
    """`FREE_TEXT_ORIGIN = CONFIDENTIALITY_CHANNEL`.

    Nem o localizador, nem o segredo, nem sequer o nome certo em string —
    e nem o enum cru, que não carrega posição.
    """
    with pytest.raises(TypeError, match="ReferenceProvenance"):
        referencia(origin=valor)


@pytest.mark.parametrize("valor", [LOCALIZADOR, SEGREDO, "payload_ref", 42, None])
def test_u71_origem_recusa_texto_no_descritor(valor):
    with pytest.raises(TypeError, match="ReferenceProvenance"):
        descritor(origin=valor)


@pytest.mark.parametrize("valor", [LOCALIZADOR, SEGREDO, "payload_ref", 42, None])
def test_u72_origem_recusa_texto_na_recusa(valor):
    with pytest.raises(TypeError, match="ReferenceProvenance"):
        recusa(origin=valor)


def test_u73_origin_nao_e_str_em_nenhum_dos_tres_value_objects():
    """`dataclasses.fields` como prova, não a docstring."""
    import dataclasses

    for classe in (ErasureTargetReference, ErasureTargetDescriptor, TargetResolutionRefusal):
        campos = {c.name: c.type for c in dataclasses.fields(classe)}
        assert campos["origin"] is ReferenceProvenance, classe.__name__


def test_u74_as_cinco_origens_reais_da_e3_sao_aceitas():
    """Conferidas no repositório antes de congelar o vocabulário."""
    assert [o.value for o in ReferenceOrigin] == [
        "payload_ref",
        "source_ref",
        "evidence_refs",
        "input_refs",
        "output_refs",
    ]
    for origem in ReferenceOrigin:
        assert referencia(origin=ReferenceProvenance(origem)).origin.origin is origem


def test_u75_nenhum_membro_generico_de_origem():
    for proibido in ("UNKNOWN", "OTHER", "GENERIC", "FALLBACK", "FREE_TEXT", "CUSTOM"):
        assert proibido not in ReferenceOrigin.__members__


@pytest.mark.parametrize("origem", sorted(ORIGENS_PLURAIS, key=lambda o: o.value))
def test_u76_posicao_admitida_apenas_nas_origens_plurais(origem):
    p = ReferenceProvenance(origem, 3)
    assert p.position == 3
    assert p.origin is origem


@pytest.mark.parametrize("origem", [ReferenceOrigin.PAYLOAD_REF, ReferenceOrigin.SOURCE_REF])
def test_u77_posicao_recusada_em_origem_escalar(origem):
    """`payload_ref` e `source_ref` são colunas escalares na E3."""
    with pytest.raises(ValueError, match="não admite position"):
        ReferenceProvenance(origem, 0)
    assert ReferenceProvenance(origem).position is None


@pytest.mark.parametrize("valor", [True, False, "3", 1.5, [], {}])
def test_u78_posicao_exige_inteiro_verdadeiro(valor):
    with pytest.raises(TypeError, match="position deve ser int"):
        ReferenceProvenance(ReferenceOrigin.EVIDENCE_REFS, valor)


def test_u79_posicao_nao_pode_ser_negativa():
    with pytest.raises(ValueError, match=">= 0"):
        ReferenceProvenance(ReferenceOrigin.EVIDENCE_REFS, -1)
    assert ReferenceProvenance(ReferenceOrigin.EVIDENCE_REFS, 0).position == 0


def test_u80_posicao_nao_e_codificada_em_texto():
    """`evidence_refs[3]` em string reabriria o canal livre."""
    with pytest.raises(TypeError):
        referencia(origin="evidence_refs[3]")


def test_u81_proveniencia_e_congelada():
    p = ReferenceProvenance(ReferenceOrigin.INPUT_REFS, 1)
    with pytest.raises(FrozenInstanceError):
        _atribuir_campo(p, "origin", ReferenceOrigin.OUTPUT_REFS)
    with pytest.raises(FrozenInstanceError):
        _atribuir_campo(p, "position", 9)


def test_u82_origem_continua_sem_virar_autoridade():
    """`ORIGIN IS TRACEABILITY, NEVER AUTHORITY`."""
    a = descritor(origin=ReferenceProvenance(ReferenceOrigin.PAYLOAD_REF))
    b = descritor(origin=ReferenceProvenance(ReferenceOrigin.OUTPUT_REFS, 2))
    assert a.capability == b.capability
    assert a.control_scope == b.control_scope
    assert a.target_class == b.target_class


@pytest.mark.parametrize("origem", list(ReferenceOrigin))
def test_u83_nenhuma_representacao_de_recusa_revela_segredo(origem):
    r = recusa(origin=ReferenceProvenance(origem))
    for proibido in (LOCALIZADOR, SEGREDO, "password", "token"):
        assert proibido not in repr(r)
        assert proibido not in str(r)


# --- A3d: referência opaca é entrada sensível necessária ------------------


@pytest.mark.parametrize(
    "valor",
    [
        SEGREDO,
        "https://host/obj?token=abc&signature=x",
        "s3://AKIA:chave@bucket/objeto",
        LOCALIZADOR,
        "payload://abc",
        "referência/comum/ação.txt",
    ],
)
def test_u84_referencia_opaca_nunca_aparece_na_representacao(valor):
    """`REQUIRED_SENSITIVE_INPUT = REDACTED_FROM_REPR_AND_STR`."""
    r = referencia(opaque_reference=valor)
    assert valor not in repr(r)
    assert valor not in str(r)
    assert valor not in f"{r}"
    assert REFERENCIA_OCULTA in repr(r)


def test_u85_referencia_opaca_continua_acessivel_a_quem_resolve():
    """Redigir a representação não pode inutilizar a entrada."""
    r = referencia(opaque_reference=SEGREDO)
    assert r.opaque_reference == SEGREDO
    porta: ErasureTargetResolverPort = _ResolvedorObservacional()
    assert isinstance(porta.resolve_target(r), ErasureTargetDescriptor)


def test_u86_a_referencia_sensivel_nao_e_copiada_para_a_recusa():
    """Nenhuma recusa tem onde guardá-la — não há campo."""
    import dataclasses

    campos = {c.name for c in dataclasses.fields(TargetResolutionRefusal)}
    assert "opaque_reference" not in campos
    assert "transient_locator" not in campos
    assert "diagnostic" not in campos


def test_u87_o_objeto_nao_e_declarado_livre_de_segredo():
    """`REDACTION != SECRET_FREE_OBJECT` — declarado, não escondido.

    O valor sensível está no objeto de propósito, porque a resolução
    precisa dele. O que a fatia garante é que ele não escapa pela
    representação — e a docstring do campo diz isso, em vez de alegar
    ausência.
    """
    fonte = (
        pathlib.Path(__file__).resolve().parents[3]
        / "app"
        / "memory"
        / "schemas"
        / "erasure_target.py"
    ).read_text(encoding="utf-8")
    assert "REDACTION != SECRET_FREE_OBJECT" in fonte
    assert "REQUIRED_SENSITIVE_INPUT" in fonte
    assert referencia(opaque_reference=SEGREDO).opaque_reference == SEGREDO


# --- A1: fronteira entre restrição lexical e exatidão material ------------


def test_u88_o_nome_do_validador_nao_promete_exatidao_material():
    """`RAW_PATTERN_SYNTAX_REJECTION != MATERIAL_TARGET_CARDINALITY_PROOF`.

    A função da cadeia 81 se chamava `validar_localizador_exato` e o EDR
    a apresentava como prova de cardinalidade. Renomear foi a correção,
    não cosmética: o nome antigo prometia o que nenhuma camada sem
    adaptador pode provar.
    """
    from app.memory.schemas import erasure_target

    assert hasattr(erasure_target, "validar_localizador_sem_expansao_literal")
    assert not hasattr(erasure_target, "validar_localizador_exato")


@pytest.mark.parametrize(
    "locator",
    ["s3://bucket/%2A", "s3://bucket/%5Ba-z%5D", "regex://bucket/.+", "glob://b/x"],
)
def test_u89_limite_declarado_percent_encoding_e_scheme_desconhecido(locator):
    """Aceitos de propósito, e o limite é declarado, não escondido.

    Decodificar `%2A` seria interpretar a string em nome de um adaptador
    que não existe, e a interpretação varia por provedor. Rejeitar
    schemes por lista quebraria a neutralidade de provedor.
    """
    assert validar_localizador_sem_expansao_literal("transient_locator", locator) is locator
    assert descritor(transient_locator=locator).transient_locator == locator


def test_u90_nenhuma_decodificacao_silenciosa_no_validador():
    """`unquote` e normalização continuam ausentes."""
    import ast
    import pathlib

    fonte = (
        pathlib.Path(__file__).resolve().parents[3]
        / "app"
        / "memory"
        / "schemas"
        / "erasure_target.py"
    ).read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    (validador,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "validar_localizador_sem_expansao_literal"
    ]
    corpo = ast.unparse(
        ast.Module(
            body=[linha for linha in validador.body if not isinstance(linha, ast.Expr)],
            type_ignores=[],
        )
    )
    for proibido in ("unquote", "normalize", "casefold", "lower()", "replace("):
        assert proibido not in corpo, proibido


def test_u91_a_recusa_literal_da_cadeia_81_continua_valendo():
    """Nenhuma das oito correções anteriores regrediu."""
    for locator in ("s3://bucket/*", "s3://b/[a-z]", "s3://b/prefixo/", SEGREDO):
        with pytest.raises(ValueError):
            descritor(transient_locator=locator)
    assert descritor(capability=capacidade(scope="workspace/w1/*")).capability.scope == (
        "workspace/w1/*"
    )


@pytest.mark.parametrize("valor", ["payload_ref", 42, None, ReferenceProvenance])
def test_u92_proveniencia_exige_o_enum_fechado_de_origem(valor):
    """Fronteira descoberta pela exigência de 100%.

    `ReferenceProvenance` recusa o texto no PRÓPRIO construtor, e não só
    quando entra num dos três value objects. Sem isto, o vocabulário
    fechado dependeria de quem o embrulha.
    """
    with pytest.raises(TypeError, match="ReferenceOrigin"):
        _construir(ReferenceProvenance, origin=valor)


# ======================================================================
# E4.9.7.3 — inventário textual e confidencialidade composta
#
# As nove evidências do terceiro reprodutor viram regressão aqui.
# A5: o inventário da cadeia 82 declarou "exatamente dois" campos
# sensíveis; cinco outros aceitavam o mesmo marcador e o revelavam.
#
# UNRESTRICTED_PUBLIC_STR = MAY_CONTAIN_SENSITIVE_VALUE
# DIRECT_REDACTION != COMPOSITE_REDACTION
# ======================================================================


MARCADOR = "https://user:password@example.invalid/object?token=E4973_SECRET"


def _sem_vazamento(objeto: object, canal: str) -> None:
    assert MARCADOR not in repr(objeto), f"{canal}: repr"
    assert MARCADOR not in str(objeto), f"{canal}: str"
    assert MARCADOR not in f"{objeto}", f"{canal}: f-string"


# --- canais diretos -------------------------------------------------------


def test_u93_control_principal_sensivel_nao_vaza_direto():
    """O canal que o EDR da cadeia 82 chamou de não explorável.

    Era explorável: a dataclass o expunha diretamente.
    """
    _sem_vazamento(escopo(control_principal_ref=MARCADOR), "ControlScope")


def test_u94_provider_e_namespace_sensiveis_nao_vazam_direto():
    _sem_vazamento(custodia(provider=MARCADOR), "CustodyNamespace.provider")
    _sem_vazamento(custodia(namespace=MARCADOR), "CustodyNamespace.namespace")


def test_u95_operation_e_scope_sensiveis_nao_vazam_direto():
    _sem_vazamento(capacidade(operation=MARCADOR), "capability.operation")
    _sem_vazamento(capacidade(scope=MARCADOR), "capability.scope")


def test_u96_version_etag_sensivel_nao_vaza():
    _sem_vazamento(descritor(version_etag=MARCADOR), "descriptor.version_etag")


# --- composições ----------------------------------------------------------


def test_u97_principal_sensivel_aninhado_na_referencia_nao_vaza():
    """`DIRECT_REDACTION != COMPOSITE_REDACTION`."""
    r = referencia(control_scope=escopo(control_principal_ref=MARCADOR))
    _sem_vazamento(r, "Reference→control_scope")


def test_u98_namespace_sensivel_aninhado_na_referencia_nao_vaza():
    r = referencia(expected_namespace=custodia(namespace=MARCADOR))
    _sem_vazamento(r, "Reference→expected_namespace")


@pytest.mark.parametrize("campo", ["provider", "namespace"])
def test_u99_custodia_sensivel_aninhada_no_descritor_nao_vaza(campo):
    d = descritor(custody_namespace=custodia(**{campo: MARCADOR}))
    _sem_vazamento(d, f"Descriptor→custody_namespace.{campo}")


@pytest.mark.parametrize("campo", ["operation", "scope"])
def test_u100_capacidade_sensivel_aninhada_no_descritor_nao_vaza(campo):
    d = descritor(capability=capacidade(**{campo: MARCADOR}))
    _sem_vazamento(d, f"Descriptor→capability.{campo}")


def test_u101_principal_sensivel_aninhado_no_descritor_nao_vaza():
    d = descritor(control_scope=escopo(control_principal_ref=MARCADOR))
    _sem_vazamento(d, "Descriptor→control_scope")


def test_u102_recusa_nao_expoe_nenhum_canal_textual():
    """A recusa não tem campo textual — nem próprio, nem composto."""
    import dataclasses

    campos = {c.name: c.type for c in dataclasses.fields(TargetResolutionRefusal)}
    assert not any(tipo is str for tipo in campos.values())
    _sem_vazamento(recusa(), "TargetResolutionRefusal")


# --- acesso, imutabilidade e igualdade preservados ------------------------


def test_u103_os_valores_continuam_acessiveis_a_quem_resolve():
    """Redigir a representação não pode inutilizar o contrato."""
    assert escopo(control_principal_ref=MARCADOR).control_principal_ref == MARCADOR
    assert custodia(provider=MARCADOR).provider == MARCADOR
    assert custodia(namespace=MARCADOR).namespace == MARCADOR
    assert capacidade(operation=MARCADOR).operation == MARCADOR
    assert capacidade(scope=MARCADOR).scope == MARCADOR
    assert descritor(version_etag=MARCADOR).version_etag == MARCADOR


def test_u104_igualdade_preservada_sem_normalizacao():
    """`repr=False` não altera `__eq__` nem o valor guardado."""
    assert custodia(provider=MARCADOR) == custodia(provider=MARCADOR)
    assert custodia(provider=MARCADOR) != custodia(provider="pia-storage")
    assert escopo(control_principal_ref="ação").control_principal_ref == "ação"


def test_u105_os_campos_livres_continuam_congelados():
    for alvo, campo in (
        (escopo(), "control_principal_ref"),
        (custodia(), "provider"),
        (custodia(), "namespace"),
        (capacidade(), "operation"),
        (capacidade(), "scope"),
    ):
        with pytest.raises(FrozenInstanceError):
            _atribuir_campo(alvo, campo, "outro")


# --- o que NÃO pode ter mudado -------------------------------------------


def test_u106_scope_continua_podendo_representar_conjunto():
    """Redigir a representação não restringe o domínio.

    `capability.scope` descreve o que a conta pode — legitimamente um
    conjunto. Confundir isso com alvo exato inverteria o contrato.
    """
    c = capacidade(scope="workspace/w1/*")
    assert c.scope == "workspace/w1/*"
    assert descritor(capability=c).capability.scope == "workspace/w1/*"


def test_u107_nenhum_provedor_foi_congelado_em_enum():
    """`PROVIDER_NEUTRALITY_PRESERVED`.

    Fechar `provider` num vocabulário resolveria o vazamento e quebraria
    a neutralidade que o Master exige.
    """
    for provedor in ("pia-storage", "s3", "gcs", "provedor-novo-qualquer", "ação"):
        assert custodia(provider=provedor).provider == provedor


def test_u108_a_representacao_continua_util():
    """Redação não pode virar apagamento — o que não é texto livre fica.

    Sem isto, `repr` deixaria de servir para depurar e a redação seria
    trocada por comodidade na primeira sessão difícil.
    """
    d = descritor()
    assert "pia_managed_artifact" in repr(d)
    assert str(S1) in repr(d)
    assert "2026" in repr(d)
    assert "verified=True" in repr(d)
    r = referencia()
    assert str(S1) in repr(r)
    assert "payload_ref" in repr(r)


# ======================================================================
# E4.9.7.4 — verificação explícita da capacidade
#
# A6: a cadeia 83 deu `= True` a `verified` ao acrescentar
# `field(repr=False)` em `operation` e `scope`. O default não era
# necessário — `field()` sem `default` deixa o campo obrigatório — e
# nenhum teste pegou, porque toda chamada existente já passava
# `verified=True` explicitamente.
#
# OMITTED_VERIFICATION != VERIFIED_TRUE
# DEFAULT_TRUE = IMPLICIT_AUTHORITY
# ======================================================================


def test_u109_verified_nao_tem_default_na_assinatura():
    """`inspect.signature` como prova, não a docstring."""
    import inspect

    parametro = inspect.signature(VerifiedDeletionCapability).parameters["verified"]
    assert parametro.default is inspect.Parameter.empty
    assert parametro.annotation is bool


def test_u110_verified_nao_tem_default_nem_factory_na_dataclass():
    """`MISSING` nos dois — nem sentinel, nem factory escondida."""
    import dataclasses

    (campo,) = [c for c in dataclasses.fields(VerifiedDeletionCapability) if c.name == "verified"]
    assert campo.default is dataclasses.MISSING
    assert campo.default_factory is dataclasses.MISSING


def test_u111_omissao_de_verified_nao_constroi_capacidade():
    """Ausência de afirmação não é afirmação de ausência."""
    with pytest.raises(TypeError):
        _construir(VerifiedDeletionCapability, operation="delete_object", scope="w/1/*")
    with pytest.raises(TypeError):
        _chamar(VerifiedDeletionCapability, "__call__")


def test_u112_omissao_nao_produz_descritor_de_sucesso():
    """`OMITTED_VERIFICATION → VERIFIED_CAPABILITY → SUCCESS_DESCRIPTOR`.

    A cadeia inteira que a cadeia 83 abriu, fechada na primeira etapa:
    sem capacidade, não há descritor.
    """
    with pytest.raises(TypeError):
        descritor(
            capability=_construir(
                VerifiedDeletionCapability, operation="delete_object", scope="w/1/*"
            )
        )


def test_u113_true_e_false_explicitos_continuam_construiveis():
    """`verified=False` é estado observado, não erro."""
    assert capacidade(verified=True).verified is True
    assert capacidade(verified=False).verified is False


def test_u114_capacidade_nao_verificada_nao_entra_em_descritor_de_sucesso():
    """Inalterado desde a E4.9.7 — reafirmado aqui como regressão."""
    with pytest.raises(ValueError, match="VERIFICADA"):
        descritor(capability=capacidade(verified=False))


@pytest.mark.parametrize("valor", [1, 0, "sim", "", None, [], 1.0])
def test_u115_verified_continua_exigindo_bool_estrito(valor):
    with pytest.raises(TypeError, match="verified deve ser bool"):
        capacidade(verified=valor)


def test_u116_nenhuma_fabrica_de_teste_mascara_a_omissao():
    """As fábricas deste módulo passam `verified` explicitamente.

    Uma fábrica com default próprio devolveria a autoridade implícita
    pela porta dos fundos — e esta guarda a derruba.
    """
    import inspect

    fonte = inspect.getsource(capacidade)
    assert '"verified": True' in fonte

    # O helper permite sobrescrever, mas nunca omitir na chamada real.
    import dataclasses

    (campo,) = [c for c in dataclasses.fields(capacidade()) if c.name == "verified"]
    assert campo.default is dataclasses.MISSING


def test_u117_nenhum_outro_campo_publico_ganhou_default():
    """Guarda contra a mesma regressão em qualquer contrato da fatia.

    A cadeia 83 mudou uma assinatura pública sem intenção, dentro de um
    corretivo de representação. Esta guarda fixa exatamente quais campos
    têm default — um default novo em qualquer outro derruba o teste.
    """
    import dataclasses

    from app.memory.schemas.erasure_target import (
        ControlScope,
        CustodyNamespace,
        ErasureTargetDescriptor,
        ErasureTargetReference,
        ReferenceProvenance,
        TargetResolutionRefusal,
    )

    com_default: dict[str, set[str]] = {}
    for classe in (
        ControlScope,
        CustodyNamespace,
        VerifiedDeletionCapability,
        ReferenceProvenance,
        ErasureTargetReference,
        ErasureTargetDescriptor,
        TargetResolutionRefusal,
    ):
        com_default[classe.__name__] = {
            c.name
            for c in dataclasses.fields(classe)
            if c.default is not dataclasses.MISSING or c.default_factory is not dataclasses.MISSING
        }

    assert com_default == {
        "ControlScope": set(),
        "CustodyNamespace": set(),
        "VerifiedDeletionCapability": set(),
        "ReferenceProvenance": {"position"},
        "ErasureTargetReference": {"expected_namespace"},
        "ErasureTargetDescriptor": {"version_etag"},
        "TargetResolutionRefusal": {"classified_as", "observed_dimension"},
    }


def test_u118_a_redacao_da_cadeia_83_nao_regrediu():
    """As 14 representações continuam sem vazamento."""
    d = descritor(capability=capacidade(operation=MARCADOR, verified=True))
    _sem_vazamento(d, "Descriptor→capability.operation")
    _sem_vazamento(capacidade(scope=MARCADOR, verified=False), "capability.scope")
    assert "verified=True" in repr(descritor())


# ======================================================================
# E4.9.8.3 — proteção de legado no binding do descritor
#
# Lacuna ANTECEDENTE: a E4.9.4 exigia nova aprovação quando muda a
# proteção de legado, e o runtime não tinha o estado em lugar algum.
#
# DOCUMENTED_BINDING != RUNTIME_BINDING
# ABSENCE_OF_INFORMATION != NOT_PROTECTED
# ======================================================================


def test_u110_o_vocabulario_tem_exatamente_dois_membros():
    assert [m.value for m in LegacyProtectionState] == ["protected", "not_protected"]
    for proibido in ("UNKNOWN", "OTHER", "UNSPECIFIED", "DEFAULT", "INHERITED", "AUTO"):
        assert proibido not in LegacyProtectionState.__members__


def test_u111_indeterminacao_e_recusa_e_nao_terceiro_estado():
    """`PROTECTION_STATE_UNKNOWN = TARGET_RESOLUTION_REFUSAL`.

    Um terceiro membro faria a indeterminação virar aprovação silenciosa —
    a forma do `verified = True` acidental que a E4.9.7.4 fechou.
    """
    assert (
        TargetResolutionRefusalReason.LEGACY_PROTECTION_STATE_UNRESOLVED.value
        == "legacy_protection_state_unresolved"
    )
    r = recusa(reason=TargetResolutionRefusalReason.LEGACY_PROTECTION_STATE_UNRESOLVED)
    assert r.reason is TargetResolutionRefusalReason.LEGACY_PROTECTION_STATE_UNRESOLVED


def test_u112_a_dimensao_de_recusa_nao_foi_ampliada():
    """Recuo deliberado: o motivo fechado já identifica a recusa.

    `observed_dimension` descreve **divergência contextual** entre
    governança, identidade e alvo. Estado de proteção não resolvido não é
    divergência de contexto — é ausência de fato observável. Ampliar a
    semântica seria delta público redundante.
    """
    assert [d.value for d in RefusalDimension] == [
        "workspace",
        "tenant",
        "control_principal",
        "provider",
        "namespace",
        "reference",
        "capability",
        "resolution_freshness",
    ]
    assert "LEGACY_PROTECTION" not in RefusalDimension.__members__


@pytest.mark.parametrize("estado", list(LegacyProtectionState))
def test_u113_os_dois_estados_sao_construiveis_no_descritor(estado):
    assert descritor(legacy_protection_state=estado).legacy_protection_state is estado


@pytest.mark.parametrize(
    "valor",
    ["protected", "not_protected", "", True, False, None, 0, 1, object()],
)
def test_u114_nao_membro_recusado_no_descritor(valor):
    """String equivalente, `bool` e `None` não são membros."""
    with pytest.raises(TypeError, match="LegacyProtectionState"):
        descritor(legacy_protection_state=valor)


def test_u115_enum_de_outra_classe_recusado():
    with pytest.raises(TypeError, match="LegacyProtectionState"):
        descritor(legacy_protection_state=ReferenceOrigin.PAYLOAD_REF)
    with pytest.raises(TypeError, match="LegacyProtectionState"):
        descritor(legacy_protection_state=ErasureTargetClass.PIA_MANAGED_ARTIFACT)


def test_u116_campo_obrigatorio_sem_default_no_descritor():
    """`DEFAULT_LEGACY_PROTECTION_STATE = FORBIDDEN`."""
    import dataclasses
    import inspect

    (campo,) = [
        c
        for c in dataclasses.fields(ErasureTargetDescriptor)
        if c.name == "legacy_protection_state"
    ]
    assert campo.default is dataclasses.MISSING
    assert campo.default_factory is dataclasses.MISSING
    parametro = inspect.signature(ErasureTargetDescriptor).parameters["legacy_protection_state"]
    assert parametro.default is inspect.Parameter.empty
    assert parametro.annotation is LegacyProtectionState


def test_u117_omissao_e_erro_e_nunca_not_protected():
    """Um default faria toda omissão parecer `NOT_PROTECTED`."""
    with pytest.raises(TypeError):
        _construir(
            ErasureTargetDescriptor,
            target_class=ErasureTargetClass.PIA_MANAGED_ARTIFACT,
            subject_coid=S1,
            control_scope=escopo(),
            custody_namespace=custodia(),
            capability=capacidade(),
            resolved_at=AGORA,
            origin=PROVENIENCIA,
            transient_locator=LOCALIZADOR,
        )


def test_u118_os_dois_estados_sao_estruturalmente_distinguiveis():
    """`SAME_STATE_REQUIRED = TRUE`, nas duas direções."""
    protegido = descritor(legacy_protection_state=LegacyProtectionState.PROTECTED)
    livre = descritor(legacy_protection_state=LegacyProtectionState.NOT_PROTECTED)
    assert protegido != livre
    assert protegido == descritor(legacy_protection_state=LegacyProtectionState.PROTECTED)
    assert livre == descritor(legacy_protection_state=LegacyProtectionState.NOT_PROTECTED)


def test_u119_replace_revalida_a_protecao():
    import dataclasses

    d = descritor(legacy_protection_state=LegacyProtectionState.PROTECTED)
    trocado = dataclasses.replace(d, legacy_protection_state=LegacyProtectionState.NOT_PROTECTED)
    assert trocado.legacy_protection_state is LegacyProtectionState.NOT_PROTECTED
    assert trocado != d
    with pytest.raises(TypeError, match="LegacyProtectionState"):
        dataclasses.replace(d, legacy_protection_state="protected")


@pytest.mark.parametrize("estado", list(LegacyProtectionState))
def test_u120_repr_mostra_token_fechado_e_nunca_texto_livre(estado):
    texto = repr(descritor(legacy_protection_state=estado))
    assert f"legacy_protection_state={estado.value!r}" in texto
    assert LOCALIZADOR not in texto


def test_u121_protecao_nao_e_legal_hold_nem_versao_nem_causalidade():
    """Quatro fatos distintos, sem equivalência.

    ```text
    LEGACY_PROTECTION != LEGAL_HOLD
    LEGACY_PROTECTION != CANONICAL_VERSION
    LEGACY_PROTECTION != CAUSAL_DEPENDENCY
    ```

    Legal hold é imposição externa sobre o titular; proteção de legado é
    escolha **do** titular.
    """
    from app.memory.models.approval_enums import ApprovalBlockerKind

    valores = {m.value for m in LegacyProtectionState}
    assert valores.isdisjoint({m.value for m in ApprovalBlockerKind})
    assert "legal_hold" not in valores
    # versão é campo próprio e independente da proteção
    d = descritor(legacy_protection_state=LegacyProtectionState.PROTECTED, version_etag="v1")
    assert d.version_etag == "v1"
    assert d.legacy_protection_state is LegacyProtectionState.PROTECTED


def test_u122_nenhuma_inferencia_a_partir_de_outro_campo():
    """O estado não é derivado de classe, custódia, origem ou versão."""
    base = descritor(legacy_protection_state=LegacyProtectionState.PROTECTED)
    variantes = (
        descritor(
            legacy_protection_state=LegacyProtectionState.PROTECTED,
            custody_namespace=custodia(provider="outro"),
        ),
        descritor(legacy_protection_state=LegacyProtectionState.PROTECTED, version_etag="v9"),
        descritor(
            legacy_protection_state=LegacyProtectionState.PROTECTED,
            origin=ReferenceProvenance(ReferenceOrigin.OUTPUT_REFS, 1),
        ),
    )
    for v in variantes:
        assert v.legacy_protection_state is base.legacy_protection_state
