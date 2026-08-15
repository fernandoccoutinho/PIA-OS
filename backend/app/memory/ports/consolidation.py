"""
Porta estrutural para o writer multi-input da E3 (`E4.5`).

## Por que uma porta

`app/memory` **nunca** importa `app.cognitive` — fronteira estrutural
estabelecida pela E4.1 e verificada por dois testes independentes
(`G17` da E3.12 e `MD6` da E4.1). A E4.5 precisa que o patrimônio seja
escrito, mas não pode escrevê-lo:

    COGNITIVE PATRIMONY WRITER = app/cognitive

O corretivo E3.4.2 foi criado exatamente para fechar essa lacuna do
lado certo. Aqui declaramos apenas a **forma** do que a E4.5 consome;
quem satisfaz essa forma é o `MultiInputTransformationManager` real,
injetado pelo compositor. Nenhum adapter, nenhuma reimplementação,
nenhum import cruzado.

## Por que `@property` e não atributos

Declarar os membros do recibo como propriedades de leitura torna o
protocolo **somente-leitura**. Um `Protocol` com atributos mutáveis
exigiria que o implementador também os tivesse mutáveis, o que um
dataclass `frozen` não oferece — e a E4.5 não tem nada que escrever
num recibo. A forma read-only é a que descreve honestamente o uso.

## O que a porta não é

Ela não é um ponto de extensão para trocar o mecanismo de escrita, nem
um lugar onde regras de patrimônio possam ser redefinidas. A regra de
CLID, o `TransformationKind`, a linhagem `MERGE` e a causalidade
pertencem à E3 e continuam lá. A porta só permite que a E4.5 os invoque
sem atravessar a fronteira.
"""

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class MultiInputTransformationReceiptPort(Protocol):
    """Forma do recibo devolvido pelo writer multi-input da E3.

    Espelha `MultiInputTransformationReceipt` (E3.4.2) sem importá-lo.
    Só identificadores: nenhuma instância ORM atravessa a fronteira, o
    que é o que permite ao lado da memória consumir o resultado sem
    adquirir a capacidade de alterar patrimônio.

    `runtime_checkable` habilita `isinstance` para verificação de
    forma — que checa a **presença** dos membros, não seus tipos. É
    suficiente para os testes de composição afirmarem que o objeto real
    satisfaz a porta; a checagem de tipos fica com o mypy, onde ela é
    de fato decidível.
    """

    @property
    def source_coids(self) -> tuple[uuid.UUID, ...]:
        """Fontes, em ordem canônica estrita por UUID."""

    @property
    def target_coid(self) -> uuid.UUID:
        """COID novo do alvo consolidado."""

    @property
    def target_clid(self) -> uuid.UUID | None:
        """CLID do alvo, ou `None` quando as fontes não compartilham
        uma única continuidade. `None` é resultado legítimo."""

    @property
    def transformation_id(self) -> uuid.UUID:
        """Id do único `TransformationRecord` da operação."""

    @property
    def lineage_edge_ids(self) -> tuple[uuid.UUID, ...]:
        """Uma edge por fonte, em **correspondência posicional** com
        `source_coids`."""

    @property
    def causal_event_ids(self) -> tuple[uuid.UUID, ...]:
        """Eventos causais gravados no alvo."""

    @property
    def predecessor_event_ids(self) -> tuple[uuid.UUID, ...]:
        """Predecessores declarados pelo chamador. Vazio significa
        evento-raiz, não ausência de operação."""


@runtime_checkable
class MultiInputTransformationPort(Protocol):
    """Forma do writer multi-input da E3 consumido pela E4.5.

    `runtime_checkable` verifica a presença de `derive_many`, não a
    assinatura — a conformidade de tipos é decidida pelo mypy, onde ela
    é de fato decidível. É o bastante para um teste afirmar que o
    objeto real satisfaz a porta em vez de presumi-lo.

    A assinatura reproduz `MultiInputTransformationManager.derive_many`
    (E3.4.2) exatamente, inclusive `operation_type` — que a E4.5 fixa em
    `"consolidate"` mas a porta mantém como parâmetro, porque a porta
    descreve o mecanismo da E3, não a política da E4.5. Estreitar aqui
    faria a porta mentir sobre o que o objeto real aceita.
    """

    def derive_many(
        self,
        *,
        source_coids: Iterable[uuid.UUID],
        operation_type: str,
        declared_losses: Iterable[str],
        declared_preservations: Iterable[str] = (),
        actor_ref: uuid.UUID | None = None,
        policy_ref: str | None = None,
        predecessor_event_ids: Iterable[uuid.UUID] = (),
        occurred_at: datetime | None = None,
    ) -> MultiInputTransformationReceiptPort:
        """Grava o patrimônio da consolidação e devolve o recibo."""
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado
