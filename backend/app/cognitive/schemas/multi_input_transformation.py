"""
`MultiInputTransformationReceipt` — recibo estrutural de uma
transformação cognitiva multi-input (`E3.4.2`).

O recibo é o **contrato público de saída** de
`MultiInputTransformationManager.derive_many()`. Ele carrega apenas
identificadores estáveis (UUIDs), nunca instâncias ORM: quem consome o
resultado não deve receber objetos mutáveis presos a uma sessão que
pode ter sido fechada, nem adquirir a capacidade de alterar patrimônio
por acidente ao segurar uma referência.

Essa forma é deliberada e olha para frente: a E4.5 consumirá este
mecanismo por **inversão de dependência**, definindo um `Protocol`
estrutural do lado dela. Um recibo feito só de UUIDs e tuplas é
estruturalmente satisfazível por esse `Protocol` sem que `app/memory`
precise importar coisa alguma de `app.cognitive` — que é exatamente a
fronteira que `G17` e `MD6` protegem. Este módulo, por sua vez, não
importa nada de `app.memory`: a dependência aponta em uma direção só.

**Invariantes são impostos em `__post_init__`, não prometidos em
docstring.** O projeto já pagou três vezes por essa lição (E4.2.1 em
`MemoryContext`, E4.3.2 em `GovernanceResolution` e `SafetyAssessment`,
E4.4.1 em `PersistenceAssessment`), sempre pelo mesmo motivo:

    frozen=True ALONE != DEEP IMMUTABILITY

`frozen=True` protege a **referência**, não o **conteúdo**. Uma lista
recebida de fora e guardada como está continua mutável pelas costas de
quem segura o recibo, e torna o objeto não-hashable. Aqui toda coleção
é convertida em tupla defensiva na construção, e o construtor direto —
que é API pública de qualquer dataclass — passa exatamente pelas mesmas
regras que o manager.
"""

import uuid
from dataclasses import dataclass


def _coid_tuple(campo: str, valor: object) -> tuple[uuid.UUID, ...]:
    """Converte uma coleção de UUIDs em tupla defensiva, validando tipos.

    `str` e `bytes` são recusados explicitamente: ambos são iteráveis,
    e aceitá-los transformaria `"abc"` numa coleção de caracteres em
    vez de um erro — o tipo de leniência que produziu o defeito
    corrigido em E4.4.1.
    """
    if isinstance(valor, str | bytes) or not hasattr(valor, "__iter__"):
        raise TypeError(
            f"{campo} deve ser uma coleção de uuid.UUID, recebido {type(valor).__name__}"
        )
    itens = tuple(valor)
    for item in itens:
        if not isinstance(item, uuid.UUID):
            raise TypeError(
                f"{campo} aceita apenas uuid.UUID, recebido {type(item).__name__}: {item!r}"
            )
    return itens


def _uuid_field(campo: str, valor: object) -> uuid.UUID:
    if not isinstance(valor, uuid.UUID):
        raise TypeError(f"{campo} deve ser uuid.UUID, recebido {type(valor).__name__}")
    return valor


@dataclass(frozen=True)
class MultiInputTransformationReceipt:
    """Recibo imutável de uma transformação multi-input já persistida.

    Todos os campos são identificadores: o recibo descreve **o que foi
    escrito**, e nada nele reabre o patrimônio para escrita.

    `target_clid` é `uuid.UUID | None`, e `None` é resultado legítimo,
    não falha: quando as fontes não compartilham uma única continuidade,
    o alvo nasce sem CLID em vez de receber um inventado
    (`MIXED HISTORIES != SINGLE CONTINUITY`).
    """

    source_coids: tuple[uuid.UUID, ...]
    target_coid: uuid.UUID
    target_clid: uuid.UUID | None
    transformation_id: uuid.UUID
    lineage_edge_ids: tuple[uuid.UUID, ...]
    causal_event_ids: tuple[uuid.UUID, ...]
    predecessor_event_ids: tuple[uuid.UUID, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_coids", _coid_tuple("source_coids", self.source_coids))
        object.__setattr__(
            self, "lineage_edge_ids", _coid_tuple("lineage_edge_ids", self.lineage_edge_ids)
        )
        object.__setattr__(
            self, "causal_event_ids", _coid_tuple("causal_event_ids", self.causal_event_ids)
        )
        object.__setattr__(
            self,
            "predecessor_event_ids",
            _coid_tuple("predecessor_event_ids", self.predecessor_event_ids),
        )
        object.__setattr__(self, "target_coid", _uuid_field("target_coid", self.target_coid))
        object.__setattr__(
            self, "transformation_id", _uuid_field("transformation_id", self.transformation_id)
        )
        if self.target_clid is not None:
            object.__setattr__(self, "target_clid", _uuid_field("target_clid", self.target_clid))

        if len(self.source_coids) < 2:
            raise ValueError(
                "uma transformação multi-input exige ao menos duas fontes — "
                "com uma única fonte a operação correta é VersionManager.derive()"
            )
        if len(set(self.source_coids)) != len(self.source_coids):
            raise ValueError(
                "fontes duplicadas não são desduplicadas silenciosamente: "
                "DUPLICATE SOURCE = INVALID INPUT"
            )
        if list(self.source_coids) != sorted(self.source_coids):
            raise ValueError(
                "source_coids deve ser apresentado em ordem canônica estrita por UUID "
                "(corretivo E3.4.2.1). O recibo NÃO reordena: `lineage_edge_ids` mantém "
                "correspondência posicional com as fontes, e reordenar apenas os COIDs "
                "separaria cada fonte de sua respectiva edge, fabricando um pareamento "
                "que nunca existiu. CANONICAL INPUT → ACCEPT; NON-CANONICAL INPUT → ERROR"
            )
        if self.target_coid in self.source_coids:
            raise ValueError(
                "o alvo de uma transformação multi-input é um CognitiveObject novo — "
                "nunca uma das próprias fontes"
            )
        if len(self.lineage_edge_ids) != len(self.source_coids):
            raise ValueError(
                f"esperada exatamente uma LineageEdge(MERGE) por fonte: "
                f"{len(self.source_coids)} fontes, {len(self.lineage_edge_ids)} edges"
            )
        if len(set(self.lineage_edge_ids)) != len(self.lineage_edge_ids):
            raise ValueError("lineage_edge_ids não pode conter repetições")
        if len(set(self.predecessor_event_ids)) != len(self.predecessor_event_ids):
            raise ValueError(
                "predecessor_event_ids não pode conter repetições — um mesmo evento "
                "declarado duas vezes duplicaria a história sem acrescentar fato"
            )
        if not self.causal_event_ids:
            raise ValueError(
                "toda transformação multi-input registra ao menos um evento causal: "
                "a ocorrência da própria operação é fato conhecido"
            )
        if len(set(self.causal_event_ids)) != len(self.causal_event_ids):
            raise ValueError("causal_event_ids não pode conter repetições")

        # Sem predecessores declarados há exatamente um evento-raiz; com
        # N predecessores há N eventos, um por predecessor. Qualquer
        # outra combinação significaria que algum evento ficou sem
        # predecessor declarado ou que um predecessor não virou evento —
        # nos dois casos o recibo mentiria sobre a história escrita.
        if not self.predecessor_event_ids:
            if len(self.causal_event_ids) != 1:
                raise ValueError(
                    "sem predecessor declarado, exatamente um evento-raiz é registrado; "
                    f"recebidos {len(self.causal_event_ids)} eventos"
                )
        elif len(self.causal_event_ids) != len(self.predecessor_event_ids):
            raise ValueError(
                f"com predecessores declarados espera-se um evento por predecessor: "
                f"{len(self.predecessor_event_ids)} predecessores, "
                f"{len(self.causal_event_ids)} eventos"
            )
