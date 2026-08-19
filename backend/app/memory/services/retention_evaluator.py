"""
`RetentionEvaluator` — avaliação **pura** de retenção (`E4.9.9.c`).

```text
ASSESSMENT_ELIGIBILITY != DELETION_DECISION
EVALUATION             != DISPOSITION
NO_POLICY              != ELIGIBLE
CLOCK_INJECTED         = REQUIRED
```

## Função, não classe

Sem estado, sem `__init__`, sem sessão, sem repositório. Um manager com
`__init__(session)` convidaria a consultar o banco lá dentro, e a leitura
de patrimônio é justamente o que esta fatia não faz.

Tudo entra por argumento: candidato, regras, janela da policy e o
instante da avaliação.

## O relógio é injetado, e é obrigatório

```text
CLOCK_INJECTED = REQUIRED
```

`datetime.now()` interno tornaria a função impura e o teste dependente do
relógio da máquina. Sem default: um default seria `now()` disfarçado.

## O que esta fatia NÃO faz

```text
SCHEDULER                 = NONE
DISPOSITION               = NONE
PERSISTENCE               = NONE
PATRIMONY_ENUMERATION     = NONE
APPROVAL_ENVELOPE         = NONE
RETENTION_POLICY_REPOSITORY_CONSUMER = NONE
```

Não enumera patrimônio, não lê banco, não agenda, não dispõe, não forma
aprovação e não escreve recibo. Responde a uma pergunta sobre **um**
candidato quando alguém a faz.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.memory.models.retention_assessment_enums import RetentionAssessmentDecision
from app.memory.models.retention_enums import RetentionAnchor, RetentionScopeKind
from app.memory.models.target_resolution_enums import LegacyProtectionState
from app.memory.schemas.retention import RetentionRule


def _validar_instante(nome: str, valor: object) -> datetime:
    if not isinstance(valor, datetime):
        raise TypeError(f"{nome} deve ser datetime, recebido {type(valor).__name__}")
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError(
            f"{nome} deve ser timezone-aware — instante ingênuo não fixa momento algum"
        )
    return valor


@dataclass(frozen=True)
class RetentionCandidate:
    """O item sobre o qual se pergunta, e nada além do necessário.

    Sem conteúdo, sem localizador, sem capacidade, sem credencial. A
    avaliação de retenção não precisa saber **o que** o item é para dizer
    se um prazo venceu.
    """

    subject_coid: uuid.UUID
    domain_id: uuid.UUID
    created_at: datetime
    legacy_protection_state: LegacyProtectionState
    """Obrigatório, sem default (`E4.9.8.3`).

    ```text
    LEGACY_PROTECTION_OVERRIDES_RETENTION_ELIGIBILITY
    ```

    Um default faria a omissão parecer `NOT_PROTECTED`, e um item
    protegido esquecido apareceria como elegível — a forma exata da
    autoridade fabricada que a E4.9.7.4 fechou.
    """

    def __post_init__(self) -> None:
        if not isinstance(self.subject_coid, uuid.UUID):
            raise TypeError("subject_coid deve ser UUID")
        if not isinstance(self.domain_id, uuid.UUID):
            raise TypeError("domain_id deve ser UUID")
        _validar_instante("created_at", self.created_at)
        if not isinstance(self.legacy_protection_state, LegacyProtectionState):
            raise TypeError(
                f"legacy_protection_state deve ser um LegacyProtectionState, "
                f"recebido {type(self.legacy_protection_state).__name__}"
            )


@dataclass(frozen=True)
class RetentionAssessment:
    """O que a avaliação concluiu, e sobre que fundamento.

    ```text
    EVERY_DECISION_CITES_ITS_BASIS
    ```

    Uma decisão sem fundamento citável seria impossível de contestar, e a
    E4.9.6 estabeleceu que `rule_id` existe para ser citado como
    fundamento de uma avaliação futura. Esta é a avaliação futura.
    """

    decision: RetentionAssessmentDecision
    subject_coid: uuid.UUID
    evaluated_at: datetime
    applicable_rule_ids: tuple[str, ...] = field(default=())
    """Todas as regras vigentes que alcançam o candidato, em ordem
    determinística — nunca `set`, que perderia a ordem."""

    due_rule_ids: tuple[str, ...] = field(default=())
    """Quais delas já venceram **individualmente**.

    Distinto de `applicable_rule_ids`: com duas regras aplicáveis, uma
    pode ter vencido e a outra não, e o resultado tem de mostrar as duas
    coisas.
    """

    effective_due_at: datetime | None = field(default=None)
    """`MAX(due_at)` entre as regras aplicáveis.

    ```text
    effective_due_at = MAX(due_at de todas as regras aplicáveis)
    ```

    O **máximo**, não o mínimo: uma regra curta não pode neutralizar
    outra que exige preservação mais longa. Se uma regra diz 30 dias e
    outra diz 365, o item só é avaliável aos 365.
    """

    next_due_at: datetime | None = field(default=None)
    """Quando a situação muda, enquanto ainda não elegível.

    Igual a `effective_due_at` em `NOT_YET_DUE`; `None` nas demais
    decisões, porque não há vencimento futuro a informar.
    """

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RetentionAssessmentDecision):
            raise TypeError("decision deve ser um RetentionAssessmentDecision")
        if not isinstance(self.subject_coid, uuid.UUID):
            raise TypeError("subject_coid deve ser UUID")
        _validar_instante("evaluated_at", self.evaluated_at)
        for nome, valor in (
            ("applicable_rule_ids", self.applicable_rule_ids),
            ("due_rule_ids", self.due_rule_ids),
        ):
            if not isinstance(valor, tuple):
                raise TypeError(f"{nome} deve ser tuple — list perderia imutabilidade")
        if not set(self.due_rule_ids) <= set(self.applicable_rule_ids):
            raise ValueError(
                "due_rule_ids contém regra que não é aplicável — uma regra não "
                "pode vencer sem alcançar o candidato"
            )
        if self.effective_due_at is not None:
            _validar_instante("effective_due_at", self.effective_due_at)
        if self.next_due_at is not None:
            _validar_instante("next_due_at", self.next_due_at)

        if self.decision is RetentionAssessmentDecision.NOT_YET_DUE:
            if self.next_due_at is None or self.next_due_at != self.effective_due_at:
                raise ValueError(
                    "not_yet_due exige next_due_at igual a effective_due_at — "
                    "quem ainda não venceu precisa saber quando vence"
                )
        elif self.next_due_at is not None:
            raise ValueError(
                f"{self.decision.value} não carrega next_due_at — só faz sentido "
                "informar vencimento futuro a quem ainda não venceu"
            )


def _due_at(candidato: RetentionCandidate, regra: RetentionRule) -> datetime:
    """Instante em que a regra vence para este candidato.

    A âncora é `created_at`, única desta versão. O preflight da E4.9.6
    mediu que `updated_at` se move por transição de acessibilidade, e
    ancorar nele faria um objeto reclassificado **rejuvenescer**.
    """
    if regra.anchor is not RetentionAnchor.CREATED_AT:  # pragma: no cover
        raise ValueError(
            f"âncora {regra.anchor.value} não é suportada — a única desta versão "
            "é created_at, e inferir outra seria inventar semântica de retenção"
        )
    return candidato.created_at + timedelta(days=regra.minimum_age_days)


def _alcanca(candidato: RetentionCandidate, regra: RetentionRule) -> bool:
    """A regra fala deste candidato?"""
    if regra.scope_kind is RetentionScopeKind.ALL_LOCAL_PATRIMONY:
        return True
    return candidato.domain_id in regra.domain_ids


def avaliar_retencao(
    *,
    candidate: RetentionCandidate,
    rules: tuple[RetentionRule, ...],
    policy_effective_from: datetime,
    policy_effective_until: datetime | None,
    evaluated_at: datetime,
) -> RetentionAssessment:
    """Avalia **um** candidato contra as regras de **uma** policy.

    Função pura: mesma entrada, mesma saída, sem relógio interno, sem I/O.

    ## Precedência

    ```text
    1. POLICY_NOT_EFFECTIVE        janela [effective_from, effective_until)
    2. OUT_OF_SCOPE                nenhuma regra alcança
    3. PRESERVE_LEGACY_PROTECTED   o titular pediu para preservar
    4. NOT_YET_DUE                 evaluated_at < MAX(due_at)
    5. ASSESS_AND_INFORM           evaluated_at >= MAX(due_at)
    ```

    ## Por que o MÁXIMO

    ```text
    effective_due_at = MAX(due_at de todas as regras aplicáveis)
    ```

    Com o mínimo, uma regra de 30 dias neutralizaria outra que exige 365 —
    o item viraria avaliável enquanto uma política vigente ainda pedia
    preservação. O máximo é a leitura conservadora, e é a única que não
    perde uma exigência de preservação por causa de outra mais curta.

    O resultado cita **todas** as aplicáveis e **quais já venceram
    individualmente**, para que a diferença fique visível a quem lê.
    """
    _validar_instante("evaluated_at", evaluated_at)
    _validar_instante("policy_effective_from", policy_effective_from)
    if policy_effective_until is not None:
        _validar_instante("policy_effective_until", policy_effective_until)
        if policy_effective_until <= policy_effective_from:
            raise ValueError(
                "policy_effective_until deve ser posterior a policy_effective_from — "
                "janela vazia ou invertida não é janela"
            )
    if not isinstance(candidate, RetentionCandidate):
        raise TypeError("candidate deve ser um RetentionCandidate")
    if not isinstance(rules, tuple):
        raise TypeError("rules deve ser tuple — list perderia imutabilidade")
    for indice, regra in enumerate(rules):
        if not isinstance(regra, RetentionRule):
            raise TypeError(f"rules[{indice}] deve ser um RetentionRule")

    if candidate.created_at > evaluated_at:
        raise ValueError(
            "candidate.created_at posterior a evaluated_at — um item não é avaliado "
            "antes de existir"
        )

    def _resultado(
        decisao: RetentionAssessmentDecision,
        *,
        aplicaveis: tuple[str, ...] = (),
        vencidas: tuple[str, ...] = (),
        efetivo: datetime | None = None,
        proximo: datetime | None = None,
    ) -> RetentionAssessment:
        return RetentionAssessment(
            decision=decisao,
            subject_coid=candidate.subject_coid,
            evaluated_at=evaluated_at,
            applicable_rule_ids=aplicaveis,
            due_rule_ids=vencidas,
            effective_due_at=efetivo,
            next_due_at=proximo,
        )

    # 1. A policy vigora? Janela de início INCLUSIVO e fim EXCLUSIVO.
    if evaluated_at < policy_effective_from:
        return _resultado(RetentionAssessmentDecision.POLICY_NOT_EFFECTIVE)
    if policy_effective_until is not None and evaluated_at >= policy_effective_until:
        return _resultado(RetentionAssessmentDecision.POLICY_NOT_EFFECTIVE)

    # 2. Alguma regra alcança o candidato?
    aplicaveis = tuple(regra for regra in rules if _alcanca(candidate, regra))
    if not aplicaveis:
        return _resultado(RetentionAssessmentDecision.OUT_OF_SCOPE)

    ids_aplicaveis = tuple(regra.rule_id for regra in aplicaveis)
    vencimentos = {regra.rule_id: _due_at(candidate, regra) for regra in aplicaveis}
    efetivo = max(vencimentos.values())
    vencidas = tuple(
        regra.rule_id for regra in aplicaveis if evaluated_at >= vencimentos[regra.rule_id]
    )

    # 3. Proteção de legado vem ANTES do prazo: prazo cumprido não revoga
    #    escolha do titular.
    if candidate.legacy_protection_state is LegacyProtectionState.PROTECTED:
        return _resultado(
            RetentionAssessmentDecision.PRESERVE_LEGACY_PROTECTED,
            aplicaveis=ids_aplicaveis,
            vencidas=vencidas,
            efetivo=efetivo,
        )

    # 4. Ainda não venceu o MAIOR prazo aplicável.
    if evaluated_at < efetivo:
        return _resultado(
            RetentionAssessmentDecision.NOT_YET_DUE,
            aplicaveis=ids_aplicaveis,
            vencidas=vencidas,
            efetivo=efetivo,
            proximo=efetivo,
        )

    # 5. Inicia-se AVALIAÇÃO — e nada além disso.
    return _resultado(
        RetentionAssessmentDecision.ASSESS_AND_INFORM,
        aplicaveis=ids_aplicaveis,
        vencidas=vencidas,
        efetivo=efetivo,
    )
