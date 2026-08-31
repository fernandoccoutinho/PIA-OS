"""
Repositório de `AccessibilityPolicy` (`E4.7`).

Espelha o contrato congelado da E4.3 para policies versionadas: publicar
é acrescentar uma versão; **nunca** atualizar a anterior. Uma sobrescrita
apagaria a policy que fundamentou decisões passadas, e elas deixariam de
ser explicáveis.

A imutabilidade vive em três camadas, e as três são necessárias:

```text
UNIQUE(policy_key, version)   o banco, autoridade final
update()/delete()             o caminho da aplicação
mapper events                 a mutação ORM que contorna o repositório
```

A terceira existe porque a E4.3.1 reproduziu exatamente esse defeito.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.memory.errors.exceptions import (
    AccessibilityPolicyImmutableError,
    AccessibilityPolicyVersionExistsError,
)
from app.memory.models.accessibility_policy import AccessibilityPolicy
from app.memory.schemas.accessibility import AccessibilityRule
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


class AccessibilityPolicyRepository(BaseRepository[AccessibilityPolicy]):
    """Publica e recupera versões de política de acessibilidade."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, AccessibilityPolicy)

    def add_policy(
        self,
        *,
        policy_key: str,
        version: int,
        governance_policy_key: str,
        rules: tuple[AccessibilityRule, ...] = (),
        effective_from: datetime | None = None,
        effective_until: datetime | None = None,
    ) -> AccessibilityPolicy:
        """Publica uma versão.

        `governance_policy_key` é obrigatório: uma policy de
        acessibilidade que não declarasse sob qual autoridade de
        governança opera teria de inventar autoridade própria, e a E4.7
        não inventa autoridade.

            GOVERNANCE DECIDES AUTHORITY
            ACCESSIBILITY POLICY APPLIES UNDER GOVERNANCE AUTHORITY

        Levanta `AccessibilityPolicyVersionExistsError` (`PIA-8035`) se a
        versão já existir — inclusive na corrida de duas sessões
        publicando a mesma versão, porque quem garante é o `UNIQUE` do
        banco, não a pré-checagem.
        """
        if not policy_key or not policy_key.strip():
            raise ValueError("policy_key não pode ser vazio ou apenas espaços")
        if not governance_policy_key or not governance_policy_key.strip():
            raise ValueError("governance_policy_key não pode ser vazio ou apenas espaços")
        if version < 1:
            raise ValueError("version deve ser >= 1")
        if (
            effective_from is not None
            and effective_until is not None
            and effective_until <= effective_from
        ):
            raise ValueError("effective_until deve ser posterior a effective_from")

        entity = AccessibilityPolicy(
            policy_key=policy_key,
            version=version,
            governance_policy_key=governance_policy_key,
            rules=AccessibilityPolicy.serialize_rules(rules),
            effective_from=effective_from,
            effective_until=effective_until,
        )
        try:
            return self.add(entity)
        except PersistenceError as exc:
            if _is_unique_violation(exc):
                raise AccessibilityPolicyVersionExistsError(policy_key, version) from exc
            raise

    def get_version(self, policy_key: str, version: int) -> AccessibilityPolicy | None:
        """Uma versão específica, ou `None`. Ausência não é exceção."""
        stmt = select(AccessibilityPolicy).where(
            AccessibilityPolicy.policy_key == policy_key,
            AccessibilityPolicy.version == version,
        )
        return self._session.execute(stmt).scalars().first()

    def effective_version_at(self, policy_key: str, moment: datetime) -> AccessibilityPolicy | None:
        """A versão vigente num instante, ou `None`.

        Vigência é `[effective_from, effective_until)` — limite final
        **exclusivo**. Com limite inclusivo, duas versões contíguas se
        sobrepõem no instante da virada e "qual valia?" passa a ter duas
        respostas.

        Havendo mais de uma vigente, devolve a de **maior versão**: a
        mais recente é a intenção mais recente. A sobreposição não é
        inventada nem corrigida aqui — policy informa, não conserta
        configuração alheia.
        """
        stmt = (
            select(AccessibilityPolicy)
            .where(
                AccessibilityPolicy.policy_key == policy_key,
                (AccessibilityPolicy.effective_from.is_(None))
                | (AccessibilityPolicy.effective_from <= moment),
                (AccessibilityPolicy.effective_until.is_(None))
                | (AccessibilityPolicy.effective_until > moment),
            )
            .order_by(AccessibilityPolicy.version.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalars().first()

    def max_version(self, policy_key: str) -> int:
        """Maior versão publicada, ou `0` se não houver nenhuma."""
        stmt = (
            select(AccessibilityPolicy.version)
            .where(AccessibilityPolicy.policy_key == policy_key)
            .order_by(AccessibilityPolicy.version.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalars().first() or 0

    def update(self, entity: AccessibilityPolicy) -> AccessibilityPolicy:
        """Sempre rejeita — versões publicadas são imutáveis.

        Fechado em duas camadas desde o início, sem repetir a dívida que
        a E4.3.1 teve de corrigir: este método e o evento de mapper no
        modelo, que pega a mutação ORM contornando o método.
        """
        raise AccessibilityPolicyImmutableError(entity.id, operation="update")

    def delete(self, entity: AccessibilityPolicy) -> None:
        """Sempre rejeita — ver `update()` acima."""
        raise AccessibilityPolicyImmutableError(entity.id, operation="delete")

    def delete_by_id(self, entity_id: uuid.UUID) -> None:
        """Sempre rejeita — ver `update()` acima."""
        raise AccessibilityPolicyImmutableError(entity_id, operation="delete")
