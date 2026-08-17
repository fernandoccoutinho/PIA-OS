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

    Sete vieram da E4.3 — o que `E4_GOVERNANCE_BOUNDARIES.md` §9 lista
    como o que governança "pode futuramente controlar". A oitava,
    `ACCESSIBILITY_TRANSITION`, foi acrescentada pelo corretivo E4.3.3,
    com EDR próprio, para fechar a lacuna que o preflight da E4.7
    confirmou (`GOVERNANCE_OPERATION_GAP`).

    A nona, a décima e a décima primeira — `RETENTION_ASSESSMENT`,
    `RETENTION_DISPOSITION` e `LEGAL_ERASURE` — vieram do corretivo
    E4.3.5, também com EDR próprio, para fechar a Stop Condition
    primária que o preflight da E4.9 encontrou
    (`RETENTION_OPERATION_AUTHORITY_GAP`). Nenhuma inventada aqui.

    **Ampliar este enum de novo exige novo EDR.** E o alcance do curinga
    histórico é definido por `EMPTY_OPERATIONS_SCOPE_V1`, não por "todos
    os membros" — ver a nota daquele conjunto.

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

    ACCESSIBILITY_TRANSITION = "accessibility_transition"
    """Alterar o `AccessibilityState` de um `CognitiveObject` (E4.3.3).

    **Distinta de `TRANSFORM`, e a distinção é material:**

        ACCESSIBILITY TRANSITION != COGNITIVE TRANSFORMATION

    `TRANSFORM` produz nova versão ou derivação. Uma transição de
    acessibilidade altera um estado do **mesmo** objeto: não cria COID,
    CLID, derivação, revisão, `TransformationRecord` nem `LineageEdge`,
    não reescreve proveniência, não apaga história causal e não altera
    existência.

        ACCESSIBILITY != EXISTENCE
        INACCESSIBLE != NONEXISTENT
        CAUSALLY_EXTINCT != HISTORICAL_ERASURE

    Reusar `TRANSFORM` daria autoridade sobre acessibilidade a quem
    recebeu autoridade apenas para transformação cognitiva:

        AUTHORIZATION TO TRANSFORM != AUTHORIZATION TO CHANGE ACCESSIBILITY

    Nomear a operação **não** a implementa. A E4.3.3 cria a autoridade
    representável; quem executa transições é a E4.7, que não existe:

        PERMISSION != EXECUTION
        AUTHORITY VOCABULARY != ACCESSIBILITY MANAGER
    """

    RETENTION_ASSESSMENT = "retention_assessment"
    """Avaliar a política de retenção de um sujeito num contexto (E4.3.5).

    Autoriza **avaliar**, e nada além disso. Não escreve, não esquece,
    não dispõe e não apaga.

    **Por que não `READ`.** Uma avaliação de retenção de fato lê dados
    que `READ` já alcança, e nesse sentido estreito não amplia acesso a
    informação nenhuma. Mas o que ela produz não é uma leitura: é uma
    afirmação sobre a permanência futura do sujeito. Reusar `READ` faria
    toda policy que hoje admite leitura passar a admitir, sem novo ato de
    publicação, uma capacidade que ninguém lhe concedeu:

        AUTHORITY TO READ != AUTHORITY TO ASSESS RETENTION
    """

    RETENTION_DISPOSITION = "retention_disposition"
    """Propor ou autorizar uma disposição tipada após a avaliação (E4.3.5).

    Separada de `RETENTION_ASSESSMENT` porque avaliar e dispor são atos
    distintos, e o segundo pressupõe o primeiro sem se confundir com ele:

        AUTHORITY TO ASSESS != AUTHORITY TO DISPOSE
        RETENTION EXPIRY    != AUTHORIZATION TO DELETE

    Autoriza representar a disposição. **Não** executa apagamento nem
    fabrica recibo — quem executa é a E4.9, que não existe.
    """

    LEGAL_ERASURE = "legal_erasure"
    """Autoridade específica para o efeito de apagamento legítimo (E4.3.5).

    Distinta das duas anteriores, e a distinção é material: uma
    disposição pode expirar sem que nada seja apagado, e um apagamento
    obrigatório pode ser exigido fora de qualquer prazo de retenção.

        AUTHORITY TO DISPOSE != AUTHORITY TO ERASE
        AUTHORITY TO ERASE   != EFFECT EXECUTED

    Autoriza **representar** essa autoridade numa policy. Não interpreta
    lei, não localiza storage, não alcança conteúdo externo e não apaga
    história causal — o preflight da E4.9 registrou que nenhuma dessas
    capacidades existe hoje, e nomear a operação não cria nenhuma delas:

        PERMISSION != EXECUTION
        AUTHORITY VOCABULARY != ERASURE MECHANISM
    """


EMPTY_OPERATIONS_SCOPE_V1: frozenset[CognitiveOperation] = frozenset(
    {
        CognitiveOperation.READ,
        CognitiveOperation.REFERENCE,
        CognitiveOperation.DERIVE,
        CognitiveOperation.TRANSFORM,
        CognitiveOperation.EXPOSE,
        CognitiveOperation.SYNCHRONIZE,
        CognitiveOperation.CONSOLIDATE,
    }
)
"""Alcance do curinga histórico `operations=()` (corretivo E4.3.3).

Uma regra publicada com `operations=frozenset()` foi escrita quando o
vocabulário tinha **estas sete** operações. Ela continua alcançando
todas elas — e apenas elas.

    EMPTY OPERATIONS != ALL FUTURE OPERATIONS
    OLD AUTHORIZATION != CONSENT TO A NEW CAPABILITY
    FUTURE OPERATION DEFAULT = EXPLICIT OPT-IN REQUIRED

**Enumerado literalmente, e nunca derivado do enum.** Escrever
`set(CognitiveOperation)` reintroduziria exatamente o defeito: o
conjunto cresceria sozinho a cada operação nova, e policies imutáveis
publicadas no passado passariam a autorizar capacidades que ninguém
lhes concedeu — sem novo ato de publicação.

**Blacklist foi rejeitada.** Uma lista de "operações sensíveis" depende
de alguém lembrar de classificar cada operação futura; esquecer uma
devolveria a autorização retroativa em silêncio. O conjunto positivo
faz o default seguro ser automático.

`V1` no nome porque este é o envelope de autoridade das policies
publicadas até a cadeia 53. Incluir uma operação futura aqui seria
ampliar retroativamente o alcance de versões imutáveis, e exige EDR
explícito — não é manutenção de rotina.

**O corretivo E4.3.5 não tocou este conjunto**, e é justamente o
comportamento que se esperava dele: `RETENTION_ASSESSMENT`,
`RETENTION_DISPOSITION` e `LEGAL_ERASURE` ficam de fora, como
`ACCESSIBILITY_TRANSITION` já ficava. Uma policy publicada antes deles
resolve as três como `NOT_APPLICABLE`.

    OLD WILDCARD AUTHORITY != FUTURE RETENTION AUTHORITY
"""


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
