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

from app.memory.models.erasure_enums import ErasureTargetClass
from app.memory.models.target_resolution_enums import TargetResolutionRefusalReason

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
    control_principal_ref: str
    """Referência opaca ao principal de controle. Descritiva, como o
    `actor_ref` da E3: não autentica e não prova identidade."""

    def __post_init__(self) -> None:
        for nome in ("workspace_id", "tenant_id"):
            valor = getattr(self, nome)
            if not isinstance(valor, uuid.UUID):
                raise TypeError(f"{nome} deve ser UUID, recebido {type(valor).__name__}")
        validar_texto_opaco("control_principal_ref", self.control_principal_ref)


@dataclass(frozen=True)
class CustodyNamespace:
    """Onde o conteúdo vive, quando vive em algum lugar.

    Provedor e namespace explícitos fecham a *credential confusion* da
    tabela de ameaças: credencial de um provedor não vale no namespace de
    outro, ainda que a referência pareça compatível.

    Nenhum provedor é padrão. `PROVIDER_NEUTRALITY_PRESERVED`.
    """

    provider: str
    namespace: str

    def __post_init__(self) -> None:
        validar_texto_opaco("provider", self.provider)
        validar_texto_opaco("namespace", self.namespace)


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

    operation: str
    scope: str
    verified: bool

    def __post_init__(self) -> None:
        validar_texto_opaco("operation", self.operation)
        validar_texto_opaco("scope", self.scope)
        if not isinstance(self.verified, bool):
            raise TypeError(f"verified deve ser bool, recebido {type(self.verified).__name__}")


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

    opaque_reference: str
    """A referência tal como está gravada. Sem FK, sem capacidade."""

    origin: str
    """De onde a referência veio. Rastreabilidade, não autoridade."""

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
        validar_texto_opaco("origin", self.origin)
        if not isinstance(self.control_scope, ControlScope):
            raise TypeError("control_scope deve ser um ControlScope")
        if self.expected_namespace is not None and not isinstance(
            self.expected_namespace, CustodyNamespace
        ):
            raise TypeError("expected_namespace deve ser um CustodyNamespace ou None")


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
    origin: str
    transient_locator: str = field(repr=False)
    """Suficiente para um adaptador futuro agir, e nada além.

    `repr=False` no campo, mais `__repr__` próprio: nenhuma
    representação textual deste objeto o revela.
    """
    version_etag: str | None = field(default=None)
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
        validar_texto_opaco("origin", self.origin)
        validar_texto_opaco("transient_locator", self.transient_locator)
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
            f"provider={self.custody_namespace.provider!r}, "
            f"namespace={self.custody_namespace.namespace!r}, "
            f"resolved_at={self.resolved_at!r}, "
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
    """

    reason: TargetResolutionRefusalReason
    subject_coid: uuid.UUID
    origin: str
    classified_as: ErasureTargetClass | None = None
    """Classe observada, quando a resolução chegou a classificar."""
    diagnostic: str | None = None
    """Contexto seguro para o chamador. **Nunca** o localizador."""

    def __post_init__(self) -> None:
        if not isinstance(self.reason, TargetResolutionRefusalReason):
            raise TypeError("reason deve ser um TargetResolutionRefusalReason")
        if not isinstance(self.subject_coid, uuid.UUID):
            raise TypeError(
                f"subject_coid deve ser UUID, recebido {type(self.subject_coid).__name__}"
            )
        validar_texto_opaco("origin", self.origin)
        if self.classified_as is not None and not isinstance(
            self.classified_as, ErasureTargetClass
        ):
            raise TypeError("classified_as deve ser um ErasureTargetClass ou None")
        if self.diagnostic is not None:
            validar_texto_opaco("diagnostic", self.diagnostic)


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
