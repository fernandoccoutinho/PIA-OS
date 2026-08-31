"""
Contratos tipados da fronteira de conformidade (`E4.10`).

```text
ComplianceFinding   NÃO persistido, sem identidade cognitiva
ComplianceReport    NÃO persistido, transitório, determinístico
```

Nada aqui tem COID, CLID, lifecycle, lineage ou provenance própria, e
nada aqui vira tabela. Persistir diagnóstico criaria a tentação de
tratá-lo como verdade estabelecida, quando ele é resultado **datado** de
uma avaliação contra uma **versão** de política — e derivável de novo a
qualquer momento a partir das duas.

É o mesmo desenho de `IntegrityFinding` (E3.10) e `GovernanceDecision`
(E4.3), e a herança é deliberada.

## O que estes tipos nunca transportam

```text
NO_CONTENT · NO_PAYLOAD · NO_TRANSCRIPT
NO_LOCATOR · NO_CAPABILITY · NO_CREDENTIAL · NO_SECRET
NO_FREE_TEXT_AS_MACHINE_INPUT
```

`IntegrityFinding` usa `dict[str, object]` para evidência porque audita
invariantes **estruturais**. Aqui a evidência toca patrimônio governado,
e um dicionário livre aceita qualquer coisa — inclusive localizador e
payload. A garantia `NO_LOCATOR` só é verificável estaticamente se o
tipo não tiver onde guardá-lo.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.error_codes import ErrorSeverity
from app.memory.models.compliance_enums import (
    ComplianceCode,
    ComplianceOutcome,
    ComplianceSubjectKind,
    MissingObservation,
    PolicyKind,
    PolicyWindowState,
)

SUJEITO_POR_POLITICA: dict[PolicyKind, ComplianceSubjectKind] = {
    PolicyKind.GOVERNANCE: ComplianceSubjectKind.GOVERNED_OPERATION,
    PolicyKind.ACCESSIBILITY: ComplianceSubjectKind.ACCESSIBILITY_TRANSITION,
    PolicyKind.RETENTION: ComplianceSubjectKind.RETENTION_CANDIDATE,
}
"""Correspondência **biunívoca** entre família de política e sujeito.

Enumerada literalmente, e não derivada por nome: uma correspondência
inferida de strings semelhantes mudaria sozinha ao renomear um membro, e
a compatibilidade entre os dois vocabulários é decisão, não coincidência
ortográfica.
"""

CODIGOS_POR_POLITICA: dict[PolicyKind, frozenset[ComplianceCode]] = {
    PolicyKind.GOVERNANCE: frozenset(
        {
            ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_AGAINST_DENY,
            ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_WITHOUT_RULE,
        }
    ),
    PolicyKind.ACCESSIBILITY: frozenset(
        {
            ComplianceCode.ACCESSIBILITY_TRANSITION_AGAINST_DENY,
            ComplianceCode.ACCESSIBILITY_EXTINCTION_WITHOUT_EVIDENCE,
            ComplianceCode.ACCESSIBILITY_TRANSITION_WITHOUT_RULE,
        }
    ),
    PolicyKind.RETENTION: frozenset({ComplianceCode.RETENTION_ASSESSMENT_INFORMATION_ABSENT}),
}
"""Quais códigos cada família pode emitir.

Um finding de acessibilidade dentro de um relatório de retenção citaria
uma regra que a política avaliada não tem. A guarda vive no construtor
do relatório, onde as duas informações se encontram.
"""


def _validar_uuid(nome: str, valor: object) -> uuid.UUID:
    if not isinstance(valor, uuid.UUID):
        raise TypeError(f"{nome} deve ser UUID, recebido {type(valor).__name__}")
    return valor


def _validar_texto(nome: str, valor: object) -> str:
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser str, recebido {type(valor).__name__}")
    if not valor.strip():
        raise ValueError(f"{nome} não pode ser vazio ou apenas espaços")
    return valor


def _canonizar_instante(nome: str, valor: object) -> datetime:
    """Exige instante ciente e canonicaliza para UTC.

    ```text
    NAIVE_INSTANT = MACHINE_DEPENDENT_RESULT
    ```

    Dois instantes iguais em fusos diferentes precisam produzir o mesmo
    diagnóstico, com a mesma igualdade estrutural — mesma disciplina de
    `AccessibilityDecision`.
    """
    if not isinstance(valor, datetime):
        raise TypeError(f"{nome} deve ser datetime, recebido {type(valor).__name__}")
    if valor.tzinfo is None:
        raise ValueError(
            f"{nome} deve ser timezone-aware: um instante ingênuo daria resultado "
            "dependente do fuso da máquina"
        )
    return valor.astimezone(UTC)


@dataclass(frozen=True)
class PolicyReference:
    """A política avaliada, identificada sem ambiguidade.

    ```text
    POLICY_KEY_ALONE = FAMILY_OF_VERSIONS
    VERSION_ALONE    = WHICH_POLICY?
    ```

    As quatro dimensões juntas são o que torna o diagnóstico
    reproduzível meses depois. `policy_version` não tem default: uma
    versão implícita significaria "a mais recente", e a mais recente
    muda — o relatório passaria a descrever outra avaliação.
    """

    kind: PolicyKind
    policy_id: uuid.UUID
    policy_key: str
    policy_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PolicyKind):
            raise TypeError(
                f"kind deve ser um PolicyKind, recebido {type(self.kind).__name__} — "
                "texto equivalente não é membro"
            )
        _validar_uuid("policy_id", self.policy_id)
        _validar_texto("policy_key", self.policy_key)
        if isinstance(self.policy_version, bool) or not isinstance(self.policy_version, int):
            raise TypeError(
                f"policy_version deve ser int, recebido {type(self.policy_version).__name__}"
            )
        if self.policy_version < 1:
            raise ValueError("policy_version deve ser >= 1")


@dataclass(frozen=True)
class ComplianceSubjectRef:
    """Projeção **segura** do sujeito avaliado.

    Identificadores e domínio; nunca conteúdo, localizador ou
    capacidade. O que um leitor precisa para ir investigar é o COID — e
    o COID já é a chave pela qual todo o resto se alcança sob a
    governança que lhe couber.
    """

    kind: ComplianceSubjectKind
    subject_coid: uuid.UUID
    domain_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ComplianceSubjectKind):
            raise TypeError(
                f"kind deve ser um ComplianceSubjectKind, recebido " f"{type(self.kind).__name__}"
            )
        _validar_uuid("subject_coid", self.subject_coid)
        if self.domain_id is not None:
            _validar_uuid("domain_id", self.domain_id)


@dataclass(frozen=True)
class ComplianceFinding:
    """Uma condição de não conformidade, localizada e classificada.

    ```text
    FINDING  = OBSERVATION
    FINDING != EXCEPTION
    FINDING != KNOWLEDGE
    FINDING != DECISION
    ```

    Cada finding carrega a identidade completa da avaliação que o
    produziu — sujeito, política, versão e instante. Um finding solto,
    sem esse vínculo, seria uma afirmação sem contexto: não se saberia
    contra qual versão ele vale, e uma versão posterior da mesma
    política poderia torná-lo falso sem que ninguém percebesse.

    `matched_rule_ids` é tupla de identificadores opacos, jamais o
    conteúdo das regras.
    """

    code: ComplianceCode
    severity: ErrorSeverity
    subject_ref: ComplianceSubjectRef
    policy_ref: PolicyReference
    policy_version: int
    evaluated_at: datetime
    matched_rule_ids: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if not isinstance(self.code, ComplianceCode):
            raise TypeError(
                f"code deve ser um ComplianceCode, recebido {type(self.code).__name__} — "
                "código diagnóstico não é texto livre"
            )
        if not isinstance(self.severity, ErrorSeverity):
            raise TypeError(
                f"severity deve ser um ErrorSeverity, recebido " f"{type(self.severity).__name__}"
            )
        if not isinstance(self.subject_ref, ComplianceSubjectRef):
            raise TypeError("subject_ref deve ser um ComplianceSubjectRef")
        if not isinstance(self.policy_ref, PolicyReference):
            raise TypeError("policy_ref deve ser um PolicyReference")
        if isinstance(self.policy_version, bool) or not isinstance(self.policy_version, int):
            raise TypeError("policy_version deve ser int")
        if self.policy_version != self.policy_ref.policy_version:
            raise ValueError(
                "policy_version diverge de policy_ref.policy_version — um finding "
                "não pode citar duas versões da mesma política"
            )
        object.__setattr__(
            self, "evaluated_at", _canonizar_instante("evaluated_at", self.evaluated_at)
        )
        if not isinstance(self.matched_rule_ids, tuple):
            raise TypeError(
                "matched_rule_ids deve ser tuple — `set` perderia a ordem e `list` "
                "a imutabilidade"
            )
        for indice, identificador in enumerate(self.matched_rule_ids):
            _validar_texto(f"matched_rule_ids[{indice}]", identificador)
        if self.code not in CODIGOS_POR_POLITICA[self.policy_ref.kind]:
            raise ValueError(
                f"{self.code.value} não pertence à família {self.policy_ref.kind.value} — "
                "um finding não cita regra que a política avaliada não tem"
            )
        if self.subject_ref.kind is not SUJEITO_POR_POLITICA[self.policy_ref.kind]:
            raise ValueError(
                f"sujeito {self.subject_ref.kind.value} é incompatível com política "
                f"{self.policy_ref.kind.value}"
            )

    def sort_key(self) -> tuple[str, str]:
        """Ordenação canônica, determinística e estável."""
        return (self.code.value, str(self.subject_ref.subject_coid))


@dataclass(frozen=True)
class ReportEvidence:
    """Evidência dos desfechos que **não** produzem finding.

    `COMPLIANT` precisa dizer o que foi avaliado, senão é
    indistinguível de "nada foi olhado". `POLICY_NOT_APPLICABLE`
    precisa dizer por quê. `INSUFFICIENT_INFORMATION` precisa dizer o
    que falta — e dizer de forma que um programa possa ir buscar.
    """

    policy_window: PolicyWindowState
    applicable_rule_ids: tuple[str, ...] = field(default=())
    missing_observations: tuple[MissingObservation, ...] = field(default=())

    def __post_init__(self) -> None:
        if not isinstance(self.policy_window, PolicyWindowState):
            raise TypeError("policy_window deve ser um PolicyWindowState")
        if not isinstance(self.applicable_rule_ids, tuple):
            raise TypeError("applicable_rule_ids deve ser tuple")
        for indice, identificador in enumerate(self.applicable_rule_ids):
            _validar_texto(f"applicable_rule_ids[{indice}]", identificador)
        if len(set(self.applicable_rule_ids)) != len(self.applicable_rule_ids):
            raise ValueError("applicable_rule_ids repetido — cada regra é citada uma vez")
        if not isinstance(self.missing_observations, tuple):
            raise TypeError("missing_observations deve ser tuple")
        for indice, faltante in enumerate(self.missing_observations):
            if not isinstance(faltante, MissingObservation):
                raise TypeError(
                    f"missing_observations[{indice}] deve ser um MissingObservation — "
                    "texto livre não é consumível por máquina"
                )
        if len(set(self.missing_observations)) != len(self.missing_observations):
            raise ValueError("missing_observations repetido")


@dataclass(frozen=True)
class ComplianceReport:
    """Resultado transitório de **uma** avaliação de conformidade.

    ```text
    COMPLIANT                -> zero findings
    POLICY_NOT_APPLICABLE    -> zero findings, zero regras aplicáveis
    INSUFFICIENT_INFORMATION -> zero findings, ao menos uma observação faltante
    VIOLATION_CONFIRMED      -> ao menos um finding
    ```

    Sem `status` derivado extra, sem score, sem percentual: a E3.10 já
    congelou que "97% de conformidade" não significaria nada
    verificável.

    ## Por que `INSUFFICIENT_INFORMATION` nunca vira `COMPLIANT`

    Três camadas, nenhuma delas convenção. O tipo é congelado; o mesmo
    par de valores não satisfaz os dois desfechos, porque um exige
    `missing_observations` não vazio e o outro exige vazio; e nenhuma
    função deste módulo produz `ComplianceOutcome` a partir de outro
    `ComplianceReport` — não existe caminho de reclassificação.
    """

    outcome: ComplianceOutcome
    subject_ref: ComplianceSubjectRef
    policy_ref: PolicyReference
    policy_version: int
    evaluated_at: datetime
    evidence: ReportEvidence
    findings: tuple[ComplianceFinding, ...] = field(default=())

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ComplianceOutcome):
            raise TypeError(
                f"outcome deve ser um ComplianceOutcome, recebido " f"{type(self.outcome).__name__}"
            )
        if not isinstance(self.subject_ref, ComplianceSubjectRef):
            raise TypeError("subject_ref deve ser um ComplianceSubjectRef")
        if not isinstance(self.policy_ref, PolicyReference):
            raise TypeError("policy_ref deve ser um PolicyReference")
        if not isinstance(self.evidence, ReportEvidence):
            raise TypeError("evidence deve ser um ReportEvidence")
        if isinstance(self.policy_version, bool) or not isinstance(self.policy_version, int):
            raise TypeError("policy_version deve ser int")
        if self.policy_version != self.policy_ref.policy_version:
            raise ValueError("policy_version diverge de policy_ref.policy_version")
        object.__setattr__(
            self, "evaluated_at", _canonizar_instante("evaluated_at", self.evaluated_at)
        )
        if self.subject_ref.kind is not SUJEITO_POR_POLITICA[self.policy_ref.kind]:
            raise ValueError(
                f"sujeito {self.subject_ref.kind.value} é incompatível com política "
                f"{self.policy_ref.kind.value}"
            )

        if not isinstance(self.findings, tuple):
            raise TypeError("findings deve ser tuple")
        for indice, finding in enumerate(self.findings):
            if not isinstance(finding, ComplianceFinding):
                raise TypeError(f"findings[{indice}] deve ser um ComplianceFinding")

        self._exigir_vinculo_exato()
        self._exigir_ordem_canonica()
        self._exigir_coerencia_do_desfecho()

    # ------------------------------------------------------------------
    # Invariantes
    # ------------------------------------------------------------------

    def _exigir_vinculo_exato(self) -> None:
        """Cada finding cita **este** sujeito, política, versão e instante.

        Sem isto, um relatório poderia reunir findings de avaliações
        diferentes e apresentá-los como se fossem uma só — e a versão da
        política, que é o que dá sentido ao diagnóstico, deixaria de ser
        verificável a partir do agregado.
        """
        for indice, finding in enumerate(self.findings):
            if finding.subject_ref != self.subject_ref:
                raise ValueError(
                    f"findings[{indice}] descreve outro sujeito — o relatório é de "
                    "uma avaliação, não de um lote"
                )
            # A VERSÃO é verificada ANTES da referência inteira, e a ordem
            # importa para quem lê o erro: `PolicyReference` já carrega a
            # versão, então uma divergência de versão faria as duas
            # checagens falharem — e a mensagem genérica esconderia
            # justamente a dimensão que dá sentido ao diagnóstico.
            if finding.policy_version != self.policy_version:
                raise ValueError(
                    f"findings[{indice}] cita a versão {finding.policy_version} e o "
                    f"relatório avalia a {self.policy_version}"
                )
            if finding.policy_ref != self.policy_ref:
                raise ValueError(f"findings[{indice}] cita outra política")
            if finding.evaluated_at != self.evaluated_at:
                raise ValueError(
                    f"findings[{indice}] tem instante diferente do relatório — um "
                    "diagnóstico é datado, e duas datas descrevem duas avaliações"
                )

    def _exigir_ordem_canonica(self) -> None:
        """Ordem determinística e sem código repetido para o mesmo sujeito."""
        chaves = [finding.sort_key() for finding in self.findings]
        if chaves != sorted(chaves):
            raise ValueError(
                "findings fora da ordem canônica (code, subject_coid) — ordem "
                "instável tornaria o resultado não determinístico"
            )
        if len(set(chaves)) != len(chaves):
            raise ValueError(
                "finding repetido: o mesmo código para o mesmo sujeito seria contado "
                "duas vezes por quem lê"
            )

    def _exigir_coerencia_do_desfecho(self) -> None:
        """A matriz fechada entre desfecho, findings e evidência."""
        tem_finding = bool(self.findings)
        faltantes = bool(self.evidence.missing_observations)
        aplicaveis = bool(self.evidence.applicable_rule_ids)

        if self.outcome is ComplianceOutcome.VIOLATION_CONFIRMED:
            if not tem_finding:
                raise ValueError(
                    "violation_confirmed exige ao menos um finding — uma violação sem "
                    "evidência localizada é acusação, não diagnóstico"
                )
            return

        if tem_finding:
            raise ValueError(
                f"{self.outcome.value} não admite finding — só a violação confirmada "
                "localiza condição no sujeito"
            )

        if self.outcome is ComplianceOutcome.INSUFFICIENT_INFORMATION:
            if not faltantes:
                raise ValueError(
                    "insufficient_information exige missing_observations — uma "
                    "insuficiência que não diz o que falta não é acionável"
                )
            return

        if faltantes:
            raise ValueError(
                f"{self.outcome.value} não admite missing_observations — decidir com "
                "observação faltante é afirmar o que ninguém observou"
            )

        if self.outcome is ComplianceOutcome.POLICY_NOT_APPLICABLE and aplicaveis:
            raise ValueError(
                "policy_not_applicable não admite applicable_rule_ids — se alguma "
                "regra alcança o sujeito, a política se aplica"
            )
        if self.outcome is ComplianceOutcome.COMPLIANT and not aplicaveis:
            raise ValueError(
                "compliant exige applicable_rule_ids — conformidade sem regra "
                "avaliada seria indistinguível de nada ter sido olhado"
            )

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    @property
    def violation_codes(self) -> tuple[ComplianceCode, ...]:
        """Códigos das violações, na ordem canônica. Contagem, não score."""
        return tuple(finding.code for finding in self.findings)
