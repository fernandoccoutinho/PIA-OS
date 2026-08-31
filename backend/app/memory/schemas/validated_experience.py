"""
Contratos tipados do registro de experiência validada (`E4.11`).

```text
VARIATION
  -> EXPERIENCE
  -> EVIDENCE
  -> VALIDATION      <- a E4.11 encerra AQUI
  -> SELECTION
  -> POSSIBLE_PERSISTENCE
  -> CONTROLLED_IMPROVEMENT
```

O registro é **estrutura de evidência**, não motor. O teste que decide
tudo, congelado no `E4_ARCHITECTURE_FREEZE` §19:

```text
IF REMOVING THE RECORD CHANGES SYSTEM BEHAVIOR
THEN IT IS A LEARNING ENGINE
```

Remover uma linha daqui pode apagar evidência auditável; não pode mudar
decisão ou execução de nada.

## O que estes tipos nunca transportam

```text
NO_SCORE · NO_CONFIDENCE · NO_WEIGHT · NO_RANKING
NO_GENERALIZATION · NO_RECOMMENDATION
NO_CONTENT · NO_PAYLOAD · NO_TRANSCRIPT
NO_LOCATOR · NO_URL · NO_CREDENTIAL · NO_CAPABILITY
```

A garantia sobre localizador é **estrutural**: `EvidenceReference.ref` é
`uuid.UUID`, e um UUID não tem onde guardar um caminho ou uma URL.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.memory.models.validated_experience_enums import (
    CriterionOriginKind,
    EvidenceKind,
    ExperienceSubjectKind,
    ValidatorKind,
)

MAX_TOKEN_LENGTH = 64
MAX_REF_LENGTH = 255
MAX_CRITERION_KEY_LENGTH = 128

GRAMATICA_DO_TOKEN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
"""Gramática **fechada** do token de resultado observado.

```text
CLOSED_GRAMMAR != FREE_TEXT
OUTCOME_TOKEN_IS_READ_AGAINST_THE_CRITERION
```

Minúsculas ASCII, dígitos e três separadores. Sem espaço, sem
maiúscula, sem acento, sem pontuação de frase — porque um campo que
aceita frase vira campo de julgamento, e julgamento é o que o registro
não pode conter.

O token **não** é ontologia universal: `produced`, `not_produced`,
`diverged` e qualquer outro só significam alguma coisa lidos contra o
`criterion_ref` que os define. Congelar um enum de resultados aqui
imporia uma taxonomia a experiências que ainda não existem.
"""


def validar_token_de_resultado(nome: str, valor: object) -> str:
    """Aceita apenas o que a gramática fechada admite.

    Devolve o valor **original**: sem `strip`, sem normalização Unicode,
    sem `casefold`. Mesma disciplina de `validar_identificador_opaco`
    (E4.9.6.2) — um identificador que o sistema altera em silêncio deixa
    de ser o que o chamador declarou.
    """
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser str, recebido {type(valor).__name__}")
    if not valor:
        raise ValueError(f"{nome} não pode ser vazio")
    if len(valor) > MAX_TOKEN_LENGTH:
        raise ValueError(f"{nome} excede {MAX_TOKEN_LENGTH} caracteres")
    if not GRAMATICA_DO_TOKEN.fullmatch(valor):
        raise ValueError(
            f"{nome} {valor!r} está fora da gramática fechada — o resultado "
            "observado é token, não frase: texto livre viraria julgamento"
        )
    return valor


def validar_referencia_opaca(nome: str, valor: object, tamanho: int) -> str:
    """Referência textual opaca, sem caractere de controle nem normalização.

    Inspeciona por `unicodedata.category`, que **classifica**, e nunca
    por `normalize`, que **transformaria** — duas sequências distintas
    jamais são fundidas aqui.
    """
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser str, recebido {type(valor).__name__}")
    if not valor.strip():
        raise ValueError(f"{nome} não pode ser vazio ou apenas espaços")
    if len(valor) > tamanho:
        raise ValueError(f"{nome} excede {tamanho} caracteres")
    for caractere in valor:
        if unicodedata.category(caractere) in {"Cc", "Cf", "Zl", "Zp"}:
            raise ValueError(
                f"{nome} contém caractere de controle — uma referência assim se "
                "apresenta de uma forma em log e de outra numa interface"
            )
    return valor


def validar_uuid(nome: str, valor: object) -> uuid.UUID:
    if not isinstance(valor, uuid.UUID):
        raise TypeError(
            f"{nome} deve ser UUID, recebido {type(valor).__name__} — texto "
            "equivalente não é identificador"
        )
    return valor


def canonizar_instante(nome: str, valor: object) -> datetime:
    """Exige instante ciente e canonicaliza para UTC.

    ```text
    NAIVE_INSTANT = MACHINE_DEPENDENT_RECORD
    ```

    Dois instantes iguais em fusos diferentes precisam produzir a mesma
    igualdade estrutural — mesma disciplina de `AccessibilityDecision` e
    de `ComplianceReport`.
    """
    if not isinstance(valor, datetime):
        raise TypeError(f"{nome} deve ser datetime, recebido {type(valor).__name__}")
    if valor.tzinfo is None:
        raise ValueError(
            f"{nome} deve ser timezone-aware: um instante ingênuo daria registro "
            "dependente do fuso da máquina"
        )
    return valor.astimezone(UTC)


@dataclass(frozen=True)
class ExperienceSubjectRef:
    """Sobre o que a experiência foi validada — união fechada.

    ```text
    SAME_UUID_DIFFERENT_UNIVERSE
    ```

    O discriminador é obrigatório porque objeto e evento compartilham o
    tipo do identificador. Sem ele, o mesmo `uuid` seria ambíguo.
    """

    kind: ExperienceSubjectKind
    ref: uuid.UUID

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ExperienceSubjectKind):
            raise TypeError(
                f"kind deve ser um ExperienceSubjectKind, recebido " f"{type(self.kind).__name__}"
            )
        validar_uuid("ref", self.ref)


@dataclass(frozen=True)
class EvidenceReference:
    """Uma referência de evidência — identidade, nunca conteúdo.

    ```text
    UUID_HAS_NOWHERE_TO_PUT_A_URL
    ```

    `ref` é `uuid.UUID` de propósito. Uma referência em `str` aceitaria
    caminho local, URL viva, token e capability, e a garantia
    `NO_LOCATOR` dependeria de vigilância. Aqui ela é do tipo.

    **Sem chave estrangeira.** Medido e decidido: uma FK exigiria que o
    alvo exista *neste* banco, o que quebraria evidência sobre objeto já
    removido e, quando o transporte for autorizado, quebraria a
    importação de um registro cujo sujeito não veio junto.
    `REFERENCE != FOREIGN_KEY`.
    """

    kind: EvidenceKind
    ref: uuid.UUID

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EvidenceKind):
            raise TypeError(f"kind deve ser um EvidenceKind, recebido {type(self.kind).__name__}")
        validar_uuid("ref", self.ref)

    def sort_key(self) -> tuple[str, str]:
        """Ordenação canônica e determinística."""
        return (self.kind.value, str(self.ref))


@dataclass(frozen=True)
class ObservedOutcome:
    """O resultado observado — fato datado, ancorado em evidência.

    ```text
    OBSERVED_FACT != JUDGEMENT
    NO_SCORE · NO_CONFIDENCE · NO_RECOMMENDATION
    ```

    Três campos, e nenhum deles opina. O token diz **o que** foi
    observado numa gramática fechada; `observed_at` diz quando; e
    `primary_evidence_ref` diz onde está o artefato que sustenta a
    observação — sem ele, o resultado seria alegação sem lastro.
    """

    outcome_token: str
    observed_at: datetime
    primary_evidence_ref: EvidenceReference

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "outcome_token", validar_token_de_resultado("outcome_token", self.outcome_token)
        )
        object.__setattr__(self, "observed_at", canonizar_instante("observed_at", self.observed_at))
        if not isinstance(self.primary_evidence_ref, EvidenceReference):
            raise TypeError("primary_evidence_ref deve ser um EvidenceReference")


@dataclass(frozen=True)
class AttributedValidator:
    """Quem validou — **atribuição**, jamais autenticação.

    ```text
    ATTRIBUTED    = YES
    AUTHENTICATED = NO
    ```

    Não existe autenticador na cadeia 95. Um campo `verified`,
    `authenticated` ou `signature` afirmaria uma garantia que o sistema
    não tem, e a ausência desses campos é o que impede a alegação falsa.
    """

    validator_kind: ValidatorKind
    validator_ref: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.validator_kind, ValidatorKind):
            raise TypeError(
                f"validator_kind deve ser um ValidatorKind, recebido "
                f"{type(self.validator_kind).__name__}"
            )
        object.__setattr__(
            self,
            "validator_ref",
            validar_referencia_opaca("validator_ref", self.validator_ref, MAX_REF_LENGTH),
        )

    def __repr__(self) -> str:
        """Redação escrita, nunca delegada.

        A referência do validador pode identificar uma pessoa, e a E4.9.8
        já congelou que identidade não vaza em representação.
        """
        return f"AttributedValidator(validator_kind={self.validator_kind.value!r})"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class CriterionReference:
    """Contra qual critério — chave, versão e origem.

    ```text
    CRITERION_KEY_ALONE = FAMILY_OF_VERSIONS
    NO_DEFAULT_VERSION
    ```

    Sem os três, o critério não é reproduzível. `criterion_version` não
    tem default: uma versão implícita significaria "a mais recente", e a
    mais recente muda — o registro passaria a citar um critério que
    ninguém aplicou. Precedente literal de `PolicyReference` (E4.10).
    """

    criterion_key: str
    criterion_version: int
    criterion_origin: CriterionOriginKind

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "criterion_key",
            validar_referencia_opaca("criterion_key", self.criterion_key, MAX_CRITERION_KEY_LENGTH),
        )
        if isinstance(self.criterion_version, bool) or not isinstance(self.criterion_version, int):
            raise TypeError(
                f"criterion_version deve ser int, recebido "
                f"{type(self.criterion_version).__name__}"
            )
        if self.criterion_version < 1:
            raise ValueError("criterion_version deve ser >= 1")
        if not isinstance(self.criterion_origin, CriterionOriginKind):
            raise TypeError("criterion_origin deve ser um CriterionOriginKind")


@dataclass(frozen=True)
class OriginAttribution:
    """De qual instalação veio o registro.

    ```text
    ORIGIN_ATTRIBUTED         = YES
    ORIGIN_AUTHENTICATED      = NO
    ORIGIN_LOCALITY_PERSISTED = NO
    ```

    Só a origem, e nenhum sinal de localidade. "Local" é relativo a quem
    lê: um registro local hoje é importado amanhã, e um booleano
    persistido passaria a mentir depois da travessia.

    O campo é **obrigatório desde a primeira linha**, e a razão é
    material: a tabela é append-only, e atribuição não se retrofita.
    Acrescentar a coluna depois deixaria as linhas antigas em `NULL`, e
    `ORIGIN_UNKNOWN != LOCAL_ORIGIN` — evidência alheia viraria própria
    por omissão, o colapso que `COUT-P3` proíbe.
    """

    origin_ref: uuid.UUID

    def __post_init__(self) -> None:
        validar_uuid("origin_ref", self.origin_ref)


@dataclass(frozen=True)
class ValidatedExperienceAppend:
    """O que se pede para registrar — vínculo completo em seis partes.

    ```text
    subject_ref + outcome_observed + validated_by
                + criterion_ref + evidence_refs + validated_at
    ```

    Separados, cada elemento é um dado solto: um resultado sem critério
    não diz contra o quê foi validado, e um validador sem instante não
    diz quando. Todos são obrigatórios e nenhum tem default.

    `experience_id` entra **no contrato de append**, e não é gerado pela
    persistência: a idempotência é por identidade, e o chamador precisa
    poder repetir a mesma chamada sabendo que ela é a mesma.
    """

    experience_id: uuid.UUID
    subject_ref: ExperienceSubjectRef
    outcome_observed: ObservedOutcome
    validated_by: AttributedValidator
    criterion_ref: CriterionReference
    evidence_refs: tuple[EvidenceReference, ...]
    validated_at: datetime
    origin: OriginAttribution

    def __post_init__(self) -> None:
        validar_uuid("experience_id", self.experience_id)
        for nome, tipo in (
            ("subject_ref", ExperienceSubjectRef),
            ("outcome_observed", ObservedOutcome),
            ("validated_by", AttributedValidator),
            ("criterion_ref", CriterionReference),
            ("origin", OriginAttribution),
        ):
            if not isinstance(getattr(self, nome), tipo):
                raise TypeError(f"{nome} deve ser um {tipo.__name__}")
        object.__setattr__(
            self, "validated_at", canonizar_instante("validated_at", self.validated_at)
        )

        if not isinstance(self.evidence_refs, tuple):
            raise TypeError(
                "evidence_refs deve ser tuple — `list` perderia a imutabilidade e "
                "`set` a ordem canônica"
            )
        if not self.evidence_refs:
            raise ValueError(
                "evidence_refs não pode ser vazia: o fluxo congelado é "
                "EXPERIENCE -> EVIDENCE -> VALIDATION, e um registro validado sem "
                "evidência contradiz a própria natureza"
            )
        for indice, referencia in enumerate(self.evidence_refs):
            if not isinstance(referencia, EvidenceReference):
                raise TypeError(f"evidence_refs[{indice}] deve ser um EvidenceReference")

        chaves = [referencia.sort_key() for referencia in self.evidence_refs]
        if len(set(chaves)) != len(chaves):
            raise ValueError(
                "evidence_refs repetida — a mesma evidência contada duas vezes "
                "sugeriria um lastro que não existe"
            )
        if chaves != sorted(chaves):
            raise ValueError(
                "evidence_refs fora da ordem canônica (kind, ref) — ordem instável "
                "tornaria dois registros idênticos textualmente diferentes"
            )

        if self.outcome_observed.observed_at > self.validated_at:
            # ```text
            # DB_CHECK_CONSTRAINT != DOMAIN_BOUNDARY_VALIDATION
            # ```
            #
            # O banco também recusa, e a redundância é deliberada — mas a
            # fronteira de domínio precisa recusar primeiro, senão uma
            # violação de coerência chegaria ao chamador como erro de
            # persistência, longe de onde nasceu (lição da E4.9.6.3).
            raise ValueError(
                "observed_at posterior a validated_at — observa-se antes de "
                "validar, e o inverso descreveria validação sobre o que ainda "
                "não foi observado"
            )

        if self.outcome_observed.primary_evidence_ref not in self.evidence_refs:
            raise ValueError(
                "primary_evidence_ref não está em evidence_refs — a evidência que "
                "sustenta o resultado precisa fazer parte do lastro declarado"
            )
