"""
Evidência e avaliação de persistência — value objects (E4.4).

```
PERSISTENCE = CONTINUITY OF A DISTINCTION
              ACROSS STATES, TRANSFORMATIONS OR TIME
```

Estes objetos **apresentam fatos já registrados**. Não os pontuam, não
os ordenam por mérito e não concluem que algo deve sobreviver.

```
LOP = PERSISTENCE PRINCIPLE, NOT A METRIC
```

Invariantes desde o primeiro commit, em `__post_init__`. O projeto já
pagou três vezes (E4.2.1, E4.3.1, E4.3.2) por declarar imutabilidade
em docstring sem impô-la em código: `frozen=True` protege a
referência, não o conteúdo.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class PersistenceEvidenceKind(StrEnum):
    """Tipos de evidência de continuidade — vocabulário **fechado**.

    Correspondem exatamente às quatro fontes canônicas congeladas pela
    E4.0 (`CLID`, `LINEAGE`, `TRANSFORMATION`, `CAUSAL HISTORY`), com
    as direções preservadas. Ampliar exige EDR.

    Direção não é detalhe: `LINEAGE_PARENT` e `LINEAGE_CHILD` são
    fatos diferentes sobre o mesmo objeto, e colapsá-los seria perder
    o que torna uma linhagem uma linhagem. O mesmo vale para
    entrada/saída de transformação.
    """

    CLID = "clid"
    """Continuidade lógica atribuída ao objeto."""

    LINEAGE_PARENT = "lineage_parent"
    """Aresta de linhagem em que o sujeito é **filho** — de onde veio."""

    LINEAGE_CHILD = "lineage_child"
    """Aresta de linhagem em que o sujeito é **pai** — o que dele derivou."""

    TRANSFORMATION_INPUT = "transformation_input"
    """Transformação que cita o sujeito como **entrada**."""

    TRANSFORMATION_OUTPUT = "transformation_output"
    """Transformação que cita o sujeito como **saída**."""

    CAUSAL_EVENT = "causal_event"
    """Evento registrado na história causal do sujeito."""


class PersistenceOutcome(StrEnum):
    """Resultado de uma avaliação — **três** estados, nunca dois.

    ```
    MISSING EVIDENCE != EVIDENCE OF NON-PERSISTENCE
    MISSING EVIDENCE != AUTHORIZATION TO FABRICATE HISTORY
    OBJECT EXISTS    != CONTINUITY IS RECORDED
    ```

    "Não existe objeto" e "existe objeto sem continuidade registrada"
    pedem providências opostas: a primeira sugere erro de referência; a
    segunda é fato legítimo sobre um objeto recém-criado. Fundi-las num
    `False` apagaria a diferença.
    """

    SUBJECT_NOT_FOUND = "subject_not_found"
    NO_RECORDED_CONTINUITY_EVIDENCE = "no_recorded_continuity_evidence"
    RECORDED_CONTINUITY_EVIDENCE = "recorded_continuity_evidence"


def _canonical_uuid_text(name: str, value: object) -> str:
    """Exige um UUID em forma **canônica**, como texto.

    Corretivo `E4.4.1`. Antes, `reference` era qualquer `str` não
    vazia, e `"nao-e-uuid"` entrava como identificador de evidência.

    O campo continua `str` — e não `uuid.UUID` — de propósito:
    `reference` é um **token estável** do contrato público, e tipá-lo
    comprometeria toda categoria futura de evidência a referenciar
    UUIDs. A validação canônica dá hoje exatamente a mesma garantia
    que a tipagem daria, sem fazer essa promessa.

    Canônica significa `str(uuid.UUID(v)) == v`: variantes em
    maiúsculas, com chaves ou em URN são recusadas — senão o mesmo
    fato produziria duas referências textuais diferentes e a
    desduplicação deixaria de funcionar.
    """
    if not isinstance(value, str):
        raise TypeError(f"{name} deve ser str, recebido {type(value).__name__}")
    try:
        canonico = str(uuid.UUID(value))
    except ValueError as exc:
        raise ValueError(f"{name} deve ser um UUID canônico, recebido {value!r}") from exc
    if canonico != value:
        raise ValueError(
            f"{name} deve estar na forma canônica do UUID ({canonico!r}), recebido {value!r}"
        )
    return canonico


def _validated_uuid(name: str, value: object) -> uuid.UUID:
    if not isinstance(value, uuid.UUID):
        raise TypeError(f"{name} deve ser uuid.UUID, recebido {type(value).__name__}")
    return value


def _optional_uuid(name: str, value: object) -> uuid.UUID | None:
    if value is None:
        return None
    return _validated_uuid(name, value)


def _required_text(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} deve ser str, recebido {type(value).__name__}")
    if not value.strip():
        raise ValueError(f"{name} não pode ser vazio ou apenas espaços")
    return value


def _optional_text(name: str, value: object) -> str | None:
    if value is None:
        return None
    return _required_text(name, value)


def _validated_member(name: str, value: object, enum_cls: type) -> object:
    """Exige o membro do enum, nunca a string equivalente.

    `StrEnum` compara igual à sua string, então aceitar `"clid"`
    passaria despercebido em quase todo teste de comportamento e só
    quebraria num `is` — lição registrada em E4.3.2.
    """
    if not isinstance(value, enum_cls):
        raise TypeError(f"{name} deve ser um {enum_cls.__name__}, recebido {type(value).__name__}")
    return value


_KINDS_WITH_RELATED_COID: frozenset[PersistenceEvidenceKind] = frozenset(
    {PersistenceEvidenceKind.LINEAGE_PARENT, PersistenceEvidenceKind.LINEAGE_CHILD}
)
"""Só arestas de linhagem relacionam o sujeito a outro objeto."""

_KINDS_WITH_QUALIFIER: frozenset[PersistenceEvidenceKind] = frozenset(
    {
        PersistenceEvidenceKind.LINEAGE_PARENT,
        PersistenceEvidenceKind.LINEAGE_CHILD,
        PersistenceEvidenceKind.CAUSAL_EVENT,
    }
)
"""Linhagem tem tipo de relação; evento causal tem tipo de evento.

CLID e transformação não têm o que qualificar: o primeiro é propriedade
do sujeito, e a direção da segunda já está no `kind`."""


@dataclass(frozen=True)
class PersistenceEvidence:
    """Um fato de continuidade, referenciado — nunca o objeto ORM.

    O contrato público carrega **identificadores e valores estáveis**.
    Uma instância ORM aqui seria mutável, ligada a uma sessão e
    inválida fora dela; a referência é o que sobrevive ao fim da
    transação e ao fim do processo.
    """

    kind: PersistenceEvidenceKind
    reference: str
    """Identificador estável do fato — o `id` do registro que o
    materializa, em texto. Para `CLID`, o próprio CLID."""

    related_coid: uuid.UUID | None = None
    """O outro extremo da relação, quando existe: o pai, o filho.
    `None` quando a evidência não relaciona dois objetos."""

    qualifier: str | None = None
    """Valor estável que qualifica o fato — `relation_type` da aresta,
    `event_type` do evento.

    Guarda o **valor persistido** (`"branch"`, `"created"`), não o
    membro do enum da E3: importar aquele enum quebraria a fronteira
    de import que a E4.1 estabeleceu, e o valor é o que é estável no
    banco de qualquer modo.
    """

    def __post_init__(self) -> None:
        """Impõe tipos **e coerência dependente de `kind`**.

        Corretivo `E4.4.1`. Antes, `frozen=True` mais validação de tipo
        deixavam passar formatos semanticamente impossíveis: aresta de
        linhagem sem o outro extremo, CLID com `related_coid`, evento
        causal sem tipo de evento. Cada um descreve um fato que não
        pode existir no patrimônio.
        """
        object.__setattr__(
            self, "kind", _validated_member("kind", self.kind, PersistenceEvidenceKind)
        )
        object.__setattr__(self, "reference", _canonical_uuid_text("reference", self.reference))
        object.__setattr__(self, "related_coid", _optional_uuid("related_coid", self.related_coid))
        object.__setattr__(self, "qualifier", _optional_text("qualifier", self.qualifier))
        self._validate_shape()

    def _validate_shape(self) -> None:
        """Cada `kind` tem uma forma, e só uma.

        - **linhagem** relaciona dois objetos por um tipo de relação:
          sem `related_coid` não há aresta; sem `qualifier` não se sabe
          que relação é;
        - **CLID** é propriedade do próprio sujeito: não há outro
          extremo nem relação a qualificar;
        - **transformação** é citada pelo seu registro; o outro extremo
          não é um objeto único, e a direção já está no `kind`;
        - **evento causal** pertence ao sujeito e sempre tem tipo.
        """
        exige_relacionado = self.kind in _KINDS_WITH_RELATED_COID
        exige_qualificador = self.kind in _KINDS_WITH_QUALIFIER

        if exige_relacionado and self.related_coid is None:
            raise ValueError(f"{self.kind.value} exige related_coid — sem ele não há aresta")
        if not exige_relacionado and self.related_coid is not None:
            raise ValueError(
                f"{self.kind.value} não relaciona dois objetos — related_coid não se aplica"
            )
        if exige_qualificador and self.qualifier is None:
            raise ValueError(
                f"{self.kind.value} exige qualifier — sem ele o fato não é identificável"
            )
        if not exige_qualificador and self.qualifier is not None:
            raise ValueError(f"{self.kind.value} não admite qualifier")

    def sort_key(self) -> tuple[str, str, str, str]:
        """Chave canônica **total** — determinismo da apresentação.

        Corretivo `E4.4.1`: a chave anterior era
        `(kind, reference, qualifier)` e ignorava `related_coid`. Duas
        arestas de linhagem do mesmo registro para objetos diferentes
        colidiam, e `sorted` — sendo estável — preservava a ordem de
        entrada. Duas permutações da mesma coleção produziam
        assessments **diferentes**, contradizendo a canonicalização
        que o módulo alegava.

        A chave agora cobre todos os campos que participam da
        igualdade. É essa cobertura total que a torna canonicalização
        de fato.
        """
        return (
            self.kind.value,
            self.reference,
            str(self.related_coid) if self.related_coid is not None else "",
            self.qualifier or "",
        )


@dataclass(frozen=True)
class PersistenceAssessment:
    """O que está registrado sobre a continuidade de um COID.

    Transitório e não persistido, como `IntegrityFinding` (E3.10),
    `SyncReport` (E3.11) e `GovernanceResolution` (E4.3.1): é resultado
    de uma leitura, sempre derivável de novo a partir do patrimônio.
    Persisti-lo criaria uma segunda fonte da verdade sobre continuidade.
    """

    coid: uuid.UUID
    outcome: PersistenceOutcome
    evidence: tuple[PersistenceEvidence, ...] = ()
    clid: uuid.UUID | None = None
    subject_deleted: bool = False
    """O sujeito está com exclusão lógica — **descritor, não evidência**.

    Corretivo `E4.4.1`. Soft delete é um fato sobre o **estado
    presente** do sujeito, não sobre a continuidade que ele atravessou:

    ```
    SOFT_DELETED != NEVER EXISTED
    SOFT_DELETED != SUBJECT_NOT_FOUND
    SOFT_DELETED != HISTORICAL ERASURE
    ```

    Por isso aparece aqui e **não** em `evidence` — pelo mesmo critério
    que mantém `revision_status` fora dela: descrever o estado presente
    não é atestar travessia. Um objeto soft-deleted continua sendo
    avaliado, e todas as suas evidências continuam visíveis.
    """

    revision_status: str | None = None
    """Estado de revisão, quando registrado — **descrição da
    trajetória**, não evidência.

    Ele descreve o estado presente do objeto; evidência é o que atesta
    travessia. Manter a distinção é o ponto: `revision_status` aparece
    no resultado sem entrar em `evidence`, e nenhuma contagem o inclui.
    """

    def __post_init__(self) -> None:
        """Invariantes em toda construção pública.

        Canonicaliza evidências (ordena e desduplica) e recusa
        combinações que não descrevem nenhum estado real.
        """
        object.__setattr__(self, "coid", _validated_uuid("coid", self.coid))
        object.__setattr__(
            self, "outcome", _validated_member("outcome", self.outcome, PersistenceOutcome)
        )
        object.__setattr__(self, "clid", _optional_uuid("clid", self.clid))
        object.__setattr__(
            self, "revision_status", _optional_text("revision_status", self.revision_status)
        )
        if not isinstance(self.subject_deleted, bool):
            raise TypeError(
                f"subject_deleted deve ser bool, recebido {type(self.subject_deleted).__name__}"
            )
        object.__setattr__(self, "evidence", _canonical_evidence(self.evidence))
        self._validate_coherence()
        self._validate_clid_coherence()

    def _validate_clid_coherence(self) -> None:
        """`clid` e a evidência `CLID` são o mesmo fato, dito duas vezes.

        Corretivo `E4.4.1`. O contrato da E4.4 classifica CLID como
        evidência canônica de continuidade, e mesmo assim o construtor
        aceitava um `clid` declarado sem evidência correspondente — um
        assessment que afirmava continuidade no descritor e a negava na
        lista de fatos.

        Congelado:

        ```
        clid is not None  ⇔  existe exatamente uma evidência CLID
                             cujo reference é esse mesmo UUID
        ```

        Uma evidência é sempre um fato **exibido**; um descritor que a
        contradiz não descreve nada.
        """
        evidencias_clid = [
            item for item in self.evidence if item.kind is PersistenceEvidenceKind.CLID
        ]
        if len(evidencias_clid) > 1:
            raise ValueError(
                "mais de uma evidência CLID — um objeto tem no máximo uma continuidade lógica"
            )
        if self.clid is None:
            if evidencias_clid:
                raise ValueError(
                    "evidência CLID presente com clid=None — o descritor nega o fato exibido"
                )
            return
        if not evidencias_clid:
            raise ValueError(
                "clid declarado sem evidência CLID — CLID é evidência canônica de "
                "continuidade, e afirmá-lo sem exibi-lo é afirmação sem fato"
            )
        if evidencias_clid[0].reference != str(self.clid):
            raise ValueError(
                f"clid declarado ({self.clid}) diverge da evidência CLID "
                f"({evidencias_clid[0].reference}) — são o mesmo fato e não podem diferir"
            )

    def _validate_coherence(self) -> None:
        """Recusa estados que se contradizem.

        - **`SUBJECT_NOT_FOUND` não carrega nada.** Se o sujeito não
          foi encontrado, qualquer evidência, CLID ou estado de revisão
          atribuído a ele seria fabricado — e fabricar história ausente
          é precisamente o que este módulo existe para não fazer.
        - **`NO_RECORDED_CONTINUITY_EVIDENCE` não carrega evidência.**
          O nome afirma ausência; carregá-la seria mentir no rótulo.
        - **`RECORDED_CONTINUITY_EVIDENCE` exige ao menos uma.** Sem
          isso o resultado afirma registro que não exibe.
        """
        if self.outcome is PersistenceOutcome.SUBJECT_NOT_FOUND:
            if self.subject_deleted:
                raise ValueError(
                    "SUBJECT_NOT_FOUND não pode estar soft-deleted — não há linha para "
                    "estar apagada; SOFT_DELETED != NEVER EXISTED"
                )
            if self.evidence or self.clid is not None or self.revision_status is not None:
                raise ValueError(
                    "SUBJECT_NOT_FOUND não pode carregar evidência, clid ou "
                    "revision_status — atribuir fato a sujeito inexistente é fabricar história"
                )
            return
        if self.outcome is PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE and self.evidence:
            raise ValueError(
                "NO_RECORDED_CONTINUITY_EVIDENCE não pode carregar evidência — "
                "o resultado afirma ausência e exibiria presença"
            )
        if self.outcome is PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE and not self.evidence:
            raise ValueError(
                "RECORDED_CONTINUITY_EVIDENCE exige ao menos uma evidência — "
                "afirmar registro sem exibi-lo não é evidência"
            )

    @property
    def has_recorded_continuity(self) -> bool:
        """Somente `RECORDED_CONTINUITY_EVIDENCE`.

        Derivada, nunca armazenada. E deliberadamente **não** é um
        score nem um limiar: responde se há evidência registrada, não
        quanta nem se é boa. `SUBJECT_NOT_FOUND` e ausência de
        evidência devolvem `False` pelo mesmo motivo — nenhum dos dois
        é continuidade registrada — mas continuam distinguíveis por
        `outcome`, que é o que preserva a diferença.
        """
        return self.outcome is PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE

    def evidence_of(self, kind: PersistenceEvidenceKind) -> tuple[PersistenceEvidence, ...]:
        """Evidências de um tipo, na ordem canônica.

        Filtro de apresentação, não julgamento: nenhum tipo vale mais
        que outro, e este método não os hierarquiza.
        """
        _validated_member("kind", kind, PersistenceEvidenceKind)
        return tuple(item for item in self.evidence if item.kind is kind)


def _canonical_evidence(value: object) -> tuple[PersistenceEvidence, ...]:
    """Ordena e desduplica evidências numa tupla imutável.

    Desduplicar é seguro porque `PersistenceEvidence` é um value
    object: duas evidências iguais em todos os campos referenciam o
    mesmo fato, e exibi-lo duas vezes sugeriria dois fatos.
    """
    if value is None:
        raise TypeError("evidence deve ser um iterável de PersistenceEvidence, recebido None")
    if isinstance(value, str | bytes) or not isinstance(value, Iterable):
        raise TypeError(
            f"evidence deve ser um iterável de PersistenceEvidence, "
            f"recebido {type(value).__name__}"
        )
    itens = tuple(value)
    if any(not isinstance(item, PersistenceEvidence) for item in itens):
        raise TypeError("evidence aceita apenas PersistenceEvidence")
    unicos = tuple(dict.fromkeys(itens))
    return tuple(sorted(unicos, key=lambda e: e.sort_key()))
