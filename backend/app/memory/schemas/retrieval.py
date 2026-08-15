"""
Vista admissível transitória do patrimônio cognitivo (`E4.6`).

```text
Memory(Context) = Admissible_Context(Persistent(CognitivePatrimony))
```

Definição **arquitetural**, não fórmula numérica.

Estes value objects são o resultado de uma composição transitória: nada
aqui é persistido, não há tabela por trás, e nenhuma instância ORM
atravessa a fronteira.

```text
MEMORY_RETRIEVAL_PERSISTENCE = TRANSIENT
NEW_PERSISTENT_ENTITY = NO
```

O invariante que organiza o módulo inteiro:

```text
RETRIEVAL CHANGES VIEW
RETRIEVAL DOES NOT REWRITE PATRIMONY

RETRIEVAL != MEMORY      RETRIEVAL != SEARCH
RETRIEVAL != EXISTENCE   RETRIEVAL != RANKING
NOT RETRIEVED != FORGOTTEN
DENIED != EMPTY RESULT
```

Invariantes vivem em `__post_init__`, não em docstring — quinta vez que
o projeto aplica essa lição (E4.2.1, E4.3.2, E4.4.1, E3.4.2.1, E4.5.1):

```text
frozen=True ALONE != DEEP IMMUTABILITY
```
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.memory.models.governance_enums import CognitiveOperation
from app.memory.schemas.governance import GovernanceResolution
from app.memory.schemas.memory_context import MemoryContext

DEFAULT_LIMIT = 50
MAX_LIMIT = 100
"""Contrato de paginação, **único** para schema e manager (E4.6.1).

Vive aqui, e não no manager, porque o `MemoryRetrievalResult` precisa
validar `limit <= MAX_LIMIT` no construtor direto. Duas cópias da mesma
constante divergiriam com o tempo — foi o que a E4.5.1 aprendeu ao
encontrar duas implementações da mesma verificação. O manager importa
daqui; a direção da dependência já era essa, então não há ciclo.
"""

KNOWN_ACCESSIBILITY_TOKENS: frozenset[str] = frozenset(
    {"active", "latent", "inaccessible", "causally_extinct"}
)
"""Vocabulário **completo** de `AccessibilityState`, como a E3 persiste.

Distinto do subconjunto exposto na vista: um token fora desta lista não
é um objeto a excluir em silêncio, é violação do contrato da porta.

    UNKNOWN TOKEN != OBJECT TO FILTER OUT
"""

KNOWN_REVISION_TOKENS: frozenset[str] = frozenset({"current", "superseded"})
"""Vocabulário completo de `RevisionStatus`. `None` também é válido e
significa "não participa de cadeia de revisão controlada"."""

RETRIEVABLE_ACCESSIBILITY_TOKENS: frozenset[str] = frozenset({"active", "latent"})
"""Tokens de `AccessibilityState` expostos na vista admissível normal.

Minúsculos porque `AccessibilityState` é `StrEnum` e a E3 persiste o
`.value`. Comparação por **igualdade exata**, sem normalização — mesma
disciplina congelada na E4.5.1 para `qualifier`.

`INACCESSIBLE` e `CAUSALLY_EXTINCT` ficam fora da vista, e isso não diz
nada sobre a existência deles:

    INACCESSIBLE     != NONEXISTENT
    CAUSALLY_EXTINCT != HISTORICALLY ERASED
    FILTERED OUT     != DELETED

Os objetos permanecem integralmente no banco, recuperáveis pelos
caminhos históricos e auditáveis da E3/E4.4. A E4.6 apenas não os
apresenta nesta vista.
"""


@dataclass(frozen=True)
class RetrievedMemoryItem:
    """Projeção imutável de um objeto cognitivo na vista admissível.

    Carrega apenas fatos **já existentes** no patrimônio. Nada é
    sintetizado: não há resumo, conteúdo, score, relevância ou
    proveniência inventada.

        COUT INFORMS; DOES NOT DECIDE

    Os tokens de enum viajam como `str` estável, como a E3 os persiste —
    expor o token não é importar o enum.
    """

    coid: uuid.UUID
    clid: uuid.UUID | None
    accessibility: str
    revision_status: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.coid, uuid.UUID):
            raise TypeError(f"coid deve ser uuid.UUID, recebido {type(self.coid).__name__}")
        if self.clid is not None and not isinstance(self.clid, uuid.UUID):
            raise TypeError(f"clid deve ser uuid.UUID ou None, recebido {type(self.clid).__name__}")
        if not isinstance(self.accessibility, str):
            raise TypeError(
                f"accessibility deve ser str, recebido {type(self.accessibility).__name__}"
            )
        if not self.accessibility.strip():
            raise ValueError("accessibility não pode ser vazio")
        if self.revision_status is not None:
            if not isinstance(self.revision_status, str):
                raise TypeError(
                    "revision_status deve ser str ou None, recebido "
                    f"{type(self.revision_status).__name__}"
                )
            if not self.revision_status.strip():
                raise ValueError("revision_status, quando informado, não pode ser vazio")
            if self.revision_status not in KNOWN_REVISION_TOKENS:
                raise ValueError(
                    f"revision_status {self.revision_status!r} não pertence ao vocabulário "
                    f"da E3 {sorted(KNOWN_REVISION_TOKENS)} (corretivo E4.6.1)"
                )
        if not isinstance(self.created_at, datetime):
            raise TypeError(
                f"created_at deve ser datetime, recebido {type(self.created_at).__name__}"
            )
        # O item projetado só existe para objetos que a vista admite.
        # Aceitar aqui um token não-recuperável faria o próprio value
        # object contradizer o filtro que o produziu.
        if self.accessibility not in RETRIEVABLE_ACCESSIBILITY_TOKENS:
            raise ValueError(
                f"accessibility {self.accessibility!r} não pertence à vista admissível "
                f"{sorted(RETRIEVABLE_ACCESSIBILITY_TOKENS)} — INACCESSIBLE e "
                "CAUSALLY_EXTINCT existem no patrimônio, mas não são apresentados aqui"
            )


@dataclass(frozen=True)
class MemoryRetrievalResult:
    """Vista admissível transitória, ou a recusa que a impediu.

    **Recusa não é resultado vazio.** A distinção é o ponto central deste
    value object:

        DENIED    != EMPTY RESULT
        NO RESULT != NEVER EXISTED

    Quando a governança não autoriza, `search_executed` é `False` e
    `has_more` é `None` — a Search nunca correu, então não há "mais
    nada" a afirmar. Deliberadamente **não** existe campo de contagem:
    registrar `matched_count = 0` numa recusa afirmaria que uma busca
    ocorreu e nada encontrou, vazando que o patrimônio está vazio sob
    aqueles critérios. Silêncio sobre existência é parte da recusa.

    Uma busca autorizada com `items = ()` é resultado **legítimo** e
    permanece distinguível da recusa por `search_executed is True`.

    A `GovernanceResolution` é preservada íntegra, inclusive as
    alternativas admissíveis propostas pela fronteira de segurança: a
    E4.6 não inventa, não remove e não reclassifica nenhuma delas.
    """

    context: MemoryContext
    governance_resolution: GovernanceResolution
    items: tuple[RetrievedMemoryItem, ...] = ()
    search_executed: bool = False
    limit: int = 0
    offset: int = 0
    has_more: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.context, MemoryContext):
            raise TypeError(
                f"context deve ser MemoryContext, recebido {type(self.context).__name__}"
            )
        if not isinstance(self.governance_resolution, GovernanceResolution):
            raise TypeError(
                "governance_resolution deve ser GovernanceResolution, recebido "
                f"{type(self.governance_resolution).__name__}"
            )
        object.__setattr__(self, "items", _itens(self.items))

        if not isinstance(self.search_executed, bool):
            raise TypeError(
                f"search_executed deve ser bool, recebido {type(self.search_executed).__name__}"
            )
        for campo in ("limit", "offset"):
            valor = getattr(self, campo)
            # `bool` é subclasse de `int`; aceitá-lo aqui deixaria
            # `limit=True` virar `limit=1` em silêncio.
            if not isinstance(valor, int) or isinstance(valor, bool):
                raise TypeError(f"{campo} deve ser int, recebido {type(valor).__name__}")
        if self.limit < 0:
            raise ValueError("limit não pode ser negativo")
        if self.limit > MAX_LIMIT:
            raise ValueError(f"limit não pode exceder MAX_LIMIT ({MAX_LIMIT}): {self.limit}")
        if self.offset < 0:
            raise ValueError("offset não pode ser negativo")
        # A resolução tem de ser sobre a operação que este módulo executa.
        # Uma autorização de TRANSFORM não autoriza um READ, e o estado
        # correspondente não é produzível pelo caminho canônico.
        #
        #     AUTHORIZATION TO TRANSFORM != AUTHORIZATION TO READ
        if self.governance_resolution.operation is not CognitiveOperation.READ:
            raise ValueError(
                f"a resolução é sobre {self.governance_resolution.operation}, e a E4.6 "
                "executa apenas CognitiveOperation.READ (corretivo E4.6.1)"
            )
        if len(self.items) > self.limit:
            raise ValueError(
                f"a página carrega {len(self.items)} itens para limit={self.limit} — "
                "o coletor canônico nunca ultrapassa o limite"
            )
        if self.has_more is not None and not isinstance(self.has_more, bool):
            raise TypeError(
                f"has_more deve ser bool ou None, recebido {type(self.has_more).__name__}"
            )

        autorizado = self.governance_resolution.execution_authorized
        if autorizado:
            self._validar_autorizado()
        else:
            self._validar_negado()

    def _validar_autorizado(self) -> None:
        if not self.search_executed:
            raise ValueError(
                "resolução autoriza a execução, mas search_executed é False — "
                "um resultado autorizado sem busca não descreve operação alguma"
            )
        if self.has_more is None:
            raise ValueError(
                "busca executada exige has_more booleano: `None` significa que a "
                "Search não correu"
            )
        if self.limit < 1:
            raise ValueError("busca executada exige limit >= 1")
        # Página parcial não pode afirmar que há mais: o coletor canônico
        # preenche a página antes de declarar `has_more`, então esta
        # combinação descreve uma operação que não aconteceu.
        if self.has_more and len(self.items) != self.limit:
            raise ValueError(
                f"has_more=True com página parcial ({len(self.items)} de {self.limit}) — "
                "o coletor preencheria a página antes de declarar que há mais"
            )

    def _validar_negado(self) -> None:
        if self.search_executed:
            raise ValueError(
                "resolução não autoriza a execução, mas search_executed é True — "
                "a Search não pode ter sido chamada"
            )
        if self.items:
            raise ValueError(
                "resultado negado não carrega itens: expor patrimônio sob recusa "
                "anularia a própria recusa"
            )
        if self.has_more is not None:
            raise ValueError(
                "resultado negado tem has_more=None — afirmar True ou False vazaria "
                "se existe mais patrimônio sob os critérios recusados"
            )

    # --- Consultas ------------------------------------------------------

    @property
    def execution_authorized(self) -> bool:
        """Derivado da resolução, nunca armazenado em paralelo.

        Guardar uma cópia permitiria que os dois divergissem, e a
        autoridade é sempre a resolução da E4.3.
        """
        return self.governance_resolution.execution_authorized

    @property
    def item_count(self) -> int:
        """Itens **nesta página**.

        Não é total contextual: apurá-lo exigiria varrer integralmente
        todos os candidatos, e `has_more` é suficiente nesta etapa.
        """
        return len(self.items)

    @property
    def coids(self) -> tuple[uuid.UUID, ...]:
        """COIDs da página, na ordem em que a vista os apresenta."""
        return tuple(item.coid for item in self.items)


def _itens(valor: object) -> tuple[RetrievedMemoryItem, ...]:
    """Converte a coleção de itens em tupla defensiva, validando tipos.

    `str` e `bytes` são recusados explicitamente: ambos são iteráveis, e
    aceitá-los transformaria texto numa coleção de caracteres em vez de
    um erro.
    """
    if isinstance(valor, str | bytes) or not hasattr(valor, "__iter__"):
        raise TypeError(
            f"items deve ser uma coleção de RetrievedMemoryItem, "
            f"recebido {type(valor).__name__}"
        )
    itens = tuple(valor)
    for item in itens:
        if not isinstance(item, RetrievedMemoryItem):
            raise TypeError(
                f"items aceita apenas RetrievedMemoryItem, recebido {type(item).__name__}"
            )
    coids = [item.coid for item in itens]
    if len(set(coids)) != len(coids):
        raise ValueError(
            "o mesmo COID aparece mais de uma vez na vista — objetos cognitivamente "
            "distintos nunca são colapsados, e COID repetido é defeito de composição"
        )
    return itens
