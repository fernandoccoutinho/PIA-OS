# EDR E4.9.2 — Legal Erasure × Causal History

**Natureza:** decisão arquitetural sobre o caminho **normal** da tensão C.
**Somente documental.**
**Exigido por:** `LEGAL_ERASURE_CAUSAL_HISTORY_GAP`, registrada como a
questão mais difícil da E4 pelo `E4_GOVERNANCE_BOUNDARIES.md` §6.2 e
deferida desde a E4.0.
**Complementa, sem reescrever:** `EDR_COUT_PIA_E4.md`,
`E4_GOVERNANCE_BOUNDARIES.md` §6, `EDR_E4_9_0_ERASURE_AUDIT_PRIMITIVE.md`,
`EDR_E4_9_1_ERASURE_TARGET_CUSTODY_CONTRACT.md`,
`PIA_OS_SOPHIA_CANONICAL_MASTER_v1.3.md`.

```text
NORMAL_REFERENT_ERASURE_PRESERVES_CAUSAL_HISTORY = AUTHORIZED_NOT_IMPLEMENTED
EXCEPTIONAL_CAUSAL_RECORD_ERASURE                = DEFERRED_STOP_CONDITION
```

---

## 1. Evidência real da baseline

Colhida no schema e no código da cadeia 70, não presumida.

### 1.1 FKs da história causal

```text
causal_histories.subject_coid              -> cognitive_objects     ON DELETE NO ACTION
causal_history_events.history_id           -> causal_histories      ON DELETE NO ACTION
causal_history_events.predecessor_event_id -> causal_history_events ON DELETE NO ACTION
causal_history_events.actor_ref            -> provenance_records    ON DELETE NO ACTION
```

Nenhum `CASCADE`. O banco **impede** que apagar um sujeito derrube sua
história por efeito colateral — a proteção é estrutural, não uma
convenção.

### 1.2 Imutabilidade, verificada método a método

```text
CausalHistoryRepository.update        RECUSA
CausalHistoryRepository.delete        RECUSA
CausalHistoryRepository.update_event  RECUSA
CausalHistoryRepository.delete_event  RECUSA
```

Recusa incondicional por contrato (`PIA-8020`), não por FK.

### 1.3 Vocabulário causal e primitivas ausentes

```text
CausalEventType = ['created', 'transformed', 'compared', 'accessed']
to_regclass('public.retention_policies') = NULL
to_regclass('public.erasure_records')    = NULL
```

Não existe evento causal de apagamento, e **nenhuma** das primitivas
autorizadas pela E4.9.0/E4.9.1 existe em runtime.

### 1.4 Fatos herdados, não reabertos

- `payload_ref` é referência opaca, nunca conteúdo (E4.9.1);
- `ObjectRepository.delete()` pode deixar referência JSON pendente —
  defeito antecedente **fora deste patch**, e não normalizado como
  caminho legítimo;
- `ErasureRecord` está autorizado e não implementado (E4.9.0);
- o contrato de alvo da E4.9.1 foi auditado como `PASS_FINAL`, sem
  implementação.

---

## 2. Alternativas A / B / C e a decisão

A tensão, em uma frase: `CausalHistoryEvent` é imutável por contrato e
sustenta `COUT-P4`; uma obrigação legítima de exclusão que alcance
conteúdo referenciado por eventos causais coloca **dois compromissos
legítimos** em rota de colisão.

| | **A — apagar referente** | **B — `ErasureRecord`** | **C — apagar registro causal** |
|---|---|---|---|
| Alcança conteúdo | **sim** | não (é registro) | sim, destruindo o rastro |
| Preserva história | **sim** | sim | **não** |
| Distingue removido de nunca-existiu | com história + B | **é a função dela** | não |
| Compatível com `PIA-8020` | sim | sim | **não** |
| Status | **autorizada** como caminho normal | **autorizado** (E4.9.0) | **rejeitada** no fluxo normal |

```text
AUTHORIZED_DIRECTION = A + B
C = REJECTED FOR THE NORMAL PATH, DEFERRED AS TYPED STOP CONDITION
```

A e B não são alternativas concorrentes: **A é o efeito, B é a prova de
que o efeito ocorreu**. Adotar A sem B produz apagamento inauditável;
adotar B sem A produz um sistema que registra apagamentos que nunca
aconteceram.

```text
B WITHOUT A = NO GROUND TO DECLARE SUCCEEDED
A WITHOUT B = UNAUDITABLE ERASURE
```

---

## 3. O caminho normal

Quando uma obrigação legítima alcança **conteúdo/referente verificável**,
mas não o registro causal em si:

```text
ERASE REFERENT
PRESERVE CognitiveObject identity/metadata required by causal structure
PRESERVE CausalHistory
PRESERVE CausalHistoryEvent
PRESERVE lineage/provenance/transformation/relationship structure
APPEND ErasureRecord only after a real observed attempt
```

Nenhum cascade, hard delete, mutação retroativa ou fabricação de evento
causal.

### 3.1 A formulação canônica

**A história causal preserva o rastro da passagem do conteúdo pelo
sistema, não a informação necessária para reconstituí-lo.**

```text
HISTORY SURVIVES        != CONTENT SURVIVES
KNOWN ERASED            != NEVER EXISTED
PRESERVED REFERENCE     != EXECUTABLE CAPABILITY
CAUSAL TRACE SURVIVES
RECONSTRUCTIBLE CONTENT DOES NOT
```

Preservar história **não** significa preservar o conteúdo apagado. O
grafo pode continuar afirmando que um referente existiu e participou de
uma relação causal, sem torná-lo recuperável.

### 3.2 O rastro só é admissível se for irreversível

Este é o ponto onde a decisão pode ser subvertida na prática, e por isso
é enunciado como escopo do efeito, não como boa intenção:

```text
STRUCTURAL CONSEQUENCE MAY SURVIVE
RECONSTRUCTIBLE DERIVATIVE = ERASURE TARGET
ERASURE SCOPE INCLUDES CONTROLLED COPIES_CACHES_REPLICAS_DERIVATIVES
```

Continuam sendo **conteúdo**, e entram no escopo do efeito quando
estiverem sob controle verificável:

- cópia integral;
- trecho suficiente para recompor;
- thumbnail ou pré-visualização reversível;
- cache e réplica;
- embedding reversível;
- hash usável como chave de relocalização;
- qualquer derivado suficiente para recompor o original.

Um sistema que apaga o original e mantém o cache não apagou nada; apenas
mudou o lugar de onde o conteúdo é lido.

---

## 4. Referências históricas depois do efeito

As referências da E3 são imutáveis, e **não são mutadas** no caminho
normal. Elas permanecem como identificadores históricos opacos, sob
cinco restrições:

1. continuam **proibidas** de ir diretamente a um executor (E4.9.1);
2. não podem recriar um `ErasureTargetDescriptor` sem **nova resolução**;
3. uma resolução posterior deve **observar** ausência ou estado apagado
   e jamais restaurar conteúdo por fallback, cache, réplica ou outro
   provedor;
4. ausência após erasure precisa ser distinguível de "nunca existiu"
   pela combinação de **história preservada + `ErasureRecord`** — sem
   guardar localizador vivo no registro;
5. a interface **não deve** oferecer a referência como link funcional
   quando o referente tiver sido apagado.

```text
DANGLING REFERENCE != BROKEN SYSTEM
DANGLING REFERENCE  = HONEST RECORD THAT SOMETHING WAS ERASED
```

Uma referência que aponta para algo removido é um estado **representável
e correto**. O que seria incorreto é apagá-la e deixar o sistema afirmar
que nunca houve nada ali.

**Não é autorizado mutar `payload_ref` ou outros refs da E3.** Se uma
referência contiver, ela própria, dado pessoal ou segredo que precise
ser apagado, isso **sai do caminho normal** e entra na exceção da §7.

---

## 5. `CausalHistoryEvent` × `ErasureRecord`

```text
CausalHistoryEvent != ErasureRecord
RetentionPolicy says what applies != effect happened
ErasureRecord records observed attempt != causal event
```

O `ErasureRecord` é **prova operacional separada**:

- append-only e local;
- usa identificador histórico do sujeito, **nunca FK** — a razão
  congelada na E4.9.0 é que um registro amarrado por FK pode ser
  destruído pelo efeito que deveria provar;
- não integra o Sync da E3;
- **não contém** conteúdo, trecho, referência histórica, localizador,
  segredo, hash reversível ou cópia reconstruível;
- é criado **somente depois** de tentativa material real;
- registra `SUCCEEDED | FAILED | PARTIAL` conforme efeito observado;
- não é aprovação, proposta, agenda nem estado pendente.

Reusar um evento causal existente para representar erasure seria
falsificar semântica; ampliar `CausalEventType` é proibido nesta entrega
e exigiria EDR próprio.

---

## 6. Atomicidade impossível

Storage externo e banco local **não formam transação atômica**. Ordem
conceitual autorizada, sem implementação:

```text
validated destructive authority
→ fresh target resolution
→ material effect attempt
→ observe provider/local outcome
→ append ErasureRecord
→ expose truthful receipt
```

**Não se alega rollback de apagamento irreversível.** Se o efeito
ocorrer e o registro falhar, o sistema **não pode** declarar sucesso
limpo nem repetir cegamente: entra em estado operacional
recuperável/auditável, a ser definido no contrato de execução da
**E4.9.4**. Esta entrega **registra** a tensão; não inventa queue, saga,
outbox ou worker.

### 6.1 Fidelidade do resultado ao alcance observado

```text
SUCCEEDED = all in-scope controlled reconstructible instances were confirmed erased
PARTIAL   = at least one effect occurred and at least one in-scope instance remains,
            is unverified, or is controlled only by a third party confirmation
FAILED    = no intended erasure effect was confirmed
```

Para provedor externo, **confirmação significa apenas que o provedor
aceitou ou confirmou a operação conforme seu contrato**. Não prova
desaparecimento universal em backups ou sistemas fora do alcance. A
interface futura deve preservar essa distinção — e é a mesma ressalva
que a auditoria da E4.9.1 exigiu que sobrevivesse até o recibo.

### 6.2 Quem decide e quem executa

```text
USER_OR_AUTHORIZED_ORGANIZATION_DECIDES
AI_MODEL_NEVER_EXECUTES_ERASURE
EXPIRY_TRIGGERS_ASSESSMENT_NOT_DELETION
ERASURE_EFFECT_REQUIRES_CONFIRMED_AUTHORITY
```

Quem decide é o usuário ou principal organizacional autorizado. Quem
executa fisicamente é um futuro adaptador de storage administrado ou
conector oficial — **nunca o modelo de IA**. O prazo de retenção inicia
avaliação e proposta; a tentativa material só ocorre depois de alvo
resolvido, autoridade destrutiva válida e confirmação vinculada ao
escopo, conforme a E4.9.4.

---

## 7. A exceção: obrigação alcança o registro causal

```text
NORMAL_REFERENT_ERASURE           = AUTHORIZED_PATH
EXCEPTIONAL_CAUSAL_RECORD_ERASURE = STOP_CONDITION
```

A exceção ocorre se a obrigação exigir remover ou alterar:

- `CognitiveObject` necessário como sujeito da história;
- `CausalHistory` ou `CausalHistoryEvent`;
- COID/CLID ou outro identificador histórico;
- `payload_ref` ou referência histórica **porque a própria string é dado
  protegido**;
- lineage, provenance, transformation ou relationship necessários ao
  rastro.

Nesse caso, é obrigatório:

- **não** usar o fluxo normal;
- **não** fazer cascade;
- **não** falsificar evento;
- **não** sobrescrever a referência;
- **não** alegar cumprimento parcial como completo;
- interromper com **exceção tipada** e exigir EDR jurídico-arquitetural
  próprio, com escopo concreto e migração/autoridade explícitas.

Esta exceção **permanece aberta por desenho**.
`CLOSED_CANDIDATE_CONDITIONAL` significa que o caminho normal está
decidido, **não** que toda obrigação possível foi resolvida.

---

## 8. Impacto no Retrieval

O ponto de composição da E4.6.3.1, auditado como `PASS_FINAL`, permite
excluir candidatos da vista **sem alterar patrimônio**. A futura E4.9
deverá usar composição para não devolver referente expirado ou apagado
no caminho canônico. Mas as três distinções não podem colapsar:

```text
NOT RETRIEVED  != HISTORY DELETED
GATE FALSE     != ERASURE EFFECT
ERASURE EFFECT != GATE FALSE
```

Preservar história **não autoriza** o Retrieval a expor conteúdo
apagado. O gate continua por chamada e não recebe comando natural.

---

## 9. Texto e voz — Master v1.3

```text
PIA_OS_INPUT_CHANNELS = TEXT | VOICE
SAME_COMMAND_ENVELOPE_FOR_ALL_CHANNELS = TRUE
VOICE_IS_AUTHORITY = FALSE
TRANSCRIPTION_IS_COMMAND_CANDIDATE
AMBIGUOUS_ERASURE_SCOPE = NO_EXECUTION
```

*"Apague tudo sobre este assunto"* **não distingue referente de história
causal** — e é exatamente por isso que não pode executar. Antes da
confirmação, a interface futura deverá apresentar **separadamente**:

- conteúdo/referente que pode ser apagado;
- metadado e história que serão **preservados**;
- itens não resolvidos;
- exceções que impedem execução;
- a impossibilidade de garantir desaparecimento universal em provedor
  externo.

Nenhum código de voz ou interface foi criado. A materialização permanece
na **E4.9.4**.

---

## 10. Riscos, consequências e o que continua aberto

**Risco 1 — "preservar história" vira desculpa para preservar conteúdo.**
É o modo mais provável de a decisão ser subvertida sem má-fé: alguém
mantém um cache "porque a história precisa dele". A §3.2 existe para
tornar isso indefensável — derivado reconstruível é alvo, não rastro.

**Risco 2 — `PARTIAL` apresentado como sucesso.** A definição da §6.1 é
deliberadamente exigente: basta uma instância em escopo permanecer,
ficar não verificada ou depender só da palavra de terceiro para o
resultado ser `PARTIAL`. Uma interface que arredonde isso para "pronto"
mente ao usuário no exato momento em que ele mais precisa da verdade.

**Risco 3 — a exceção da §7 ser tratada como caso de borda raro.** Ela
não é rara: obrigações de proteção de dados frequentemente alcançam
identificadores. O sistema deve **parar** e escalar, não improvisar.

**Consequência prospectiva honesta.** Quando A e B existirem, o PIA-OS
poderá afirmar, com prova, que um referente foi apagado e que a história
de sua passagem permanece. Hoje ele não pode afirmar nada disso, e
nenhuma interface deve sugerir que pode.

**Continua aberto:**

```text
LEGAL_ERASURE_CAUSAL_HISTORY_GAP  = CLOSED_CANDIDATE_CONDITIONAL
EXCEPTIONAL_CAUSAL_RECORD_ERASURE = DEFERRED_STOP_CONDITION
ON_EXPIRY_ACTION_UNRESOLVED       = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
```

Decidir o caminho normal **não** libera a E4.9. Restam duas Stop
Conditions abertas e uma exceção deferida por desenho — e nenhuma delas
é decisão do implementador.
