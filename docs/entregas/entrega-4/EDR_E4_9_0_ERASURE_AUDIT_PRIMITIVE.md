# EDR E4.9.0 — Erasure Audit Primitive Authorization

**Natureza:** autorização arquitetural prospectiva de uma primitiva
persistente. **Somente documental.**
**Exigido por:** a Tensão D do preflight da E4.9 —
`STOP_CONDITION = ERASURE_AUDIT_PRIMITIVE_GAP`.
**Complementa, sem reescrever:** `EDR_COUT_PIA_E4.md`,
`E4_GOVERNANCE_BOUNDARIES.md` §6 e §6.2, `E4_DOMAIN_MODEL_DRAFT.md` §9,
`E4_PRIMITIVE_OWNERSHIP.md`, `EDR_E4_3_5_RETENTION_OPERATION_AUTHORITY.md`.

```text
ARCHITECTURAL AUTHORIZATION != IMPLEMENTATION
AUDIT PRIMITIVE             != ERASURE EFFECT
RECORD                      != PROOF WITHOUT OBSERVED EFFECT
```

---

## 1. A lacuna confirmada

O preflight da E4.9 inspecionou as entidades persistentes existentes —
os sete modelos da E3, `MemoryDomain`, `DomainMembership`,
`GovernancePolicy` e `AccessibilityPolicy` — e nenhuma registra *houve
remoção obrigatória, sob esta autoridade, nesta data*.

Três achados sustentam a lacuna:

1. `CausalEventType` tem quatro membros — `CREATED`, `TRANSFORMED`,
   `COMPARED`, `ACCESSED` — e nenhum representa apagamento. Reusar
   qualquer um falsificaria semântica.
2. `RetentionPolicy`, sozinha, não prova que uma ação ocorreu:
   `POLICY SAYS WHAT APPLIES != ACTION HAPPENED`.
3. Um registro que dependesse do sujeito por FK poderia ser destruído
   pelo próprio efeito que deveria provar.

O contrato congelado (`E4_GOVERNANCE_BOUNDARIES.md` §6.1) exige que a
exclusão legítima seja **explícita, registrada e distinguível**. Sem
primitiva de registro, "registrada" não tem onde acontecer.

---

## 2. O que é autorizado

```text
TECHNICAL_NAME        = ErasureRecord
OWNER                 = E4.9
PERSISTENCE           = PERSISTENT
IDENTITY              = OWN UUID
MUTABILITY            = APPEND_ONLY
PORTABILITY           = LOCAL
SYNC                  = NONE
COGNITIVE_PATRIMONY   = FALSE
CONTENT_STORAGE       = FORBIDDEN
IMPLEMENTATION_STATUS = AUTHORIZED_NOT_IMPLEMENTED
```

`ErasureRecord` é **recibo auditável de uma tentativa material de
apagamento cujo efeito foi observado por um executor autorizado**.

É `LOCAL` pela mesma razão que as policies: autoridade não é
transferível, e um recibo importado afirmaria um apagamento que esta
instalação nunca observou.

---

## 3. O que `ErasureRecord` não é

```text
ERASURE_RECORD != RETENTION_POLICY
ERASURE_RECORD != RETENTION_ASSESSMENT
ERASURE_RECORD != DISPOSITION_PROPOSAL
ERASURE_RECORD != USER_APPROVAL
ERASURE_RECORD != EXECUTION AUTHORITY
ERASURE_RECORD != ERASURE EFFECT
ERASURE_RECORD != CAUSAL_HISTORY_EVENT
```

A matriz que sustenta cada uma dessas distinções está no
`E4_9_0_ERASURE_AUDIT_PRIMITIVE_AUTHORIZATION.md` §2. O ponto comum:
cinco coisas diferentes — a regra vigente, a avaliação datada, a
proposta, a autorização e o efeito observado — vivem em contratos
distintos, e fundir qualquer par delas produziria um sistema que não
consegue responder *o que foi decidido* separadamente de *o que
aconteceu*.

---

## 4. Escopo do resultado

```text
SUCCEEDED   FAILED   PARTIAL
```

Somente após uma tentativa real. `PENDING`, `PROPOSED`, `APPROVED` e
`SCHEDULED` **não pertencem** a esta primitiva: são estados de um fluxo
de decisão que ainda não tem contrato, e admiti-los aqui transformaria
um recibo de execução em fila de trabalho.

Duas regras que não podem ser afrouxadas na implementação futura:

```text
NO SUCCEEDED WITHOUT OBSERVED EFFECT
PARTIAL OR FAILED != COMPLETED ERASURE
```

Um apagamento parcial apresentado como concluído é pior que nenhum
registro: cria confiança em algo que não ocorreu.

---

## 5. Metadados autorizados conceitualmente

**Contrato conceitual, não autorização de migração literal.** A
implementação futura deverá revisar cardinalidade, nullability, tipos e
constraints contra os contratos então existentes.

| Campo | Papel |
|---|---|
| `id` | identidade própria (UUID) |
| `subject_coid` | identificador **histórico** do sujeito alcançado |
| `retention_policy_id` / `_key` / `_version` | versão de policy de retenção, quando aplicável |
| `governance_policy_id` / `_key` / `_version` | policy de governança efetivamente usada |
| `governance_rule_id` | a regra explícita de `LEGAL_ERASURE` que autorizou |
| `governance_resolution_ref` | vínculo fiel à resolução autorizadora futura |
| `attempted_at` | instante UTC da tentativa |
| `completed_at` | instante UTC do resultado, se concluído |
| `scope_token` | vocabulário fechado do que se tentou alcançar |
| `outcome` | `SUCCEEDED` \| `FAILED` \| `PARTIAL` |
| `executor_ref` | identidade **verificável** futura |
| `failure_code` | código estruturado, quando aplicável |
| `effect_digest` | evidência não reversível e não reconstrutiva do efeito |
| `created_at` | instante persistido |

### 5.1 Proibido armazenar

```text
raw content
content excerpt
prompt/response text
payload_ref vivo
source_ref vivo
evidence_refs vivos
storage credential
secret/token
recoverable encryption key
reversible content hash used as lookup key
copy or derivative sufficient to reconstruct erased content
```

O identificador histórico do sujeito **pode** permanecer, porque a
função dele é exatamente distinguir "removido" de "nunca existiu" — a
distinção que o §6.1 do `E4_GOVERNANCE_BOUNDARIES.md` exige. Ele não
pode ser um localizador vivo do conteúdo apagado.

```text
HISTORICAL SUBJECT IDENTIFIER != LIVE CONTENT LOCATOR
```

`effect_digest` merece cuidado próprio na implementação: um digest cuja
pré-imagem seja adivinhável a partir de um espaço pequeno de candidatos
é reconstrução por força bruta, não evidência. A escolha do mecanismo
fica com a etapa que o implementar, sob esta restrição.

---

## 6. Relação com `CausalHistory`

`ErasureRecord` **não pertence** a `CausalHistory` e **não exige**
ampliar `CausalEventType`.

```text
ERASURE_RECORD SUBJECT LINK = HISTORICAL IDENTIFIER, NOT CASCADING FK
CAUSAL_HISTORY   = PRESERVED
CAUSAL_EVENT_TYPE = UNCHANGED
OPTION_C          = NOT_AUTHORIZED
```

Quatro razões, e a segunda é a decisiva:

1. a história causal pertence à E3.9 e é append-only por contrato
   (`PIA-8020`);
2. **um registro cujo FK dependa do sujeito apagado pode ser destruído
   pelo efeito que deveria provar** — `causal_histories.subject_coid`
   referencia `cognitive_objects.id`, e o preflight mediu que a
   exclusão física de um objeto com história é bloqueada justamente por
   essa cadeia;
3. legal erasure é trilha operacional e jurídica **local**; evento
   causal é vocabulário universal do patrimônio;
4. a opção C — apagar o próprio registro causal — permanece rejeitada
   para o fluxo normal.

Uma obrigação externa que atinja o próprio registro causal continua
sendo Stop Condition e exigirá EDR excepcional próprio.

---

## 7. Direção congelada: A + B

```text
OPTION_A = ERASE EXTERNAL REFERENT, PRESERVE NON-RECONSTRUCTIVE EVIDENCE
OPTION_B = ErasureRecord
AUTHORIZED_DIRECTION = A + B
OPTION_C = REJECTED_FOR_NORMAL_FLOW
```

A e B são **complementares, não alternativas**:

- **A** é o efeito real no referente externo;
- **B** é o registro local e append-only do efeito observado.

```text
B WITHOUT A = NO GROUND TO DECLARE SUCCEEDED
A WITHOUT B = UNAUDITABLE ERASURE
```

Esta decisão **não fecha** `ERASURE_TARGET_OWNERSHIP_GAP`. O preflight
constatou que `CognitiveObject` não contém conteúdo algum, que
`payload_ref`/`source_ref`/`evidence_refs` são texto opaco sem
resolvedor, e que `ARTIFACT_STORAGE = DEFERRED`. Não existe Artifact
Storage, porta, credencial nem executor. A opção A permanece **direção
autorizada e não executável**.

---

## 8. Autoridade e aprovação

A E4.3.5 tornou `LEGAL_ERASURE` representável. Ela **não** criou
autenticação, identidade verificável ou aprovação.

```text
LEGAL_ERASURE OPERATION != VERIFIED USER APPROVAL
GOVERNANCE RESOLUTION   != EXECUTION RECEIPT
ACTOR_REF STRING        != VERIFIED IDENTITY
```

`MemoryContext.actor_ref` é, pelo texto do próprio código, "entrada
descritiva, não ator autorizado". Um `ErasureRecord` futuro **não
poderá** promovê-lo a executor confirmado: `executor_ref` exige
identidade verificável, e ela não existe em nenhuma camada do sistema
hoje.

Esta decisão **não fecha** `DESTRUCTIVE_EXECUTION_AUTHORITY_GAP`.

---

## 9. Imutabilidade e ciclo de vida

Regras prospectivas autorizadas:

- criação **somente** após tentativa material observada;
- append-only depois de persistido;
- `update()` e `delete()` recusados no repositório futuro, na disciplina
  já provada por `GovernancePolicy` e `AccessibilityPolicy`;
- mutação ORM direta recusada por evento de mapper;
- **nenhuma** transformação de `FAILED` em `SUCCEEDED` por update;
- nova tentativa gera **novo** `ErasureRecord`, ligado conceitualmente à
  tentativa anterior, sem sobrescrevê-la;
- nenhum cascade a partir de `CognitiveObject`, de policy ou de storage;
- downgrade futuro `CONDITIONALLY_REVERSIBLE`, bloqueando se houver
  registros publicados — mesma guarda embutida na migração da E4.7.

---

## 10. Estado das Stop Conditions

```text
RETENTION_OPERATION_AUTHORITY_GAP   = CLOSED_FINAL
ERASURE_AUDIT_PRIMITIVE_GAP         = CLOSED_CANDIDATE_BY_AUTHORIZATION

ERASURE_TARGET_OWNERSHIP_GAP        = OPEN
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = OPEN_CONDITIONAL
ON_EXPIRY_ACTION_UNRESOLVED         = OPEN
RETENTION_RETRIEVAL_COMPOSITION_GAP = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN

ERASURE_RECORD_IMPLEMENTED = FALSE
E4_9_IMPLEMENTATION        = NOT_STARTED
READY_FOR_E4_9             = FALSE
READY_FOR_E4_10            = FALSE
```

Vale dizer sem rodeio o que esta etapa **não** conseguiu: ela remove o
segundo de sete bloqueios. Autorizar a primitiva de auditoria não cria
o registro, não alcança conteúdo nenhum e não autoriza executor algum.

---

## 11. Divergência registrada — §11 do prompt não pôde ser cumprido por inteiro

O §11 exige corrigir uma imprecisão documental da E4.3.5: a alegação de
que "quem executa é a E4.9". A inspeção mostrou que essa frase existe em
**um único lugar**, e é um `.py`:

```text
backend/app/memory/models/governance_enums.py, docstring de
RETENTION_DISPOSITION:

    "Autoriza representar a disposição. **Não** executa apagamento nem
     fabrica recibo — quem executa é a E4.9, que não existe."
```

Ela **não** aparece nos documentos `EDR_E4_3_5_...md` nem
`E4_3_5_...md`, que já usam formulação neutra.

Corrigi-la exigiria editar um arquivo de produção, o que colide
frontalmente com três seções do mesmo prompt: o §9 proíbe alterar
qualquer `.py`, o §12 exige `PRODUCTION_TREE = IDENTICAL`, e o §14.11
faz de alterar tree de produção uma Stop Condition.

**Decisão tomada:** não editar o `.py`. A alegação fica registrada aqui
como imprecisão conhecida, com o texto neutro proposto:

```text
    "Autoriza representar a disposição. **Não** executa apagamento nem
     fabrica recibo — nenhum executor foi autorizado ou implementado."
```

A substituição exige um corretivo próprio de uma linha
(`E4.3.5.1`, docstring apenas), que o titular precisa autorizar porque
altera o tree de produção. Enquanto isso não ocorre, prevalece a
formulação normativa deste EDR:

```text
AUTHORIZED_EXECUTOR = NONE
NO MODULE HAS BEEN AUTHORIZED TO EXECUTE ERASURE
```

Registrar a divergência em vez de escolher em silêncio segue a
hierarquia de autoridade do projeto e o §0.2.6 do master.

---

## 12. SOPHIA

```text
COMMERCIAL_BRAND = SOPHIA
SYSTEM_CODEBASE_AND_ARCHITECTURE = PIA-OS
CURRENT_CAPABILITY_NOT_OVERSTATED = TRUE
```

Consequência prospectiva, dita sem inflar: quando `ErasureRecord`
existir, a Biblioteca Cognitiva poderá distinguir *apagamento executado*
de *apagamento obrigatório pendente* — dois dos sete estados que o §15
do prompt da E4.9 exige que o usuário consiga distinguir. Hoje ela não
pode, e **nenhuma interface deve sugerir que pode**.

```text
THE PIA-OS DOES NOT ERASE EXTERNAL CONTENT TODAY
NO ERASURE HAS BEEN EXECUTED, RECORDED OR AUTHORIZED
```
