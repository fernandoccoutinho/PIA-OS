"""
ProvenanceRecord — proveniência de uma contribuição cognitiva
(`E3.6` / `LIB-06`).

Contrato: `E3_DOMAIN_MODEL_DRAFT.md`, seção "2. ProvenanceRecord".
Representa a proveniência de uma contribuição — nunca o conteúdo
integral da conversa/execução que a produziu (§4 do módulo E3.6:
"PROVENANCE != TRANSCRIPT"). Nenhum campo aqui armazena payload de
prompt/resposta; referências a artefatos usam identificadores estáveis
(COID, `provider_id`/`model_id` como rótulos, não credenciais/SDKs).

**Concretizações desta implementação** (documentadas, não invenções —
mesmo padrão de E3.3/E3.4/E3.5 para referências a entidades ainda não
implementadas):

- `coid: UUID` (novo, não está no Draft) — o Draft só define
  `ProvenanceRecord` como referenciado *por* `CognitiveDistinction`
  (`origin`/`provenance`, `CognitiveDistinction` está `DEFERRED` desde
  E3.1) — sem essa entidade intermediária, `ProvenanceRecord` precisa
  de uma âncora direta para ser utilizável nesta fase. `coid` é essa
  âncora — FK direta para `cognitive_objects.id`, mesmo padrão de
  `LineageEdge`/`Relationship`.
- `source_type`/`actor_type` implementados como enums fechados
  (`ProvenanceSourceType`/`ProvenanceActorType`) — o próprio Draft
  delega isso a E3.6: "enum fechado em E3.6, aberto aqui [no Draft]".
- O prompt do módulo E3.6 usa a terminologia `execution_id`/
  `parent_execution_id`; o Draft congelado não tem esses nomes — tem
  `agent_instance_id` (distingue instâncias/execuções) e
  `parent_agent_output_ref` (referência solta, `str?`, não FK
  estruturada, para a execução/output anterior numa cadeia
  `SEQUENTIAL`). Resolvido priorizando o Draft (autoritativo,
  conforme o próprio módulo E3.6 instrui) — nenhum campo duplicado
  foi criado. `provenance_id` (=`id`) já identifica univocamente
  "esta contribuição/execução", cumprindo o papel que `execution_id`
  descreveria.

Multi-IA Triple-Mode: todos os campos preparatórios
(`orchestration_run_id`, `agent_role`, `agent_instance_id`,
`agent_sequence`, `parent_agent_output_ref`) são opcionais — nenhum
provider/modo de orquestração é obrigatório (§11, §23 do módulo E3.6).

Append-only: `ProvenanceRepository.update()`/`.delete()` sempre
rejeitam — mesma disciplina de `LineageEdge`/`TransformationRecord`/
`Relationship`.
"""

import uuid

from sqlalchemy import JSON, ForeignKey, Index, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.cognitive.models.enums import ProvenanceActorType, ProvenanceSourceType
from app.models.base_model import BaseModel


class ProvenanceRecord(BaseModel):
    """Registro append-only da proveniência de uma contribuição
    cognitiva associada a um `CognitiveObject` (`coid`).

    Múltiplos `ProvenanceRecord`s podem existir para o mesmo `coid` —
    deliberadamente sem `UniqueConstraint` sobre `coid` isolado (§18
    do módulo E3.6: "duas IAs podem gerar dois ProvenanceRecords
    distintos para o mesmo CognitiveObject? SIM"). Múltiplas
    proveniências nunca se sobrescrevem — cada uma é uma linha própria.
    """

    __tablename__ = "provenance_records"

    __table_args__ = (
        # --- E3.7 / LIB-07 (Index Manager) — índice estrutural ---
        # `trace_id` é altamente seletivo e nullable: índice parcial,
        # que só cobre as linhas onde o identificador foi de fato
        # populado. Puramente derivado — localizar por `trace_id` não
        # transforma `trace_id` em identidade cognitiva nem em
        # entidade (E3.7 §11). Declarado aqui, e não só na migração,
        # para manter `Base.metadata` sincronizado com o banco.
        Index(
            "ix_provenance_records_trace_id",
            "trace_id",
            postgresql_where=text("trace_id IS NOT NULL"),
            sqlite_where=text("trace_id IS NOT NULL"),
        ),
    )

    coid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cognitive_objects.id"), nullable=False, index=True
    )
    """`CognitiveObject` ao qual esta proveniência se refere. FK sem
    `ON DELETE CASCADE` — mesma política de `LineageEdge`/`Relationship`
    (soft delete de `CognitiveObject` nunca remove a linha física)."""

    source_type: Mapped[ProvenanceSourceType] = mapped_column(
        SAEnum(
            ProvenanceSourceType,
            name="provenance_source_type",
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    """Ver `app.cognitive.models.enums.ProvenanceSourceType`."""

    source_ref: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    """Referência opaca à origem — nunca conteúdo bruto embutido."""

    actor_type: Mapped[ProvenanceActorType] = mapped_column(
        SAEnum(
            ProvenanceActorType,
            name="provenance_actor_type",
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    """Ver `app.cognitive.models.enums.ProvenanceActorType` — nunca
    assume `AGENT` por padrão."""

    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    """Identificador do ator — cumpre o papel que o módulo E3.6 chama
    de `agent_id` quando `actor_type == AGENT`, mas também serve
    `HUMAN`/`SYSTEM` (nome genérico do Draft, não específico de IA)."""

    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    """OPCIONAL — nunca obrigatório, mesmo quando `actor_type ==
    AGENT` (§ obrigatória do módulo E3.0/E3.6: nenhuma validação
    condicional que torne isso obrigatório foi implementada)."""

    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    """OPCIONAL — idem `provider_id`."""

    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    """Populável a partir de `app.logging.context.LoggingContext`
    quando disponível — `ProvenanceRepository`/`ProvenanceManager` não
    exigem essa integração, apenas aceitam o valor se fornecido."""

    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    """Correlação entre operações relacionadas — não é o mesmo
    identificador que `trace_id` (ver docstring de `trace_id` abaixo
    para a distinção semântica; correção E3.6.1)."""

    trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    """Cadeia distribuída/operacional rastreável entre componentes
    (correção E3.6.1, débito C1). Comprimento consistente com
    `session_id`/`correlation_id` (`String(255)`), nullable, nunca
    obrigatório, provider-neutral — nenhum SDK/mecanismo de tracing
    específico é assumido ou exigido.

    Distinto de `session_id` (contexto conversacional/sessão lógica) e
    `correlation_id` (correlação entre operações relacionadas) — os
    três podem coincidir para um dado chamador, mas não são impostos
    como iguais entre si; cada um responde a uma pergunta diferente."""

    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    """Lista de referências (nunca conteúdo bruto) — default vazio."""

    orchestration_run_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    """Identifica uma execução de orquestração Multi-IA
    (COMPETITIVE/COMPLEMENTARY/SEQUENTIAL) — opcional, nunca populado
    por lógica própria de E3.6 (campo preparatório para `E7`)."""

    agent_role: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    """Ex.: "generator" | "critic" | "verifier" | "synthesizer" —
    vocabulário de `E7`, não fechado aqui."""

    agent_instance_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    """Distingue instâncias do mesmo agente/role numa mesma
    orquestração — cumpre o papel que o módulo E3.6 chama de
    `execution_id`."""

    agent_sequence: Mapped[int | None] = mapped_column(nullable=True, default=None)
    """Posição do agente numa cadeia `SEQUENTIAL` — irrelevante em
    `COMPETITIVE`/`COMPLEMENTARY`."""

    parent_agent_output_ref: Mapped[str | None] = mapped_column(
        String(512), nullable=True, default=None
    )
    """Referência solta (não FK estruturada — mesmo tipo `str?` do
    Draft) ao output anterior numa cadeia `SEQUENTIAL` — cumpre o
    papel que o módulo E3.6 chama de `parent_execution_id`."""

    @property
    def provenance_id(self) -> uuid.UUID:
        """Alias de leitura de `id` — mesmo padrão de
        `CognitiveObject.coid`/`TransformationRecord.transformation_id`."""
        return self.id
