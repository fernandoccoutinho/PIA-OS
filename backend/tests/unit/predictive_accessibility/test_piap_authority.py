"""
Contrato de autoridade e validação de aprovação (`E5.a`).

```text
E5_VALIDATES_BUT_DOES_NOT_GRANT_APPROVAL = TRUE
NEGATIVE_APPROVAL_OUTCOME != EXCEPTION
PARALLEL_AUTHORITY_STATUS = FORBIDDEN
```
"""

import dataclasses
import pathlib
import uuid
from datetime import UTC, datetime

import pytest

from app.predictive_accessibility.piap import authority as authority_module
from app.predictive_accessibility.piap.authority import (
    ApprovalBinding,
    AuthorityContext,
    BoundObjectRef,
    validate_approval,
)
from app.predictive_accessibility.piap.capacity import (
    MAX_APPROVAL_SCOPE_ITEMS,
    MAX_PIAP_VERSION_NUMBER,
)
from app.predictive_accessibility.piap.enums import (
    ApprovalValidationOutcome,
    AuthorityStatus,
    BoundObjectKind,
)

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_EXPIRA = datetime(2026, 6, 1, tzinfo=UTC)
_DEPOIS = datetime(2026, 7, 1, tzinfo=UTC)


def _vinculo(kind: BoundObjectKind = BoundObjectKind.PROPOSED_BOUND) -> BoundObjectRef:
    return BoundObjectRef(kind=kind, ref=uuid.UUID(int=99))


def _aprovacao(**kwargs) -> ApprovalBinding:
    base = {
        "approval_reference": "APR-0001",
        "approval_version": 2,
        "approval_scope": ("bound.read", "bound.write"),
        "approval_expiry": _EXPIRA,
        "approval_jurisdiction": "br",
        "bound_to": _vinculo(),
    }
    base.update(kwargs)
    return ApprovalBinding(**base)


def _contexto(**kwargs) -> AuthorityContext:
    base = {"status": AuthorityStatus.ASSERTED_AUTHORIZED, "approval": _aprovacao()}
    base.update(kwargs)
    return AuthorityContext(**base)


def _validar(contexto: AuthorityContext, **kwargs) -> ApprovalValidationOutcome:
    base = {
        "at": _T0,
        "expected_version": 2,
        "required_scope": ("bound.read",),
        "expected_jurisdiction": "br",
        "expected_binding": _vinculo(),
    }
    base.update(kwargs)
    return validate_approval(contexto, **base)


# --- fonte única do status -------------------------------------------------


def test_approval_binding_nao_tem_status_paralelo() -> None:
    """A prova de `PARALLEL_AUTHORITY_STATUS = FORBIDDEN` no tipo."""
    nomes = {campo.name for campo in dataclasses.fields(ApprovalBinding)}
    assert "approval_status" not in nomes
    assert "status" not in nomes
    assert "status" in {campo.name for campo in dataclasses.fields(AuthorityContext)}


# --- estados impossíveis ---------------------------------------------------


def test_autorizado_sem_binding_rejeita() -> None:
    with pytest.raises(ValueError, match="ASSERTED_AUTHORIZED"):
        AuthorityContext(status=AuthorityStatus.ASSERTED_AUTHORIZED, approval=None)


def test_unknown_com_binding_rejeita() -> None:
    with pytest.raises(ValueError, match="UNKNOWN"):
        AuthorityContext(status=AuthorityStatus.UNKNOWN, approval=_aprovacao())


def test_negativa_admite_as_duas_formas() -> None:
    sem = AuthorityContext(status=AuthorityStatus.ASSERTED_NOT_AUTHORIZED)
    com = AuthorityContext(status=AuthorityStatus.ASSERTED_NOT_AUTHORIZED, approval=_aprovacao())
    assert sem.approval is None
    assert com.approval is not None


# --- escopo ----------------------------------------------------------------


def test_escopo_vazio_rejeita() -> None:
    with pytest.raises(ValueError, match="vazio"):
        _aprovacao(approval_scope=())


def test_escopo_duplicado_rejeita() -> None:
    with pytest.raises(ValueError, match="duplicada"):
        _aprovacao(approval_scope=("a", "a"))


def test_escopo_fora_de_ordem_rejeita_sem_reordenar() -> None:
    with pytest.raises(ValueError, match="ordem canônica"):
        _aprovacao(approval_scope=("z", "a"))


def test_escopo_de_tipo_errado_e_type_error() -> None:
    with pytest.raises(TypeError):
        _aprovacao(approval_scope=["a"])


# --- os oito desfechos -----------------------------------------------------


def test_valid() -> None:
    assert _validar(_contexto()) is ApprovalValidationOutcome.VALID


def test_missing() -> None:
    contexto = AuthorityContext(status=AuthorityStatus.UNKNOWN)
    assert _validar(contexto) is ApprovalValidationOutcome.MISSING


def test_not_authorized() -> None:
    contexto = AuthorityContext(
        status=AuthorityStatus.ASSERTED_NOT_AUTHORIZED, approval=_aprovacao()
    )
    assert _validar(contexto) is ApprovalValidationOutcome.NOT_AUTHORIZED


def test_binding_mismatch() -> None:
    resultado = _validar(
        _contexto(), expected_binding=_vinculo(BoundObjectKind.PROMOTION_CANDIDATE)
    )
    assert resultado is ApprovalValidationOutcome.BINDING_MISMATCH


def test_version_mismatch() -> None:
    assert _validar(_contexto(), expected_version=7) is ApprovalValidationOutcome.VERSION_MISMATCH


def test_jurisdiction_mismatch_por_divergencia() -> None:
    resultado = _validar(_contexto(), expected_jurisdiction="us")
    assert resultado is ApprovalValidationOutcome.JURISDICTION_MISMATCH


def test_jurisdiction_mismatch_por_ausencia() -> None:
    contexto = _contexto(approval=_aprovacao(approval_jurisdiction=None))
    assert _validar(contexto) is ApprovalValidationOutcome.JURISDICTION_MISMATCH


def test_jurisdicao_nao_exigida_nao_bloqueia() -> None:
    contexto = _contexto(approval=_aprovacao(approval_jurisdiction=None))
    assert _validar(contexto, expected_jurisdiction=None) is ApprovalValidationOutcome.VALID


def test_out_of_scope() -> None:
    resultado = _validar(_contexto(), required_scope=("bound.other",))
    assert resultado is ApprovalValidationOutcome.OUT_OF_SCOPE


def test_expired() -> None:
    assert _validar(_contexto(), at=_DEPOIS) is ApprovalValidationOutcome.EXPIRED


def test_expiracao_exata_conta_como_expirada() -> None:
    assert _validar(_contexto(), at=_EXPIRA) is ApprovalValidationOutcome.EXPIRED


def test_sem_expiracao_nao_expira() -> None:
    contexto = _contexto(approval=_aprovacao(approval_expiry=None))
    assert _validar(contexto, at=_DEPOIS) is ApprovalValidationOutcome.VALID


def test_todos_os_oito_desfechos_sao_alcancaveis() -> None:
    alcancados = {
        _validar(_contexto()),
        _validar(AuthorityContext(status=AuthorityStatus.UNKNOWN)),
        _validar(
            AuthorityContext(status=AuthorityStatus.ASSERTED_NOT_AUTHORIZED, approval=_aprovacao())
        ),
        _validar(_contexto(), expected_binding=_vinculo(BoundObjectKind.PROMOTION_CANDIDATE)),
        _validar(_contexto(), expected_version=7),
        _validar(_contexto(), expected_jurisdiction="us"),
        _validar(_contexto(), required_scope=("bound.other",)),
        _validar(_contexto(), at=_DEPOIS),
    }
    assert alcancados == set(ApprovalValidationOutcome)


# --- precedência com defeitos simultâneos ----------------------------------


def test_precedencia_missing_vence_tudo() -> None:
    contexto = AuthorityContext(status=AuthorityStatus.ASSERTED_NOT_AUTHORIZED)
    resultado = _validar(
        contexto,
        at=_DEPOIS,
        expected_version=7,
        required_scope=("bound.other",),
        expected_jurisdiction="us",
        expected_binding=_vinculo(BoundObjectKind.PROMOTION_CANDIDATE),
    )
    assert resultado is ApprovalValidationOutcome.MISSING


def test_precedencia_not_authorized_vence_binding() -> None:
    contexto = AuthorityContext(
        status=AuthorityStatus.ASSERTED_NOT_AUTHORIZED, approval=_aprovacao()
    )
    resultado = _validar(contexto, expected_binding=_vinculo(BoundObjectKind.PROMOTION_CANDIDATE))
    assert resultado is ApprovalValidationOutcome.NOT_AUTHORIZED


def test_precedencia_binding_vence_version_jurisdicao_escopo_e_expiracao() -> None:
    resultado = _validar(
        _contexto(),
        at=_DEPOIS,
        expected_version=7,
        required_scope=("bound.other",),
        expected_jurisdiction="us",
        expected_binding=_vinculo(BoundObjectKind.PROMOTION_CANDIDATE),
    )
    assert resultado is ApprovalValidationOutcome.BINDING_MISMATCH


def test_precedencia_version_vence_jurisdicao_escopo_e_expiracao() -> None:
    resultado = _validar(
        _contexto(),
        at=_DEPOIS,
        expected_version=7,
        required_scope=("bound.other",),
        expected_jurisdiction="us",
    )
    assert resultado is ApprovalValidationOutcome.VERSION_MISMATCH


def test_precedencia_jurisdicao_vence_escopo_e_expiracao() -> None:
    resultado = _validar(
        _contexto(), at=_DEPOIS, required_scope=("bound.other",), expected_jurisdiction="us"
    )
    assert resultado is ApprovalValidationOutcome.JURISDICTION_MISMATCH


def test_precedencia_escopo_vence_expiracao() -> None:
    resultado = _validar(_contexto(), at=_DEPOIS, required_scope=("bound.other",))
    assert resultado is ApprovalValidationOutcome.OUT_OF_SCOPE


# --- pureza ----------------------------------------------------------------


def test_validacao_nao_altera_o_contexto() -> None:
    contexto = _contexto()
    antes = dataclasses.replace(contexto)
    _validar(contexto, at=_DEPOIS)
    assert contexto == antes


def test_validacao_e_deterministica() -> None:
    contexto = _contexto()
    assert _validar(contexto) is _validar(contexto)


def test_desfecho_negativo_nao_e_excecao() -> None:
    """A prova de `NEGATIVE_APPROVAL_OUTCOME != EXCEPTION`."""
    resultado = _validar(AuthorityContext(status=AuthorityStatus.UNKNOWN))
    assert isinstance(resultado, ApprovalValidationOutcome)


def test_argumentos_invalidos_sao_erro_de_chamador() -> None:
    with pytest.raises(TypeError):
        validate_approval(
            object(),  # type: ignore[arg-type]
            at=_T0,
            expected_version=1,
            required_scope=("a",),
            expected_jurisdiction=None,
            expected_binding=_vinculo(),
        )
    with pytest.raises(ValueError):
        _validar(_contexto(), at=datetime(2026, 1, 1))
    with pytest.raises(TypeError):
        _validar(_contexto(), expected_binding=object())


def test_referencia_de_aprovacao_redigida_no_repr() -> None:
    assert "APR-0001" not in repr(_aprovacao())


# --- capacidade: teto de versão e cardinalidade de escopo -----------------
#
# ```text
# UNBOUNDED_POSITIVE_VERSION = TRANSPORTED_PROMISE_THE_PLATFORM_CANNOT_KEEP
# CARDINALITY_CHECK_BEFORE_EXPENSIVE_PER_ITEM_VALIDATION = TRUE
# ```
#
# Contra o parent, `validar_inteiro_positivo` só tinha piso e `validar_escopo`
# validava item a item antes de contar.


def _escopo(n: int) -> tuple[str, ...]:
    """Escopo canônico com `n` itens distintos e já ordenados."""
    return tuple(sorted(f"bound.scope.{i:04d}" for i in range(n)))


def test_cap_versao_no_teto_e_aceita() -> None:
    aprovacao = _aprovacao(approval_version=MAX_PIAP_VERSION_NUMBER)
    assert aprovacao.approval_version == MAX_PIAP_VERSION_NUMBER


def test_cap_versao_um_e_aceita() -> None:
    assert _aprovacao(approval_version=1).approval_version == 1


def test_cap_versao_acima_do_teto_rejeita_em_approval_version() -> None:
    with pytest.raises(ValueError, match="MAX_PIAP_VERSION_NUMBER"):
        _aprovacao(approval_version=MAX_PIAP_VERSION_NUMBER + 1)


def test_cap_versao_acima_do_teto_rejeita_em_expected_version() -> None:
    with pytest.raises(ValueError, match="MAX_PIAP_VERSION_NUMBER"):
        _validar(_contexto(), expected_version=MAX_PIAP_VERSION_NUMBER + 1)


def test_cap_versao_zero_e_negativa_continuam_rejeitadas() -> None:
    """O piso não foi trocado pelo teto: o domínio é fechado dos dois lados."""
    with pytest.raises(ValueError, match=">= 1"):
        _aprovacao(approval_version=0)
    with pytest.raises(ValueError, match=">= 1"):
        _aprovacao(approval_version=-1)


def test_cap_escopo_no_teto_e_aceito() -> None:
    aprovacao = _aprovacao(approval_scope=_escopo(MAX_APPROVAL_SCOPE_ITEMS))
    assert len(aprovacao.approval_scope) == MAX_APPROVAL_SCOPE_ITEMS


def test_cap_escopo_acima_do_teto_rejeita() -> None:
    with pytest.raises(ValueError, match="MAX_APPROVAL_SCOPE_ITEMS"):
        _aprovacao(approval_scope=_escopo(MAX_APPROVAL_SCOPE_ITEMS + 1))


def test_cap_escopo_conta_antes_de_validar_item_a_item() -> None:
    """A contagem precede a varredura Unicode, e a mensagem prova qual guarda agiu.

    Um escopo grande DEMAIS e com item inválido deve reprovar pela
    cardinalidade — não pelo item. Se a ordem se inverter, a mensagem muda e
    este teste reprova.
    """
    grande_e_invalido = _escopo(MAX_APPROVAL_SCOPE_ITEMS) + ("\u0000invalido",)
    with pytest.raises(ValueError, match="MAX_APPROVAL_SCOPE_ITEMS"):
        _aprovacao(approval_scope=grande_e_invalido)


def test_cap_escopo_vazio_continua_rejeitado() -> None:
    with pytest.raises(ValueError, match="não pode ser vazio"):
        _aprovacao(approval_scope=())


def test_cap_constantes_vem_de_fonte_unica() -> None:
    """`authority.py` não redeclara teto nenhum: ele os importa de `capacity`."""
    fonte = pathlib.Path(authority_module.__file__).read_text(encoding="utf-8")
    assert "MAX_APPROVAL_SCOPE_ITEMS = " not in fonte
    assert "MAX_PIAP_VERSION_NUMBER = " not in fonte
    assert authority_module.MAX_APPROVAL_SCOPE_ITEMS is MAX_APPROVAL_SCOPE_ITEMS
    assert authority_module.MAX_PIAP_VERSION_NUMBER is MAX_PIAP_VERSION_NUMBER
