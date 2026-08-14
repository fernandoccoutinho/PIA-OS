"""
`PersistenceManager` — evidências de continuidade registradas (E4.4).

```
PersistenceManager.assess(coid) -> PersistenceAssessment
```

Composição **estritamente read-only** sobre as primitivas da E3.
Nenhuma entidade nova, nenhuma migração, nenhuma segunda fonte da
verdade.

```
DATABASE_WRITES_DURING_ASSESSMENT = 0
```

O que este serviço **não** faz — e a lista importa tanto quanto o que
ele faz:

- não cria CLID, objeto, linhagem, transformação, proveniência ou
  história causal;
- não altera `RevisionStatus` nem `AccessibilityState`;
- não cria nem retira `MemoryDomainMembership`;
- não executa governança, `Search`, `Retrieval` ou consolidação;
- não persiste o próprio assessment;
- não commita nem controla transação;
- não calcula score, rank, importância, confiança ou prioridade.

```
LOP = PERSISTENCE PRINCIPLE, NOT A METRIC
COUT INFORMS; DOES NOT DECIDE
```

**Ler nunca cria evidência ausente.**

## Independência de contexto

```
CONTEXT CHANGES VIEW
CONTEXT DOES NOT CHANGE PERSISTENCE
```

`assess()` recebe **apenas um COID**. Não recebe `MemoryContext`, nem
policy, nem domínio, nem ator — e essa é a garantia mais forte
possível: não é que o resultado ignore o contexto, é que o contexto
**não tem por onde entrar**.

```
GOVERNANCE MAY RESTRICT ACCESS
GOVERNANCE MUST NOT REWRITE EXISTENCE
GOVERNANCE MUST NOT REWRITE PERSISTENCE
```

## Fronteira com E4.5

```
E4_4 != CONSOLIDATION
```

E4.5 consumirá `PersistenceAssessment` para reconhecer evidências.
Nenhuma abstração de escrita foi criada aqui "para preparar" a
consolidação: abstração sem consumidor real é especulação, e a E4.1 já
registrou essa lição.
"""

import uuid

from app.memory.repositories.continuity_evidence_repository import (
    ContinuityEvidenceRepository,
)
from app.memory.schemas.persistence import (
    PersistenceAssessment,
    PersistenceEvidence,
    PersistenceEvidenceKind,
    PersistenceOutcome,
)


class PersistenceManager:
    """Reúne e apresenta evidências de continuidade já registradas."""

    def __init__(self, evidence_repository: ContinuityEvidenceRepository) -> None:
        self._evidence = evidence_repository

    def assess(self, coid: uuid.UUID) -> PersistenceAssessment:
        """Avalia o que está registrado sobre a continuidade de um COID.

        Três resultados possíveis, e nenhum colapsa nos outros:

        ```
        SUBJECT_NOT_FOUND                 o objeto não existe
        NO_RECORDED_CONTINUITY_EVIDENCE   existe, nada registrado
        RECORDED_CONTINUITY_EVIDENCE      existe, com evidência
        ```

        ```
        MISSING EVIDENCE != EVIDENCE OF NON-PERSISTENCE
        MISSING EVIDENCE != AUTHORIZATION TO FABRICATE HISTORY
        OBJECT EXISTS    != CONTINUITY IS RECORDED
        ```

        Ausência de evidência é reportada como ausência — nunca
        preenchida por inferência, nunca convertida em prova de que
        não houve continuidade.

        Múltiplos ramos permanecem múltiplos: nada aqui escolhe uma
        trajetória como "a verdadeira"
        (`EQUIVALENCE != DESTRUCTIVE COLLAPSE`,
        `DIVERGENCE != INVALIDITY`).

        Estritamente read-only.
        """
        if not isinstance(coid, uuid.UUID):
            raise TypeError(f"coid deve ser uuid.UUID, recebido {type(coid).__name__}")

        instantaneo = self._evidence.subject_snapshot(coid)
        if instantaneo is None:
            return PersistenceAssessment(coid=coid, outcome=PersistenceOutcome.SUBJECT_NOT_FOUND)

        clid, revision_status = instantaneo
        evidencias: list[PersistenceEvidence] = []

        if clid is not None:
            evidencias.append(
                PersistenceEvidence(kind=PersistenceEvidenceKind.CLID, reference=str(clid))
            )

        for aresta_id, parent_coid, relation_type in self._evidence.lineage_as_child(coid):
            evidencias.append(
                PersistenceEvidence(
                    kind=PersistenceEvidenceKind.LINEAGE_PARENT,
                    reference=str(aresta_id),
                    related_coid=parent_coid,
                    qualifier=_as_stable_value(relation_type),
                )
            )
        for aresta_id, child_coid, relation_type in self._evidence.lineage_as_parent(coid):
            evidencias.append(
                PersistenceEvidence(
                    kind=PersistenceEvidenceKind.LINEAGE_CHILD,
                    reference=str(aresta_id),
                    related_coid=child_coid,
                    qualifier=_as_stable_value(relation_type),
                )
            )

        como_entrada, como_saida = self._evidence.transformations_citing(coid)
        for registro_id in como_entrada:
            evidencias.append(
                PersistenceEvidence(
                    kind=PersistenceEvidenceKind.TRANSFORMATION_INPUT,
                    reference=str(registro_id),
                )
            )
        for registro_id in como_saida:
            evidencias.append(
                PersistenceEvidence(
                    kind=PersistenceEvidenceKind.TRANSFORMATION_OUTPUT,
                    reference=str(registro_id),
                )
            )

        for evento_id, event_type in self._evidence.causal_events(coid):
            evidencias.append(
                PersistenceEvidence(
                    kind=PersistenceEvidenceKind.CAUSAL_EVENT,
                    reference=str(evento_id),
                    qualifier=_as_stable_value(event_type),
                )
            )

        outcome = (
            PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE
            if evidencias
            else PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE
        )
        return PersistenceAssessment(
            coid=coid,
            outcome=outcome,
            evidence=tuple(evidencias),
            clid=clid,
            revision_status=_as_stable_value(revision_status),
        )


def _as_stable_value(value: object) -> str | None:
    """Converte um valor lido do banco no seu texto estável.

    A E3 persiste seus enums pelo `.value` (`native_enum=False` com
    `values_callable`), então o que vem do banco já é a string
    estável. A conversão existe para o caso de o driver devolver um
    membro de enum, sem que este módulo precise **importar** aquele
    enum — o que quebraria a fronteira estabelecida na E4.1.
    """
    if value is None:
        return None
    bruto = getattr(value, "value", value)
    return bruto if isinstance(bruto, str) else str(bruto)
