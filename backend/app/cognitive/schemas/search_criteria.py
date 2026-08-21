"""
`SearchCriteria` — contrato de consulta de `E3.8`/`LIB-08`.

Objeto **tipado, imutável e fechado**: aceita apenas dimensões
cognitivas que já existem no domínio congelado. Não é `dict[str, Any]`,
não é linguagem de consulta textual, não tem parser, não tem AST
booleana arbitrária e não admite "metadata filters" (proibidos por
`E3.6.2`: `COGNITIVE_DOMAIN_METADATA_PRIMITIVE = NONE`).

Composição:

```text
SIMPLE_TYPED_CONJUNCTION = YES   (todos os critérios informados são AND)
ARBITRARY_BOOLEAN_AST    = NO
```

`OR` e `NOT` não foram implementados. `OR` não tem caso de uso
demonstrado nesta fase; `NOT` transformaria a busca em varredura geral
e ampliaria a semântica muito além do que o contrato congelado
sustenta — ambos ficam `DEFERRED`.

Ausência de um critério significa **"não filtre por esta dimensão"**,
nunca um default implícito. Em particular, não filtrar por
`accessibility` devolve objetos de todos os estados, e não filtrar por
`revision_status` devolve `CURRENT` e `SUPERSEDED` juntos: nenhum
histórico é silenciosamente apagado da resposta.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, fields
from datetime import datetime

from app.cognitive.errors.exceptions import SearchCriteriaError
from app.cognitive.models.enums import AccessibilityState, RevisionStatus


@dataclass(frozen=True)
class SearchCriteria:
    """Critérios de busca — todos opcionais, combinados por `AND`.

    Pelo menos um critério é obrigatório: uma consulta sem nenhum
    critério é uma varredura completa do patrimônio disfarçada de
    busca, e o módulo se recusa a executá-la (§21 — evitar full scan
    desnecessário). Quem quiser listar tudo tem
    `ObjectRepository.list()`/`paginate()`, que já existem desde
    `E3.1` e são explícitos quanto ao que fazem.
    """

    coid: uuid.UUID | None = None
    clid: uuid.UUID | None = None
    accessibility: AccessibilityState | None = None
    revision_status: RevisionStatus | None = None
    trace_id: str | None = None
    created_from: datetime | None = None
    created_until: datetime | None = None
    include_deleted: bool = False

    #: Dimensões que contam como "filtro informado". `include_deleted`
    #: fica de fora de propósito: é modificador de escopo, não critério
    #: — sozinho, produziria a varredura completa que a validação
    #: existe para impedir.
    _FILTER_FIELDS = (
        "coid",
        "clid",
        "accessibility",
        "revision_status",
        "trace_id",
        "created_from",
        "created_until",
    )

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Rejeita critérios malformados antes de qualquer acesso ao
        banco. Consulta bem-formada com zero resultados **não** passa
        por aqui — conjunto vazio é resposta válida."""
        if not self.has_any_filter():
            raise SearchCriteriaError(
                "nenhuma dimensão informada — uma busca sem critérios seria "
                "varredura completa do patrimônio"
            )
        if self.trace_id is not None and not self.trace_id.strip():
            raise SearchCriteriaError("trace_id não pode ser vazio ou apenas espaços")
        if (
            self.created_from is not None
            and self.created_until is not None
            and self.created_from > self.created_until
        ):
            raise SearchCriteriaError("janela temporal invertida (created_from > created_until)")

    def has_any_filter(self) -> bool:
        return any(getattr(self, name) is not None for name in self._FILTER_FIELDS)

    def active_dimensions(self) -> tuple[str, ...]:
        """Dimensões efetivamente informadas — usada em documentação,
        testes e diagnóstico. Não expõe valores."""
        return tuple(
            f.name
            for f in fields(self)
            if f.name in self._FILTER_FIELDS and getattr(self, f.name) is not None
        )
