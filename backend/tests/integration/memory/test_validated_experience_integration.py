"""
Registro de experiência validada contra PostgreSQL real (`E4.11`).

```text
APPEND_ONLY_IN_THREE_LAYERS
ZERO_OVERWRITE
REPETITION_IS_EVIDENCE
```

O que só o banco real prova: que a trigger recusa `UPDATE` e `DELETE`
mesmo por SQL que não passa pelo repositório, que o replay concorrente
em **duas sessões** converge sem sobrescrever, e que um conflito de
identidade não deixa escrita alguma.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.memory.errors.exceptions import (
    ValidatedExperienceConflictError,
    ValidatedExperienceImmutableError,
)
from app.memory.models.memory_domain import MemoryDomain
from app.memory.models.validated_experience import ValidatedExperience
from app.memory.models.validated_experience_enums import (
    CriterionOriginKind,
    EvidenceKind,
    ExperienceSubjectKind,
    ValidatorKind,
)
from app.memory.repositories.validated_experience_repository import (
    ValidatedExperienceRepository,
)
from app.memory.schemas.validated_experience import (
    AttributedValidator,
    CriterionReference,
    EvidenceReference,
    ExperienceSubjectRef,
    ObservedOutcome,
    OriginAttribution,
    ValidatedExperienceAppend,
)

AGORA = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)

TABELAS_CONGELADAS = (
    "cognitive_objects",
    "provenance_records",
    "causal_history_events",
    "erasure_records",
    "approval_records",
    "governance_policies",
)


def _disponivel() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _disponivel(),
    reason="PostgreSQL real indisponível — append-only e trigger exigem banco.",
)


@pytest.fixture(autouse=True)
def _limpar():
    migrations.upgrade("head")
    _truncar()
    yield
    _truncar()


def _truncar() -> None:
    """Remove as linhas **desativando a trigger**, e só nos testes.

    A trigger existe para recusar mutação em produção; um teste que não
    conseguisse limpar o próprio estado deixaria a suíte dependente de
    ordem. `session_replication_role` é o mecanismo do PostgreSQL para
    isso, e vale só para esta sessão.
    """
    with engine.begin() as conn:
        conn.execute(sa.text("SET session_replication_role = replica"))
        conn.execute(sa.text("TRUNCATE validated_experiences"))
        conn.execute(sa.text("SET session_replication_role = DEFAULT"))
        # As provas do achado A1 gravam um `MemoryDomain` para medir que a
        # escrita NÃO relacionada sobrevive. Ele pertence à E4.1 e não é
        # append-only — mas deixá-lo para trás bloquearia o downgrade de
        # `memory_domains` e reprovaria os testes de round trip da E3 e da
        # E4.1. Removo apenas as linhas que estes testes criaram, pelo
        # prefixo do nome; nenhuma outra é tocada.
        conn.execute(sa.text("DELETE FROM memory_domains WHERE name LIKE 'dominio-i3%'"))


def _evidencia(kind: EvidenceKind = EvidenceKind.CAUSAL_EVENT, ref: uuid.UUID | None = None):
    return EvidenceReference(kind=kind, ref=ref or uuid.uuid4())


def _entrada(
    *,
    experience_id: uuid.UUID | None = None,
    token: str = "produced",
    evidencia: EvidenceReference | None = None,
    validated_at: datetime = AGORA,
    criterion_version: int = 3,
    criterion_origin: CriterionOriginKind = CriterionOriginKind.PUBLISHED,
) -> ValidatedExperienceAppend:
    lastro = evidencia or _evidencia()
    return ValidatedExperienceAppend(
        experience_id=experience_id or uuid.uuid4(),
        subject_ref=ExperienceSubjectRef(kind=ExperienceSubjectKind.CAUSAL_EVENT, ref=uuid.uuid4()),
        outcome_observed=ObservedOutcome(
            outcome_token=token, observed_at=AGORA, primary_evidence_ref=lastro
        ),
        validated_by=AttributedValidator(
            validator_kind=ValidatorKind.HUMAN, validator_ref="humano:ana"
        ),
        criterion_ref=CriterionReference(
            criterion_key="crit.fidelidade",
            criterion_version=criterion_version,
            criterion_origin=criterion_origin,
        ),
        evidence_refs=(lastro,),
        validated_at=validated_at,
        origin=OriginAttribution(origin_ref=uuid.uuid4()),
    )


def _censo() -> dict[str, int]:
    with Session(engine) as sessao:
        return {
            tabela: sessao.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar_one()
            for tabela in (*TABELAS_CONGELADAS, "validated_experiences")
        }


def _registrar(entrada: ValidatedExperienceAppend) -> uuid.UUID:
    with Session(engine) as sessao:
        registro = ValidatedExperienceRepository(sessao).append(entrada)
        sessao.commit()
        return registro.id


# ----------------------------------------------------------------------
# Append e leitura
# ----------------------------------------------------------------------


def test_i01_append_persiste_o_vinculo_completo():
    entrada = _entrada()
    _registrar(entrada)

    with Session(engine) as sessao:
        registro = ValidatedExperienceRepository(sessao).get(entrada.experience_id)
        assert registro is not None
        assert registro.subject_ref == entrada.subject_ref.ref
        assert registro.outcome_token == "produced"
        assert registro.validator_ref == "humano:ana"
        assert registro.criterion_key == "crit.fidelidade"
        assert registro.criterion_version == 3
        assert registro.origin_ref == entrada.origin.origin_ref
        assert registro.validated_at == AGORA


def test_i02_a_identidade_e_a_fornecida_pelo_chamador():
    """`EXPERIENCE_ID != COID` — e não é gerada no flush."""
    identidade = uuid.uuid4()
    assert _registrar(_entrada(experience_id=identidade)) == identidade


def test_i03_o_lastro_volta_do_banco_ja_tipado():
    """`PERSISTENT IMMUTABILITY != DEEP READ IMMUTABILITY` — ambas exigidas."""
    entrada = _entrada()
    _registrar(entrada)
    with Session(engine) as sessao:
        registro = ValidatedExperienceRepository(sessao).get(entrada.experience_id)
        assert registro is not None
        assert isinstance(registro.evidence_refs, tuple)
        assert isinstance(registro.evidence_refs[0], EvidenceReference)
        assert registro.evidence_refs == entrada.evidence_refs


def test_i04_leitura_por_sujeito_em_ordem_canonica():
    sujeito = ExperienceSubjectRef(kind=ExperienceSubjectKind.CAUSAL_EVENT, ref=uuid.uuid4())
    instantes = [AGORA + timedelta(minutes=posicao) for posicao in (2, 0, 1)]
    for instante in instantes:
        base = _entrada(validated_at=instante)
        with Session(engine) as sessao:
            ValidatedExperienceRepository(sessao).append(
                ValidatedExperienceAppend(
                    experience_id=base.experience_id,
                    subject_ref=sujeito,
                    outcome_observed=base.outcome_observed,
                    validated_by=base.validated_by,
                    criterion_ref=base.criterion_ref,
                    evidence_refs=base.evidence_refs,
                    validated_at=instante,
                    origin=base.origin,
                )
            )
            sessao.commit()

    with Session(engine) as sessao:
        encontrados = ValidatedExperienceRepository(sessao).list_by_subject(
            sujeito.kind, sujeito.ref
        )
    assert [registro.validated_at for registro in encontrados] == sorted(instantes)


def _criterio(versao: int = 3, origem: CriterionOriginKind = CriterionOriginKind.PUBLISHED):
    return CriterionReference(
        criterion_key="crit.fidelidade", criterion_version=versao, criterion_origin=origem
    )


def test_i05_leitura_por_criterio():
    _registrar(_entrada(criterion_version=3))
    _registrar(_entrada(criterion_version=4))
    with Session(engine) as sessao:
        repositorio = ValidatedExperienceRepository(sessao)
        assert len(repositorio.list_by_criterion(_criterio(3))) == 1
        assert len(repositorio.list_by_criterion(_criterio(4))) == 1


def test_i05_1_a_consulta_separa_origens_do_mesmo_criterio():
    """`PARTIAL_REFERENCE_QUERY != EXACT_CRITERION_BINDING`.

    Duas linhas com a MESMA chave e versão, origens diferentes. Antes da
    correção da auditoria, a consulta devolvia as duas e apresentava dois
    critérios distintos como um só.
    """
    _registrar(_entrada(criterion_origin=CriterionOriginKind.PUBLISHED))
    _registrar(_entrada(criterion_origin=CriterionOriginKind.DECLARED))

    with Session(engine) as sessao:
        repositorio = ValidatedExperienceRepository(sessao)
        publicadas = repositorio.list_by_criterion(_criterio(origem=CriterionOriginKind.PUBLISHED))
        declaradas = repositorio.list_by_criterion(_criterio(origem=CriterionOriginKind.DECLARED))

    assert [r.criterion_origin for r in publicadas] == [CriterionOriginKind.PUBLISHED]
    assert [r.criterion_origin for r in declaradas] == [CriterionOriginKind.DECLARED]


def test_i05_2_a_consulta_recusa_referencia_parcial():
    """Três argumentos soltos permitiriam omitir a origem por engano."""
    with Session(engine) as sessao, pytest.raises(TypeError, match="CriterionReference"):
        ValidatedExperienceRepository(sessao).list_by_criterion("crit.fidelidade")


# ----------------------------------------------------------------------
# Idempotência por identidade
# ----------------------------------------------------------------------


def test_i06_replay_identico_devolve_o_existente_sem_nova_linha():
    entrada = _entrada()
    _registrar(entrada)
    antes = _censo()
    devolvido = _registrar(entrada)
    assert devolvido == entrada.experience_id
    assert _censo() == antes


def test_i07_conflito_de_identidade_recusa_com_zero_escrita():
    """`REPLAY_SAME_ID + DIFFERENT_CANONICAL_PAYLOAD -> PIA-8050`."""
    entrada = _entrada(token="produced")
    _registrar(entrada)
    antes = _censo()

    divergente = ValidatedExperienceAppend(
        experience_id=entrada.experience_id,
        subject_ref=entrada.subject_ref,
        outcome_observed=ObservedOutcome(
            outcome_token="diverged",
            observed_at=AGORA,
            primary_evidence_ref=entrada.evidence_refs[0],
        ),
        validated_by=entrada.validated_by,
        criterion_ref=entrada.criterion_ref,
        evidence_refs=entrada.evidence_refs,
        validated_at=entrada.validated_at,
        origin=entrada.origin,
    )
    with Session(engine) as sessao, pytest.raises(ValidatedExperienceConflictError) as capturado:
        ValidatedExperienceRepository(sessao).append(divergente)

    assert capturado.value.error_code.code == "PIA-8050"
    assert capturado.value.diverging_fields == ("outcome_token",)
    assert _censo() == antes
    with Session(engine) as sessao:
        registro = ValidatedExperienceRepository(sessao).get(entrada.experience_id)
        assert registro is not None
        assert registro.outcome_token == "produced"


def test_i08_identidades_diferentes_com_os_mesmos_valores_sao_permitidas():
    """`REPETITION_IS_EVIDENCE` — fundi-las apagaria a distinção."""
    primeira = _entrada()
    _registrar(primeira)
    segunda = ValidatedExperienceAppend(
        experience_id=uuid.uuid4(),
        subject_ref=primeira.subject_ref,
        outcome_observed=primeira.outcome_observed,
        validated_by=primeira.validated_by,
        criterion_ref=primeira.criterion_ref,
        evidence_refs=primeira.evidence_refs,
        validated_at=primeira.validated_at,
        origin=primeira.origin,
    )
    _registrar(segunda)

    with Session(engine) as sessao:
        encontrados = ValidatedExperienceRepository(sessao).list_by_subject(
            primeira.subject_ref.kind, primeira.subject_ref.ref
        )
    assert len(encontrados) == 2


def test_i09_replay_concorrente_em_duas_sessoes_converge():
    """Duas sessões abertas ao mesmo tempo, ambas passando pela leitura.

    A primeira commita entre a leitura e o flush da segunda — a rota do
    `IntegrityError` é a única que resolve esta corrida, e sem ela o
    replay legítimo apareceria como erro de banco cru.
    """
    entrada = _entrada()
    primeira = Session(engine)
    segunda = Session(engine)
    try:
        repo_a = ValidatedExperienceRepository(primeira)
        repo_b = ValidatedExperienceRepository(segunda)

        # Ambas leem e não encontram nada.
        assert repo_a.get(entrada.experience_id) is None
        assert repo_b.get(entrada.experience_id) is None

        repo_a.append(entrada)
        primeira.commit()

        devolvido = repo_b.append(entrada)
        segunda.commit()
        assert devolvido.id == entrada.experience_id
    finally:
        primeira.close()
        segunda.close()

    with Session(engine) as sessao:
        total = sessao.execute(sa.text("SELECT count(*) FROM validated_experiences")).scalar_one()
    assert total == 1


def test_i10_conflito_concorrente_tambem_recusa():
    entrada = _entrada(token="produced")
    divergente = ValidatedExperienceAppend(
        experience_id=entrada.experience_id,
        subject_ref=entrada.subject_ref,
        outcome_observed=ObservedOutcome(
            outcome_token="not_produced",
            observed_at=AGORA,
            primary_evidence_ref=entrada.evidence_refs[0],
        ),
        validated_by=entrada.validated_by,
        criterion_ref=entrada.criterion_ref,
        evidence_refs=entrada.evidence_refs,
        validated_at=entrada.validated_at,
        origin=entrada.origin,
    )
    primeira = Session(engine)
    segunda = Session(engine)
    try:
        repo_a = ValidatedExperienceRepository(primeira)
        repo_b = ValidatedExperienceRepository(segunda)
        assert repo_b.get(entrada.experience_id) is None
        repo_a.append(entrada)
        primeira.commit()
        with pytest.raises(ValidatedExperienceConflictError):
            repo_b.append(divergente)
    finally:
        primeira.close()
        segunda.close()

    with Session(engine) as sessao:
        registro = ValidatedExperienceRepository(sessao).get(entrada.experience_id)
        assert registro is not None
        assert registro.outcome_token == "produced"


# ----------------------------------------------------------------------
# Append-only nas três camadas
# ----------------------------------------------------------------------


@pytest.mark.parametrize("operacao", ["update", "delete", "soft_delete"])
def test_i11_o_repositorio_recusa_mutacao(operacao):
    entrada = _entrada()
    _registrar(entrada)
    with Session(engine) as sessao:
        repositorio = ValidatedExperienceRepository(sessao)
        registro = repositorio.get(entrada.experience_id)
        with pytest.raises(ValidatedExperienceImmutableError) as capturado:
            getattr(repositorio, operacao)(registro)
        assert capturado.value.error_code.code == "PIA-8051"


@pytest.mark.parametrize("operacao", ["bulk_update", "bulk_delete"])
def test_i12_o_repositorio_recusa_mutacao_em_lote(operacao):
    with Session(engine) as sessao, pytest.raises(ValidatedExperienceImmutableError):
        getattr(ValidatedExperienceRepository(sessao), operacao)()


@pytest.mark.parametrize(
    "comando",
    [
        "UPDATE validated_experiences SET outcome_token = 'x'",
        "DELETE FROM validated_experiences",
    ],
)
def test_i13_o_banco_recusa_sql_arbitrario(comando):
    """A terceira camada: SQL que não passa pelo repositório também é recusado."""
    entrada = _entrada()
    _registrar(entrada)
    antes = _censo()

    with pytest.raises(Exception, match="append-only"), engine.begin() as conn:
        conn.execute(sa.text(comando))

    assert _censo() == antes
    with Session(engine) as sessao:
        registro = ValidatedExperienceRepository(sessao).get(entrada.experience_id)
        assert registro is not None
        assert registro.outcome_token == "produced"


# ----------------------------------------------------------------------
# Constraints do banco
# ----------------------------------------------------------------------


def test_i14_o_banco_recusa_validacao_anterior_a_observacao():
    """`observed_at <= validated_at` — observa-se antes de validar."""
    with pytest.raises(Exception), engine.begin() as conn:  # noqa: B017
        conn.execute(
            sa.text(
                "INSERT INTO validated_experiences (id, subject_kind, subject_ref, "
                "outcome_token, observed_at, primary_evidence_kind, primary_evidence_ref, "
                "validator_kind, validator_ref, criterion_key, criterion_version, "
                "criterion_origin, evidence_refs, validated_at, origin_ref) VALUES "
                "(gen_random_uuid(), 'causal_event', gen_random_uuid(), 'produced', "
                "now(), 'causal_event', gen_random_uuid(), 'human', 'h:a', 'c', 1, "
                "'published', '[]'::jsonb, now() - interval '1 day', gen_random_uuid())"
            )
        )


def test_i15_o_banco_recusa_versao_de_criterio_invalida():
    with pytest.raises(Exception), engine.begin() as conn:  # noqa: B017
        conn.execute(
            sa.text(
                "INSERT INTO validated_experiences (id, subject_kind, subject_ref, "
                "outcome_token, observed_at, primary_evidence_kind, primary_evidence_ref, "
                "validator_kind, validator_ref, criterion_key, criterion_version, "
                "criterion_origin, evidence_refs, validated_at, origin_ref) VALUES "
                "(gen_random_uuid(), 'causal_event', gen_random_uuid(), 'produced', "
                "now(), 'causal_event', gen_random_uuid(), 'human', 'h:a', 'c', 0, "
                "'published', '[]'::jsonb, now(), gen_random_uuid())"
            )
        )


# ----------------------------------------------------------------------
# Migration
# ----------------------------------------------------------------------


def test_i16_cabeca_unica_e_sucessora_linear():
    assert migrations.head_revision() == "e7c25a91f4b3"
    assert migrations.current_revision() == "e7c25a91f4b3"


def test_i17_round_trip_com_a_tabela_vazia():
    """`TABLE_EMPTY -> downgrade permitido`."""
    _truncar()
    migrations.downgrade("d5b31f7a08c4")
    with Session(engine) as sessao:
        existe = sessao.execute(
            sa.text("SELECT count(*) FROM pg_tables WHERE tablename = 'validated_experiences'")
        ).scalar_one()
    assert existe == 0
    migrations.upgrade("head")
    assert migrations.current_revision() == "e7c25a91f4b3"


def test_i18_downgrade_com_dados_recusa_antes_de_qualquer_ddl():
    """`REFUSE_BEFORE_ALTER, NEVER_MID_MIGRATION`.

    Depois da recusa, tabela, trigger, função, dados e revisão precisam
    estar exatamente como estavam — uma tabela append-only que ficasse
    gravável no meio de uma migration abortada perdeu a propriedade que
    a define.
    """
    entrada = _entrada()
    _registrar(entrada)

    with pytest.raises(RuntimeError, match="downgrade recusado"):
        migrations.downgrade("d5b31f7a08c4")

    with Session(engine) as sessao:
        tabela = sessao.execute(
            sa.text("SELECT count(*) FROM pg_tables WHERE tablename = 'validated_experiences'")
        ).scalar_one()
        gatilho = sessao.execute(
            sa.text(
                "SELECT count(*) FROM pg_trigger WHERE tgname = "
                "'trg_validated_experiences_append_only'"
            )
        ).scalar_one()
        funcao = sessao.execute(
            sa.text(
                "SELECT count(*) FROM pg_proc WHERE proname = "
                "'reject_validated_experience_mutation'"
            )
        ).scalar_one()
        indices = sessao.execute(
            sa.text("SELECT count(*) FROM pg_indexes WHERE tablename = 'validated_experiences'")
        ).scalar_one()
        linhas = sessao.execute(sa.text("SELECT count(*) FROM validated_experiences")).scalar_one()

    assert (tabela, gatilho, funcao, linhas) == (1, 1, 1, 1)
    assert indices >= 3
    assert migrations.current_revision() == "e7c25a91f4b3"

    # E a trigger continua ativa depois da recusa.
    with pytest.raises(Exception, match="append-only"), engine.begin() as conn:
        conn.execute(sa.text("UPDATE validated_experiences SET outcome_token = 'x'"))


def test_i19_nenhuma_tabela_congelada_foi_tocada():
    """A E4.11 não escreve em nada que não seja a própria tabela."""
    antes = _censo()
    _registrar(_entrada())
    depois = _censo()
    for tabela in TABELAS_CONGELADAS:
        assert depois[tabela] == antes[tabela], tabela
    assert depois["validated_experiences"] == antes["validated_experiences"] + 1


def test_i20_o_registro_nao_viaja_no_sync_da_e3():
    """`TRANSPORT_IMPLEMENTED = NO` — medido contra o mapa real da E3.

    Criar a tabela **não** a faz viajar: o que viaja é o que está em
    `SECTION_BY_TABLE`, e a E4.11 não a registra ali. Tocar nesse mapa
    seria alterar E3 congelada.
    """
    from app.cognitive.schemas.synchronization import SECTION_BY_TABLE

    assert "validated_experiences" not in SECTION_BY_TABLE


def test_i21_a_tabela_esta_no_metadata_da_aplicacao():
    """Guarda de premissa do teste anterior: a tabela existe e é conhecida."""
    assert ValidatedExperience.__tablename__ in ValidatedExperience.metadata.tables


# ----------------------------------------------------------------------
# Fronteiras de atribuição e leitura — tipos exatos
# ----------------------------------------------------------------------


def test_i22_a_fronteira_de_atribuicao_valida_o_lastro():
    """`TYPE DECORATOR BOUNDARY != ORM ASSIGNMENT BOUNDARY`.

    O `TypeDecorator` cobre disco; o `@validates` cobre a construção
    direta do modelo, que nunca passa pelo bind antes do flush. Os dois
    chamam a mesma função — a lição literal da E4.9.6.2.
    """
    evidencia = _evidencia()
    with pytest.raises(TypeError, match="sequência"):
        ValidatedExperience(evidence_refs="nao-e-sequencia")
    with pytest.raises(ValueError, match="não pode ser vazia"):
        ValidatedExperience(evidence_refs=())
    with pytest.raises(TypeError, match=r"evidence_refs\[0\]"):
        ValidatedExperience(evidence_refs=(str(evidencia.ref),))
    with pytest.raises(ValueError, match="repetida"):
        ValidatedExperience(evidence_refs=(evidencia, evidencia))

    primeira = _evidencia(EvidenceKind.CAUSAL_EVENT)
    segunda = _evidencia(EvidenceKind.PROVENANCE_RECORD)
    with pytest.raises(ValueError, match="ordem canônica"):
        ValidatedExperience(evidence_refs=(segunda, primeira))


def test_i23_o_decorador_recusa_lastro_ausente_ou_malformado():
    """`None` é recusado no domínio, e não delegado ao `NOT NULL`."""
    from app.memory.models.validated_experience import EvidenceRefsType

    decorador = EvidenceRefsType()
    with pytest.raises(ValueError, match="não admite None"):
        decorador.process_bind_param(None, None)
    with pytest.raises(ValueError, match="não admite None"):
        decorador.process_result_value(None, None)
    with pytest.raises(TypeError, match="formato inesperado"):
        decorador.process_result_value({"kind": "causal_event"}, None)


def test_i24_o_decorador_usa_json_generico_fora_do_postgresql():
    """A representação em memória é a mesma; o tipo no banco acompanha o
    dialeto, como no precedente da E4.9.6."""
    from sqlalchemy.dialects import sqlite

    from app.memory.models.validated_experience import EvidenceRefsType

    tipo = EvidenceRefsType().load_dialect_impl(sqlite.dialect())
    # O SQLite devolve sua própria especialização de JSON; o que a
    # guarda mede é que NÃO é `JSONB`, que só existe no PostgreSQL.
    assert "JSONB" not in tipo.__class__.__name__
    assert isinstance(tipo, sa.JSON)


@pytest.mark.parametrize(
    ("metodo", "argumentos", "erro"),
    [
        ("get", (str(uuid.uuid4()),), TypeError),
        ("list_by_subject", ("causal_event", uuid.uuid4()), TypeError),
        ("list_by_criterion", ("crit.x",), TypeError),
        ("list_by_criterion", (("crit.x", 1, "published"),), TypeError),
    ],
)
def test_i25_a_leitura_recusa_tipo_errado(metodo, argumentos, erro):
    with Session(engine) as sessao, pytest.raises(erro):
        getattr(ValidatedExperienceRepository(sessao), metodo)(*argumentos)


def test_i26_a_leitura_recusa_sujeito_nao_uuid():
    with Session(engine) as sessao, pytest.raises(TypeError, match="subject_ref deve ser UUID"):
        ValidatedExperienceRepository(sessao).list_by_subject(
            ExperienceSubjectKind.CAUSAL_EVENT, "nao-e-uuid"
        )


@pytest.mark.parametrize(("limite", "deslocamento"), [(0, 0), (1, -1), (True, 0), (1, True)])
def test_i27_a_paginacao_recusa_valor_invalido(limite, deslocamento):
    with Session(engine) as sessao, pytest.raises(ValueError):
        ValidatedExperienceRepository(sessao).list_by_criterion(
            _criterio(), limit=limite, offset=deslocamento
        )


def test_i28_o_append_recusa_entrada_nao_tipada():
    with Session(engine) as sessao, pytest.raises(TypeError, match="ValidatedExperienceAppend"):
        ValidatedExperienceRepository(sessao).append({"experience_id": uuid.uuid4()})


def test_i29_snapshot_que_nao_ve_a_vencedora_propaga_sinal():
    """`REPEATABLE READ` não permite leitura segura da linha concorrente.

    CORRIGIDO NA AUDITORIA DA CADEIA 96 (achado A1). A versão anterior
    devolvia a linha existente aqui — o que era impossível, porque o
    snapshot de B não a enxerga. O que a tornava "possível" era o
    `Session.rollback()` integral, que reiniciava a transação de B e, de
    quebra, apagava toda escrita anterior do chamador.

    O contrato passou a ser: sem leitura segura, o sinal sobe e o
    chamador repete numa transação nova. E a escrita não relacionada
    **sobrevive**.
    """
    from sqlalchemy.exc import IntegrityError

    entrada = _entrada()
    isolada = engine.execution_options(isolation_level="REPEATABLE READ")

    primeira = Session(engine)
    segunda = Session(isolada)
    try:
        repo_b = ValidatedExperienceRepository(segunda)
        assert repo_b.get(entrada.experience_id) is None

        # Escrita NÃO relacionada, anterior ao append, na mesma UoW.
        segunda.add(MemoryDomain(name="dominio-nao-relacionado-i29"))
        segunda.flush()
        antes = segunda.execute(sa.text("SELECT count(*) FROM memory_domains")).scalar_one()

        ValidatedExperienceRepository(primeira).append(entrada)
        primeira.commit()

        with pytest.raises(IntegrityError):
            repo_b.append(entrada)

        # `UNRELATED_ROWS_AFTER_INTEGRITY_PATH` — a transação de B segue
        # viva e a escrita anterior continua lá.
        depois = segunda.execute(sa.text("SELECT count(*) FROM memory_domains")).scalar_one()
        assert depois == antes
        segunda.rollback()
    finally:
        primeira.close()
        segunda.close()

    with Session(engine) as sessao:
        total = sessao.execute(
            sa.text("SELECT count(*) FROM validated_experiences WHERE id = :i"),
            {"i": entrada.experience_id},
        ).scalar_one()
    assert total == 1


def test_i30_integrity_error_que_nao_e_replay_e_propagado():
    """A rota do `IntegrityError` não engole erro que não seja corrida.

    Alcançada por **subclasse controlada** — construção legítima, sem
    `object.__setattr__` nem monkeypatch. A entrada viola o `CHECK` de
    coerência temporal, que a fronteira de domínio já recusa; aqui ela
    chega ao banco, o INSERT falha, e a releitura **não** encontra linha
    alguma. O correto é propagar: não houve replay.
    """

    class EntradaIncoerente(ValidatedExperienceAppend):
        def __post_init__(self) -> None:  # noqa: D105
            return

    lastro = _evidencia()
    entrada = EntradaIncoerente(
        experience_id=uuid.uuid4(),
        subject_ref=ExperienceSubjectRef(kind=ExperienceSubjectKind.CAUSAL_EVENT, ref=uuid.uuid4()),
        outcome_observed=ObservedOutcome(
            outcome_token="produced",
            observed_at=AGORA + timedelta(days=1),
            primary_evidence_ref=lastro,
        ),
        validated_by=AttributedValidator(
            validator_kind=ValidatorKind.HUMAN, validator_ref="humano:ana"
        ),
        criterion_ref=CriterionReference(
            criterion_key="crit.fidelidade",
            criterion_version=1,
            criterion_origin=CriterionOriginKind.PUBLISHED,
        ),
        evidence_refs=(lastro,),
        validated_at=AGORA,
        origin=OriginAttribution(origin_ref=uuid.uuid4()),
    )

    antes = _censo()
    with Session(engine) as sessao, pytest.raises(Exception, match="observed_before_validated"):
        ValidatedExperienceRepository(sessao).append(entrada)
    assert _censo() == antes


# ----------------------------------------------------------------------
# A1 — a transação do chamador é do chamador
# ----------------------------------------------------------------------


def _contar_dominios(sessao: Session, nome: str) -> int:
    """Conta pelo NOME, não o total.

    `memory_domains` pertence à E4.1 e não é truncada por esta fixture —
    contar o total misturaria linhas de outros testes e faria a asserção
    depender da ordem de execução.
    """
    return sessao.execute(
        sa.text("SELECT count(*) FROM memory_domains WHERE name = :n"), {"n": nome}
    ).scalar_one()


def test_i31_escrita_nao_relacionada_sobrevive_ao_replay_identico():
    """`UNRELATED_ROWS_AFTER_INTEGRITY_PATH` — o repositório não é dono
    da transação, e o replay não pode apagar o que o chamador escreveu."""
    entrada = _entrada()
    _registrar(entrada)

    with Session(engine) as sessao:
        nome = f"dominio-i31-{uuid.uuid4().hex}"
        sessao.add(MemoryDomain(name=nome))
        sessao.flush()
        antes = _contar_dominios(sessao, nome)

        devolvido = ValidatedExperienceRepository(sessao).append(entrada)
        assert devolvido.id == entrada.experience_id
        assert _contar_dominios(sessao, nome) == antes

        sessao.commit()

    with Session(engine) as sessao:
        assert _contar_dominios(sessao, nome) == 1


def test_i32_escrita_nao_relacionada_sobrevive_ao_conflito():
    """No conflito, quem decide `commit` ou `rollback` é o chamador."""
    entrada = _entrada(token="produced")
    _registrar(entrada)
    divergente = ValidatedExperienceAppend(
        experience_id=entrada.experience_id,
        subject_ref=entrada.subject_ref,
        outcome_observed=ObservedOutcome(
            outcome_token="diverged",
            observed_at=AGORA,
            primary_evidence_ref=entrada.evidence_refs[0],
        ),
        validated_by=entrada.validated_by,
        criterion_ref=entrada.criterion_ref,
        evidence_refs=entrada.evidence_refs,
        validated_at=entrada.validated_at,
        origin=entrada.origin,
    )

    with Session(engine) as sessao:
        nome = f"dominio-i32-{uuid.uuid4().hex}"
        sessao.add(MemoryDomain(name=nome))
        sessao.flush()
        antes = _contar_dominios(sessao, nome)

        with pytest.raises(ValidatedExperienceConflictError):
            ValidatedExperienceRepository(sessao).append(divergente)

        assert _contar_dominios(sessao, nome) == antes
        sessao.commit()

    with Session(engine) as sessao:
        assert _contar_dominios(sessao, nome) == 1


def test_i33_colisao_real_de_identidade_devolve_a_vencedora():
    """A rota do `SAVEPOINT`, exercitada até o fim.

    Alcançada por **subclasse controlada** que faz a leitura prévia
    devolver `None` uma única vez — construção legítima, sem
    `object.__setattr__` nem monkeypatch. O INSERT vai ao banco, a chave
    primária o recusa, o savepoint desfaz **só** ele, e a releitura
    devolve a linha vencedora.
    """
    entrada = _entrada()
    _registrar(entrada)

    class RepositorioComLeituraCega(ValidatedExperienceRepository):
        def __init__(self, sessao):  # noqa: ANN001, D107
            super().__init__(sessao)
            self._cego = True

        def get(self, experience_id):  # noqa: ANN001, ANN201, D102
            if self._cego:
                self._cego = False
                return None
            return super().get(experience_id)

    with Session(engine) as sessao:
        nome = f"dominio-i33-{uuid.uuid4().hex}"
        sessao.add(MemoryDomain(name=nome))
        sessao.flush()
        antes = _contar_dominios(sessao, nome)

        devolvido = RepositorioComLeituraCega(sessao).append(entrada)

        assert devolvido.id == entrada.experience_id
        assert _contar_dominios(sessao, nome) == antes
        sessao.commit()

    with Session(engine) as sessao:
        total = sessao.execute(sa.text("SELECT count(*) FROM validated_experiences")).scalar_one()
    assert total == 1


def test_i34_o_repositorio_nao_commita_nem_desfaz_a_sessao():
    """Medido por execução: a sessão registra o que foi chamado nela."""
    chamadas: list[str] = []

    class SessaoObservada(Session):
        def commit(self):  # noqa: ANN201, D102
            chamadas.append("commit")
            super().commit()

        def rollback(self):  # noqa: ANN201, D102
            chamadas.append("rollback")
            super().rollback()

    entrada = _entrada()
    with SessaoObservada(engine) as sessao:
        repositorio = ValidatedExperienceRepository(sessao)
        repositorio.append(entrada)
        repositorio.append(entrada)
        repositorio.get(entrada.experience_id)
        repositorio.list_by_subject(entrada.subject_ref.kind, entrada.subject_ref.ref)
        assert chamadas == []
        sessao.commit()
    assert chamadas == ["commit"]


# ----------------------------------------------------------------------
# A2 — UPDATE, DELETE e TRUNCATE recusados
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "comando",
    [
        "UPDATE validated_experiences SET outcome_token = 'x'",
        "DELETE FROM validated_experiences",
        "TRUNCATE validated_experiences",
    ],
)
def test_i35_o_banco_recusa_as_tres_operacoes_destrutivas(comando):
    """`ROW_TRIGGER_DOES_NOT_SEE_TRUNCATE`.

    `TRUNCATE` não dispara trigger de linha e exige trigger própria, em
    `FOR EACH STATEMENT`. Sem ela, um comando apagava a tabela
    append-only inteira sem encontrar recusa alguma — achado A2 da
    auditoria.
    """
    entrada = _entrada()
    _registrar(entrada)
    antes = _censo()

    with pytest.raises(Exception, match="append-only"), engine.begin() as conn:
        conn.execute(sa.text(comando))

    assert _censo() == antes
    with Session(engine) as sessao:
        registro = ValidatedExperienceRepository(sessao).get(entrada.experience_id)
        assert registro is not None
        assert registro.outcome_token == "produced"


def test_i36_os_dois_gatilhos_de_protecao_existem():
    with Session(engine) as sessao:
        gatilhos = {
            linha[0]
            for linha in sessao.execute(
                sa.text(
                    "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND "
                    "tgrelid = 'validated_experiences'::regclass"
                )
            )
        }
    assert gatilhos == {
        "trg_validated_experiences_append_only",
        "trg_validated_experiences_no_truncate",
    }


# ----------------------------------------------------------------------
# A3 — o lastro é validado pelo banco, não só pelo domínio
# ----------------------------------------------------------------------

_INSERT_BRUTO = (
    "INSERT INTO validated_experiences (id, subject_kind, subject_ref, outcome_token, "
    "observed_at, primary_evidence_kind, primary_evidence_ref, validator_kind, "
    "validator_ref, criterion_key, criterion_version, criterion_origin, evidence_refs, "
    "validated_at, origin_ref, created_at, updated_at) VALUES (gen_random_uuid(), "
    "'causal_event', gen_random_uuid(), 'produced', now(), 'causal_event', "
    ":primaria, 'human', 'h:a', 'c', 1, 'published', CAST(:lastro AS jsonb), now(), "
    "gen_random_uuid(), now(), now())"
)

_PRIMARIA = "11111111-1111-1111-1111-111111111111"
_OUTRA = "22222222-2222-2222-2222-222222222222"


def _item(kind: str, ref: str, **extras: object) -> str:
    """Monta um elemento de lastro em JSON, com campos extras opcionais.

    Concatenação por `json.dumps` em vez de interpolação: os casos
    inválidos precisam ser **exatamente** o que se quer testar, e um
    `%s` mal colocado transformaria "chave extra" em "JSON malformado".
    """
    import json

    return json.dumps({"kind": kind, "ref": ref, **extras})


@pytest.mark.parametrize(
    ("caso", "lastro"),
    [
        ("array vazio", "[]"),
        ("objeto em vez de array", _item("causal_event", _PRIMARIA)),
        ("elemento não objeto", '["texto"]'),
        ("chave ausente", '[{"kind": "causal_event"}]'),
        ("chave extra content", f"[{_item('causal_event', _PRIMARIA, content='x')}]"),
        ("chave extra url", f"[{_item('causal_event', _PRIMARIA, url='http://v')}]"),
        ("chave extra credential", f"[{_item('causal_event', _PRIMARIA, credential='s')}]"),
        ("chave arbitrária", f"[{_item('causal_event', _PRIMARIA, zz=1)}]"),
        ("kind desconhecido", f"[{_item('inventado', _PRIMARIA)}]"),
        ("uuid inválido", f"[{_item('causal_event', 'nao-uuid')}]"),
        (
            "duplicata",
            f"[{_item('causal_event', _PRIMARIA)}, {_item('causal_event', _PRIMARIA)}]",
        ),
        (
            "ordem não canônica",
            f"[{_item('causal_event', _OUTRA)}, {_item('causal_event', _PRIMARIA)}]",
        ),
        ("primária ausente do lastro", f"[{_item('causal_event', _OUTRA)}]"),
    ],
)
def test_i37_sql_bruto_com_lastro_invalido_e_recusado(caso, lastro):
    """`APP_TYPED_BOUNDARY != DATABASE_INTEGRITY`.

    O domínio já recusava tudo isto; a coluna impunha apenas `NOT NULL`.
    Numa tabela append-only, uma linha inválida ficaria permanente —
    achado A3 da auditoria.
    """
    antes = _censo()
    with pytest.raises(Exception), engine.begin() as conn:  # noqa: B017
        conn.execute(sa.text(_INSERT_BRUTO), {"lastro": lastro, "primaria": _PRIMARIA})
    assert _censo() == antes, caso


def test_i38_sql_bruto_com_lastro_canonico_e_aceito():
    """A validação recusa o inválido sem recusar o válido."""
    lastro = f"[{_item('causal_event', _PRIMARIA)}, {_item('provenance_record', _OUTRA)}]"
    with engine.begin() as conn:
        conn.execute(sa.text(_INSERT_BRUTO), {"lastro": lastro, "primaria": _PRIMARIA})
    with Session(engine) as sessao:
        total = sessao.execute(sa.text("SELECT count(*) FROM validated_experiences")).scalar_one()
    assert total == 1
