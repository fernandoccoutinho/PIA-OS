"""
ProvenanceManager — LIB-06, registro e consulta de proveniência de
contribuições cognitivas.

Responsabilidade única: registrar e consultar `ProvenanceRecord`s —
não controla commit, não conhece SDK de provider, não infere
proveniência automaticamente, não decide qualidade/confiança/
relevância (§4, §7, §11 do módulo E3.6).

**Provenance != Transcript** (§4): nunca armazena conteúdo integral de
prompt/resposta — apenas os fatos de proveniência (quem, quando,
via qual execução). **Provenance != Relationship** (§16): não cria
`Relationship` automaticamente para representar proveniência.
"""

import uuid

from app.cognitive.models.enums import ProvenanceActorType, ProvenanceSourceType
from app.cognitive.models.provenance_record import ProvenanceRecord
from app.cognitive.repositories.provenance_repository import ProvenanceRepository


class ProvenanceManager:
    """Registra e consulta `ProvenanceRecord`s.

    Depende apenas de `ProvenanceRepository` — não conhece
    `ObjectRepository` diretamente (validação de existência do `coid`
    é FK no banco, traduzida pelo repositório se necessário — mesma
    economia já aplicada a `LineageRepository.add_edge`/
    `RelationshipRepository.add_relationship`, que também operam só
    por COID).
    """

    def __init__(self, provenance_repository: ProvenanceRepository) -> None:
        self._provenance = provenance_repository

    def record(
        self,
        *,
        coid: uuid.UUID,
        source_type: ProvenanceSourceType,
        actor_type: ProvenanceActorType,
        source_ref: str | None = None,
        actor_id: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
        evidence_refs: list[str] | None = None,
        orchestration_run_id: str | None = None,
        agent_role: str | None = None,
        agent_instance_id: str | None = None,
        agent_sequence: int | None = None,
        parent_agent_output_ref: str | None = None,
    ) -> ProvenanceRecord:
        """Registra uma nova proveniência para `coid`.

        `provider_id`/`model_id` nunca são obrigatórios — mesmo quando
        `actor_type == ProvenanceActorType.AGENT` — nenhuma validação
        condicional foi implementada que os exija (§ obrigatória do
        módulo E3.0/E3.6). Todos os campos Multi-IA Triple-Mode
        (`orchestration_run_id`, `agent_role`, `agent_instance_id`,
        `agent_sequence`, `parent_agent_output_ref`) são opcionais —
        `ProvenanceManager` nunca os popula por lógica própria, apenas
        os aceita se o chamador os fornecer (§3, §11 do módulo E3.6).

        Não commita — `flush()` implícito via `ProvenanceRepository.add()`;
        commit permanece do chamador via `UnitOfWork`.
        """
        record = ProvenanceRecord(
            coid=coid,
            source_type=source_type,
            actor_type=actor_type,
            source_ref=source_ref,
            actor_id=actor_id,
            provider_id=provider_id,
            model_id=model_id,
            session_id=session_id,
            correlation_id=correlation_id,
            evidence_refs=list(evidence_refs or []),
            orchestration_run_id=orchestration_run_id,
            agent_role=agent_role,
            agent_instance_id=agent_instance_id,
            agent_sequence=agent_sequence,
            parent_agent_output_ref=parent_agent_output_ref,
        )
        return self._provenance.add(record)

    def list_for(self, coid: uuid.UUID) -> list[ProvenanceRecord]:
        """Todas as proveniências registradas para `coid`, ordenadas
        deterministicamente."""
        return self._provenance.list_by_coid(coid)
