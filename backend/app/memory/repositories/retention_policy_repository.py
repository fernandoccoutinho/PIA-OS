"""
`RetentionPolicyRepository` — publicação e consulta de policies (`E4.9.6`).

Duas garantias que precisam vir do banco, não do código:

- **não sobrescrever versão publicada** — `UNIQUE(policy_key, version)`;
- **não duplicar versão sob concorrência** — a mesma constraint, que é
  a única coisa que continua valendo quando duas sessões escrevem no
  mesmo instante.

O repositório traduz a violação para exceção de domínio; a autoridade
final é a constraint.

## O que este repositório deliberadamente não tem

```text
RETENTION_POLICY_PERSISTENCE != RETENTION_EVALUATION
RETENTION_EVALUATOR = NOT_COMPOSED
```

Nenhum `evaluate`, `assess`, `expire`, `notify`, `trash`, `erase` ou
`delete_target`. Nenhum acesso a `CognitiveObject`, Retrieval, arquivos
ou conectores. Nenhuma chamada a `ErasureRecordRepository`. Nenhum
relógio implícito que dispare ação.

`effective_version_at` recebe o instante como **argumento** justamente
por isso: um repositório que lesse o relógio por conta própria estaria
a um passo de agir sozinho, e a diferença entre "qual versão valia
naquele momento" e "está na hora de fazer algo" é a diferença entre
consultar e executar.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.memory.errors.exceptions import (
    RetentionPolicyImmutableError,
    RetentionPolicyVersionExistsError,
)
from app.memory.models.retention_policy import RetentionPolicy
from app.memory.schemas.retention import RetentionRule
from app.repositories.base_repository import BaseRepository
from app.repositories.exceptions import PersistenceError

_POSTGRES_UNIQUE_VIOLATION_SQLSTATE = "23505"
_SQLITE_UNIQUE_ERRORNAME = "SQLITE_CONSTRAINT_UNIQUE"


def _is_unique_violation(exc: PersistenceError) -> bool:
    """Classifica por **sinal estruturado do driver**, nunca por texto.

    Lição de E3.2.1: classificar por parsing de mensagem é classificar
    por eliminação, e erra em silêncio quando a mensagem muda.
    """
    orig = getattr(exc, "__cause__", None)
    orig = getattr(orig, "orig", None) or orig
    if getattr(orig, "sqlstate", None) == _POSTGRES_UNIQUE_VIOLATION_SQLSTATE:
        return True
    return getattr(orig, "sqlite_errorname", None) == _SQLITE_UNIQUE_ERRORNAME


class RetentionPolicyRepository(BaseRepository[RetentionPolicy]):
    """Persistência e consulta de `RetentionPolicy`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, RetentionPolicy)

    def add_policy(
        self,
        *,
        policy_key: str,
        version: int,
        governance_policy_key: str,
        rules: tuple[RetentionRule, ...],
        effective_from: datetime | None = None,
        effective_until: datetime | None = None,
    ) -> RetentionPolicy:
        """Publica uma versão de policy de retenção.

        Levanta `RetentionPolicyVersionExistsError` (`PIA-8042`) se a
        versão já existir — nunca atualiza a linha existente.
        """
        if not isinstance(policy_key, str) or not policy_key.strip():
            raise ValueError("policy_key não pode ser vazio ou apenas espaços")
        if not isinstance(governance_policy_key, str) or not governance_policy_key.strip():
            raise ValueError("governance_policy_key não pode ser vazio ou apenas espaços")
        if isinstance(version, bool) or not isinstance(version, int):
            raise TypeError(f"version deve ser int, recebido {type(version).__name__}")
        if version < 1:
            raise ValueError("version deve ser >= 1")

        for nome, momento in (
            ("effective_from", effective_from),
            ("effective_until", effective_until),
        ):
            if momento is not None and (
                momento.tzinfo is None or momento.tzinfo.utcoffset(momento) is None
            ):
                raise ValueError(f"{nome} deve ser timezone-aware")

        if (
            effective_from is not None
            and effective_until is not None
            and effective_until <= effective_from
        ):
            raise ValueError("effective_until deve ser posterior a effective_from")

        entity = RetentionPolicy(
            policy_key=policy_key,
            version=version,
            governance_policy_key=governance_policy_key,
            rules=RetentionPolicy.serialize_rules(rules),
            effective_from=effective_from,
            effective_until=effective_until,
        )
        try:
            return self.add(entity)
        except PersistenceError as exc:
            if _is_unique_violation(exc):
                raise RetentionPolicyVersionExistsError(policy_key, version) from exc
            raise

    def get_version(self, policy_key: str, version: int) -> RetentionPolicy | None:
        """Uma versão específica, ou `None`. Ausência não é exceção."""
        stmt = select(RetentionPolicy).where(
            RetentionPolicy.policy_key == policy_key,
            RetentionPolicy.version == version,
        )
        return self._session.execute(stmt).scalars().one_or_none()

    def list_versions(self, policy_key: str) -> list[RetentionPolicy]:
        """Todas as versões, em ordem crescente de `version`."""
        stmt = (
            select(RetentionPolicy)
            .where(RetentionPolicy.policy_key == policy_key)
            .order_by(RetentionPolicy.version.asc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def effective_version_at(self, policy_key: str, moment: datetime) -> RetentionPolicy | None:
        """A versão vigente num instante, ou `None`.

        Janela `[effective_from, effective_until)` — início inclusivo,
        fim **exclusivo**. Com fim inclusivo, duas versões contíguas
        se sobreporiam exatamente no instante da virada, e "qual
        valia?" teria duas respostas.

        `None` em `effective_from` significa "desde sempre"; `None` em
        `effective_until`, "sem fim previsto".

        Desempate pela **maior versão**: se duas versões declaram
        janelas sobrepostas, a mais recente governa. Isto é escolha
        consciente e não corrige a sobreposição — publicar janelas
        sobrepostas continua sendo possível, e a resposta precisa ser
        determinística de qualquer forma.

        O instante vem por argumento: este repositório não lê o
        relógio, porque consultar qual regra valia não é decidir que
        está na hora de agir.
        """
        if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
            raise ValueError("moment deve ser timezone-aware")

        stmt = (
            select(RetentionPolicy)
            .where(
                RetentionPolicy.policy_key == policy_key,
                (RetentionPolicy.effective_from.is_(None))
                | (RetentionPolicy.effective_from <= moment),
                (RetentionPolicy.effective_until.is_(None))
                | (RetentionPolicy.effective_until > moment),
            )
            .order_by(RetentionPolicy.version.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalars().first()

    def max_version(self, policy_key: str) -> int:
        """Maior versão existente, ou `0` se não houver nenhuma.

        Serve para *sugerir* a próxima versão. Não é reserva: entre
        esta leitura e a escrita, outra sessão pode publicar a mesma —
        e aí a constraint recusa, corretamente. A checagem é
        conveniência; a garantia é do banco.
        """
        stmt = select(func.max(RetentionPolicy.version)).where(
            RetentionPolicy.policy_key == policy_key
        )
        return self._session.execute(stmt).scalar() or 0

    def update(self, entity: RetentionPolicy) -> RetentionPolicy:
        """Sempre rejeita — versões publicadas são imutáveis."""
        raise RetentionPolicyImmutableError(entity.id, operation="update")

    def delete(self, entity: RetentionPolicy) -> None:
        """Sempre rejeita — ver `update()`."""
        raise RetentionPolicyImmutableError(entity.id, operation="delete")

    def delete_by_id(self, entity_id: uuid.UUID) -> None:
        """Sempre rejeita — remover por id continua sendo remover."""
        raise RetentionPolicyImmutableError(entity_id, operation="delete_by_id")

    def soft_delete(self, entity: RetentionPolicy) -> None:
        """Sempre rejeita.

        O modelo não compõe `SoftDeleteMixin` e não tem `deleted_at`,
        então este método não existiria por herança. Existe explícito
        para que uma tentativa futura de "só esconder da listagem"
        encontre recusa em vez de `AttributeError` ambíguo.
        """
        raise RetentionPolicyImmutableError(entity.id, operation="soft_delete")

    def bulk_update(self, *args: object, **kwargs: object) -> None:
        """Sempre rejeita — mutação em massa também é mutação."""
        raise RetentionPolicyImmutableError(None, operation="bulk_update")

    def bulk_delete(self, *args: object, **kwargs: object) -> None:
        """Sempre rejeita — ver `bulk_update()`."""
        raise RetentionPolicyImmutableError(None, operation="bulk_delete")
