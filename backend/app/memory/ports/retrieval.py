"""
Porta estrutural para a Search cognitiva da E3.8 (`E4.6`).

## Por que existe

`app/memory` nunca importa `app.cognitive` — fronteira verificada por
`G17` (E3.12) e `MD6` (E4.1). A E4.6 precisa consultar o patrimônio, mas
não pode conhecer `SearchCriteria` nem `CognitiveObject` nominalmente.

Precedente arquitetural: as portas da E4.5
(`app/memory/ports/consolidation.py`). A diferença é que aqui a porta é
**genérica**: a E4.5 conhecia a forma completa do recibo, enquanto a
E4.6 não deve conhecer a forma dos critérios de busca.

## Critérios são opacos

`CriteriaT_contra` é um parâmetro de tipo **contravariante**: a E4.6
transporta o objeto de critérios do chamador até a Search sem nunca
inspecioná-lo. O vocabulário de critérios continua pertencendo à E3.8, e
recriá-lo aqui produziria um segundo `SearchCriteria` que divergiria do
primeiro — exatamente o tipo de duplicação que a arquitetura recusa.

    SEARCH CRITERIA OWNERSHIP = E3.8

## Resultado é estrutural, não nominal

`CognitiveObjectView` declara apenas os fatos que a vista admissível
precisa ler. Ele é satisfeito pelo `CognitiveObject` real sem que este
saiba da sua existência.

`accessibility` e `revision_status` são tipados como `str` porque
`AccessibilityState` e `RevisionStatus` são `StrEnum` na E3 — uma
subclasse de `str`. A satisfação é covariante e **tipada**: nenhum
`Any`, nenhum `getattr`, nenhuma reflexão, nenhum import de enum.

    TOKEN != ENUM IMPORT

O custo declarado é o mesmo já assumido pela E4.4 ao ler a E3 por
descritores de tabela: acoplamento por **forma**, não por tipo nominal.
Se a E3 renomear um campo ou trocar o tipo base de um enum, isto quebra
aqui — e é o mypy, não o runtime, que deve apontar.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, TypeVar, runtime_checkable

CriteriaT_contra = TypeVar("CriteriaT_contra", contravariant=True)
"""Critérios de busca da E3.8, tratados como **opacos** pela E4.6.

Contravariante porque a porta apenas os **consome**: um port que aceite
critérios mais gerais é utilizável onde se espera um que aceite critérios
mais específicos.
"""


@runtime_checkable
class CognitiveObjectView(Protocol):
    """Forma mínima de um objeto cognitivo, para composição da vista.

    Somente-leitura por construção: todos os membros são propriedades, e
    a E4.6 não tem nada que escrever num objeto do patrimônio.

        RETRIEVAL CHANGES VIEW
        RETRIEVAL DOES NOT REWRITE PATRIMONY

    `runtime_checkable` habilita `isinstance` — que para protocolos de
    dados verifica a **presença** dos membros, não seus tipos. Serve para
    um teste afirmar que o objeto real satisfaz a porta em vez de
    presumi-lo; a checagem de tipos fica com o mypy, onde é decidível.
    """

    @property
    def id(self) -> uuid.UUID:
        """COID — identidade do objeto cognitivo."""

    @property
    def clid(self) -> uuid.UUID | None:
        """Continuidade conceitual. `None` é estado legítimo, não falha."""

    @property
    def accessibility(self) -> str:
        """Token de `AccessibilityState`, exatamente como a E3 o expõe."""

    @property
    def revision_status(self) -> str | None:
        """Token de `RevisionStatus`, ou `None` para objetos que não
        participam de cadeia de revisão controlada."""

    @property
    def created_at(self) -> datetime:
        """Instante de criação — participa da ordenação canônica da E3,
        que é **ordem**, não ranking."""

    @property
    def deleted_at(self) -> datetime | None:
        """Marca de exclusão lógica. `SOFT_DELETED != NEVER EXISTED`."""


@runtime_checkable
class CognitiveSearchPort(Protocol[CriteriaT_contra]):
    """Forma da Search oficial da E3.8 consumida pela E4.6.

    Reproduz `SearchEngine.search` exatamente, inclusive `limit`/`offset`,
    porque a E4.6 pagina em **lotes determinísticos** sobre a Search e
    aplica os filtros contextuais depois. Estreitar a assinatura aqui
    faria a porta mentir sobre o que o objeto real aceita.

    A Search continua sendo da E3: esta porta não a substitui, não a
    reimplementa e não amplia seu vocabulário.

        RETRIEVAL != SEARCH
        SEARCH MISS != NON-EXISTENCE
    """

    def search(
        self,
        criteria: CriteriaT_contra,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Sequence[CognitiveObjectView]:
        """Objetos que satisfazem os critérios, em ordem determinística."""
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado


@runtime_checkable
class RetrievalCandidateGatePort(Protocol):
    """Filtro **estritamente redutor** por chamada, aplicado pela E4.6.3.

    ## O que ele pode fazer, e só

    Excluir, daquela resposta, um candidato que a E4.6 já admitiu. Nada
    além disso:

        GATE REDUCES A RESPONSE
        GATE DOES NOT ADD, REORDER, TRANSFORM OR REVEAL

    Um gate que devolvesse objetos acrescentaria patrimônio à vista; um
    que devolvesse índices reordenaria; um que recebesse a página inteira
    poderia reescrevê-la. Por isso a assinatura é a mais estreita
    possível: **um candidato, um booleano**. A forma do contrato é a
    garantia — não uma promessa na docstring.

    ## O que ele não é

    ```text
    CANDIDATE GATE != GOVERNANCE
    CANDIDATE GATE != DOMAIN SCOPE
    CANDIDATE GATE != RETENTION POLICY
    CANDIDATE GATE != FORGETTING
    CANDIDATE GATE != DELETION
    ```

    Este protocolo é **neutro**: não conhece retenção, expiração,
    esquecimento nem apagamento. A E4.6 continua sendo recuperação base,
    e não passa a ser *retention-aware* por existir este ponto:

        COMPOSITION POINT != RETENTION DECISION

    Autoridade é anterior e independente. O gate só é consultado depois
    de a Governança autorizar `READ`, de o escopo base admitir o
    candidato e de a duplicata ter sido descartada. Ele nunca vê o que a
    autoridade recusou, e recusar no gate não é recusar por autoridade.

    ## `False` é transitório

    ```text
    NOT RETURNED IN THIS RESPONSE != FORGOTTEN
    NOT RETURNED IN THIS RESPONSE != INACCESSIBLE
    NOT RETURNED IN THIS RESPONSE != DELETED
    NOT RETURNED IN THIS RESPONSE != NONEXISTENT
    ```

    Um `False` não escreve nada: não muda `deleted_at`, acessibilidade,
    revisão, memberships, história ou o próprio candidato. Na chamada
    seguinte, sem gate, o mesmo objeto reaparece.

    ## Fail-closed

    O retorno deve ser `bool` **exato**. `0`, `1`, `None`, string vazia e
    objetos truthy/falsy são violação de contrato, não resposta — coagir
    com `bool(...)` faria um colaborador defeituoso decidir sobre a vista
    sem que ninguém percebesse.

        INVALID GATE RESULT != EXCLUSION
        INVALID GATE RESULT != INCLUSION
        COLLABORATOR FAILURE != EMPTY VIEW
    """

    def allows(self, candidate: CognitiveObjectView) -> bool:
        """`True` mantém o candidato nesta resposta; `False` o exclui dela."""
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado
