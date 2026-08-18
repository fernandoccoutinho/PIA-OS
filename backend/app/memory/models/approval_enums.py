"""
Vocabulários fechados da aprovação destrutiva (`E4.9.8`).

```text
PROPOSAL        != APPROVAL
APPROVAL        != EXECUTION
EXECUTION       != RECEIPT
APPROVAL_RECORD != ERASURE_RECORD
```

Seis `StrEnum` fechados, no padrão da E3 e da E4.3: ampliar exige EDR.
Nenhum deles duplica fonte da verdade existente — o inventário do
repositório na cadeia 84 não encontrou nenhum símbolo de *approval*,
*assurance*, *nonce*, *channel*, *voice* ou *trash* em `backend/app`.

**Por que não reutilizar enums vizinhos.** `RetentionExpiryAction`
descreve o que a expiração de uma policy dispara, e o §5.3 do prompt
proíbe usá-lo para finalidade que ele nega — expiração inicia avaliação,
nunca exclusão. `ErasureOutcome` descreve o que uma tentativa **material**
observou, e `APPROVED`, `PENDING` ou `PROPOSED` ali fariam o recibo
herdar estados que ele proíbe desde a E4.9.0.

```text
EXPIRY_ACTION   != DESTRUCTIVE_OPERATION
ERASURE_OUTCOME != APPROVAL_STATE
```
"""

from enum import StrEnum


class DestructiveOperation(StrEnum):
    """O que a proposta pede — exatamente duas operações.

    ```text
    TRASH != LEGAL_ERASURE
    TRASHED != SPACE_RECLAIMED
    ```

    A distinção é do adendo v1.4 e da E4.9.3: mover para a lixeira é
    **reversível** e não recupera espaço por si; apagamento definitivo é
    irreversível. Colapsá-las num único `delete` faria a interface
    prometer reversibilidade que o efeito não teria — ou o contrário.

    Não existe membro genérico nem string livre: uma operação ambígua é
    inconstruível.
    """

    MOVE_TO_TRASH = "move_to_trash"
    """Reversível. Exige principal autenticado e confirmação explícita,
    com exigência de assurance proporcionalmente menor."""

    PERMANENT_ERASURE = "permanent_erasure"
    """Irreversível. Exige `STEP_UP_VERIFIED` — ver
    `AssuranceLevel.satisfies`."""


class AssuranceLevel(StrEnum):
    """Grau de garantia de identidade **declarado por fronteira externa**.

    ```text
    TYPED_ASSURANCE_CLAIM != AUTHENTICATION_PERFORMED
    ```

    Este módulo **não autentica**. O nível é evidência tipada que uma
    fronteira externa futura deverá ter verificado; construir o valor em
    Python não prova nada sobre o mundo. É a mesma disciplina de
    `VerifiedDeletionCapability.verified` na E4.9.7: o campo registra o
    que foi observado, e quem observa é outro.

    Neutro de provedor por desenho — nenhum IdP, método ou fator aparece
    aqui. Ordenado do mais fraco ao mais forte.
    """

    UNAUTHENTICATED = "unauthenticated"
    """Nenhuma evidência. **Nenhuma operação destrutiva a aceita.**"""

    AUTHENTICATED = "authenticated"
    """Principal autenticado pela fronteira externa. Suficiente para
    `MOVE_TO_TRASH`, nunca para apagamento definitivo."""

    STEP_UP_VERIFIED = "step_up_verified"
    """Reautenticação específica para a ação. Exigida por
    `PERMANENT_ERASURE`."""

    def satisfies(self, operacao: DestructiveOperation) -> bool:
        """A operação é admissível neste nível de assurance?

        ```text
        PERMANENT_ERASURE requer STEP_UP_VERIFIED
        MOVE_TO_TRASH     requer AUTHENTICATED ou mais
        UNAUTHENTICATED   não satisfaz nenhuma
        ```

        Proporcionalidade, não uniformidade: exigir step-up para a
        lixeira treinaria o usuário a reautenticar por reflexo, e um
        reflexo é exatamente o que não se quer no dia do apagamento
        definitivo. Mas nenhuma operação aceita ausência de evidência.
        """
        if self is AssuranceLevel.UNAUTHENTICATED:
            return False
        if operacao is DestructiveOperation.PERMANENT_ERASURE:
            return self is AssuranceLevel.STEP_UP_VERIFIED
        return True


class InputChannel(StrEnum):
    """De onde veio a intenção — **proveniência, nunca autoridade**.

    ```text
    TEXT_GOVERNANCE = VOICE_GOVERNANCE
    VOICE != IDENTITY
    VOICE != AUTHORITY
    VOICE_TRANSCRIPT != CONFIRMATION
    ```

    O adendo v1.3 é explícito: texto e voz têm **paridade de
    governança**. Este enum existe para registrar o canal, não para
    diferenciar o que ele permite — e os testes provam paridade por
    parametrização, com os mesmos invariantes e as mesmas recusas nos
    dois.

    Nenhum áudio, transcrição ou texto original é guardado em lugar
    algum desta fatia.
    """

    TEXT = "text"
    VOICE = "voice"


class VoiceReviewState(StrEnum):
    """Estado da revisão da entrada de voz, quando o canal é `VOICE`.

    ```text
    LOW_CONFIDENCE  -> não forma proposta
    AMBIGUOUS       -> não forma proposta
    NOT_REVIEWED    -> não forma proposta
    ASR_ERROR_MUST_NOT_BECOME_CONSENT
    ```

    Baixa confiança, ambiguidade e ausência de revisão pertencem à
    **fronteira anterior**, e o §6 do prompt é claro: não devem ser
    "corrigidas" por este módulo. Este contrato apenas recusa formar a
    proposta — corrigir aqui seria o módulo decidir o que o usuário quis
    dizer, que é a forma mais direta de um erro de ASR virar
    consentimento.

    `NOT_APPLICABLE` é o estado do canal `TEXT`, e é obrigatório declará-lo
    — não é default. Ver `SafeVoiceProvenance`.
    """

    NOT_APPLICABLE = "not_applicable"
    """Canal é `TEXT`. Não há revisão de voz a declarar."""

    NOT_REVIEWED = "not_reviewed"
    LOW_CONFIDENCE = "low_confidence"
    AMBIGUOUS = "ambiguous"
    REVIEWED_AND_CONFIRMED = "reviewed_and_confirmed"
    """Único estado de voz que permite formar proposta."""

    def permite_proposta(self, canal: InputChannel) -> bool:
        """O par canal/revisão pode formar proposta destrutiva?

        Exige coerência nos dois sentidos: `TEXT` **tem** de declarar
        `NOT_APPLICABLE`, e `VOICE` **não pode** declará-lo. Aceitar
        `NOT_APPLICABLE` numa entrada de voz deixaria a revisão sumir sem
        que ninguém a negasse.
        """
        if canal is InputChannel.TEXT:
            return self is VoiceReviewState.NOT_APPLICABLE
        return self is VoiceReviewState.REVIEWED_AND_CONFIRMED


class ApprovalBlockerKind(StrEnum):
    """Por que uma proposta **não pode** ser aprovada — vocabulário fechado.

    ```text
    BLOCKER_KIND != FREE_TEXT_DIAGNOSTIC
    ```

    O §5.1 exige bloqueios, legal holds, conflitos, dependências e
    provedores externos em vocabulário tipado, **sem** diagnóstico
    textual livre. É a lição direta da E4.9.7.2: um campo `str` de
    diagnóstico é um canal de confidencialidade, e a auditoria o
    encontrou aceitando o próprio localizador.

    Nenhum membro genérico. Um bloqueio novo exige EDR.
    """

    LEGAL_HOLD = "legal_hold"
    """Retenção legal ativa. `LEGAL_HOLD` sobrepõe pedido do titular."""

    RETENTION_POLICY_CONFLICT = "retention_policy_conflict"
    CAUSAL_HISTORY_DEPENDENCY = "causal_history_dependency"
    """Outro registro depende causalmente do alvo."""

    EXTERNAL_PROVIDER_UNAVAILABLE = "external_provider_unavailable"
    CAPABILITY_NOT_VERIFIED = "capability_not_verified"
    CONTROL_SCOPE_CONFLICT = "control_scope_conflict"


class ImpactVolumeKind(StrEnum):
    """O volume apresentado é conhecido ou explicitamente desconhecido?

    ```text
    UNKNOWN_VOLUME != ZERO_VOLUME
    ```

    Fabricar `0` quando o volume não é conhecido faria a interface
    prometer ao usuário que a operação não libera espaço — afirmação que
    ninguém mediu. O §5.3 proíbe volume fabricado, e a única forma
    honesta de proibi-lo é ter um estado que diga "não sei".
    """

    KNOWN = "known"
    """`bytes_total` obrigatório e `>= 0`."""

    UNKNOWN = "unknown"
    """`bytes_total` **tem** de ser ausente. Ver `PresentedImpact`."""
