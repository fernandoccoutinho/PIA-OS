"""
`MemoryDomainMembershipRepository` — associação domínio ↔ COID (E4.1).

O ponto delicado deste módulo vive aqui: `memory_domain_memberships`
tem **duas** chaves estrangeiras, e uma violação `23503` isolada não
diz qual delas falhou. A E3.3 enfrentou o mesmo problema em
`LineageEdge` (parent/child) e documentou a limitação honestamente,
reportando um dos dois por melhor esforço.

Aqui a ambiguidade é **eliminável**, porque as duas FKs não são
simétricas: uma aponta para a tabela deste próprio módulo. Ordem de
checagem (E4.1 §5.2):

1. o domínio existe? — consulta à tabela própria, sem tocar
   `app.cognitive` → `MemoryDomainNotFoundError` (`PIA-8023`);
2. tenta escrever;
3. `23505` → duplicata (`PIA-8024`);
4. `23503` restante → só pode ser o `coid` (`PIA-8025`).

A pré-checagem é para **diagnóstico**, nunca para correção: a FK do
banco continua sendo a autoridade final. Se o domínio for removido
entre os passos 1 e 2, o resultado é uma `23503` corretamente
classificada — não um dado inconsistente. A mesma disciplina de defesa
em profundidade de E3.3/E3.5: o domínio dá a mensagem boa, o banco dá
a garantia.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.memory.errors.exceptions import (
    MemoryDomainMembershipDuplicateError,
    MemoryDomainMembershipObjectNotFoundError,
    MemoryDomainNotFoundError,
)
from app.memory.models.memory_domain_membership import MemoryDomainMembership
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository
from app.repositories.base_repository import BaseRepository
from app.repositories.exceptions import PersistenceError

_POSTGRES_UNIQUE_VIOLATION_SQLSTATE = "23505"
_POSTGRES_FOREIGN_KEY_VIOLATION_SQLSTATE = "23503"
_SQLITE_UNIQUE_ERRORNAME = "SQLITE_CONSTRAINT_UNIQUE"
_SQLITE_FOREIGN_KEY_ERRORNAME = "SQLITE_CONSTRAINT_FOREIGNKEY"


def _classify_membership_integrity_violation(exc: PersistenceError) -> str | None:
    """Classifica a violação por **sinal estruturado do driver**.

    Nunca por parsing de mensagem — a lição de E3.2.1: classificar por
    texto é classificar por eliminação, e erra em silêncio quando a
    mensagem muda. Causa desconhecida devolve `None` e a exceção
    original é relançada sem reinterpretação.
    """
    orig = getattr(exc, "__cause__", None)
    orig = getattr(orig, "orig", None) or orig
    sqlstate = getattr(orig, "sqlstate", None)
    if sqlstate == _POSTGRES_UNIQUE_VIOLATION_SQLSTATE:
        return "unique"
    if sqlstate == _POSTGRES_FOREIGN_KEY_VIOLATION_SQLSTATE:
        return "foreign_key"
    errorname = getattr(orig, "sqlite_errorname", None)
    if errorname == _SQLITE_UNIQUE_ERRORNAME:
        return "unique"
    if errorname == _SQLITE_FOREIGN_KEY_ERRORNAME:
        return "foreign_key"
    return None


class MemoryDomainMembershipRepository(BaseRepository[MemoryDomainMembership]):
    """Persistência e consulta do pertencimento domínio ↔ COID."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, MemoryDomainMembership)
        self._domains = MemoryDomainRepository(session)

    def add_membership(self, *, domain_id: uuid.UUID, coid: uuid.UUID) -> MemoryDomainMembership:
        """Classifica um COID em um domínio.

        Não altera absolutamente nada no `CognitiveObject`: não toca
        identidade, CLID, `accessibility`, `revision_status`,
        proveniência, linhagem ou história causal. Também não cria
        `ProvenanceRecord` nem `CausalHistoryEvent` — classificação
        administrativa não é evento de origem cognitiva nem
        causalidade (E4.1 §17/§18).
        """
        if not self._domains.exists_domain(domain_id):
            raise MemoryDomainNotFoundError(domain_id)

        entity = MemoryDomainMembership(domain_id=domain_id, coid=coid)
        try:
            return self.add(entity)
        except PersistenceError as exc:
            violation = _classify_membership_integrity_violation(exc)
            if violation == "unique":
                raise MemoryDomainMembershipDuplicateError(domain_id, coid) from exc
            if violation == "foreign_key":
                # O domínio foi confirmado logo acima; se a FK ainda
                # falha, ou o `coid` não existe, ou o domínio sumiu na
                # janela entre a checagem e a escrita. Em ambos os
                # casos o candidato ausente que o chamador precisa
                # investigar é o COID — e nenhum objeto é fabricado
                # para acomodar a classificação.
                raise MemoryDomainMembershipObjectNotFoundError(coid) from exc
            raise

    def contains(self, *, domain_id: uuid.UUID, coid: uuid.UUID) -> bool:
        """O COID já pertence a este domínio?"""
        stmt = (
            select(MemoryDomainMembership.id)
            .where(
                MemoryDomainMembership.domain_id == domain_id,
                MemoryDomainMembership.coid == coid,
            )
            .limit(1)
        )
        return self._session.execute(stmt).first() is not None

    def list_memberships_of_domain(self, domain_id: uuid.UUID) -> list[MemoryDomainMembership]:
        """Memberships do domínio, em ordem determinística canônica.

        Devolve as **associações**, não objetos cognitivos: hidratar
        `CognitiveObject` aqui exigiria importar `app.cognitive` e
        quebraria a fronteira estrutural (E4.1 §2.1). Quem precisa dos
        objetos usa os COIDs contra a E3 — que continua sendo a única
        fonte da verdade sobre eles.
        """
        stmt = (
            select(MemoryDomainMembership)
            .where(MemoryDomainMembership.domain_id == domain_id)
            .order_by(MemoryDomainMembership.created_at.asc(), MemoryDomainMembership.id.asc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def list_memberships_of_object(self, coid: uuid.UUID) -> list[MemoryDomainMembership]:
        """Memberships do COID, em ordem determinística canônica.

        Lista vazia é resultado **válido**, não erro: um objeto fora de
        todo domínio existe plenamente
        (`ZERO DOMAIN MEMBERSHIP != NONEXISTENCE`).
        """
        stmt = (
            select(MemoryDomainMembership)
            .where(MemoryDomainMembership.coid == coid)
            .order_by(MemoryDomainMembership.created_at.asc(), MemoryDomainMembership.id.asc())
        )
        return list(self._session.execute(stmt).scalars().all())
