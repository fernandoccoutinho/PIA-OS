"""
Vocabulários fechados da camada de governança (E4.3).

Todos são `StrEnum` fechados, como os enums de domínio da E3
(`AccessibilityState`, `CausalEventType`): ampliar exige EDR. Um
vocabulário aberto de operações ou de resultados seria a porta por
onde entraria, sem revisão, a semântica que este módulo existe para
delimitar.
"""

from enum import StrEnum


class CognitiveOperation(StrEnum):
    """Operações cognitivas que uma policy pode regular.

    São exatamente as sete que `E4_GOVERNANCE_BOUNDARIES.md` §9 lista
    como o que governança "pode futuramente controlar" — nenhuma
    inventada aqui.

    Nomear uma operação **não** a implementa:

        PERMISSION != OPERATION IMPLEMENTATION

    Permitir `CONSOLIDATE` não cria consolidação; E4.5 sequer existe.
    A policy diz o que seria admissível; quem executa é outro módulo,
    quando houver.
    """

    READ = "read"
    """Ler patrimônio cognitivo."""

    REFERENCE = "reference"
    """Referenciar um objeto sem transformá-lo."""

    DERIVE = "derive"
    """Derivar um novo objeto a partir de outro."""

    TRANSFORM = "transform"
    """Transformar, produzindo nova versão ou derivação."""

    EXPOSE = "expose"
    """Expor patrimônio para fora do sistema."""

    SYNCHRONIZE = "synchronize"
    """Transmitir patrimônio entre instâncias."""

    CONSOLIDATE = "consolidate"
    """Consolidar múltiplas fontes numa síntese."""


class GovernanceEffect(StrEnum):
    """Efeito declarado por uma regra.

    Apenas dois, e deliberadamente: um terceiro efeito ("neutro",
    "auditar", "avisar") transformaria a regra em fluxo de execução, e
    governança aqui decide admissibilidade — não orquestra
    comportamento.
    """

    ADMIT = "admit"
    DENY = "deny"


class GovernanceOutcome(StrEnum):
    """Resultado de uma avaliação.

    **Três resultados, não dois.** Sem `NOT_APPLICABLE`, "nenhuma
    regra se aplicou" colapsaria em `INADMISSIBLE` e ficaria
    indistinguível de "uma regra negou explicitamente" — o mesmo
    colapso diagnóstico que a E3.12 provou não cometer no *negative
    strong gate*, onde cinco defeitos produzem cinco diagnósticos.

    Consequência operacional que precisa ficar dita: `NOT_APPLICABLE`
    **não concede**. Quem consome trata como não-admissão, mas sabendo
    que a causa é ausência de regra, não proibição — e essas duas
    situações pedem providências diferentes de quem administra a
    instalação.
    """

    ADMISSIBLE = "admissible"
    INADMISSIBLE = "inadmissible"
    NOT_APPLICABLE = "not_applicable"
