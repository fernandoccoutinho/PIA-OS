"""
`MemoryContext` — perspectiva operacional sobre o patrimônio (E4.2).

Contexto é a circunstância sob a qual o patrimônio será, mais tarde,
governado (E4.3), tornado acessível (E4.7) e recuperado (E4.6). Ele
**descreve de onde se olha**; nunca altera o que existe.

```
CONTEXT CHANGES VIEW
CONTEXT DOES NOT REWRITE PATRIMONY
```

Congelado, e cada linha protege um modo de falha real:

```
CONTEXT != IDENTITY          perspectiva não identifica nada
CONTEXT != MEMORY            memória é função de contexto sobre patrimônio,
                             não o contexto em si
CONTEXT != POLICY            contexto diz de onde se olha; policy diz o que
                             é permitido ver — fundi-los produziria um objeto
                             que é pergunta e resposta ao mesmo tempo
CONTEXT != SESSION           uma sessão participa de um contexto; não o define
CONTEXT != DOMAIN            declarar domínios não é pertencer a eles
CONTEXT != COGNITIVE OBJECT  não tem COID, CLID, linhagem nem história
```

**Não é persistido.** A classificação `TRANSIENT` está congelada na
matriz F de `E4_SYNC_BOUNDARY.md`, e o teste arquitetural forte da
E4.0 já havia demonstrado que separar vista de patrimônio não exige
tabela alguma.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class MemoryContext:
    """Perspectiva imutável. Todos os campos são opcionais.

    Imutável por decisão, não por conveniência: se a perspectiva muda,
    ela é **outra** perspectiva (`C1 → C2`), nunca "mutar C1 em
    silêncio". É isso que torna reprodutível qualquer decisão que
    venha a ser tomada sob um contexto, e auditável a diferença entre
    duas decisões.

    `frozen=True` também entrega igualdade e hash **estruturais** —
    exatamente a comparação que o módulo precisa, sem inventar um
    identificador persistente para algo que é, por contrato, uma
    circunstância.

    Construa por `build()`, não pelo construtor: é `build()` que
    canonicaliza `domain_ids`.
    """

    domain_ids: tuple[uuid.UUID, ...] = ()
    """Domínios que o contexto **declara**.

    Apenas declara. Nenhuma união ou interseção de patrimônio é
    executada aqui (§29 do prompt canônico) — como usar o conjunto é
    decisão de Governance (E4.3) e Retrieval (E4.6). Inventar a
    semântica agora seria decidir admissibilidade sem autoridade.

    Declarar um domínio **não** cria membership:

        domain in context != object added to domain

    Conjunto vazio é válido: ausência de contextualização não implica
    ausência de patrimônio.
    """

    session_id: str | None = None
    """Sessão em que a operação ocorre — descritivo, opcional.

    `session_id != context identity`. O mesmo contexto semântico pode
    existir em sessões diferentes, e a mesma sessão pode produzir
    vários contextos. A E3 já registra `session_id` em
    `provenance_records`, o que confirma o desenho: sessão é uma
    dimensão entre outras, não a moldura.
    """

    actor_ref: str | None = None
    """Quem opera — **entrada descritiva**, não ator autorizado.

    ```
    ACTOR PRESENCE != AUTHORIZATION
    ```

    Este módulo não decide permissões e não expõe nenhuma API de
    `allow`/`deny`. Governança é E4.3, e a presença de um ator aqui é
    informação para ela, nunca uma conclusão sobre ela.
    """

    purpose: str | None = None
    """Para quê — descritivo, opcional.

    String livre por ser o mínimo defensável: qualquer vocabulário
    fechado agora seria inventado sem evidência de uso.

    `purpose` **não** decide verdade, não altera persistência, não
    altera acessibilidade e não ranqueia memórias. Nenhum score existe
    neste módulo.
    """

    @staticmethod
    def build(
        *,
        domain_ids: Iterable[uuid.UUID] | None = None,
        session_id: str | None = None,
        actor_ref: str | None = None,
        purpose: str | None = None,
    ) -> "MemoryContext":
        """Constrói um contexto canônico e determinístico.

        `domain_ids` é **ordenado e desduplicado**: a ordem em que
        alguém informa domínios não é informação semântica, e
        tratá-la como se fosse tornaria dois contextos idênticos
        artificialmente distintos. Portanto:

            build(domain_ids=[D2, D1]) == build(domain_ids=[D1, D2])
            build(domain_ids=[D1, D1]) == build(domain_ids=[D1])

        Campos ausentes (`None`) são situação **válida** e não geram
        erro. Strings presentes porém em branco são precondição
        violada pelo chamador — `ValueError`, mesma convenção de
        `CoidManager.generate_unique` (E3.2) e do `trace_id` em branco
        do `IndexManager` (E3.7).
        """
        for nome, valor in (
            ("session_id", session_id),
            ("actor_ref", actor_ref),
            ("purpose", purpose),
        ):
            if valor is not None and not valor.strip():
                raise ValueError(f"{nome} não pode ser vazio ou apenas espaços — omita-o")

        canonicos = tuple(sorted(set(domain_ids or ()), key=str))
        return MemoryContext(
            domain_ids=canonicos,
            session_id=session_id,
            actor_ref=actor_ref,
            purpose=purpose,
        )

    def derive(
        self,
        *,
        domain_ids: Iterable[uuid.UUID] | None = None,
        session_id: str | None = None,
        actor_ref: str | None = None,
        purpose: str | None = None,
    ) -> "MemoryContext":
        """Deriva uma **variante explícita**, sem tocar neste contexto.

        Só os campos informados mudam; os demais são herdados. O
        contexto base permanece exatamente como estava — a derivação
        é `C1 → C2`, nunca mutação de `C1`.

        Para limpar um campo herdado, construa com `build()` em vez de
        derivar: um `None` aqui significa "não mexa nisto", e dar dois
        sentidos ao mesmo valor tornaria a operação ambígua justamente
        onde ela precisa ser previsível.
        """
        return MemoryContext.build(
            domain_ids=self.domain_ids if domain_ids is None else domain_ids,
            session_id=self.session_id if session_id is None else session_id,
            actor_ref=self.actor_ref if actor_ref is None else actor_ref,
            purpose=self.purpose if purpose is None else purpose,
        )

    def without_domains(self) -> "MemoryContext":
        """Variante sem nenhum domínio declarado.

        Existe porque `derive()` não consegue expressar remoção (ver a
        docstring de lá), e contexto vazio é estado válido — não um
        contexto degenerado.
        """
        return replace(self, domain_ids=())

    @property
    def is_empty(self) -> bool:
        """Nenhuma dimensão informada.

        Contexto vazio é **válido**:

            empty context != no memory
            empty context != all authorized

        Ele não afirma nada sobre o patrimônio nem concede nada.
        Governança futura continua decidindo admissibilidade — sobre
        um contexto vazio como sobre qualquer outro.
        """
        return (
            not self.domain_ids
            and self.session_id is None
            and self.actor_ref is None
            and self.purpose is None
        )
