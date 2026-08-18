"""
Testes de Multi-IA-readiness estrutural — §19, §33 do módulo E3.1.

Nenhum agente real é instanciado; nenhum SDK de IA é necessário. O
objetivo é provar, estruturalmente, que `CognitiveObject`/
`ObjectRepository` não pressupõem um único agente, um único provider,
uma única resposta por tarefa, ou last-write-wins para resultados
concorrentes — sem implementar nenhuma lógica de orquestração
(isso é E7).
"""

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.repositories.object_repository import ObjectRepository


def test_two_agent_outputs_for_the_same_task_coexist_as_distinct_objects(cognitive_session):
    """Simula (via fixture simples, sem SDK real) o cenário COMPETITIVE:
    Agent A produz X, Agent B produz X — ambos devem poder existir como
    dois CognitiveObjects distintos, sem sobrescrita automática."""
    repo = ObjectRepository(cognitive_session)

    agent_a_output = repo.add(CognitiveObject())
    agent_b_output = repo.add(CognitiveObject())
    cognitive_session.commit()

    assert agent_a_output.id != agent_b_output.id
    assert repo.get_by_id(agent_a_output.id) is not None
    assert repo.get_by_id(agent_b_output.id) is not None
    assert len(repo.list()) == 2


def test_creating_a_new_object_never_overwrites_an_existing_one(cognitive_session):
    """Nenhum caminho de `ObjectRepository.add` aceita um `entity_id`
    para "sobrescrever" — cada `add()` sempre resulta em uma nova
    linha com PK própria (gerada pelo banco/`UUIDMixin`), nunca em um
    update implícito de um objeto existente. Isso é o que impede
    last-write-wins estrutural entre saídas concorrentes de agentes
    diferentes (invariante multi-IA do EDR)."""
    repo = ObjectRepository(cognitive_session)

    first = repo.add(CognitiveObject())
    cognitive_session.commit()
    second = repo.add(CognitiveObject())
    cognitive_session.commit()

    assert first.id != second.id
    assert repo.get_by_id(first.id) is not None  # o primeiro não foi sobrescrito


def test_cognitive_object_has_no_single_agent_or_provider_column():
    """Nenhuma coluna de `CognitiveObject` pressupõe um único
    agente/provider/modelo — essa informação, quando existir, vive em
    `ProvenanceRecord` (E3.6), que suporta N agentes por design (ver
    `E3_DOMAIN_MODEL_DRAFT.md`, campos Multi-IA de `ProvenanceRecord`)."""
    column_names = {c.name for c in CognitiveObject.__table__.columns}
    assert column_names.isdisjoint({"provider_id", "model_id", "agent_id", "agent_role"})


def test_cognitive_object_has_no_single_response_per_task_constraint():
    """Não existe nenhuma unique constraint que limitaria
    `CognitiveObject` a uma única linha "por tarefa" — a única unicidade
    é a PK (`id`), que é sempre nova por construção."""
    constraint_columns = {
        tuple(col.name for col in constraint.columns)
        for constraint in CognitiveObject.__table__.constraints
    }
    # A única constraint de coluna(s) deve ser a PK (`id`) — nenhuma
    # unique constraint adicional que amarraria objetos a uma "tarefa".
    assert constraint_columns == {("id",)}
