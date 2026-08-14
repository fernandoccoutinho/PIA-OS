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

    PROHIBITED = "prohibited"
    """Recusado pela fronteira de segurança da plataforma (E4.3.1).

    Acrescentado, e distinto de `INADMISSIBLE` de propósito: este é o
    único resultado que **nenhuma policy local pode reverter**.
    Colapsá-lo em `INADMISSIBLE` faria parecer que uma regra local com
    `ADMIT` poderia tê-lo evitado — e ela não pode.

    Nenhum outro resultado foi acrescentado.
    """


class CriticalCapability(StrEnum):
    """Capacidades cuja habilitação operacional a plataforma recusa.

    Vocabulário **fechado e mínimo**, e o critério de admissão é
    estreito: capacidade cuja entrega operacional causa dano grave e
    irreversível a pessoas. Ampliar exige EDR.

    Estas são **capacidades**, não temas:

        TOPIC != CAPABILITY

    Falar sobre exploração infantil para prevenir, detectar, proteger,
    responder, denunciar ou pesquisar não habilita capacidade alguma —
    e bloquear por tema destruiria exatamente esse trabalho.
    """

    CHILD_SEXUAL_EXPLOITATION = "child_sexual_exploitation"
    """Produção, obtenção ou facilitação de material ou ato de
    exploração sexual infantil."""

    MINOR_TARGETING_FOR_EXPLOITATION = "minor_targeting_for_exploitation"
    """Seleção, perfilamento ou aliciamento de menores para
    exploração — inclusive quando apresentado como segmentação,
    triagem ou análise de audiência."""

    WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT = "weapon_of_mass_destruction_enablement"
    """Facilitação operacional de armas químicas, biológicas,
    radiológicas ou nucleares."""

    CATASTROPHIC_HARM_ENABLEMENT = "catastrophic_harm_enablement"
    """Facilitação operacional de dano catastrófico em larga escala que
    não é, ele próprio, uma arma — sabotagem de infraestrutura crítica,
    por exemplo.

    Única categoria acrescentada além das nomeadas no corretivo, e
    justificada: o requisito fala em "armas **ou** dano catastrófico",
    duas coisas. Sem esta, a fronteira teria um vão que o próprio
    enunciado descreve.
    """


class CapabilityEngagement(StrEnum):
    """Como a operação se relaciona com a capacidade crítica.

    É esta dimensão — e não o tema — que separa o que a plataforma
    recusa do que ela permite que a governança local decida:

        KNOWLEDGE != EXECUTION
        ANALYSIS  != OPERATIONAL ENABLEMENT
    """

    OPERATIONAL_ENABLEMENT = "operational_enablement"
    """Entregaria capacidade utilizável para causar o dano."""

    ANALYTICAL = "analytical"
    """Histórico, científico, jurídico, jornalístico, analítico."""

    PREVENTIVE = "preventive"
    """Prevenção, detecção, proteção, resposta, denúncia ou pesquisa
    ética — inclusive com dados sintéticos."""

    UNSPECIFIED = "unspecified"
    """Não estabelecido.

    Diante de capacidade crítica isto **proíbe**, e a razão é o
    princípio, não a cautela genérica:

        MISSING SAFE INTENT != AUTHORIZATION TO INVENT ONE

    Tratar "não sei" como "provavelmente tudo bem" seria fabricar
    finalidade legítima ausente.
    """
