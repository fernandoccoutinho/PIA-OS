"""
Prova do lock consultivo do perfil manual — separada, e por uma razão.

```text
OUTCOME_PRESERVED != MECHANISM_EXERCISED
```

ACHADO REGISTRADO. O mutante que removia o lock consultivo
**sobreviveu** à prova de idempotência: com quatro chamadores
concorrentes, o índice parcial mais o savepoint já entregam o resultado
exigido (uma linha, um `connection_id`, zero `IntegrityError` exposto).
Isto é, o lock **não é** o que sustenta aquela propriedade.

A conclusão honesta não é "o lock é inútil" nem "o mutante estava
errado": é que a prova media o **desfecho**, e o lock é uma camada de
serialização cujo efeito próprio precisa de prova própria. Sem este
arquivo, remover o lock passaria despercebido — e a próxima entrega
herdaria um mecanismo que ninguém verifica.

O que o lock entrega, e só ele: **serialização**. Com ele, o segundo
chamador espera; sem ele, os dois tentam inserir e um perde a corrida no
índice. Os dois caminhos chegam a uma linha só; apenas um deles evita o
trabalho descartado.
"""

import threading
import time

import pytest
import sqlalchemy as sa

from app.connections.repositories.connection_repository import (
    MANUAL_PROFILE_LOCK_NAMESPACE,
    ConnectionRepository,
)
from app.database.engine import engine
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not check_database_health().available,
        reason="PostgreSQL real indisponível — advisory lock é a prova.",
    ),
]


@pytest.fixture(autouse=True)
def _base_limpa():
    with engine.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM connection_profiles"))
    yield
    with engine.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM connection_profiles"))


def test_e741l01_o_lock_consultivo_e_de_fato_tomado() -> None:
    """`pg_advisory_xact_lock` aparece em `pg_locks` durante a transação.

    Prova direta do mecanismo, e não do desfecho: o lock existe, é do
    namespace declarado, e é da própria transação — some no commit sem
    ninguém precisar liberá-lo.
    """
    with UnitOfWork() as uow:
        ConnectionRepository(uow.session).acquire_manual_profile_lock(
            control_principal_ref="observado"
        )
        with engine.connect() as observador:
            travas = observador.execute(
                sa.text(
                    "SELECT classid, objid FROM pg_locks "
                    "WHERE locktype = 'advisory' AND classid = :ns"
                ),
                {"ns": MANUAL_PROFILE_LOCK_NAMESPACE},
            ).all()
        assert travas, "o lock consultivo não foi tomado"
        uow.commit()

    # `xact`: liberado no fim da transação, sem ninguém lembrar de soltá-lo.
    with engine.connect() as observador:
        restantes = observador.execute(
            sa.text(
                "SELECT count(*) FROM pg_locks " "WHERE locktype = 'advisory' AND classid = :ns"
            ),
            {"ns": MANUAL_PROFILE_LOCK_NAMESPACE},
        ).scalar_one()
    assert restantes == 0, "o lock sobreviveu ao commit"


def test_e741l02_o_segundo_chamador_espera_em_vez_de_correr() -> None:
    """Serialização observável: o segundo só progride quando o primeiro sai.

    Sem o lock, os dois entram ao mesmo tempo e o desempate acontece no
    índice — mesmo resultado final, mecanismo diferente. É essa diferença
    que este teste mede.
    """
    liberado = threading.Event()
    segundo_entrou = threading.Event()
    erros: list[BaseException] = []

    def primeiro() -> None:
        try:
            with UnitOfWork() as uow:
                ConnectionRepository(uow.session).acquire_manual_profile_lock(
                    control_principal_ref="disputado"
                )
                liberado.wait(timeout=10)
                uow.commit()
        except BaseException as erro:  # noqa: BLE001
            erros.append(erro)

    def segundo() -> None:
        try:
            with UnitOfWork() as uow:
                ConnectionRepository(uow.session).acquire_manual_profile_lock(
                    control_principal_ref="disputado"
                )
                segundo_entrou.set()
                uow.commit()
        except BaseException as erro:  # noqa: BLE001
            erros.append(erro)

    fio_a = threading.Thread(target=primeiro)
    fio_b = threading.Thread(target=segundo)
    fio_a.start()
    time.sleep(0.4)
    fio_b.start()

    assert not segundo_entrou.wait(timeout=1.0), "o segundo passou sem esperar o primeiro"
    liberado.set()
    assert segundo_entrou.wait(timeout=10), "o segundo nunca progrediu"

    fio_a.join(timeout=15)
    fio_b.join(timeout=15)
    assert not erros, erros


def test_e741l03_perder_a_corrida_nao_invalida_a_transacao_externa() -> None:
    """O savepoint tem efeito PRÓPRIO, e ele precisa de prova própria.

    ```text
    PERDER A CORRIDA != INVALIDAR A TRANSAÇÃO EXTERNA
    ```

    SEGUNDO ACHADO REGISTRADO. O mutante que remove o `begin_nested()`
    sobreviveu à prova de idempotência — e a razão é boa: com o lock
    consultivo funcionando, os quatro chamadores **serializam**, o
    segundo relê e encontra o vencedor, e nenhum `INSERT` perdedor chega
    a existir. O savepoint nunca é exercitado por aquele caminho.

    ```text
    DEFENSE_IN_DEPTH_NÃO_EXERCITADA = DEFENSE_NÃO_PROVADA
    ```

    A corrida é montada aqui de forma **determinística**: o vencedor é
    inserido por outra conexão, e a transação externa então tenta o
    `INSERT` perdedor tendo já escrito algo que precisa sobreviver. Sem
    o savepoint, o `IntegrityError` invalidaria a transação inteira — e
    a escrita anterior morreria junto.
    """
    from sqlalchemy.exc import IntegrityError

    from app.connections.models.enums import ConnectionMethod, ConnectionState

    # Vencedor da corrida, criado FORA da transação sob teste.
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO connection_profiles "
                "(id, control_principal_ref, method, endpoint_ref, state) "
                "VALUES (gen_random_uuid(), 'corrida', 'manual_handoff', NULL, 'available')"
            )
        )

    with UnitOfWork() as uow:
        repositorio = ConnectionRepository(uow.session)
        # Escrita anterior que PRECISA sobreviver ao perdedor.
        familia = repositorio.add_provider_family(slug="sobrevivente", display_name="S")
        familia_id = familia.id

        with pytest.raises(IntegrityError), repositorio.nested_transaction():
            repositorio.create_profile(
                control_principal_ref="corrida",
                method=ConnectionMethod.MANUAL_HANDOFF,
                state=ConnectionState.AVAILABLE,
                endpoint_ref=None,
                access_provider_id=None,
            )

        # A transação externa continua utilizável: lê e commita.
        assert repositorio.get_provider_family(family_id=familia_id) is not None
        uow.commit()

    with engine.connect() as conexao:
        sobreviveu = conexao.execute(
            sa.text("SELECT count(*) FROM connection_provider_families WHERE slug='sobrevivente'")
        ).scalar_one()
        perfis = conexao.execute(
            sa.text(
                "SELECT count(*) FROM connection_profiles WHERE control_principal_ref='corrida'"
            )
        ).scalar_one()
    assert sobreviveu == 1, "a escrita anterior morreu junto com o perdedor"
    assert perfis == 1, "o perdedor entrou no banco"

    with engine.begin() as conexao:
        conexao.execute(
            sa.text("DELETE FROM connection_provider_families WHERE slug='sobrevivente'")
        )
