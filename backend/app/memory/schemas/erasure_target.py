"""
Contratos tipados de resolução de alvo (`E4.9.7`).

```text
REFERENCE          != RESOLVED_TARGET
TARGET_RESOLUTION  != DELETION_AUTHORITY
DELETION_AUTHORITY != EFFECT
EFFECT             != ERASURE_RECORD
```

Esta fatia materializa **somente** o que permite que uma referência seja
classificada e, no futuro, resolvida por um adaptador autorizado. Nada
aqui apaga, marca, move, persiste ou registra recibo. Resolver é
observacional: se resolver tivesse efeito colateral, uma consulta
exploratória já seria uma ação destrutiva parcial, e nenhuma aprovação
posterior poderia desfazê-la.

## O que estes objetos deliberadamente não são

```text
DESCRIPTOR != PATRIMONY
DESCRIPTOR != POLICY
DESCRIPTOR != APPROVAL
DESCRIPTOR != EFFECT
DESCRIPTOR != RECEIPT
```

Nenhum deles é entidade ORM, nenhum tem coluna, migração, repositório ou
serializer. O descritor é **capacidade contextual transitória**: existe
dentro de uma resolução e morre com ela.

## Confidencialidade do localizador

O localizador é o único campo que aproxima o sistema de um efeito real, e
por isso é o mais restrito:

```text
MUST_NOT_PERSIST
MUST_NOT_APPEAR_IN_ERASURE_RECORD
MUST_NOT_APPEAR_IN_CLEAR_REPR_OR_STR
MUST_NOT_BE_LOGGED_BY_THIS_MODULE
MUST_NOT_CONTAIN_SECRET_OR_CREDENTIAL
```

`repr()` e `str()` do descritor o substituem por um marcador. Não existe
`to_dict`, `model_dump`, logger ou coluna que possa vazá-lo.
"""

import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

from app.memory.models.erasure_enums import ErasureTargetClass
from app.memory.models.target_resolution_enums import (
    ORIGENS_PLURAIS,
    ReferenceOrigin,
    RefusalDimension,
    TargetResolutionRefusalReason,
)

MAX_OPAQUE_LENGTH = 512
"""Teto das strings opacas, alinhado às colunas de referência da E3.

`payload_ref` e `source_ref` são `VARCHAR(512)`; um contrato transitório
que aceitasse mais aceitaria o que a origem não consegue guardar.
"""

CATEGORIAS_UNICODE_PROIBIDAS = frozenset({"Cc", "Cf", "Zl", "Zp"})
"""Mesmo repertório recusado pela E4.9.6.2 em identificador opaco.

Reafirmado aqui em vez de importado de `schemas.retention`: aquele
módulo é da retenção, e uma dependência entre as duas fatias faria a
alteração de uma mexer no contrato da outra. O valor é o mesmo e as duas
guardas estáticas fixam cada um no seu lugar.
"""

NOMES_DE_CAMPO_PROIBIDOS = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "bearer",
        "senha",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "api_key",
        "apikey",
        "key",
        "private_key",
        "credential",
        "credentials",
        "cookie",
        "session",
        "session_id",
        "authorization",
        "auth",
        "oauth",
        "signature",
        "certificate",
        "pem",
        "passphrase",
        "pin",
        "otp",
        "mfa",
    }
)
"""Nomes que **nunca** podem virar campo destes contratos.

Precedente direto da lista de 29 nomes da E4.9.5. Capacidade verificada é
uma afirmação tipada sobre operação e escopo; a credencial que permite
executá-la pertence ao adaptador, e nunca a um value object que circula.
"""

CLASSES_DE_CONTEUDO = frozenset(
    {
        ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        ErasureTargetClass.AUTHORIZED_CONNECTOR_REFERENT,
    }
)
"""As duas únicas classes que podem representar conteúdo apagável.

`COGNITIVE_METADATA_RECORD` e `UNRESOLVED_OPAQUE_REFERENCE` **não** são
conteúdo e não constroem descritor de sucesso — saem como recusa tipada,
preservando a classificação sem fabricar um alvo executável.
"""

LOCALIZADOR_OCULTO = "<locator:redacted>"
"""O que `repr()` mostra no lugar do localizador."""


def validar_texto_opaco(nome: str, valor: object, tamanho: int = MAX_OPAQUE_LENGTH) -> str:
    """Contrato de string opaca desta fatia (`E4.9.7`).

    ```text
    VALIDATED OPAQUE VALUE != NORMALIZED VALUE
    ```

    Recusa tipo errado, vazio, branco, categorias Unicode `Cc`/`Cf`/`Zl`/
    `Zp` e excesso. Devolve o valor **original**, byte a byte: sem
    `strip`, sem `unicodedata.normalize`, sem `casefold`. Português
    acentuado e qualquer caractere visível permanecem intactos.

    A inspeção é por `unicodedata.category`, que **classifica**, e nunca
    por `normalize`, que **transformaria**. Duas sequências Unicode
    distintas jamais são fundidas aqui — a mesma posição que a E4.9.6.2
    fixou para os identificadores de retenção.
    """
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser str, recebido {type(valor).__name__}")
    if not valor.strip():
        raise ValueError(f"{nome} não pode ser vazio ou apenas espaços")
    for caractere in valor:
        categoria = unicodedata.category(caractere)
        if categoria in CATEGORIAS_UNICODE_PROIBIDAS:
            raise ValueError(
                f"{nome} não pode conter caracteres de controle, formatação ou "
                f"separação invisível — U+{ord(caractere):04X} pertence à "
                f"categoria Unicode {categoria}"
            )
    if len(valor) > tamanho:
        raise ValueError(f"{nome} excede {tamanho} caracteres")
    return valor


def validar_instante_ciente(nome: str, valor: object) -> datetime:
    """Exige `datetime` timezone-aware.

    Ingênuo é recusado, e não normalizado para UTC: assumir fuso é
    inventar um instante que o chamador não declarou. Mesma disciplina de
    `effective_from` na E4.9.6.
    """
    if not isinstance(valor, datetime):
        raise TypeError(f"{nome} deve ser datetime, recebido {type(valor).__name__}")
    if valor.tzinfo is None or valor.tzinfo.utcoffset(valor) is None:
        raise ValueError(f"{nome} deve ser timezone-aware")
    return valor


METACARACTERES_DE_EXPANSAO = ("*", "[", "]", "{", "}")
"""Metacaracteres que exprimem coleção, classe ou expansão de padrão.

Neutros de provedor: nenhum deles é sintaxe de um storage específico, e
todos são universalmente usados para designar **mais de um** objeto.
"""


def validar_localizador_sem_expansao_literal(nome: str, valor: object) -> str:
    """Recusa **sintaxe literal** de expansão no localizador (`E4.9.7.1`).

    ```text
    RAW_PATTERN_SYNTAX_REJECTION != MATERIAL_TARGET_CARDINALITY_PROOF
    PROVIDER_NEUTRAL_LEXICAL_CHECK != ADAPTER_SEMANTICS
    MATERIAL_EXACT_TARGET_PROOF = DEFERRED
    ```

    **Renomeada na E4.9.7.2, e a renomeação é a correção.** A versão da
    cadeia 81 se chamava `validar_localizador_exato` e o EDR apresentava a
    checagem como prova de que um descritor representa um alvo material
    exato. A auditoria mostrou o limite: `s3://bucket/%2A`,
    `s3://bucket/%5Ba-z%5D` e `regex://bucket/.+` são aceitos, e se são
    expansão depende do adaptador que os interpretar — adaptador que não
    existe.

    Uma camada neutra de provedor consegue provar restrição **lexical**.
    Não consegue provar a semântica material de toda string para todo
    provedor futuro. O nome passou a dizer o que a função faz.

    `ONE_DESCRIPTOR = ONE_EXACT_TARGET` continua sendo requisito do
    contrato — mas é obrigação do adaptador e da prova de efeito, não
    garantia já fechada por este value object.

    A cadeia 80 provava cardinalidade inspecionando **nomes de campo
    plurais**, e a auditoria mostrou por que isso não prova nada: uma
    única string cabe `s3://bucket/*`. Um campo escalar contendo um
    padrão continua designando um conjunto.

    A verificação é **estrutural**, não uma lista de substrings
    apresentada como segurança:

    1. `userinfo` (`//usuário:senha@`) — credencial embutida;
    2. query ou fragmento — o localizador não transporta parâmetro de
       capacidade; versão pertence a `version_etag`, que já existe como
       campo próprio, e credencial pertence ao adaptador;
    3. metacaracteres de expansão e `?` — designam mais de um objeto;
    4. barra final — prefixo é coleção, não objeto.

    O valor aceito é devolvido **byte a byte**: nada é normalizado,
    reescrito ou canonicalizado. Recusar não é corrigir.

    ### Limites declarados

    - **Percent-encoding não é decodificado.** `%2A` continua aceito, e
      `unquote` **não** é aplicado: decodificar seria interpretar a
      string em nome de um adaptador que ainda não existe, e a
      interpretação varia por provedor. Aplicar `unquote` aqui trocaria
      um limite declarado por uma normalização silenciosa, que o §3.4 do
      prompt proíbe.
    - **Scheme desconhecido não é rejeitado.** `regex://`, `glob://` ou
      qualquer outro passam se a forma literal for limpa. Rejeitar
      schemes por lista quebraria a neutralidade de provedor e criaria
      exatamente a "lista finita apresentada como prova" que a auditoria
      recusou.
    - Um localizador cujo nome legítimo contenha `[`, `{` ou `?` é
      recusado. É recusa conservadora deliberada: aceitar por engano
      designa alvo errado; recusar por engano só exige que o adaptador
      forneça outra forma de endereçar o mesmo objeto.
    - Segredo escondido **no caminho** — uma chave pré-assinada embutida
      como segmento — não é detectável por estrutura, e nenhuma lista de
      palavras o detectaria de forma confiável. Fica declarado como
      limite, não coberto por checagem que falharia em silêncio.
    - Vírgula não é recusada: é comum em nome legítimo de objeto, e
      recusá-la trocaria uma proteção real por ruído.
    """
    texto = validar_texto_opaco(nome, valor)

    partes = urlsplit(texto)
    if partes.username or partes.password:
        raise ValueError(
            f"{nome} não pode embutir credencial — usuário e senha em URL são "
            "material de autenticação, e autenticação pertence ao adaptador, "
            "nunca a um value object que circula"
        )
    if "?" in texto or "#" in texto:
        raise ValueError(
            f"{nome} não pode conter query nem fragmento — parâmetro de "
            "capacidade não pertence ao localizador (versão vai em "
            "version_etag), e `?` também designaria um caractere qualquer"
        )
    for metacaractere in METACARACTERES_DE_EXPANSAO:
        if metacaractere in texto:
            raise ValueError(
                f"{nome} não pode conter '{metacaractere}' — um descritor de "
                "sucesso representa exatamente um alvo, e expansão de padrão "
                "designa mais de um"
            )
    if texto.endswith("/"):
        raise ValueError(
            f"{nome} não pode terminar em '/' — prefixo designa uma coleção, " "não um objeto"
        )
    return texto


REFERENCIA_OCULTA = "<opaque_reference:redacted>"
"""O que `repr()` mostra no lugar da referência opaca."""

TEXTO_OCULTO = "<text:redacted>"
"""O que `repr()` mostra no lugar de qualquer campo textual livre.

```text
UNRESTRICTED_PUBLIC_STR = MAY_CONTAIN_SENSITIVE_VALUE
```

Acrescentado pela `E4.9.7.3`. O inventário da cadeia 82 afirmou que
**exatamente dois** campos podiam transportar material sensível, e a
auditoria mediu nove vazamentos: `control_principal_ref`, `provider`,
`namespace`, `operation` e `scope` aceitavam o mesmo marcador e o
revelavam em `repr()`, `str()` e dentro das composições.

A regra que passa a valer é a do domínio **executável**, não a do nome:
enquanto um campo público aceita texto arbitrário, ele pode conter valor
sensível — e a classificação honesta é essa, salvo se um tipo fechado ou
uma gramática efetivamente aplicada provar o contrário.

```text
SEMANTIC_FIELD_NAME != ENFORCED_VALUE_DOMAIN
TEXT_VALIDATION     != NON_SENSITIVE_VALUE_PROOF
INVENTORY_OF_NAMES  != CONFIDENTIALITY_PROOF
```
"""


@dataclass(frozen=True)
class ReferenceProvenance:
    """De onde veio a referência — em vocabulário fechado (`E4.9.7.2`).

    ```text
    ORIGIN = CLOSED_TYPED_PROVENANCE
    FREE_TEXT_ORIGIN = CONFIDENTIALITY_CHANNEL
    ```

    Substitui o `origin: str` da cadeia 81 nos três value objects. O campo
    antigo dizia "origem" no nome e aceitava qualquer texto no tipo — e a
    auditoria mediu o custo: localizador e URL assinada entravam por ele e
    a representação da recusa os revelava.

    A correção **não** é redigir a representação, porque o valor proibido
    continuaria dentro do objeto e poderia ser propagado da referência
    para a recusa. É tornar o campo incapaz de transportar conteúdo
    arbitrário.

    `position` existe porque três das cinco origens da E3 são listas
    JSON. Ela é **inteiro tipado e separado**, nunca `evidence_refs[3]`
    codificado numa string — codificar posição em texto reabriria o canal
    livre pela porta dos fundos.

    ```text
    ORIGIN IS TRACEABILITY, NEVER AUTHORITY
    ```

    Continua valendo o que a E4.9.1 sublinhou: transformar origem em
    autoridade recriaria, por outro caminho, o defeito de tratar uma
    string sintaticamente válida como capacidade.
    """

    origin: ReferenceOrigin
    position: int | None = None
    """Índice dentro da origem, quando ela é uma lista JSON da E3."""

    def __post_init__(self) -> None:
        if not isinstance(self.origin, ReferenceOrigin):
            raise TypeError(
                f"origin deve ser um ReferenceOrigin, recebido " f"{type(self.origin).__name__}"
            )
        if self.position is None:
            return
        if isinstance(self.position, bool) or not isinstance(self.position, int):
            raise TypeError(f"position deve ser int, recebido {type(self.position).__name__}")
        if self.position < 0:
            raise ValueError("position deve ser >= 0")
        if self.origin not in ORIGENS_PLURAIS:
            raise ValueError(
                f"{self.origin.value} é campo escalar na E3 e não admite position — "
                "uma posição ali não significaria nada"
            )


@dataclass(frozen=True)
class ControlScope:
    """A quem um alvo está tecnicamente vinculado.

    ```text
    TECHNICAL_CUSTODY != LEGAL_OWNERSHIP
    ```

    A E4.9.1 foi explícita: este contrato **não** conclui titularidade
    jurídica. Ele decide algo estreito e verificável — quem controla
    tecnicamente o destino. Um sistema que deduzisse direito a partir de
    uma string apagaria o que não devia com a convicção de estar
    cumprindo a lei.

    Os três campos formam a identidade contextual do descritor. Nenhum
    deles autentica ninguém: são **declarados pela fronteira**, e é por
    isso que esta classe não se chama `AuthorizedContext`.
    """

    workspace_id: uuid.UUID
    tenant_id: uuid.UUID
    control_principal_ref: str = field(repr=False)
    """Referência opaca ao principal de controle. Descritiva, como o
    `actor_ref` da E3: não autentica e não prova identidade.

    ```text
    UNRESTRICTED_PUBLIC_STR = MAY_CONTAIN_SENSITIVE_VALUE
    ```

    **Redigido desde a E4.9.7.3.** O EDR da cadeia 82 reconheceu que este
    campo podia receber algo sensível e afirmou que não era diretamente
    explorável "porque não entra em recusa". Era falso em runtime: a
    dataclass o expunha diretamente, e `ErasureTargetReference.__repr__`
    inclui `control_scope!r`. O valor continua acessível a quem resolve.
    """

    def __post_init__(self) -> None:
        for nome in ("workspace_id", "tenant_id"):
            valor = getattr(self, nome)
            if not isinstance(valor, uuid.UUID):
                raise TypeError(f"{nome} deve ser UUID, recebido {type(valor).__name__}")
        validar_texto_opaco("control_principal_ref", self.control_principal_ref)

    def __repr__(self) -> str:
        """Identidade contextual visível; o texto livre, não."""
        return (
            f"ControlScope(workspace_id={self.workspace_id!r}, "
            f"tenant_id={self.tenant_id!r}, "
            f"control_principal_ref={TEXTO_OCULTO})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class CustodyNamespace:
    """Onde o conteúdo vive, quando vive em algum lugar.

    Provedor e namespace explícitos **endereçam** a *credential
    confusion* da tabela de ameaças: credencial de um provedor não vale
    no namespace de outro, ainda que a referência pareça compatível.

    ```text
    CREDENTIAL_CONFUSION_RUNTIME_CLOSURE = DEFERRED
    ```

    Corrigido na E4.9.7.2: a cadeia 81 dizia "fecham". Não fecham — os
    campos tornam a divergência **verificável** e o contrato obriga a
    recusa, mas nada valida a credencial, porque não há conector. Fechar
    é obrigação do adaptador autorizado.

    Nenhum provedor é padrão. `PROVIDER_NEUTRALITY_PRESERVED`.
    """

    provider: str = field(repr=False)
    namespace: str = field(repr=False)
    """Ambos são texto arbitrário — logo, `MAY_CONTAIN_SENSITIVE_VALUE`.

    **Redigidos desde a E4.9.7.3.** Congelá-los num enum resolveria o
    vazamento e quebraria `PROVIDER_NEUTRALITY_PRESERVED`, que o §3.3 do
    corretivo proíbe: um provedor real não pode virar vocabulário
    fechado. Impor gramática de "identificador, não URL" seria inventar
    uma regra que nenhum contrato sustenta — há provedores cujo namespace
    legítimo é uma URI. Resta redigir a representação e manter o valor
    acessível.
    """

    def __post_init__(self) -> None:
        validar_texto_opaco("provider", self.provider)
        validar_texto_opaco("namespace", self.namespace)

    def __repr__(self) -> str:
        return f"CustodyNamespace(provider={TEXTO_OCULTO}, namespace={TEXTO_OCULTO})"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class VerifiedDeletionCapability:
    """O que a conta ou conector **comprovadamente** pode excluir.

    ```text
    VERIFIED_CAPABILITY != CREDENTIAL
    ```

    É uma afirmação tipada sobre operação e escopo. A credencial que
    permite executá-la pertence ao adaptador e nunca a este objeto —
    `NOMES_DE_CAMPO_PROIBIDOS` e uma guarda estática fixam isso.

    `verified=False` é permitido e significativo: o resolvedor observou a
    capacidade e ela **não** se confirmou. O descritor de sucesso exige
    `verified=True`, então esse caso vira recusa
    `DELETION_CAPABILITY_NOT_VERIFIED` em vez de sumir.
    """

    operation: str = field(repr=False)
    scope: str = field(repr=False)
    verified: bool
    """`operation` e `scope` são texto arbitrário e ficam redigidos.

    **E4.9.7.3.** `scope` **continua podendo representar conjunto** —
    `workspace/w1/*` é caso legítimo, porque capacidade descreve o que a
    conta pode, não um objeto. Redigir a representação não restringe o
    domínio: só impede que o valor escape por `repr`.

    `verified` é `bool` e permanece visível: não é texto e não transporta
    conteúdo.

    ```text
    OMITTED_VERIFICATION != VERIFIED_TRUE
    DEFAULT_TRUE = IMPLICIT_AUTHORITY
    ```

    **`verified` é obrigatório e não tem default — E4.9.7.4.** A cadeia
    83 lhe atribuiu `= True` ao acrescentar `field(repr=False)` em
    `operation` e `scope`. O default **não era necessário**: `field()`
    sem `default` deixa o campo obrigatório, então os dois anteriores
    nunca forçaram um valor aqui. Foi regressão acidental, dentro de um
    corretivo de representação, e nenhum teste a pegou porque toda
    chamada existente já passava `verified=True` explicitamente.

    A consequência era de autoridade, não de estilo: omitir a evidência
    produzia capacidade verificada e, com ela, um descritor de sucesso —
    `OMITTED_VERIFICATION → VERIFIED_CAPABILITY → SUCCESS_DESCRIPTOR`.

    Default `False` também estaria errado, por outra razão: esconderia a
    omissão como observação negativa. **Ausência de afirmação não é
    afirmação de ausência.** O chamador declara o que observou.
    """

    def __post_init__(self) -> None:
        validar_texto_opaco("operation", self.operation)
        validar_texto_opaco("scope", self.scope)
        if not isinstance(self.verified, bool):
            raise TypeError(f"verified deve ser bool, recebido {type(self.verified).__name__}")

    def __repr__(self) -> str:
        return (
            f"VerifiedDeletionCapability(operation={TEXTO_OCULTO}, "
            f"scope={TEXTO_OCULTO}, verified={self.verified!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class ErasureTargetReference:
    """O que entra na resolução — e apenas isso.

    Transporta o necessário para **tentar** resolver. Não autentica, não
    autoriza e não classifica: a classe do alvo é resultado da resolução,
    nunca entrada dela.

    ```text
    NATURAL_LANGUAGE_REFERENCE != RESOLVED_ERASURE_TARGET
    ORIGIN IS TRACEABILITY, NEVER AUTHORITY
    ```

    `origin` registra de onde veio a referência que motivou a tentativa.
    A E4.9.1 sublinhou a armadilha: transformar origem em autoridade
    recriaria, por outro caminho, o defeito de tratar uma string
    sintaticamente válida como capacidade.
    """

    subject_coid: uuid.UUID
    """Identificador histórico do sujeito. Distingue *removido* de
    *nunca existiu*, e **não** é localizador."""

    opaque_reference: str = field(repr=False)
    """A referência tal como está gravada. Sem FK, sem capacidade.

    ```text
    OPAQUE_REFERENCE = REQUIRED_SENSITIVE_INPUT
    REQUIRED_SENSITIVE_INPUT = REDACTED_FROM_REPR_AND_STR
    REDACTION != SECRET_FREE_OBJECT
    ```

    **Entrada necessária, e por isso tratada de forma diferente de
    `origin`.** Este campo transporta a referência legada da E3, que pode
    conter material sensível — uma URL assinada gravada há anos em
    `source_ref` é referência legítima. Substituí-lo por vocabulário
    fechado destruiria a função do contrato: sem ele não há o que
    resolver.

    A solução correta é outra: o valor continua acessível a quem resolve
    e é **redigido** em `repr()` e `str()`. E, ao contrário do que a
    cadeia 80 tentou com o localizador, aqui isso **não** é apresentado
    como objeto livre de segredo — o objeto transporta entrada sensível
    necessária e restringe a exposição dela.
    """

    origin: ReferenceProvenance
    """De onde a referência veio. Rastreabilidade, não autoridade.

    Tipado desde a E4.9.7.2 — ver `ReferenceProvenance`.
    """

    control_scope: ControlScope
    expected_namespace: CustodyNamespace | None = None
    """Provedor/namespace esperado, quando conhecido. `None` é legítimo:
    a maior parte das referências da E3 não diz onde o conteúdo vive."""

    def __post_init__(self) -> None:
        if not isinstance(self.subject_coid, uuid.UUID):
            raise TypeError(
                f"subject_coid deve ser UUID, recebido {type(self.subject_coid).__name__}"
            )
        validar_texto_opaco("opaque_reference", self.opaque_reference)
        if not isinstance(self.origin, ReferenceProvenance):
            raise TypeError("origin deve ser um ReferenceProvenance")
        if not isinstance(self.control_scope, ControlScope):
            raise TypeError("control_scope deve ser um ControlScope")
        if self.expected_namespace is not None and not isinstance(
            self.expected_namespace, CustodyNamespace
        ):
            raise TypeError("expected_namespace deve ser um CustodyNamespace ou None")

    def __repr__(self) -> str:
        """Representação **sem** a referência opaca.

        A dataclass já a oculta por `repr=False`; este método existe pela
        mesma razão do `__repr__` do descritor — um argumento é fácil de
        apagar sem perceber, e a redação explícita fica visível no texto.
        """
        return (
            f"ErasureTargetReference(subject_coid={self.subject_coid!r}, "
            f"origin={self.origin!r}, "
            f"control_scope={self.control_scope!r}, "
            f"expected_namespace={self.expected_namespace!r}, "
            f"opaque_reference={REFERENCIA_OCULTA})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class ErasureTargetDescriptor:
    """Um alvo resolvido — exatamente **um**, e transitório.

    Só existe para as duas classes de conteúdo. Metadado e referência não
    resolvida saem como `TargetResolutionRefusal`, preservando a
    classificação sem fabricar um alvo executável.

    ```text
    ONE DESCRIPTOR = ONE EXACT TARGET
    NO WILDCARD, NO EXPANSION AFTER CONFIRMATION
    ```

    A ausência de qualquer campo de conjunto, curinga ou padrão é o que
    fecha o *target expansion* no tipo: não há como um descritor
    representar vários alvos, porque não há onde escrevê-los.
    """

    target_class: ErasureTargetClass
    subject_coid: uuid.UUID
    control_scope: ControlScope
    custody_namespace: CustodyNamespace
    capability: VerifiedDeletionCapability
    resolved_at: datetime
    origin: ReferenceProvenance
    transient_locator: str = field(repr=False)
    """Suficiente para um adaptador futuro agir, e nada além.

    `repr=False` no campo, mais `__repr__` próprio: nenhuma
    representação textual deste objeto o revela.
    """
    version_etag: str | None = field(default=None, repr=False)
    """Detecta resolução obsoleta quando o provedor oferece versão."""

    def __post_init__(self) -> None:
        if not isinstance(self.target_class, ErasureTargetClass):
            raise TypeError("target_class deve ser um ErasureTargetClass")
        if self.target_class not in CLASSES_DE_CONTEUDO:
            raise ValueError(
                f"{self.target_class.value} não é conteúdo apagável — metadado "
                "cognitivo e referência não resolvida exigem recusa tipada, "
                "nunca descritor de sucesso"
            )
        if not isinstance(self.subject_coid, uuid.UUID):
            raise TypeError(
                f"subject_coid deve ser UUID, recebido {type(self.subject_coid).__name__}"
            )
        if not isinstance(self.control_scope, ControlScope):
            raise TypeError("control_scope deve ser um ControlScope")
        if not isinstance(self.custody_namespace, CustodyNamespace):
            raise TypeError("custody_namespace deve ser um CustodyNamespace")
        if not isinstance(self.capability, VerifiedDeletionCapability):
            raise TypeError("capability deve ser um VerifiedDeletionCapability")
        if not self.capability.verified:
            raise ValueError(
                "descritor de sucesso exige capacidade de exclusão VERIFICADA — "
                "capacidade presumida é a forma silenciosa do confused deputy"
            )
        validar_instante_ciente("resolved_at", self.resolved_at)
        if not isinstance(self.origin, ReferenceProvenance):
            raise TypeError("origin deve ser um ReferenceProvenance")
        validar_localizador_sem_expansao_literal("transient_locator", self.transient_locator)
        if self.version_etag is not None:
            validar_texto_opaco("version_etag", self.version_etag)

    def __repr__(self) -> str:
        """Representação **sem** o localizador.

        A dataclass já o oculta por `repr=False`; este método existe para
        que a ocultação não dependa de um argumento que alguém possa
        remover sem perceber, e para que a redação seja explícita no
        texto.
        """
        return (
            f"ErasureTargetDescriptor(target_class={self.target_class.value!r}, "
            f"subject_coid={self.subject_coid!r}, "
            f"custody_namespace={self.custody_namespace!r}, "
            f"capability={self.capability!r}, "
            f"resolved_at={self.resolved_at!r}, "
            f"version_etag={TEXTO_OCULTO if self.version_etag else None!r}, "
            f"transient_locator={LOCALIZADOR_OCULTO})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class TargetResolutionRefusal:
    """A resolução não produziu alvo — e diz por quê, com tipo.

    Recusa é um **resultado**, não um caminho de erro. Por isso não é
    exceção, não é `None` e não é `False`: o consumidor precisa
    distingui-la de sucesso por narrowing estático, e uma exceção
    incidental obrigaria a capturar para descobrir o que houve.

    ```text
    TYPED REFUSAL, NEVER BEST EFFORT
    ```

    `classified_as` preserva a classificação quando ela foi possível —
    saber que o alvo é metadado é informação útil, e perdê-la faria toda
    recusa parecer a mesma.

    ### Mudança pública da E4.9.7.1

    O campo `diagnostic: str | None` da cadeia 80 **foi removido**. Ele
    era validado apenas como texto opaco, e a auditoria mediu o
    resultado: aceitava o próprio localizador, e a representação padrão
    da dataclass o revelava.

    ```text
    SAFE_DIAGNOSTIC != FREE_TEXT
    REDACTED_REPR   != SECRET_FREE_OBJECT
    ```

    Redigir a representação não teria bastado, porque o valor proibido
    já estaria **dentro** do objeto. O contexto seguro passou a ser
    `observed_dimension`, um vocabulário fechado que nomeia a dimensão
    divergente e não tem onde transportar localizador, segredo ou
    conteúdo. Manter a assinatura antiga só para preservar
    compatibilidade seria manter uma API que a auditoria demonstrou
    insegura.
    """

    reason: TargetResolutionRefusalReason
    subject_coid: uuid.UUID
    origin: ReferenceProvenance
    classified_as: ErasureTargetClass | None = None
    """Classe observada, quando a resolução chegou a classificar."""
    observed_dimension: RefusalDimension | None = None
    """Qual dimensão do contexto divergiu, quando a recusa observou uma.

    Vocabulário **fechado**. Substitui o texto livre da cadeia 80.
    """

    def __post_init__(self) -> None:
        if not isinstance(self.reason, TargetResolutionRefusalReason):
            raise TypeError("reason deve ser um TargetResolutionRefusalReason")
        if not isinstance(self.subject_coid, uuid.UUID):
            raise TypeError(
                f"subject_coid deve ser UUID, recebido {type(self.subject_coid).__name__}"
            )
        if not isinstance(self.origin, ReferenceProvenance):
            raise TypeError("origin deve ser um ReferenceProvenance")
        if self.classified_as is not None and not isinstance(
            self.classified_as, ErasureTargetClass
        ):
            raise TypeError("classified_as deve ser um ErasureTargetClass ou None")
        if self.observed_dimension is not None and not isinstance(
            self.observed_dimension, RefusalDimension
        ):
            raise TypeError("observed_dimension deve ser um RefusalDimension ou None")


TargetResolutionResult = ErasureTargetDescriptor | TargetResolutionRefusal
"""Sucesso ou recusa — nunca os dois, nunca nenhum.

União de duas classes **disjuntas**, e não um objeto com campo de
estado. A diferença importa: um objeto com `success: bool` admite estado
inconsistente por construção, e a E4.7.2 já pagou por resultado que não
era máquina de estados exaustiva. Aqui não há quinto desfecho porque não
há onde escrevê-lo.

O consumidor faz narrowing com `isinstance`, sem `Any`, `cast` ou
`type: ignore`.
"""
