"""
`IntentAuthorizationBroker` — o produtor autorizado da E8.

O broker não classifica e não decide admissibilidade. Ele faz quatro
coisas, e recusa tecnicamente se qualquer uma falhar:

1. exige classificação de uma porta semântica autorizada;
2. verifica que o classificador cobre o vocabulário fechado inteiro
   (não-vacuidade);
3. verifica que o que voltou é tipado nos valores canônicos;
4. vincula o resultado ao objetivo, à versão do classificador e a uma
   janela de validade.

    ABSENCE -> TECHNICAL UNAVAILABILITY
    MISSING DESCRIPTOR != NOT_APPLICABLE

Toda falha vira `IntentAuthorizationUnavailableError`, com zero efeito.
Nenhum caminho deste módulo devolve descritor de conveniência,
engajamento inventado ou conjunto vazio "por precaução": um descritor
fabricado seria pior que descritor nenhum, porque atravessaria a
fronteira E4 parecendo legítimo.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.authorization.descriptor import AuthorizedCapabilityDescriptor, objective_digest
from app.authorization.ports import SemanticCapabilityClassifierPort, SemanticClassification
from app.memory.models.governance_enums import (
    CapabilityEngagement,
    CognitiveOperation,
    CriticalCapability,
)

DEFAULT_DESCRIPTOR_TTL = timedelta(minutes=5)
"""Validade curta por default.

Curta porque o descritor é uma afirmação sobre um objetivo num instante,
não uma licença. Ampliá-la é decisão de quem chama, explicitamente.
"""

REQUIRED_CAPABILITY_COVERAGE: frozenset[CriticalCapability] = frozenset(CriticalCapability)
"""Cobertura exigida: o vocabulário fechado **inteiro**.

Derivado do enum de propósito, e a diferença em relação a
`EMPTY_OPERATIONS_SCOPE_V1` (que é enumerado literalmente, nunca
derivado) é material e vale registrar: lá, derivar do enum ampliaria
retroativamente autorizações já publicadas — o default seguro é o
conjunto pequeno. Aqui, o default seguro é o conjunto **grande**: se uma
capacidade crítica for acrescentada por EDR, todo classificador que não
a cobrir deve passar a ser recusado automaticamente, sem ninguém
lembrar de atualizar uma lista.

    NEW CAPABILITY -> EXISTING CLASSIFIERS BECOME INSUFFICIENT
"""


class IntentAuthorizationUnavailableError(Exception):
    """A E8 não pôde produzir descritor — falha técnica, nunca permissão.

    Código próprio `PIA-8070`, e não reuso de `PIA-8069`: aquele fala do
    gate de proteção humana que não pôde decidir; este fala do produtor
    que não pôde classificar. Reusar o código faria as duas causas
    virarem a mesma linha de log, e elas se resolvem em lugares
    diferentes.
    """

    error_code = "PIA-8070"

    def __init__(self, reason: str) -> None:
        super().__init__(f"{self.error_code}: {reason}")
        self.reason = reason


class IntentAuthorizationBroker:
    """Produtor autorizado do descritor semântico (E8 IAB)."""

    def __init__(
        self,
        classifier: SemanticCapabilityClassifierPort,
        *,
        ttl: timedelta = DEFAULT_DESCRIPTOR_TTL,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("ttl deve ser estritamente positivo")
        self._classifier = classifier
        self._ttl = ttl
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)

    def authorize(
        self,
        *,
        objective: str,
        operation: CognitiveOperation,
        moment: datetime | None = None,
    ) -> AuthorizedCapabilityDescriptor:
        """Produz o descritor para **este** objetivo, ou recusa tecnicamente.

        `moment` é injetável e lido **uma vez**. Duas leituras de relógio
        num mesmo fluxo envelhecem entre si — foi o defeito
        `MULTIPLE_CLOCK_READS = FLAKY_BY_CONSTRUCTION` da Chain123, e a
        correção é a mesma aqui.
        """
        if not isinstance(operation, CognitiveOperation):
            raise IntentAuthorizationUnavailableError(
                "operation deve ser um CognitiveOperation tipado"
            )

        try:
            digest = objective_digest(objective)
        except (TypeError, ValueError) as erro:
            raise IntentAuthorizationUnavailableError(f"objetivo inválido: {erro}") from erro

        self._require_non_vacuous_coverage()

        classificacao = self._require_classification(objective)

        instante = moment if moment is not None else self._clock()
        if not isinstance(instante, datetime) or instante.tzinfo is None:
            raise IntentAuthorizationUnavailableError(
                "moment deve ser um datetime consciente de fuso"
            )
        instante = instante.astimezone(UTC)

        versao = self._classifier.classifier_version
        if not isinstance(versao, str) or not versao.strip():
            raise IntentAuthorizationUnavailableError(
                "classificador não declarou classifier_version utilizável"
            )

        try:
            return AuthorizedCapabilityDescriptor(
                operation=operation,
                capabilities=classificacao.capabilities,
                engagement=classificacao.engagement,
                objective_sha256=digest,
                classifier_version=versao,
                evaluated_at=instante,
                valid_until=instante + self._ttl,
                stated_intent=self._preservable_intent(classificacao),
            )
        except (TypeError, ValueError) as erro:
            raise IntentAuthorizationUnavailableError(
                f"descritor não pôde ser construído: {erro}"
            ) from erro

    def _require_non_vacuous_coverage(self) -> None:
        """Recusa classificador que não alcança o vocabulário inteiro."""
        try:
            cobertura = self._classifier.covered_capabilities
        except Exception as erro:
            raise IntentAuthorizationUnavailableError(
                f"classificador não declarou cobertura: {erro}"
            ) from erro

        if isinstance(cobertura, str | bytes) or not hasattr(cobertura, "__iter__"):
            raise IntentAuthorizationUnavailableError(
                "covered_capabilities deve ser um iterável de CriticalCapability"
            )
        itens = frozenset(cobertura)
        if any(not isinstance(item, CriticalCapability) for item in itens):
            raise IntentAuthorizationUnavailableError(
                "covered_capabilities aceita apenas CriticalCapability"
            )

        faltando = REQUIRED_CAPABILITY_COVERAGE - itens
        if faltando:
            nomes = ", ".join(sorted(c.value for c in faltando))
            raise IntentAuthorizationUnavailableError(
                f"classificador não cobre o vocabulário fechado — faltam: {nomes}"
            )

    def _require_classification(self, objective: str) -> SemanticClassification:
        """Obtém a classificação, convertendo qualquer falha em recusa."""
        try:
            classificacao = self._classifier.classify(objective=objective)
        except Exception as erro:
            raise IntentAuthorizationUnavailableError(f"classificador falhou: {erro}") from erro

        if not isinstance(classificacao, SemanticClassification):
            raise IntentAuthorizationUnavailableError(
                "classificador devolveu tipo fora do contrato — "
                "SemanticClassification é obrigatório"
            )
        return classificacao

    @staticmethod
    def _preservable_intent(classificacao: SemanticClassification) -> str | None:
        """Só carrega `rationale` quando o engajamento já o torna preservável.

        Mesma regra de `_preserved_intent` na fronteira E4, e pela mesma
        razão: em `UNSPECIFIED` não há finalidade legítima estabelecida,
        e escrevê-la seria fabricar a que falta.
        """
        if classificacao.engagement in (
            CapabilityEngagement.ANALYTICAL,
            CapabilityEngagement.PREVENTIVE,
        ):
            return classificacao.rationale
        return None
