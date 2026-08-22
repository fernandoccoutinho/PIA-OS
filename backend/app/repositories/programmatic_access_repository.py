"""
Persistência do acesso programático (E6.2): autenticação, revogação e cota.

```text
QUOTA_SOURCE_OF_TRUTH = POSTGRESQL
IN_MEMORY_QUOTA_AS_AUTHORITY = FORBIDDEN
CLOCK = POSTGRESQL_CLOCK
```

A cota usa uma **única** instrução `INSERT ... ON CONFLICT ... DO UPDATE
... WHERE used < limit RETURNING`. Ler-depois-escrever seria uma corrida:
duas réplicas leriam `used = limite - 1` e ambas passariam. Aqui a
condição vive dentro do `UPDATE`, então o PostgreSQL serializa a decisão
na própria linha.

A janela é derivada do relógio do PostgreSQL (`now()`), não do relógio de
cada processo — relógios de aplicação divergem e uma janela por réplica
não é uma janela.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.programmatic_service_principal import (
    ProgrammaticQuotaBucket,
    ProgrammaticServicePrincipal,
    canonical_scopes,
)


class ProgrammaticAccessRepository:
    """Único caminho de leitura/escrita das duas tabelas da E6.2."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # --- autenticação ------------------------------------------------------

    def get_by_key_id(self, key_id: str) -> ProgrammaticServicePrincipal | None:
        """Busca pelo identificador público. `None` é resposta válida.

        Não filtra por revogação/expiração aqui de propósito: quem decide
        é o verificador, com o instante do banco, para que a mesma consulta
        sirva à autenticação e à operação administrativa.
        """
        return self._session.scalars(
            sa.select(ProgrammaticServicePrincipal).where(
                ProgrammaticServicePrincipal.key_id == key_id
            )
        ).one_or_none()

    def database_now(self) -> datetime:
        """Instante do PostgreSQL — nunca `datetime.now()` da aplicação."""
        moment = self._session.execute(sa.select(sa.func.now())).scalar_one()
        if not isinstance(moment, datetime):  # pragma: no cover - defesa de tipo
            raise TypeError("now() do banco não retornou datetime")
        return moment

    # --- provisionamento administrativo -----------------------------------

    def create_principal(
        self,
        *,
        key_id: str,
        secret_digest: str,
        scopes: tuple[str, ...],
        quota_limit: int,
        quota_window_seconds: int,
        description: str | None = None,
        expires_at: datetime | None = None,
    ) -> ProgrammaticServicePrincipal:
        """Canonicaliza os escopos AQUI, na fronteira central de escrita.

        Delegar isso à CLI deixaria o vocabulário fechado valendo apenas
        para quem passa por ela: qualquer outro chamador do repositório
        persistiria escopo desconhecido, duplicado ou fora de ordem. A
        garantia tem de morar no único ponto por onde toda escrita passa.

        ```text
        CLI_VALIDATION != WRITER_INVARIANT
        UNKNOWN_SCOPE = REJECTED_AT_WRITE_TIME
        ```
        """
        canonicos = canonical_scopes(scopes)
        principal = ProgrammaticServicePrincipal(
            key_id=key_id,
            secret_digest=secret_digest,
            scopes=list(canonicos),
            quota_limit=quota_limit,
            quota_window_seconds=quota_window_seconds,
            description=description,
            expires_at=expires_at,
        )
        self._session.add(principal)
        self._session.flush()
        return principal

    def revoke(self, key_id: str) -> bool:
        """Idempotente: revogar duas vezes preserva o primeiro instante.

        Devolve `True` quando a linha existe (revogada agora ou já antes),
        `False` quando não existe. Não revela digest nem segredo.
        """
        principal = self.get_by_key_id(key_id)
        if principal is None:
            return False
        if principal.revoked_at is None:
            principal.revoked_at = self.database_now()
            self._session.flush()
        return True

    # --- cota --------------------------------------------------------------

    def consume_quota(
        self,
        *,
        principal_id: uuid.UUID,
        operation: str,
        quota_limit: int,
        quota_window_seconds: int,
    ) -> bool:
        """Incremento condicional atômico. `False` = teto atingido.

        O `WHERE` do `DO UPDATE` é o que torna a operação segura sob
        concorrência: quando a condição falha, o `RETURNING` não devolve
        linha alguma e nenhuma contagem é incrementada.
        """
        if quota_limit <= 0 or quota_window_seconds <= 0:
            raise ValueError("quota_limit e quota_window_seconds devem ser positivos")
        instrucao = sa.text(
            """
            INSERT INTO programmatic_quota_buckets
                (id, principal_id, operation, window_start, used, created_at, updated_at)
            VALUES (
                :bucket_id,
                :principal_id,
                :operation,
                to_timestamp(
                    floor(extract(epoch FROM now()) / :window_seconds) * :window_seconds
                ),
                1,
                now(),
                now()
            )
            ON CONFLICT (principal_id, operation, window_start)
            DO UPDATE SET
                used = programmatic_quota_buckets.used + 1,
                updated_at = now()
            WHERE programmatic_quota_buckets.used < :quota_limit
            RETURNING used
            """
        )
        resultado = self._session.execute(
            instrucao,
            {
                "bucket_id": uuid.uuid4(),
                "principal_id": principal_id,
                "operation": operation,
                "window_seconds": quota_window_seconds,
                "quota_limit": quota_limit,
            },
        ).scalar_one_or_none()
        return resultado is not None

    def current_usage(
        self, *, principal_id: uuid.UUID, operation: str, quota_window_seconds: int
    ) -> int:
        """Contagem da janela corrente — diagnóstico, não autoridade."""
        bucket = self._session.scalars(
            sa.select(ProgrammaticQuotaBucket)
            .where(
                ProgrammaticQuotaBucket.principal_id == principal_id,
                ProgrammaticQuotaBucket.operation == operation,
                ProgrammaticQuotaBucket.window_start
                == sa.func.to_timestamp(
                    sa.func.floor(sa.func.extract("epoch", sa.func.now()) / quota_window_seconds)
                    * quota_window_seconds
                ),
            )
            .limit(1)
        ).one_or_none()
        return 0 if bucket is None else bucket.used
