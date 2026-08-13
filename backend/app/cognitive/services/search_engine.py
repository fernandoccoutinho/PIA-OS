"""
`SearchEngine` — composição de consultas sobre o patrimônio cognitivo
(`E3.8`/`LIB-08`).

```text
COGNITIVE PATRIMONY → INDEX → SEARCH → RESULT SET
```

e nunca o contrário. Os invariantes que este módulo existe para
sustentar:

```text
SEARCH != SOURCE OF TRUTH
SEARCH_IS_READ_ONLY = TRUE
SEARCH MISS   != NON-EXISTENCE
SEARCH RANK   != TRUTH VALUE
SEARCH RESULT != NEW COGNITIVE FACT
```

Buscar é operação de **acesso**. Não cria, não modifica, não valida,
não invalida e não apaga distinção alguma — e, em particular, o
patrimônio persistido é bit a bit o mesmo antes e depois de qualquer
consulta (`P_after == P_before`).

O que este módulo **não** é: não é graph engine (`MULTI_HOP_GRAPH_SEARCH
= DEFERRED`), não faz busca textual, vetorial, semântica ou por
embeddings (não há payload no `CognitiveObject` para isso), não ranqueia
por relevância, não persiste consultas nem resultados, e não reintroduz
metadata.

Fronteira com `E3.7`: o Index Manager oferece caminhos de acesso por
uma dimensão; o Search Engine compõe dimensões numa consulta só. Nada
aqui reimplementa `IndexManager` — quem precisa de uma dimensão
isolada continua usando o Index Manager.
"""

from app.cognitive.errors.exceptions import SearchCriteriaError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.repositories.search_repository import SearchRepository
from app.cognitive.schemas.search_criteria import SearchCriteria


class SearchEngine:
    """Consulta composta, determinística e somente-leitura."""

    def __init__(self, search_repository: SearchRepository) -> None:
        self._search = search_repository

    def search(
        self,
        criteria: SearchCriteria,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[CognitiveObject]:
        """Objetos que satisfazem **todos** os critérios informados,
        em ordem determinística (`created_at ASC, id ASC`).

        Lista vazia significa exatamente *"nenhum objeto satisfaz os
        critérios desta consulta sob o escopo aplicado"* — nunca *"o
        objeto nunca existiu"*. Não gera tombstone, não altera
        `AccessibilityState`, não registra extinção e não infere
        causalidade.

        `limit`/`offset` são paginação por deslocamento, estável
        porque a ordenação é total. Ordenação **não é ranking**:
        nenhum score, peso ou relevância existe aqui.
        """
        self._validate_pagination(limit=limit, offset=offset)
        return self._search.search(criteria, limit=limit, offset=offset)

    def count(self, criteria: SearchCriteria) -> int:
        """Total de objetos que satisfazem os critérios, ignorando
        paginação. Zero é resposta válida, não erro."""
        return self._search.count(criteria)

    @staticmethod
    def _validate_pagination(*, limit: int | None, offset: int | None) -> None:
        if limit is not None and limit < 0:
            raise SearchCriteriaError("limit não pode ser negativo")
        if offset is not None and offset < 0:
            raise SearchCriteriaError("offset não pode ser negativo")
