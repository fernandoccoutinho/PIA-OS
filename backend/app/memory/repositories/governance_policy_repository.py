"""
`GovernancePolicyRepository` — persistência de policies versionadas (E4.3).

Duas garantias que precisam vir do banco, não do código:

- **não sobrescrever versão publicada** — `UNIQUE(policy_key, version)`;
- **não duplicar versão sob concorrência** — a mesma constraint, que é
  a única coisa que continua valendo quando duas sessões escrevem no
  mesmo instante.

O repositório traduz a violação para exceção de domínio; a autoridade
final é a constraint. Mesma disciplina de defesa em profundidade de
E3.3/E3.4/E3.5 e da E4.1.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.memory.errors.exceptions import (
    GovernancePolicyImmutableError,
    GovernancePolicyVersionExistsError,
)
from app.memory.models.governance_policy import GovernancePolicy
from app.memory.schemas.governance import GovernanceRule
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


class GovernancePolicyRepository(BaseRepository[GovernancePolicy]):
    """Persistência e consulta de `GovernancePolicy`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, GovernancePolicy)

    def add_policy(
        self,
        *,
        policy_key: str,
        version: int,
        rules: tuple[GovernanceRule, ...] = (),
        effective_from: datetime | None = None,
        effective_until: datetime | None = None,
    ) -> GovernancePolicy:
        """Publica uma versão de policy.

        Levanta `GovernancePolicyVersionExistsError` (`PIA-8027`) se a
        versão já existir — nunca atualiza a linha existente. Uma
        sobrescrita silenciosa apagaria a policy que fundamentou
        decisões passadas, e elas deixariam de ser explicáveis.
        """
        if not policy_key or not policy_key.strip():
            raise ValueError("policy_key não pode ser vazio ou apenas espaços")
        if version < 1:
            raise ValueError("version deve ser >= 1")
        if (
            effective_from is not None
            and effective_until is not None
            and effective_until <= effective_from
        ):
            raise ValueError("effective_until deve ser posterior a effective_from")

        entity = GovernancePolicy(
            policy_key=policy_key,
            version=version,
            rules=GovernancePolicy.serialize_rules(rules),
            effective_from=effective_from,
            effective_until=effective_until,
        )
        try:
            return self.add(entity)
        except PersistenceError as exc:
            if _is_unique_violation(exc):
                raise GovernancePolicyVersionExistsError(policy_key, version) from exc
            raise

    def get_version(self, policy_key: str, version: int) -> GovernancePolicy | None:
        """Uma versão específica, ou `None`. Ausência não é exceção."""
        stmt = select(GovernancePolicy).where(
            GovernancePolicy.policy_key == policy_key,
            GovernancePolicy.version == version,
        )
        return self._session.execute(stmt).scalars().one_or_none()

    def list_versions(self, policy_key: str) -> list[GovernancePolicy]:
        """Todas as versões, em ordem crescente de `version`."""
        stmt = (
            select(GovernancePolicy)
            .where(GovernancePolicy.policy_key == policy_key)
            .order_by(GovernancePolicy.version.asc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def max_version(self, policy_key: str) -> int:
        """Maior versão existente, ou `0` se não houver nenhuma.

        Serve para *sugerir* a próxima versão. Não é reserva: entre
        esta leitura e a escrita, outra sessão pode publicar a mesma —
        e aí a constraint recusa, corretamente. A checagem é
        conveniência; a garantia é do banco.
        """
        stmt = select(func.max(GovernancePolicy.version)).where(
            GovernancePolicy.policy_key == policy_key
        )
        return self._session.execute(stmt).scalar() or 0

    def effective_version_at(self, policy_key: str, moment: datetime) -> GovernancePolicy | None:
        """A versão vigente num instante, ou `None`.

        Vigência é `[effective_from, effective_until)` — limite final
        **exclusivo**. Com limite inclusivo, duas versões contíguas se
        sobrepõem exatamente no instante da virada e a pergunta "qual
        valia?" passa a ter duas respostas.

        Havendo mais de uma vigente (janelas sobrepostas declaradas por
        quem administra), devolve a de **maior versão**: a mais recente
        é a intenção mais recente. A sobreposição não é inventada nem
        corrigida aqui — governança informa, não conserta configuração
        alheia.
        """
        stmt = (
            select(GovernancePolicy)
            .where(
                GovernancePolicy.policy_key == policy_key,
                (GovernancePolicy.effective_from.is_(None))
                | (GovernancePolicy.effective_from <= moment),
                (GovernancePolicy.effective_until.is_(None))
                | (GovernancePolicy.effective_until > moment),
            )
            .order_by(GovernancePolicy.version.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalars().first()

    def update(self, entity: GovernancePolicy) -> GovernancePolicy:
        """Sempre rejeita — versões publicadas são imutáveis (E4.3.1).

        A E4.3 herdava `update()` de `BaseRepository` e afirmava
        imutabilidade só na documentação. Mesma dívida que a E3.3.1
        fechou em `LineageEdge`; aqui ela é fechada em duas camadas —
        este método e o evento de mapper no modelo, que pega a mutação
        ORM que contorna o método.
        """
        raise GovernancePolicyImmutableError(entity.id, operation="update")

    def delete(self, entity: GovernancePolicy) -> None:
        """Sempre rejeita — ver `update()` acima."""
        raise GovernancePolicyImmutableError(entity.id, operation="delete")
