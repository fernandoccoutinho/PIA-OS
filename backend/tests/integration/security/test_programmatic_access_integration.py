"""
Cota atômica, revogação e migration da `E6.2` contra PostgreSQL real.

```text
TWO_SESSIONS_CANNOT_EXCEED_LIMIT
WINDOW_CLOCK = POSTGRESQL
REPOSITORY_FAILURE -> DENY
MIGRATION_ROUND_TRIP = UP_DOWN_UP, SINGLE HEAD
```

A prova de concorrência é o motivo de a cota viver no banco. Um contador
em memória passaria neste arquivo com uma sessão e falharia em produção
com duas réplicas — por isso o teste usa conexões distintas de verdade.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.database.session import SessionLocal
from app.models.programmatic_service_principal import (
    OPERATION_PREDICTIVE_EVALUATE,
    SCOPE_PREDICTIVE_EVALUATE,
)
from app.repositories.programmatic_access_repository import ProgrammaticAccessRepository
from app.security.programmatic_access import compute_secret_digest

pytestmark = pytest.mark.skipif(
    not check_database_health().available,
    reason="PostgreSQL real indisponível — cota atômica não pode ser provada sem banco.",
)

_MIGRATION_E62 = "b4d71c58ae02"
_MIGRATION_PARENT = "f8a91c2d4e60"


@pytest.fixture(autouse=True)
def _limpa():
    with engine.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM programmatic_quota_buckets"))
        conexao.execute(sa.text("DELETE FROM programmatic_service_principals"))
    yield


def _novo_principal(
    *, quota_limit: int = 3, quota_window_seconds: int = 3600
) -> tuple[uuid.UUID, str]:
    key_id = f"kid-{uuid.uuid4().hex[:16]}"
    with SessionLocal() as sessao:
        principal = ProgrammaticAccessRepository(sessao).create_principal(
            key_id=key_id,
            secret_digest=compute_secret_digest(key_id, "segredo"),
            scopes=(SCOPE_PREDICTIVE_EVALUATE,),
            quota_limit=quota_limit,
            quota_window_seconds=quota_window_seconds,
        )
        sessao.commit()
        return principal.id, key_id


def _consome(principal_id: uuid.UUID, limite: int, janela: int = 3600) -> bool:
    """Uma sessão nova por chamada — simula réplicas distintas."""
    with SessionLocal() as sessao:
        liberado = ProgrammaticAccessRepository(sessao).consume_quota(
            principal_id=principal_id,
            operation=OPERATION_PREDICTIVE_EVALUATE,
            quota_limit=limite,
            quota_window_seconds=janela,
        )
        sessao.commit()
        return liberado


# --- prova 4/7: concorrência ------------------------------------------------


def test_e62q01_duas_sessoes_alternadas_nao_ultrapassam_o_teto() -> None:
    principal_id, _ = _novo_principal(quota_limit=3)
    resultados = [_consome(principal_id, 3) for _ in range(5)]
    assert resultados == [True, True, True, False, False]


def test_e62q02_concorrencia_real_em_threads_respeita_o_teto() -> None:
    """Vinte tentativas simultâneas, teto sete: exatamente sete liberam."""
    principal_id, _ = _novo_principal(quota_limit=7)
    with ThreadPoolExecutor(max_workers=10) as executor:
        resultados = list(executor.map(lambda _: _consome(principal_id, 7), range(20)))
    assert sum(resultados) == 7
    with engine.connect() as conexao:
        usado = conexao.execute(
            sa.text("SELECT used FROM programmatic_quota_buckets WHERE principal_id = :pid"),
            {"pid": principal_id},
        ).scalar_one()
    assert usado == 7


def test_e62q03_um_unico_bucket_por_janela() -> None:
    """Sem a unicidade, cada réplica criaria seu bucket e o teto dobraria."""
    principal_id, _ = _novo_principal(quota_limit=5)
    for _ in range(4):
        _consome(principal_id, 5)
    with engine.connect() as conexao:
        linhas = conexao.execute(
            sa.text("SELECT count(*) FROM programmatic_quota_buckets WHERE principal_id = :pid"),
            {"pid": principal_id},
        ).scalar_one()
    assert linhas == 1


def test_e62q04_janelas_distintas_tem_buckets_distintos() -> None:
    principal_id, _ = _novo_principal(quota_limit=1)
    assert _consome(principal_id, 1, janela=1) is True
    with engine.begin() as conexao:
        # Reposiciona a janela para trás em vez de esperar o relógio real.
        conexao.execute(
            sa.text(
                "UPDATE programmatic_quota_buckets "
                "SET window_start = window_start - interval '10 seconds' "
                "WHERE principal_id = :pid"
            ),
            {"pid": principal_id},
        )
    assert _consome(principal_id, 1, janela=1) is True
    with engine.connect() as conexao:
        buckets = conexao.execute(
            sa.text("SELECT count(*) FROM programmatic_quota_buckets WHERE principal_id = :pid"),
            {"pid": principal_id},
        ).scalar_one()
    assert buckets == 2


def test_e62q05_janela_usa_o_relogio_do_postgres() -> None:
    principal_id, _ = _novo_principal(quota_limit=2)
    _consome(principal_id, 2, janela=3600)
    with engine.connect() as conexao:
        inicio, agora = conexao.execute(
            sa.text(
                "SELECT window_start, now() FROM programmatic_quota_buckets "
                "WHERE principal_id = :pid"
            ),
            {"pid": principal_id},
        ).one()
    assert inicio <= agora
    assert (agora - inicio) < timedelta(seconds=3600)


def test_e62q06_limite_invalido_e_recusado_em_vez_de_ignorado() -> None:
    principal_id, _ = _novo_principal()
    with SessionLocal() as sessao:
        repositorio = ProgrammaticAccessRepository(sessao)
        with pytest.raises(ValueError):
            repositorio.consume_quota(
                principal_id=principal_id,
                operation=OPERATION_PREDICTIVE_EVALUATE,
                quota_limit=0,
                quota_window_seconds=60,
            )


# --- revogação --------------------------------------------------------------


def test_e62q07_revogacao_e_idempotente_e_preserva_o_primeiro_instante() -> None:
    _, key_id = _novo_principal()
    with SessionLocal() as sessao:
        repositorio = ProgrammaticAccessRepository(sessao)
        assert repositorio.revoke(key_id) is True
        sessao.commit()
        primeiro = repositorio.get_by_key_id(key_id).revoked_at
    with SessionLocal() as sessao:
        repositorio = ProgrammaticAccessRepository(sessao)
        assert repositorio.revoke(key_id) is True
        sessao.commit()
        assert repositorio.get_by_key_id(key_id).revoked_at == primeiro


def test_e62q08_revogar_inexistente_devolve_false_sem_criar_linha() -> None:
    with SessionLocal() as sessao:
        assert ProgrammaticAccessRepository(sessao).revoke("kid-inexistente") is False
    with engine.connect() as conexao:
        total = conexao.execute(
            sa.text("SELECT count(*) FROM programmatic_service_principals")
        ).scalar_one()
    assert total == 0


def test_e62q09_principal_expirado_deixa_de_ser_ativo() -> None:
    _, key_id = _novo_principal()
    with SessionLocal() as sessao:
        repositorio = ProgrammaticAccessRepository(sessao)
        linha = repositorio.get_by_key_id(key_id)
        linha.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        sessao.commit()
        assert linha.is_active_at(repositorio.database_now()) is False


# --- constraints ------------------------------------------------------------


def test_e62q10_banco_recusa_cota_nao_positiva() -> None:
    with pytest.raises(IntegrityError), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO programmatic_service_principals "
                "(id, key_id, secret_digest, scopes, quota_limit, "
                " quota_window_seconds, created_at, updated_at) "
                "VALUES (gen_random_uuid(), 'kid-limite-zero', :d, "
                "'[\"predictive:evaluate\"]'::jsonb, 0, 60, now(), now())"
            ),
            {"d": "a" * 64},
        )


def test_e62q11_banco_recusa_digest_de_tamanho_errado() -> None:
    with pytest.raises(IntegrityError), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO programmatic_service_principals "
                "(id, key_id, secret_digest, scopes, quota_limit, "
                " quota_window_seconds, created_at, updated_at) "
                "VALUES (gen_random_uuid(), 'kid-digest-curto', 'abc', "
                "'[\"predictive:evaluate\"]'::jsonb, 5, 60, now(), now())"
            )
        )


def test_e62q12_key_id_e_unico() -> None:
    _, key_id = _novo_principal()
    with pytest.raises(IntegrityError), SessionLocal() as sessao:
        ProgrammaticAccessRepository(sessao).create_principal(
            key_id=key_id,
            secret_digest="b" * 64,
            scopes=(SCOPE_PREDICTIVE_EVALUATE,),
            quota_limit=1,
            quota_window_seconds=60,
        )
        sessao.commit()


# --- prova 17: migration ----------------------------------------------------


def test_e62q13_migration_tem_head_unico_e_pai_correto() -> None:
    from alembic.script import ScriptDirectory

    diretorio = ScriptDirectory.from_config(migrations.get_alembic_config())
    heads = diretorio.get_heads()
    assert tuple(heads) == (_MIGRATION_E62,), heads
    revisao = diretorio.get_revision(_MIGRATION_E62)
    assert revisao.down_revision == _MIGRATION_PARENT


def test_e62q14_round_trip_da_migration_em_banco_limpo() -> None:
    """`upgrade -> downgrade -> upgrade` sem resíduo de tabela."""
    with engine.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM programmatic_quota_buckets"))
        conexao.execute(sa.text("DELETE FROM programmatic_service_principals"))
    migrations.downgrade(_MIGRATION_PARENT)
    inspetor = sa.inspect(engine)
    assert "programmatic_service_principals" not in inspetor.get_table_names()
    assert "programmatic_quota_buckets" not in inspetor.get_table_names()
    migrations.upgrade("head")
    inspetor = sa.inspect(engine)
    assert "programmatic_service_principals" in inspetor.get_table_names()
    assert "programmatic_quota_buckets" in inspetor.get_table_names()


# --- prova 18: CLI ----------------------------------------------------------


def test_e62q15_cli_cria_exibe_uma_vez_e_revoga(capsys: pytest.CaptureFixture[str]) -> None:
    from scripts import programmatic_principal as cli

    codigo = cli.main(
        ["create", "--quota-limit", "5", "--quota-window", "60", "--description", "teste"]
    )
    assert codigo == 0
    saida = capsys.readouterr().out
    assert "exibida uma unica vez" in saida
    key_id = saida.split("key_id: ")[1].split("\n")[0].strip()
    token = saida.split("unica vez): ")[1].split("\n")[0].strip()
    secret = token.rsplit(".", 1)[1]

    with SessionLocal() as sessao:
        linha = ProgrammaticAccessRepository(sessao).get_by_key_id(key_id)
        assert linha is not None
        assert secret not in linha.secret_digest
        assert linha.secret_digest == compute_secret_digest(key_id, secret)
        assert linha.scopes == [SCOPE_PREDICTIVE_EVALUATE]

    assert cli.main(["revoke", "--key-id", key_id]) == 0
    assert cli.main(["revoke", "--key-id", key_id]) == 0
    assert cli.main(["revoke", "--key-id", "kid-nao-existe"]) == 1


def test_e62q16_cli_recusa_parametros_invalidos() -> None:
    from scripts import programmatic_principal as cli

    assert cli.main(["create", "--quota-limit", "0", "--quota-window", "60"]) == 2
    assert cli.main(["create", "--quota-limit", "5", "--quota-window", "0"]) == 2
    assert cli.main(["create", "--quota-limit", "5", "--quota-window", "999999"]) == 2
    assert cli.main(["revoke", "--key-id", "   "]) == 2


def test_e62q17_cli_nao_oferece_listagem_de_segredo() -> None:
    import pathlib

    from scripts import programmatic_principal as cli

    fonte = pathlib.Path(cli.__file__).read_text(encoding="utf-8")
    assert "list" not in {
        acao.dest for acao in cli._build_parser()._subparsers._group_actions  # type: ignore[union-attr]
    }
    assert "def list_secrets" not in fonte
    assert "recover" not in fonte


# --- M1 corrigido: canonicidade imposta no escritor central ---------------


def test_e62q18_create_principal_recusa_escopo_desconhecido() -> None:
    """A sonda da auditoria persistia `("admin:*", "admin:*")`. Agora recusa."""
    with SessionLocal() as sessao:
        repositorio = ProgrammaticAccessRepository(sessao)
        with pytest.raises(ValueError, match="vocabulário fechado"):
            repositorio.create_principal(
                key_id=f"kid-{uuid.uuid4().hex[:16]}",
                secret_digest="a" * 64,
                scopes=("admin:*", "admin:*"),
                quota_limit=5,
                quota_window_seconds=60,
            )
    with engine.connect() as conexao:
        total = conexao.execute(
            sa.text("SELECT count(*) FROM programmatic_service_principals")
        ).scalar_one()
    assert total == 0, "recusa não pode deixar linha atrás"


def test_e62q19_create_principal_recusa_escopo_vazio() -> None:
    with SessionLocal() as sessao, pytest.raises(ValueError):
        ProgrammaticAccessRepository(sessao).create_principal(
            key_id=f"kid-{uuid.uuid4().hex[:16]}",
            secret_digest="a" * 64,
            scopes=(),
            quota_limit=5,
            quota_window_seconds=60,
        )


def test_e62q20_create_principal_canonicaliza_duplicatas() -> None:
    """Duplicata reescrita para a lista canônica, não persistida como veio."""
    key_id = f"kid-{uuid.uuid4().hex[:16]}"
    with SessionLocal() as sessao:
        principal = ProgrammaticAccessRepository(sessao).create_principal(
            key_id=key_id,
            secret_digest="a" * 64,
            scopes=(SCOPE_PREDICTIVE_EVALUATE, SCOPE_PREDICTIVE_EVALUATE),
            quota_limit=5,
            quota_window_seconds=60,
        )
        sessao.commit()
        assert principal.scopes == [SCOPE_PREDICTIVE_EVALUATE]
    with engine.connect() as conexao:
        persistido = conexao.execute(
            sa.text("SELECT scopes FROM programmatic_service_principals WHERE key_id = :kid"),
            {"kid": key_id},
        ).scalar_one()
    assert persistido == [SCOPE_PREDICTIVE_EVALUATE]


def test_e62q21_cli_e_repositorio_usam_o_mesmo_contrato() -> None:
    """Um vocabulário só. Dois validadores divergiriam com o tempo."""
    import app.models.programmatic_service_principal as modelo
    import app.repositories.programmatic_access_repository as repo
    from scripts import programmatic_principal as cli

    assert cli.canonical_scopes is modelo.canonical_scopes
    assert repo.canonical_scopes is modelo.canonical_scopes
