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
    """Atualizado pela E4.9.6.1: `rules` recebe e devolve a tupla TIPADA.

    A serialização canônica passou para o `TypeDecorator`, na ida para o
    disco. Não existe mais `list[dict]` em memória — nem na escrita.
    """
    p = RetentionPolicy(
        policy_key="ret.default",
        version=1,
        governance_policy_key="gov.default",
        rules=(regra(),),
    )
    assert p.typed_rules[0].rule_id == "ret-001"
    assert p.typed_rules is p.rules


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


# ======================================================================
# E4.9.6.1 — corretivo A1: validação de identificador opaco
#
# Todos os casos abaixo FALHAM na cadeia 76 e passam a partir da 77:
# o `add_policy` daquela cadeia verificava apenas `strip()`, e `\n`,
# `\t`, NUL e DEL têm conteúdo não branco ao redor.
# ======================================================================


CONTROLES = ["x\ntexto", "x\rtexto", "x\ttexto", "x\x00texto", "x\x7ftexto", "\x1ftexto"]


@pytest.mark.parametrize("valor", CONTROLES)
@pytest.mark.parametrize("campo", ["policy_key", "governance_policy_key"])
def test_u40_controle_recusado_nos_dois_campos(campo, valor):
    """Reprodução do achado A1 da auditoria da cadeia 76."""
    base: dict[str, object] = {
        "policy_key": "ret.default",
        "version": 1,
        "governance_policy_key": "gov.default",
        "rules": (regra(),),
    }
    base[campo] = valor
    with pytest.raises(ValueError, match="caracteres de controle"):
        _repo().add_policy(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("campo", ["policy_key", "governance_policy_key"])
def test_u41_limite_de_256_caracteres(campo):
    """256 aceita, 257 recusa — nos dois campos."""
    from unittest.mock import patch

    base: dict[str, object] = {
        "policy_key": "ret.default",
        "version": 1,
        "governance_policy_key": "gov.default",
        "rules": (regra(),),
    }

    aceita = dict(base, **{campo: "k" * 256})
    with patch.object(RetentionPolicyRepository, "add", side_effect=lambda e: e):
        gravada = _repo().add_policy(**aceita)  # type: ignore[arg-type]
    assert len(getattr(gravada, campo)) == 256

    with pytest.raises(ValueError, match="excede 256"):
        _repo().add_policy(**dict(base, **{campo: "k" * 257}))  # type: ignore[arg-type]


@pytest.mark.parametrize("campo", ["policy_key", "governance_policy_key"])
def test_u42_tipo_errado_recusado_por_typeerror(campo):
    """`TypeError` e `ValueError` permanecem diagnósticos distintos."""
    base: dict[str, object] = {
        "policy_key": "ret.default",
        "version": 1,
        "governance_policy_key": "gov.default",
        "rules": (regra(),),
    }
    with pytest.raises(TypeError):
        _repo().add_policy(**dict(base, **{campo: 123}))  # type: ignore[arg-type]


def test_u43_chave_valida_permanece_byte_a_byte_inalterada():
    """`VALIDATED OPAQUE KEY != NORMALIZED KEY`.

    Sem `strip`, sem normalização Unicode, sem `casefold`. Uma chave
    que o sistema altera em silêncio deixa de ser a identidade que o
    chamador declarou.
    """
    from unittest.mock import patch

    chave = "  Ret.Café_ÑÃO-01  "
    with patch.object(RetentionPolicyRepository, "add", side_effect=lambda e: e):
        gravada = _repo().add_policy(
            policy_key=chave,
            version=1,
            governance_policy_key=chave,
            rules=(regra(),),
        )
    assert gravada.policy_key == chave
    assert gravada.governance_policy_key == chave


def test_u44_validador_compartilhado_tem_um_contrato_so():
    """`rule_id` e as chaves passam pelo MESMO validador."""
    from app.memory.schemas.retention import validar_identificador_opaco

    assert validar_identificador_opaco("x", "válido", 256) == "válido"
    with pytest.raises(ValueError):
        validar_identificador_opaco("x", "a\nb", 256)
    with pytest.raises(ValueError):
        validar_identificador_opaco("x", "   ", 256)
    with pytest.raises(TypeError):
        validar_identificador_opaco("x", 1, 256)


# ======================================================================
# E4.9.6.1 — corretivo A2: imutabilidade profunda de leitura
# ======================================================================


def test_u45_rules_e_tupla_tipada_nao_lista_de_dicts():
    """Reprodução do achado A2: não existe mais `list[dict]` pública."""
    p = RetentionPolicy(
        policy_key="ret.default",
        version=1,
        governance_policy_key="gov.default",
        rules=(regra(),),
    )
    assert isinstance(p.rules, tuple)
    assert all(isinstance(r, RetentionRule) for r in p.rules)


def test_u46_mutacao_aninhada_recusada():
    """O caso exato que a auditoria reproduziu na cadeia 76."""
    p = RetentionPolicy(
        policy_key="ret.default",
        version=1,
        governance_policy_key="gov.default",
        rules=(regra(),),
    )
    antes = p.rules[0].minimum_age_days

    with pytest.raises(TypeError):
        p.rules[0]["minimum_age_days"] = 0  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        p.rules[0].minimum_age_days = 0  # type: ignore[misc]
    with pytest.raises(TypeError):
        p.rules[0] = regra(rule_id="outra")  # type: ignore[index]

    assert p.rules[0].minimum_age_days == antes


def test_u47_domain_ids_tambem_e_imutavel():
    p = RetentionPolicy(
        policy_key="ret.default",
        version=1,
        governance_policy_key="gov.default",
        rules=(
            regra(
                rule_id="d",
                scope_kind=RetentionScopeKind.MEMORY_DOMAIN_SET,
                domain_ids={D1},
            ),
        ),
    )
    dominios = p.rules[0].domain_ids
    assert isinstance(dominios, frozenset)
    with pytest.raises(AttributeError):
        dominios.add(D2)  # type: ignore[attr-defined]


def test_u48_type_decorator_faz_o_round_trip_canonico():
    """`typed -> persisted -> typed` determinístico, sem sessão."""
    from sqlalchemy.dialects import postgresql

    from app.memory.models.retention_policy import RetentionRulesType

    tipo = RetentionRulesType()
    dialeto = postgresql.dialect()
    originais = (regra(rule_id="b"), regra(rule_id="a"))

    persistido = tipo.process_bind_param(originais, dialeto)
    assert isinstance(persistido, list)
    assert [linha["rule_id"] for linha in persistido] == ["a", "b"]

    voltou = tipo.process_result_value(persistido, dialeto)
    assert voltou is not None
    assert set(voltou) == set(originais)
    assert isinstance(voltou, tuple)


def test_u49_type_decorator_trata_nulo_e_forma_invalida():
    from sqlalchemy.dialects import postgresql

    from app.memory.models.retention_policy import RetentionRulesType

    tipo = RetentionRulesType()
    dialeto = postgresql.dialect()
    assert tipo.process_bind_param(None, dialeto) is None
    assert tipo.process_result_value(None, dialeto) is None
    with pytest.raises(ValueError, match="lista JSON"):
        tipo.process_result_value({"nao": "lista"}, dialeto)


def test_u50_type_decorator_usa_jsonb_no_postgres_e_json_nos_demais():
    """`MIGRATION_DELTA = 0`: o tipo no banco é o mesmo da cadeia 76."""
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.types import JSON

    from app.memory.models.retention_policy import RetentionRulesType

    tipo = RetentionRulesType()
    assert isinstance(tipo.load_dialect_impl(postgresql.dialect()), JSONB)
    assert isinstance(tipo.load_dialect_impl(sqlite.dialect()), JSON)


# ======================================================================
# E4.9.6.2 — completude de fronteira
#
# A3B: todos os casos de construtor/atribuição abaixo FALHAM na cadeia
# 77, onde o congelamento vivia só no `TypeDecorator` e o construtor ORM
# guardava `list[dict]` mutável.
# A3A: a matriz Unicode é endurecimento novo, autorizado pela auditoria
# da cadeia 77 — não descumprimento retroativo da E4.9.6.1, que fechou
# exatamente C0+DEL como seu contrato mandava.
# ======================================================================


def _policy(**overrides: object) -> RetentionPolicy:
    base: dict[str, object] = {
        "policy_key": "ret.default",
        "version": 1,
        "governance_policy_key": "gov.default",
        "rules": (regra(),),
    }
    base.update(overrides)
    return RetentionPolicy(**base)  # type: ignore[arg-type]


# --- Fronteira 1: construtor ORM direto ----------------------------------


def test_u51_construtor_direto_aceita_a_tupla_tipada():
    p = _policy()
    assert isinstance(p.rules, tuple)
    assert isinstance(p.rules[0], RetentionRule)
    assert p.typed_rules is p.rules


@pytest.mark.parametrize(
    "valor",
    [
        [
            {
                "rule_id": "r1",
                "scope_kind": "all_local_patrimony",
                "domain_ids": [],
                "anchor": "created_at",
                "minimum_age_days": 30,
                "on_expiry_action": "assess_and_inform",
            }
        ],
        {"rule_id": "r1"},
        "texto",
        42,
        None,
        [regra()],
    ],
)
def test_u52_construtor_direto_recusa_representacao_nao_tipada(valor):
    """Reprodução do achado A3b — a lista de dicionários do auditor."""
    with pytest.raises(TypeError):
        _policy(rules=valor)


def test_u53_construtor_direto_recusa_tupla_vazia():
    with pytest.raises(ValueError, match="ao menos uma regra"):
        _policy(rules=())


def test_u54_construtor_direto_recusa_item_de_tipo_errado():
    with pytest.raises(TypeError, match="RetentionRule"):
        _policy(rules=({"rule_id": "r1"},))


def test_u55_construtor_direto_recusa_duplicata_antes_do_bind():
    with pytest.raises(ValueError, match="duplicado"):
        _policy(rules=(regra(rule_id="a"), regra(rule_id="a")))


# --- Fronteira 2: atribuição posterior ------------------------------------


@pytest.mark.parametrize("valor", [[{"rule_id": "r1"}], "texto", 42, None, ()])
def test_u56_atribuicao_invalida_preserva_o_valor_anterior(valor):
    """Recusar não é o mesmo que corromper."""
    p = _policy()
    antes = p.rules
    with pytest.raises((TypeError, ValueError)):
        p.rules = valor
    assert p.rules is antes
    assert isinstance(p.rules[0], RetentionRule)


def test_u57_atribuicao_valida_substitui():
    p = _policy()
    nova = (regra(rule_id="outra"),)
    p.rules = nova
    assert p.rules is nova


def test_u58_mutacao_aninhada_impossivel_pelo_construtor_direto():
    """O caminho exato da reprodução da auditoria da cadeia 77."""
    p = _policy()
    with pytest.raises(TypeError):
        p.rules[0]["minimum_age_days"] = 0  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        p.rules[0].minimum_age_days = 0  # type: ignore[misc]
    assert p.rules[0].minimum_age_days == 30


# --- typed_rules defensivo ------------------------------------------------


def test_u59_typed_rules_verifica_em_runtime_e_nao_mente_o_tipo():
    """`ANNOTATED TYPE != RUNTIME TYPE PROOF`.

    O `__dict__` é forçado de propósito, contornando o `@validates`,
    para provar que a propriedade não é passthrough: a anotação diz
    `tuple[RetentionRule, ...]` e o runtime a sustenta.
    """
    p = _policy()
    p.__dict__["rules"] = [{"rule_id": "r1"}]
    with pytest.raises(TypeError):
        _ = p.typed_rules

    p.__dict__["rules"] = ()
    with pytest.raises(ValueError):
        _ = p.typed_rules


def test_u60_typed_rules_nao_fabrica_copia():
    p = _policy()
    assert p.typed_rules is p.rules


# --- Fronteira 3: bind ----------------------------------------------------


def _tipo_e_dialeto():
    from sqlalchemy.dialects import postgresql

    from app.memory.models.retention_policy import RetentionRulesType

    return RetentionRulesType(), postgresql.dialect()


@pytest.mark.parametrize(
    "valor",
    [
        [{"rule_id": "r1", "minimum_age_days": 30}],
        "texto",
        42,
        [regra()],
        (regra(), "x"),
    ],
)
def test_u61_bind_produz_erro_de_contrato_nunca_incidental(valor):
    """Na cadeia 77 isto morria em `AttributeError: 'dict' object ...`."""
    tipo, dialeto = _tipo_e_dialeto()
    with pytest.raises((TypeError, ValueError)) as capturado:
        tipo.process_bind_param(valor, dialeto)
    assert not isinstance(capturado.value, AttributeError)


def test_u62_bind_recusa_tupla_vazia_e_duplicata():
    tipo, dialeto = _tipo_e_dialeto()
    with pytest.raises(ValueError, match="ao menos uma regra"):
        tipo.process_bind_param((), dialeto)
    with pytest.raises(ValueError, match="duplicado"):
        tipo.process_bind_param((regra(rule_id="a"), regra(rule_id="a")), dialeto)


def test_u63_bind_valido_serializa_canonicamente():
    tipo, dialeto = _tipo_e_dialeto()
    persistido = tipo.process_bind_param((regra(rule_id="b"), regra(rule_id="a")), dialeto)
    assert [linha["rule_id"] for linha in persistido] == ["a", "b"]


# --- Fronteira 4: result --------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        [{"lixo": True}],
        ["nao e objeto"],
        [42],
        [None],
        [{"rule_id": "r1", "scope_kind": "all_local_patrimony"}],
    ],
)
def test_u64_result_recusa_payload_malformado_de_forma_controlada(payload):
    """Antes da E4.9.6.2 chave ausente virava `KeyError` incidental."""
    tipo, dialeto = _tipo_e_dialeto()
    with pytest.raises((TypeError, ValueError)):
        tipo.process_result_value(payload, dialeto)


def test_u65_round_trip_tipado_e_deterministico():
    tipo, dialeto = _tipo_e_dialeto()
    originais = (regra(rule_id="b"), regra(rule_id="a"))
    ida = tipo.process_bind_param(originais, dialeto)
    volta = tipo.process_result_value(ida, dialeto)
    assert isinstance(volta, tuple)
    assert all(isinstance(r, RetentionRule) for r in volta)
    assert tipo.process_bind_param(volta, dialeto) == ida


# --- A3a: matriz Unicode --------------------------------------------------


INVISIVEIS = [
    "\u0000",  # Cc NUL
    "\u000a",  # Cc LINE FEED
    "\u007f",  # Cc DELETE
    "\u0085",  # Cc NEXT LINE
    "\u009f",  # Cc APPLICATION PROGRAM COMMAND
    "\u200b",  # Cf ZERO WIDTH SPACE
    "\u202e",  # Cf RIGHT-TO-LEFT OVERRIDE
    "\ufeff",  # Cf BYTE ORDER MARK
    "\u2028",  # Zl LINE SEPARATOR
    "\u2029",  # Zp PARAGRAPH SEPARATOR
]


@pytest.mark.parametrize("invisivel", INVISIVEIS)
@pytest.mark.parametrize("campo", ["policy_key", "governance_policy_key"])
def test_u66_invisiveis_unicode_recusados_nos_dois_campos(campo, invisivel):
    base: dict[str, object] = {
        "policy_key": "ret.default",
        "version": 1,
        "governance_policy_key": "gov.default",
        "rules": (regra(),),
    }
    base[campo] = f"x{invisivel}y"
    with pytest.raises(ValueError, match="caracteres de controle"):
        _repo().add_policy(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("invisivel", INVISIVEIS)
def test_u67_invisiveis_unicode_recusados_tambem_no_rule_id(invisivel):
    with pytest.raises(ValueError):
        regra(rule_id=f"x{invisivel}y")


@pytest.mark.parametrize(
    "valido",
    ["ret.default", "ação", "produção", "São_Paulo", "chave com espaço", "ret-001_v2"],
)
def test_u68_identificador_valido_devolvido_byte_a_byte(valido):
    """`VALIDATED OPAQUE KEY != NORMALIZED KEY`."""
    from app.memory.schemas.retention import validar_identificador_opaco

    devolvido = validar_identificador_opaco("policy_key", valido, 256)
    assert devolvido is valido
    assert devolvido.encode("utf-8") == valido.encode("utf-8")


def test_u69_sequencias_unicode_distintas_nao_sao_fundidas():
    """`ação` pré-composta e decomposta continuam sendo duas chaves."""
    from app.memory.schemas.retention import validar_identificador_opaco

    precomposta = "a\u00e7\u00e3o"
    decomposta = "ac\u0327a\u0303o"
    assert precomposta != decomposta
    assert validar_identificador_opaco("policy_key", precomposta, 256) == precomposta
    assert validar_identificador_opaco("policy_key", decomposta, 256) == decomposta


def test_u70_espaco_comum_nao_e_invisivel_proibido():
    """`Zs` não está na lista — só `Zl` e `Zp` estão."""
    import unicodedata

    from app.memory.schemas.retention import validar_identificador_opaco

    assert unicodedata.category(" ") == "Zs"
    assert validar_identificador_opaco("policy_key", "com espaço", 256) == "com espaço"


# --- Contrato compartilhado ----------------------------------------------


def test_u71_validador_de_regras_devolve_a_mesma_tupla_sem_reordenar():
    from app.memory.schemas.retention import validar_regras_retencao

    original = (regra(rule_id="b"), regra(rule_id="a"))
    devolvida = validar_regras_retencao("rules", original)
    assert devolvida is original
    assert [r.rule_id for r in devolvida] == ["b", "a"]


def test_u72_serialize_rules_delegou_ao_contrato_compartilhado():
    """Uma lista deixou de ser aceita — o contrato exige tupla."""
    with pytest.raises(TypeError):
        RetentionPolicy.serialize_rules([regra()])  # type: ignore[arg-type]


def test_u73_codigos_de_erro_permanecem_inalterados():
    assert PIA_8042_RETENTION_POLICY_VERSION_EXISTS.code == "PIA-8042"
    assert PIA_8043_RETENTION_POLICY_IMMUTABLE.code == "PIA-8043"
    assert RetentionPolicyVersionExistsError("k", 1).error_code.code == "PIA-8042"
    assert RetentionPolicyImmutableError(None, operation="update").error_code.code == "PIA-8043"
