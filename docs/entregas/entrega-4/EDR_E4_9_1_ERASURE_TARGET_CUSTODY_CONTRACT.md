# EDR E4.9.1 — Erasure Target Custody Contract

**Natureza:** autorização arquitetural prospectiva de contrato de alvo e
custódia. **Somente documental.**
**Exigido por:** a Tensão B do preflight da E4.9 —
`STOP_CONDITION = ERASURE_TARGET_OWNERSHIP_GAP`.
**Complementa, sem reescrever:** `EDR_COUT_PIA_E4.md`,
`E4_GOVERNANCE_BOUNDARIES.md` §6, `EDR_E4_9_0_ERASURE_AUDIT_PRIMITIVE.md`,
`EDR_E4_3_5_RETENTION_OPERATION_AUTHORITY.md`,
`PIA_OS_SOPHIA_CANONICAL_MASTER_v1.3.md`.

```text
ERASURE_TARGET_CUSTODY_CONTRACT = AUTHORIZED_NOT_IMPLEMENTED
ARCHITECTURAL AUTHORIZATION    != IMPLEMENTATION
```

---

## 1. O problema

A pergunta que este EDR fecha é única e desconfortável: **o que o PIA-OS
pode honestamente afirmar que apaga?**

O preflight da E4.9 constatou que a resposta atual é *nada*, e que a
ambiguidade é perigosa justamente porque várias operações *parecem*
apagamento sem o serem.

### 1.1 Evidência colhida na cadeia 69

Verificado no schema e no código reais, não presumido:

```text
cognitive_objects: ['clid', 'accessibility', 'revision_status',
                    'id', 'created_at', 'updated_at', 'deleted_at']
```

Nenhuma coluna de conteúdo. As referências são opacas e **sem chave
estrangeira**:

```text
causal_history_events.payload_ref   VARCHAR(512)   FKs = 0
provenance_records.source_ref       VARCHAR(512)   FKs = 0
provenance_records.evidence_refs    JSON           FKs = 0
transformation_records.input_refs   JSON           FKs = 0
transformation_records.output_refs  JSON           FKs = 0
```

Busca por resolvedor, storage, conector ou executor em `backend/app`:
**nenhuma ocorrência**.

```text
ARTIFACT_STORAGE = DEFERRED
EXTERNAL_CONNECTOR_EXECUTION = NOT_IMPLEMENTED
ERASURE_EXECUTOR = NONE
```

### 1.2 O que decorre disso, sem margem

- marcar `deleted_at` **não** apaga conteúdo;
- mudar `accessibility` **não** apaga conteúdo;
- apagar a linha de `CognitiveObject` apaga **metadado e identidade**, não
  o referente;
- limpar uma referência **não prova** que o referente foi apagado;
- uma string de referência **não prova** custódia, autoridade nem
  capacidade;
- nenhuma operação atual pode ser chamada honestamente de *legal erasure*
  do conteúdo.

O defeito antecedente de `ObjectRepository.delete()` com referências JSON
(registrado no preflight) **continua existente e fora deste escopo**.
Não é corrigido aqui nem normalizado como caminho legítimo.

---

## 2. Ownership técnico, não jurídico

```text
TECHNICAL_CUSTODY != LEGAL_OWNERSHIP
USER_OR_ORGANIZATION_CONTROLS_DESTINATION
PIA_EXECUTES_ONLY_WITH_VERIFIED_CAPABILITY_AND_AUTHORITY
```

Este documento **não conclui** quem detém direitos jurídicos sobre dados,
obras, segredos ou dados pessoais. Jurisdição, contrato e obrigação legal
são entradas externas futuras, e software não as decide.

O que o contrato decide é estreito e verificável: **quem controla
tecnicamente o destino**, e **se o PIA-OS tem capacidade comprovada de
agir sobre ele**. Confundir as duas coisas seria o pior erro possível
neste módulo — um sistema que conclui titularidade jurídica a partir de
uma string de referência apaga o que não devia, com a convicção de estar
cumprindo a lei.

---

## 3. Taxonomia de custódia — classificação fechada

| Classe | Significado | É conteúdo? |
|---|---|---|
| `PIA_MANAGED_ARTIFACT` | bytes/conteúdo em storage administrado pelo PIA-OS para o titular do controle | **sim** |
| `AUTHORIZED_CONNECTOR_REFERENT` | conteúdo em provedor externo; o PIA-OS só pode **solicitar** exclusão por conector oficial com capacidade, conta e escopo verificados | **sim** |
| `COGNITIVE_METADATA_RECORD` | linha/estrutura local da E3/E4 | **não** |
| `UNRESOLVED_OPAQUE_REFERENCE` | referência existente sem resolução verificável | **não** |

Somente as duas primeiras podem representar conteúdo apagável.

`COGNITIVE_METADATA_RECORD` **não pode ser promovido a legal erasure**:
remover metadado é uma operação com semântica e autoridade próprias, e
apresentá-la como apagamento de conteúdo seria exatamente a mentira que
o §6.1 do `E4_GOVERNANCE_BOUNDARIES.md` proíbe.

`UNRESOLVED_OPAQUE_REFERENCE` exige **recusa explícita**. Não é um caso
degenerado tolerável: é o caso mais comum hoje, e tratá-lo como
best-effort produziria apagamentos alegados sem efeito observado.

```text
METADATA REMOVAL != CONTENT ERASURE
UNRESOLVED REFERENCE = TYPED REFUSAL, NEVER BEST EFFORT
```

---

## 4. Alternativas consideradas

| # | Alternativa | Por que foi rejeitada |
|---|---|---|
| 1 | tratar toda referência como alvo apagável | é a origem do problema: string sintaticamente válida vira autoridade |
| 2 | duas classes (interno × externo) | perde a distinção entre *metadado* e *referência não resolvida*, que exigem tratamentos opostos |
| 3 | decidir titularidade jurídica no software | fora da competência do sistema; produz apagamento indevido com aparência de conformidade |
| 4 | resolver e executar na mesma porta | resolução deixaria de ser observacional; um erro de resolução viraria efeito |
| 5 | persistir o localizador para reexecução | o localizador é exatamente o que não pode sobreviver ao efeito |
| 6 | promover remoção de metadado a *legal erasure* | apagaria a distinção que o contrato existe para preservar |
| **7** | **quatro classes + descritor transitório + duas portas separadas** | **adotada** |

---

## 5. Descritor transitório de alvo

Autorizado, **sem implementação**: um value object transitório e imutável
— nome recomendado `ErasureTargetDescriptor` — produzido **apenas** por
uma futura porta de resolução autorizada.

Contrato conceitual mínimo:

| Elemento | Papel |
|---|---|
| classe do alvo | uma das quatro da §3 |
| identificador histórico do sujeito | distingue *removido* de *nunca existiu* |
| Workspace/tenant/principal de controle | a quem o alvo está vinculado |
| provedor/namespace de custódia | onde o conteúdo vive |
| localizador opaco **transitório** | suficiente para o adaptador executar, e nada além |
| capacidade de exclusão verificada + escopo | o que a conta/conector realmente pode |
| instante da resolução e, quando houver, versão/etag | detecta resolução obsoleta |
| origem da referência que motivou a resolução | rastreabilidade — **não** autoridade |

### 5.1 Proibições

```text
conteúdo, trecho, cópia ou derivado reconstruível
segredo, token, credencial ou material de autenticação
persistência automática do localizador
inclusão do localizador no futuro ErasureRecord
log em claro
reutilização entre Workspaces, tenants, contas ou provedores
execução com resolução obsoleta
```

O descritor é **capacidade contextual transitória**:

```text
DESCRIPTOR != PATRIMONY
DESCRIPTOR != POLICY
DESCRIPTOR != APPROVAL
DESCRIPTOR != EFFECT
DESCRIPTOR != RECEIPT
```

A última linha da tabela merece ênfase: registrar a **origem** da
referência é rastreabilidade, e transformá-la em autoridade seria
recriar o defeito da §4.1 por outro caminho.

---

## 6. Duas portas, não uma

Autorizadas conceitualmente, sem código:

```text
ErasureTargetResolverPort
  referência + contexto autorizado → descritor verificado OU recusa tipada

ErasureEffectPort
  descritor + autorização destrutiva válida → tentativa material observável
```

A separação é **obrigatória**:

```text
REFERENCE        != RESOLVED TARGET
TARGET RESOLUTION!= DELETION AUTHORITY
DELETION AUTHORITY != EFFECT
EFFECT           != ERASURE RECORD
```

**Resolver um alvo é observacional.** A resolução não pode apagar,
modificar ou marcar coisa alguma — nem o sujeito, nem a referência, nem
estado no provedor. Se resolver tivesse efeito colateral, uma consulta
exploratória já seria uma ação destrutiva parcial, e nenhuma aprovação
posterior poderia desfazê-la.

Os nomes podem ser refinados pelo módulo que implementar as portas; a
separação, não.

---

## 7. Modelo de ameaças

| Ameaça | Como se manifesta | O que o contrato exige |
|---|---|---|
| **Confused deputy** | usuário fornece string sintaticamente válida; o PIA-OS usa a própria credencial para apagar objeto de outro titular | resolução por adaptador autorizado, com principal de controle e escopo verificados; string nunca é autoridade |
| **Cross-tenant** | descritor resolvido num Workspace usado em outro | vínculo de Workspace/tenant no descritor; reutilização entre eles **proibida** |
| **Locator leakage** | localizador vai para log, `ErasureRecord` ou telemetria | localizador é transitório, nunca persistido, nunca logado em claro, nunca no recibo |
| **Stale resolution** | alvo mudou entre resolução e execução | instante e versão/etag no descritor; execução com resolução obsoleta **recusada** |
| **Credential confusion** | credencial de um provedor usada em namespace de outro | provedor/namespace explícitos e capacidade verificada por escopo |
| **Target expansion** | confirmação para um alvo, execução sobre vários | nenhuma expansão de alvo depois da confirmação |

As seis são **modeladas, não mitigadas**: nenhuma delas tem mitigação em
runtime hoje, porque não há resolvedor nem executor. O contrato existe
para que a mitigação seja obrigatória quando houver.

---

## 8. Admissão de um alvo executável

Um futuro alvo só chega ao executor se **todas** forem verdadeiras:

1. identidade e principal de controle verificados;
2. Workspace/tenant vinculados e iguais aos da autorização;
3. referência resolvida por adaptador autorizado para o provedor/namespace;
4. capacidade explícita de exclusão no escopo da conta/conector;
5. alvo **não** é apenas metadado nem string opaca;
6. resolução ainda válida e, quando aplicável, versão/etag coerente;
7. intenção/approval destrutivos vinculam exatamente ação, alvo, escopo e
   impacto;
8. nenhuma expansão de alvo ocorre depois da confirmação;
9. tentativa e efeito podem ser **observados** para alimentar
   `ErasureRecord`;
10. falha em qualquer prova produz **recusa tipada**, nunca best effort
    silencioso.

Este EDR autoriza os critérios. **Nenhum deles está implementado.**

---

## 9. Referências legadas não são capacidades

```text
payload_ref     != ErasureTargetDescriptor
source_ref      != ErasureTargetDescriptor
evidence_refs   != ErasureTargetDescriptor
input_refs      != ErasureTargetDescriptor
output_refs     != ErasureTargetDescriptor
COID            != CONTENT LOCATOR
```

É **proibido** passar qualquer dessas strings diretamente a um executor.
Elas podem apenas **iniciar uma tentativa de resolução** por adaptador
autorizado — que pode perfeitamente terminar em recusa.

O COID merece menção própria porque é o identificador mais familiar do
sistema e o mais tentador de reusar: ele identifica um objeto cognitivo
local, e não localiza conteúdo em lugar nenhum.

---

## 10. Relação com `ErasureRecord` e história causal

A direção A+B, recomendada pelo preflight e parcialmente autorizada pela
E4.9.0, é preservada:

```text
A = apagar referente verificável quando houver custódia/capacidade
B = registrar resultado observado em ErasureRecord, sem conteúdo nem localizador
C = apagar história causal permanece rejeitada como caminho normal
```

O vínculo entre `ErasureRecord` e sujeito continua sendo **identificador
histórico, nunca FK** — pela razão já congelada na E4.9.0: um registro
amarrado por FK ao sujeito pode ser destruído pelo efeito que deveria
provar.

O recibo **não pode** guardar `payload_ref`, `source_ref`,
`evidence_refs`, `input_refs`, `output_refs`, o localizador do descritor,
segredo, hash reversível ou cópia reconstruível.

Esta entrega **não fecha** `LEGAL_ERASURE_CAUSAL_HISTORY_GAP`. Ela
estabelece a entrada necessária para a decisão seguinte: sem saber o que
é um alvo, não há como decidir o que acontece quando uma obrigação
alcança o registro causal.

---

## 11. Master v1.3 — texto e voz

O contrato de alvo é materialmente relacionado a futuros comandos
destrutivos, então o adendo multicanal **se aplica** aqui — ao contrário
da E4.6.3.1, onde era `NOT_APPLICABLE`.

```text
PIA_OS_INPUT_CHANNELS = TEXT | VOICE
SAME_COMMAND_ENVELOPE_FOR_ALL_CHANNELS = TRUE
VOICE_IS_AUTHORITY = FALSE
TRANSCRIPTION_IS_COMMAND_CANDIDATE
NATURAL_LANGUAGE_REFERENCE != RESOLVED ERASURE TARGET
```

Uma ordem digitada ou falada — *"apague tudo sobre este assunto"* —
**nunca** pode produzir diretamente descritor ou efeito. Ela é candidata
a comando, e precisará ser estruturada, desambiguada, resolvida e
confirmada no módulo de autoridade destrutiva.

Nenhum código de voz foi criado aqui. A implementação material continua
reservada ao módulo de comandos/aprovação, previsto para a **E4.9.4**.

---

## 12. Fronteiras: implementadas × apenas autorizadas

| Fronteira | Estado |
|---|---|
| classificação fechada de alvos | **autorizada**, não implementada |
| `ErasureTargetDescriptor` | **autorizado**, não implementado |
| `ErasureTargetResolverPort` | **autorizada**, não implementada |
| `ErasureEffectPort` | **autorizada**, não implementada |
| critérios de admissão (§8) | **autorizados**, não implementados |
| `ErasureRecord` | autorizado na E4.9.0, não implementado |
| `RetentionPolicy` | admitida pela E4.0, não implementada |
| Artifact Storage / conector / credencial | **não autorizados** aqui |
| executor destrutivo / aprovação | **não autorizados** aqui |
| ponto de composição da recuperação | **implementado** (E4.6.3.1, `PASS_FINAL`) |
| operações de governança de retenção | **implementadas** (E4.3.5) |

```text
NOTHING IN THIS DOCUMENT ERASES ANYTHING
NO STORAGE, CONNECTOR, CREDENTIAL OR EXECUTOR EXISTS
```

---

## 13. Consequências, riscos e o que continua aberto

**Consequência prospectiva honesta.** Quando houver resolvedor, o sistema
poderá dizer, para cada referência, *se* há alvo apagável e *sob qual
custódia*. Hoje ele não pode dizer isso de referência nenhuma, e nenhuma
interface deve sugerir que pode.

**Risco declarado — a classe `AUTHORIZED_CONNECTOR_REFERENT` é a mais
frágil.** Ela depende de um terceiro cumprir o que promete: o PIA-OS
*solicita* exclusão e observa o que o provedor responde. Um `SUCCEEDED`
nessa classe significa "o provedor confirmou", não "os bytes deixaram de
existir em toda parte". Essa distinção precisa sobreviver até a
interface.

**Risco declarado — verificação de capacidade é o elo caro.** "Capacidade
de exclusão verificada" é fácil de escrever e difícil de provar contra
APIs reais. Um módulo futuro que aceite a *declaração* de capacidade em
vez de sua verificação reintroduz o confused deputy por dentro.

**Continua aberto:**

```text
ERASURE_TARGET_OWNERSHIP_GAP     = CLOSED_CANDIDATE_BY_AUTHORIZATION
LEGAL_ERASURE_CAUSAL_HISTORY_GAP = OPEN_CONDITIONAL
ON_EXPIRY_ACTION_UNRESOLVED      = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
```

Fechar o alvo **não** libera a E4.9. Restam três decisões, e nenhuma é do
implementador.
