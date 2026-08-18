"""
`RetentionPolicy` — configuração de retenção persistida (`E4.9.6`).

```text
RetentionPolicy != CognitiveObject
RetentionPolicy != CognitivePatrimony
RetentionPolicy != ApprovalRecord
RetentionPolicy != ErasureRecord

RETENTION_POLICY_PORTABLE = FALSE
RETENTION_POLICY_SYNC     = NONE
```

Uma policy não tem COID, não tem CLID, não tem linhagem, não tem
proveniência, não tem história causal e não participa de
transformações. É configuração **local**, pela mesma razão congelada
na E4.0 para `GovernancePolicy`: autoridade não é transferível, e uma
policy importada regularia patrimônio alheio sem que ninguém no
destino tivesse decidido isso.

**Versões publicadas são imutáveis.** Correção semântica cria versão
nova, nunca sobrescreve — sem isso, é impossível responder meses
depois sob qual regra determinado item se tornou elegível a avaliação.

## O que esta tabela NÃO faz

```text
RETENTION_POLICY_PERSISTENCE != RETENTION_EVALUATION
RETENTION_EVALUATION         != USER_DECISION
USER_DECISION                != DESTRUCTIVE_EXECUTION
```

Publicar uma policy é **configurar uma regra futura**, não rodá-la.
Nenhum avaliador foi composto; nada consulta esta tabela para agir.
"""

from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import JSON, TypeDecorator, TypeEngine

from app.memory.schemas.retention import (
    RetentionRule,
    regra_de_json,
    validar_regras_retencao,
)
from app.models.base_model import BaseModel


class RetentionRulesType(TypeDecorator[tuple["RetentionRule", ...]]):
    """A **fronteira de congelamento** das regras (`E4.9.6.1`).

    ```text
    PERSISTENT IMMUTABILITY != DEEP READ IMMUTABILITY
    BOTH ARE REQUIRED
    ```

    A E4.9.6 protegeu a persistência em três camadas — mapper event,
    repositório e trigger — e mesmo assim a auditoria reproduziu:

    ```python
    policy.rules[0]["minimum_age_days"] = 0   # aceito em memória
    policy.typed_rules                        # passa a divergir do banco
    ```

    Nenhuma das três camadas dispara, porque **nada foi persistido**. O
    objeto na identity map passou a mostrar algo que o banco não tem, e
    duas leituras na mesma sessão podiam divergir.

    Este `TypeDecorator` faz o objeto **carregado** e o objeto **gravado**
    usarem a representação tipada, e todo método herdado de
    `BaseRepository` — `get_by_id`, `list`, `paginate`, `refresh` — passa
    a devolver a estrutura já congelada, sem que nenhuma assinatura
    precise mudar.

    ```text
    TYPE DECORATOR BOUNDARY != ORM ASSIGNMENT BOUNDARY
    ```

    **Correção da E4.9.6.2:** a E4.9.6.1 afirmava aqui que "não há
    `list[dict]` pública em momento algum, nem na escrita". Era falso, e
    a auditoria da cadeia 77 reproduziu: estas duas funções só correm no
    bind e no result, então `RetentionPolicy(rules=[{...}])` nunca
    passava por nenhuma delas. A fronteira de **atribuição** é o
    `@validates` de `RetentionPolicy`; este decorador cobre disco.
    As duas chamam `validar_regras_retencao`, para que não voltem a
    divergir.

    A alternativa considerada era uma `RetentionPolicyView` com
    confinamento total do ORM, e ela foi rejeitada: exigiria
    sobrescrever sete métodos herdados com tipo de retorno incompatível
    com `BaseRepository[ModelType]`, o que só fecharia no mypy com
    `type: ignore` novo — vedado pela Stop Condition 8 do corretivo — ou
    alterando `BaseRepository`, vedado pela Stop Condition 3.

    A coluna física continua `rules`, com o mesmo tipo no banco:
    `MIGRATION_DELTA = 0`.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        """JSONB no PostgreSQL, JSON genérico nos demais.

        Idêntico ao que a migration `c8a3f5017e94` criou — o tipo no
        banco não muda, só a representação em memória.
        """
        if dialect.name == "postgresql":
            # `JSONB` é untyped nos stubs do SQLAlchemy. A supressão é a
            # MESMA que a cadeia 76 já carregava nesta linha de tipo, na
            # constante `_RULES_JSON` que este decorador substituiu — não
            # é supressão nova, e a contagem no arquivo continua 1.
            return dialect.type_descriptor(JSONB())  # type: ignore[no-untyped-call]
        return dialect.type_descriptor(JSON())

    def process_bind_param(
        self, value: "tuple[RetentionRule, ...] | None", dialect: Dialect
    ) -> list[dict[str, Any]] | None:
        """Regras tipadas → JSON canônico, na ida para o disco.

        **`None` é recusado** desde a E4.9.6.3. A coluna é
        `nullable=False`, então `NULL` nunca é um valor legítimo desta
        coluna, e devolver `None` daqui delegava a recusa ao banco:

        ```text
        NOT NULL CONSTRAINT != DOMAIN BOUNDARY VALIDATION
        ```

        A E4.9.6.2 afirmou que atribuição, bind e leitura defensiva
        usavam o mesmo contrato. Com o atalho de `None` isso não era
        literalmente verdade, e a auditoria da cadeia 78 apontou o
        bypass. Agora é: toda entrada passa por
        `validar_regras_retencao`.

        O tipo de retorno mantém `| None` porque é a assinatura que o
        `TypeDecorator` declara; o valor `None` simplesmente não é
        alcançável por este corpo.
        """
        return RetentionPolicy.serialize_rules(validar_regras_retencao("rules", value))

    def process_result_value(
        self, value: object, dialect: Dialect
    ) -> "tuple[RetentionRule, ...] | None":
        """JSON → regras tipadas, na volta do disco.

        **`None` é recusado** desde a E4.9.6.3, pela mesma razão do
        bind: a coluna é `nullable=False`, logo `NULL` na volta é
        estado impossível, não valor. Aceitá-lo em silêncio produziria
        uma policy publicada sem regra alguma, que é exatamente o que
        `rules` sem `default` existe para impedir.

        Reconstrói **pelo construtor**, que reaplica todos os
        invariantes de domínio, depois de `validar_forma_json_regra`
        ter verificado a forma de cada campo.
        """
        if value is None:
            raise ValueError(
                "coluna `rules` é NOT NULL — NULL na leitura é estado impossível, "
                "não uma policy sem regras"
            )
        if not isinstance(value, list):
            raise ValueError("coluna `rules` deve conter uma lista JSON de regras")
        return RetentionPolicy.deserialize_rules(value)


MAX_KEY_LENGTH = 256
"""Teto das identidades lógicas, alinhado ao limite da E4.9.5.

Reexportado de `schemas.retention` para o modelo — o valor é o mesmo, e
o validador compartilhado vive junto do contrato tipado.
"""


class RetentionPolicy(BaseModel):
    """Policy de retenção local e versionada.

    Identidade em duas camadas, como as policies existentes:

    - `id` — identidade de **registro** (uma linha, uma versão);
    - `policy_key` — identidade **lógica**, estável entre versões.
    """

    __tablename__ = "retention_policies"

    policy_key: Mapped[str] = mapped_column(String(MAX_KEY_LENGTH), nullable=False, index=True)
    """Identidade lógica, estável entre versões. Não é o `id`."""

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    """Versão monotônica dentro do `policy_key`, começando em 1."""

    governance_policy_key: Mapped[str] = mapped_column(String(MAX_KEY_LENGTH), nullable=False)
    """`policy_key` da `GovernancePolicy` cuja autoridade esta policy exige.

    Texto, **sem FK** — mesmo raciocínio de `AccessibilityPolicy`: uma
    FK apontaria para a linha de uma versão específica e congelaria a
    autoridade numa versão que pode ter sido sucedida, o oposto do
    versionamento que a E4.3 estabeleceu.
    """

    rules: Mapped[tuple["RetentionRule", ...]] = mapped_column(RetentionRulesType(), nullable=False)
    """Regras **tipadas e profundamente imutáveis** em memória.

    `tuple` de `RetentionRule` congeladas, cada uma com `domain_ids`
    em `frozenset`. Não existe `list[dict]` pública: mutação aninhada
    falha antes de alterar o valor observado, e duas leituras na mesma
    sessão não podem divergir.

    Serializadas de forma **determinística**, nunca vazias.

    Sem `default`: uma policy publicada sem regra não expressa retenção
    alguma, e ausência de policy já representa ausência de regra
    aplicável. Um default de lista vazia tornaria trivial publicar uma
    policy que parece regular algo e não regula nada.

    Conjuntos viram listas ordenadas na serialização: `frozenset` não
    tem ordem estável entre execuções, e sem canonicalização o mesmo
    conjunto de regras produziria bytes diferentes a cada gravação.
    """

    effective_from: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    """Início da vigência. `None` = vigente desde sempre."""

    effective_until: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    """Fim da vigência (**exclusivo**). `None` = sem fim previsto.

    Exclusivo de propósito: com limite inclusivo, duas versões
    contíguas se sobrepõem exatamente no instante da virada, e a
    pergunta "qual valia?" passa a ter duas respostas.
    """

    __table_args__ = (
        UniqueConstraint("policy_key", "version", name="uq_retention_policies_key_version"),
        CheckConstraint("version >= 1", name="ck_retention_policies_version_positive"),
        CheckConstraint(
            "length(btrim(policy_key)) > 0",
            name="ck_retention_policies_policy_key_not_blank",
        ),
        CheckConstraint(
            "length(btrim(governance_policy_key)) > 0",
            name="ck_retention_policies_governance_key_not_blank",
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL "
            "OR effective_until > effective_from",
            name="ck_retention_policies_effective_window",
        ),
    )
    """`UNIQUE(policy_key, version)` é a autoridade final contra
    sobrescrita silenciosa **e** contra a corrida de duas sessões
    publicando a mesma versão. O repositório traduz a violação para
    exceção de domínio; o banco é quem garante.

    Não há `CHECK` sobre o conteúdo de `rules` além de `NOT NULL`. A
    não vacuidade e a forma das regras são impostas pelo tipo, na
    serialização — e este docstring diz isso em vez de sugerir uma
    garantia de banco que não existe.
    """

    @staticmethod
    def serialize_rules(rules: "tuple[RetentionRule, ...]") -> list[dict[str, Any]]:
        """Converte regras tipadas em JSON canônico.

        Recusa conjunto vazio, item de tipo errado e `rule_id`
        duplicado. Duplicata tornaria o fundamento de uma avaliação
        ambíguo — mesma disciplina de `GovernancePolicy.serialize_rules`.

        Desde a E4.9.6.2 esses invariantes vêm de
        `validar_regras_retencao`, e não de uma cópia local: manter duas
        listas de checagens é como as fronteiras divergem, que é
        exatamente o defeito que este corretivo fecha.
        """
        rules = validar_regras_retencao("rules", rules)

        return [
            {
                "rule_id": regra.rule_id,
                "scope_kind": regra.scope_kind.value,
                "domain_ids": sorted(str(d) for d in regra.domain_ids),
                "anchor": regra.anchor.value,
                "minimum_age_days": regra.minimum_age_days,
                "on_expiry_action": regra.on_expiry_action.value,
            }
            for regra in sorted(rules, key=lambda r: r.sort_key())
        ]

    @staticmethod
    def deserialize_rules(payload: list[dict[str, Any]]) -> "tuple[RetentionRule, ...]":
        """Reconstrói regras tipadas a partir do JSON.

        Delega item a item para `regra_de_json`, que valida a **forma**
        dos seis campos antes de converter e só então chama o construtor
        de `RetentionRule`, autoridade final do **domínio**.

        A duplicidade é checada **depois** da forma. Na cadeia 78 um
        `rule_id` de tipo errado chegava primeiro a este `set` e
        produzia `unhashable type: 'list'` — erro incidental da
        estrutura de dados, não do contrato.
        """
        if not payload:
            raise ValueError("payload de regras vazio — versão inválida")

        regras = tuple(regra_de_json(indice, item) for indice, item in enumerate(payload))

        vistos: set[str] = set()
        for regra in regras:
            if regra.rule_id in vistos:
                raise ValueError(
                    f"rule_id duplicado na mesma versão: '{regra.rule_id}' — "
                    "duplicata torna o fundamento da avaliação ambíguo"
                )
            vistos.add(regra.rule_id)

        return regras

    @validates("rules")
    def _validar_rules(self, key: str, value: object) -> "tuple[RetentionRule, ...]":
        """A fronteira de **atribuição** — construtor e `setattr` (`E4.9.6.2`).

        ```text
        TYPE DECORATOR BOUNDARY != ORM ASSIGNMENT BOUNDARY
        ```

        O `TypeDecorator` cobre disco; este validador cobre memória. O
        construtor declarativo do SQLAlchemy atribui cada `kwarg` por
        `setattr`, então esta função corre tanto em
        `RetentionPolicy(rules=...)` quanto em `policy.rules = ...`.

        **Não** corre no carregamento: o `loading` popula o `__dict__`
        por caminho próprio, sem evento de atributo — e é correto que
        seja assim, porque quem valida o que vem do banco é o
        `process_result_value`, que reconstrói pelo construtor tipado.

        Como levanta antes de escrever, uma atribuição inválida deixa o
        valor anterior intacto: recusar não é o mesmo que corromper.

        **E4.9.6.3 — `INITIALIZATION != REASSIGNMENT`.** A cadeia 78
        validava só a forma e devolvia qualquer tupla válida, inclusive
        na segunda atribuição. O mapper impedia o `UPDATE`, mas um
        consumidor na mesma `UnitOfWork` observaria uma regra que o
        banco não tem — exatamente a classe de risco que motivou a
        E4.9.6.1.

        ```text
        VALID_TUPLE != AUTHORITY_TO_REWRITE_PUBLISHED_POLICY
        ```

        A distinção usa o **estado do mapeamento**, não `"rules" in
        self.__dict__` sozinho: numa instância expirada o `__dict__`
        não tem a chave, e confiar só nele trataria a reatribuição
        seguinte como primeira inicialização — o escape que o §11.5 do
        prompt manda evitar. `has_identity` é verdadeiro para
        persistente e para expirada, então as duas recusam; e é falso
        para transiente, onde `estado.dict` distingue a primeira
        atribuição das seguintes.

        Carregamento e `refresh` continuam funcionando porque não
        passam por evento de atributo.
        """
        estado = inspect(self)
        if estado.has_identity or key in estado.dict:
            raise ValueError(
                "rules não pode ser reatribuída — uma versão de RetentionPolicy é "
                "imutável, e corrigir semântica cria versão nova "
                "(INITIALIZATION != REASSIGNMENT)"
            )
        return validar_regras_retencao(key, value)

    @property
    def typed_rules(self) -> "tuple[RetentionRule, ...]":
        """Regras desta versão, já tipadas — com verificação em runtime.

        ```text
        ANNOTATED TYPE != RUNTIME TYPE PROOF
        ```

        Na E4.9.6.1 esta propriedade era `return self.rules` puro, e a
        anotação `tuple[RetentionRule, ...]` era uma promessa que o
        runtime não cumpria: com a representação antiga no atributo, ela
        devolvia `dict`. Agora reafirma o contrato compartilhado, de
        modo que a anotação e o valor devolvido não podem divergir.

        Quando o valor é válido, devolve a **mesma** tupla — `is` com
        `rules` continua verdadeiro, e nenhuma cópia é fabricada.
        """
        return validar_regras_retencao("rules", self.rules)


@event.listens_for(RetentionPolicy, "before_update")
def _reject_retention_policy_update(
    mapper: object, connection: object, target: RetentionPolicy
) -> None:
    """Rejeita qualquer `UPDATE` numa versão publicada.

    Camada 1 de 3. Pega a mutação feita **por fora** do repositório —
    carregar o objeto, mutar o atributo e chamar `commit()` contorna
    qualquer override de método, e a E4.3.1 reproduziu esse defeito de
    verdade.
    """
    from app.memory.errors.exceptions import RetentionPolicyImmutableError

    raise RetentionPolicyImmutableError(target.id, operation="update")


@event.listens_for(RetentionPolicy, "before_delete")
def _reject_retention_policy_delete(
    mapper: object, connection: object, target: RetentionPolicy
) -> None:
    """Rejeita qualquer `DELETE` numa versão publicada.

    Remover a policy que fundamentou avaliações passadas apagaria o
    fundamento sem apagar a consequência.
    """
    from app.memory.errors.exceptions import RetentionPolicyImmutableError

    raise RetentionPolicyImmutableError(target.id, operation="delete")
