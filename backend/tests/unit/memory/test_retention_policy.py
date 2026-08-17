"""
Testes unitários da `RetentionPolicy` (`E4.9.6`).

O que estes testes protegem, acima de tudo: que a policy diga **quando
avaliar** e nunca **o que apagar**.

```text
RETENTION_POLICY_PERSISTENCE != RETENTION_EVALUATION
```
"""

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from app.memory.errors.codes import (
    PIA_8042_RETENTION_POLICY_VERSION_EXISTS,
    PIA_8043_RETENTION_POLICY_IMMUTABLE,
)
from app.memory.errors.exceptions import (
    RetentionPolicyImmutableError,
    RetentionPolicyVersionExistsError,
)
from app.memory.models.retention_enums import (
    RetentionAnchor,
    RetentionExpiryAction,
    RetentionScopeKind,
)
from app.memory.models.retention_policy import RetentionPolicy
from app.memory.repositories.retention_policy_repository import RetentionPolicyRepository
from app.memory.schemas.retention import MAX_RULE_ID_LENGTH, RetentionRule

D1 = uuid.uuid4()
D2 = uuid.uuid4()
AGORA = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def regra(**overrides: object) -> RetentionRule:
    base: dict[str, object] = {
        "rule_id": "ret-001",
        "scope_kind": RetentionScopeKind.ALL_LOCAL_PATRIMONY,
        "minimum_age_days": 30,
    }
    base.update(overrides)
    return RetentionRule(**base)  # type: ignore[arg-type]


# --- Enums ---------------------------------------------------------------


def test_u01_enums_tem_exatamente_os_membros_autorizados():
    assert [e.value for e in RetentionScopeKind] == [
        "all_local_patrimony",
        "memory_domain_set",
    ]
    assert [e.value for e in RetentionAnchor] == ["created_at"]
    assert [e.value for e in RetentionExpiryAction] == ["assess_and_inform"]


def test_u02_nenhuma_acao_destrutiva_no_vocabulario_de_expiracao():
    """`EXPIRY_TRIGGERS_ASSESSMENT_NOT_DELETION`."""
    proibidos = {
        "DELETE",
        "ERASE",
        "TRASH",
        "MARK_INACCESSIBLE",
        "ARCHIVE",
        "NOTIFY_AND_DELETE",
        "AUTO_CLEANUP",
        "PURGE",
        "CLEANUP",
    }
    assert set(RetentionExpiryAction.__members__) & proibidos == set()
    assert len(RetentionExpiryAction) == 1


@pytest.mark.parametrize(
    ("enum_cls", "token"),
    [
        (RetentionScopeKind, "everything"),
        (RetentionAnchor, "updated_at"),
        (RetentionExpiryAction, "delete"),
    ],
)
def test_u03_token_desconhecido_recusado(enum_cls, token):
    with pytest.raises(ValueError):
        enum_cls(token)


def test_u04_updated_at_nao_e_ancora():
    """`UPDATED_AT != RETENTION_ANCHOR` — medido no preflight da E4.9."""
    assert "UPDATED_AT" not in RetentionAnchor.__members__


# --- Matriz de escopo ----------------------------------------------------


def test_u05_all_local_patrimony_com_dominios_recusado():
    """Listar domínios sugeriria restrição inexistente."""
    with pytest.raises(ValueError, match="ALL_LOCAL_PATRIMONY"):
        regra(scope_kind=RetentionScopeKind.ALL_LOCAL_PATRIMONY, domain_ids=frozenset({D1}))


def test_u06_memory_domain_set_vazio_recusado():
    """`EMPTY SET != WILDCARD`."""
    with pytest.raises(ValueError, match="MEMORY_DOMAIN_SET"):
        regra(scope_kind=RetentionScopeKind.MEMORY_DOMAIN_SET, domain_ids=frozenset())


def test_u07_matriz_valida_nos_dois_sentidos():
    assert regra().domain_ids == frozenset()
    r = regra(scope_kind=RetentionScopeKind.MEMORY_DOMAIN_SET, domain_ids=frozenset({D1, D2}))
    assert r.domain_ids == frozenset({D1, D2})


# --- Tipos e invariantes da regra ---------------------------------------


@pytest.mark.parametrize("valor", [True, False])
def test_u08_bool_recusado_como_idade(valor):
    """`bool` é subclasse de `int`: `True` viraria um dia."""
    with pytest.raises(TypeError):
        regra(minimum_age_days=valor)


@pytest.mark.parametrize("valor", [0, -1])
def test_u09_idade_minima_deve_ser_positiva(valor):
    with pytest.raises(ValueError):
        regra(minimum_age_days=valor)


@pytest.mark.parametrize("valor", ["", "   ", "\t"])
def test_u10_rule_id_vazio_recusado(valor):
    with pytest.raises(ValueError):
        regra(rule_id=valor)


@pytest.mark.parametrize("valor", ["a\x00b", "quebra\nlinha", "del\x7f"])
def test_u11_rule_id_com_controle_recusado(valor):
    with pytest.raises(ValueError):
        regra(rule_id=valor)


def test_u12_rule_id_respeita_o_teto():
    regra(rule_id="x" * MAX_RULE_ID_LENGTH)
    with pytest.raises(ValueError):
        regra(rule_id="x" * (MAX_RULE_ID_LENGTH + 1))


@pytest.mark.parametrize("valor", ["abc", b"abc"])
def test_u13_str_e_bytes_recusados_como_colecao(valor):
    with pytest.raises(TypeError):
        regra(scope_kind=RetentionScopeKind.MEMORY_DOMAIN_SET, domain_ids=valor)


def test_u14_domain_ids_aceita_apenas_uuid():
    with pytest.raises(TypeError):
        regra(scope_kind=RetentionScopeKind.MEMORY_DOMAIN_SET, domain_ids=[str(D1)])


def test_u15_enum_estrito_sem_coercao_de_string():
    """`StrEnum` compara igual à string; o tipo é a garantia."""
    with pytest.raises(TypeError):
        regra(scope_kind="all_local_patrimony")
    with pytest.raises(TypeError):
        regra(anchor="created_at")
    with pytest.raises(TypeError):
        regra(on_expiry_action="assess_and_inform")


def test_u16_regra_e_congelada_e_normaliza_colecao():
    r = regra(scope_kind=RetentionScopeKind.MEMORY_DOMAIN_SET, domain_ids=[D1, D1, D2])
    assert isinstance(r.domain_ids, frozenset)
    assert r.domain_ids == {D1, D2}
    with pytest.raises(FrozenInstanceError):
        r.minimum_age_days = 5  # type: ignore[misc]


# --- Serialização --------------------------------------------------------


def test_u17_regras_vazias_recusadas():
    """Policy sem regra não expressa retenção alguma."""
    with pytest.raises(ValueError, match="ao menos uma regra"):
        RetentionPolicy.serialize_rules(())


def test_u18_rule_id_duplicado_recusado():
    with pytest.raises(ValueError, match="duplicado"):
        RetentionPolicy.serialize_rules((regra(rule_id="a"), regra(rule_id="a")))


def test_u19_serializacao_e_canonica_independente_da_ordem():
    a, b, c = regra(rule_id="a"), regra(rule_id="b"), regra(rule_id="c")
    assert RetentionPolicy.serialize_rules((c, a, b)) == RetentionPolicy.serialize_rules((a, b, c))


def test_u20_domain_ids_serializa_em_ordem_deterministica():
    r = regra(scope_kind=RetentionScopeKind.MEMORY_DOMAIN_SET, domain_ids={D1, D2})
    serializado = RetentionPolicy.serialize_rules((r,))[0]["domain_ids"]
    assert serializado == sorted(str(d) for d in {D1, D2})


def test_u21_round_trip_tipado():
    originais = (
        regra(rule_id="a"),
        regra(
            rule_id="b",
            scope_kind=RetentionScopeKind.MEMORY_DOMAIN_SET,
            domain_ids={D1, D2},
            minimum_age_days=365,
        ),
    )
    voltou = RetentionPolicy.deserialize_rules(RetentionPolicy.serialize_rules(originais))
    assert set(voltou) == set(originais)


def test_u22_desserializacao_reaplica_invariantes():
    """Valor fora do vocabulário levanta erro em vez de virar regra inerte."""
    payload = RetentionPolicy.serialize_rules((regra(),))
    payload[0]["on_expiry_action"] = "delete"
    with pytest.raises(ValueError):
        RetentionPolicy.deserialize_rules(payload)


def test_u23_desserializacao_recusa_payload_vazio():
    with pytest.raises(ValueError):
        RetentionPolicy.deserialize_rules([])


def test_u24_desserializacao_recusa_duplicata():
    payload = RetentionPolicy.serialize_rules((regra(rule_id="a"), regra(rule_id="b")))
    payload[1]["rule_id"] = "a"
    with pytest.raises(ValueError, match="duplicado"):
        RetentionPolicy.deserialize_rules(payload)


def test_u25_typed_rules_expoe_as_regras():
    p = RetentionPolicy(
        policy_key="ret.default",
        version=1,
        governance_policy_key="gov.default",
        rules=RetentionPolicy.serialize_rules((regra(),)),
    )
    assert p.typed_rules[0].rule_id == "ret-001"


# --- Repositório: validação de entrada ----------------------------------


def _repo() -> RetentionPolicyRepository:
    return RetentionPolicyRepository.__new__(RetentionPolicyRepository)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"policy_key": ""},
        {"policy_key": "   "},
        {"governance_policy_key": ""},
        {"version": 0},
        {"version": -2},
    ],
)
def test_u26_entradas_invalidas_recusadas(kwargs):
    base: dict[str, object] = {
        "policy_key": "ret.default",
        "version": 1,
        "governance_policy_key": "gov.default",
        "rules": (regra(),),
    }
    base.update(kwargs)
    with pytest.raises(ValueError):
        _repo().add_policy(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("valor", [True, False])
def test_u27_bool_recusado_como_versao(valor):
    with pytest.raises(TypeError):
        _repo().add_policy(
            policy_key="ret.default",
            version=valor,
            governance_policy_key="gov.default",
            rules=(regra(),),
        )


@pytest.mark.parametrize("campo", ["effective_from", "effective_until"])
def test_u28_datetime_naive_recusado(campo):
    with pytest.raises(ValueError, match="timezone-aware"):
        _repo().add_policy(
            policy_key="ret.default",
            version=1,
            governance_policy_key="gov.default",
            rules=(regra(),),
            **{campo: datetime(2026, 8, 17, 12, 0)},
        )


def test_u29_janela_incoerente_recusada():
    with pytest.raises(ValueError, match="posterior"):
        _repo().add_policy(
            policy_key="ret.default",
            version=1,
            governance_policy_key="gov.default",
            rules=(regra(),),
            effective_from=AGORA,
            effective_until=AGORA - timedelta(days=1),
        )


def test_u30_effective_version_at_exige_instante_aware():
    with pytest.raises(ValueError, match="timezone-aware"):
        _repo().effective_version_at("ret.default", datetime(2026, 8, 17, 12, 0))


# --- Repositório: mutações recusadas ------------------------------------


@pytest.mark.parametrize(
    "operacao", ["update", "delete", "soft_delete", "bulk_update", "bulk_delete"]
)
def test_u31_repositorio_recusa_toda_mutacao(operacao):
    alvo = RetentionPolicy(id=uuid.uuid4())
    with pytest.raises(RetentionPolicyImmutableError) as info:
        getattr(_repo(), operacao)(alvo)
    assert info.value.operation == operacao


def test_u32_delete_by_id_tambem_recusado():
    rid = uuid.uuid4()
    with pytest.raises(RetentionPolicyImmutableError) as info:
        _repo().delete_by_id(rid)
    assert info.value.operation == "delete_by_id"
    assert info.value.policy_id == rid


# --- Erros ---------------------------------------------------------------


def test_u33_codigos_de_erro_corretos():
    pid = uuid.uuid4()
    imut = RetentionPolicyImmutableError(pid, operation="update")
    assert imut.error_code is PIA_8043_RETENTION_POLICY_IMMUTABLE
    assert imut.error_code.code == "PIA-8043"
    assert imut.detail == {"policy_id": str(pid), "operation": "update"}

    dup = RetentionPolicyVersionExistsError("ret.default", 2)
    assert dup.error_code is PIA_8042_RETENTION_POLICY_VERSION_EXISTS
    assert dup.error_code.code == "PIA-8042"
    assert dup.detail == {"policy_key": "ret.default", "version": 2}


def test_u34_erro_de_imutabilidade_aceita_id_nulo():
    exc = RetentionPolicyImmutableError(None, operation="bulk_delete")
    assert exc.detail == {"policy_id": None, "operation": "bulk_delete"}


# --- O que a policy NÃO faz ---------------------------------------------


def test_u35_repositorio_nao_tem_metodo_de_avaliacao_ou_efeito():
    """`RETENTION_EVALUATOR = NOT_COMPOSED`."""
    proibidos = {
        "evaluate",
        "assess",
        "expire",
        "notify",
        "trash",
        "erase",
        "delete_target",
        "cleanup",
        "purge",
        "apply",
        "run",
    }
    assert proibidos & set(dir(RetentionPolicyRepository)) == set()


def test_u36_modelo_nao_tem_campo_de_conteudo_nem_patrimonio():
    """Policy é configuração: sem COID, CLID, linhagem ou conteúdo."""
    proibidos = {
        "coid",
        "clid",
        "payload",
        "payload_ref",
        "content",
        "locator",
        "uri",
        "path",
        "lineage",
        "provenance",
        "causal_history_id",
        "subject_identifier",
    }
    colunas = {c.name for c in RetentionPolicy.__table__.columns}
    assert colunas & proibidos == set()


def test_u37_modelo_nao_tem_foreign_key():
    """Referências são declarativas e históricas."""
    assert RetentionPolicy.__table__.foreign_keys == set()


def test_u38_rule_id_nao_str_recusado_por_tipo():
    """`TypeError` e `ValueError` permanecem diagnósticos distintos."""
    with pytest.raises(TypeError):
        regra(rule_id=123)


def test_u39_violacao_nao_unique_sobe_sem_traducao():
    """Só a violação de UNIQUE vira `RetentionPolicyVersionExistsError`.

    Qualquer outro `PersistenceError` sobe intacto — traduzir por
    eliminação esconderia a causa real, que foi a lição da E3.2.1.
    """
    from unittest.mock import patch

    from app.repositories.exceptions import PersistenceError

    repo = _repo()
    with (
        patch.object(RetentionPolicyRepository, "add", side_effect=PersistenceError("outro")),
        pytest.raises(PersistenceError),
    ):
        repo.add_policy(
            policy_key="ret.default",
            version=1,
            governance_policy_key="gov.default",
            rules=(regra(),),
        )
