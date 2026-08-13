"""
IndexManager — primitivas determinísticas de localização
(`E3.7`/`LIB-07`).

Responde à pergunta central do módulo: *como localizar eficientemente
distinções cognitivas já persistidas sem transformar o índice numa
segunda fonte da verdade?*

A resposta implementada é deliberadamente pequena:

```text
INDEX != SOURCE OF TRUTH
INDEX  = DERIVED + REBUILDABLE
```

Não existe tabela de índice, entidade de índice, identidade de índice
nem lifecycle de índice. O que existe é (a) um conjunto de índices
nativos do PostgreSQL sobre as tabelas já persistentes, criados pela
migração `b7c41d0e92a5`, e (b) esta camada de serviço, que oferece
acesso determinístico por dimensões estruturais.

O que este módulo **não** é:

- não é Search Engine (`E3.8`): sem query language, ranking,
  relevância, similaridade semântica, embeddings, vetores, busca
  textual, fuzzy ou consulta composta;
- não é Metadata (`E3.6.2`: `COGNITIVE_DOMAIN_METADATA_PRIMITIVE = NONE`);
- não é CausalHistory (`E3.9`) nem execução cognitiva (`E7`).

Invariante que sustenta todo o módulo: nenhum método aqui escreve.
`IndexManager` lê estruturas persistidas e devolve entidades reais —
localizar nunca fabrica, altera ou apaga a distinção localizada.
"""

import uuid

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import AccessibilityState, RevisionStatus
from app.cognitive.repositories.index_repository import IndexRepository
from app.cognitive.repositories.object_repository import ObjectRepository


class IndexManager:
    """Localização estrutural determinística de objetos cognitivos.

    Recebe `ObjectRepository` (identidade — reaproveitado, nunca
    reimplementado) e `IndexRepository` (demais dimensões). A escolha
    de compor os dois em vez de duplicar `get_by_id` segue a regra do
    projeto de não reimplementar lógica existente.
    """

    def __init__(
        self,
        object_repository: ObjectRepository,
        index_repository: IndexRepository,
    ) -> None:
        self._objects = object_repository
        self._index = index_repository

    def by_coid(self, coid: uuid.UUID, *, include_deleted: bool = False) -> CognitiveObject | None:
        """Localiza por identidade do objeto. Servido pela chave
        primária — nenhum índice novo foi criado para isto.

        `None` significa "não localizado por esta consulta", nunca
        "não existe": com `include_deleted=True` o mesmo COID pode ser
        recuperado após soft delete (E3.7 §7 —
        `INDEX MISS != COGNITIVE ERASURE`).
        """
        return self._objects.get_by_id(coid, include_deleted=include_deleted)

    def by_clid(self, clid: uuid.UUID, *, include_deleted: bool = False) -> list[CognitiveObject]:
        """Todos os objetos de uma linha de continuidade, em ordem
        determinística — histórico completo, não apenas o `CURRENT`."""
        return self._index.objects_by_clid(clid, include_deleted=include_deleted)

    def by_accessibility(
        self,
        state: AccessibilityState,
        *,
        limit: int | None = None,
        include_deleted: bool = False,
    ) -> list[CognitiveObject]:
        """Localiza por estado de acessibilidade. Todos os quatro
        estados permanecem localizáveis — mudar `AccessibilityState`
        nunca destrói patrimônio."""
        return self._index.objects_by_accessibility(
            state, limit=limit, include_deleted=include_deleted
        )

    def by_revision_status(
        self,
        status: RevisionStatus,
        *,
        limit: int | None = None,
        include_deleted: bool = False,
    ) -> list[CognitiveObject]:
        """Localiza por `revision_status`. `SUPERSEDED` continua
        estruturalmente localizável; preferir `CURRENT` é decisão de
        camadas superiores, não do índice."""
        return self._index.objects_by_revision_status(
            status, limit=limit, include_deleted=include_deleted
        )

    def by_trace_id(self, trace_id: str, *, include_deleted: bool = False) -> list[CognitiveObject]:
        """Localiza objetos associados a um `trace_id` através de
        `ProvenanceRecord`.

        `trace_id` vazio ou só com espaços é erro de chamada, não uma
        consulta legítima que casualmente não encontra nada — daí
        `ValueError` (stdlib) em vez de um código `PIA-8xxx` novo:
        nenhuma condição de domínio nova é introduzida por este
        módulo.
        """
        if not trace_id.strip():
            raise ValueError("trace_id não pode ser vazio ou apenas espaços.")
        return self._index.objects_by_trace_id(trace_id, include_deleted=include_deleted)
