# EDR E4.9.4 — Autoridade destrutiva do usuário presente

**Natureza:** decisão arquitetural **exclusivamente documental**.
**Baseline:** cadeia 73 (`9b2e0738`), auditada como
`E4_9_3_1_AUDIT = PASS_FINAL`.
**Fecha:** a última Stop Condition **normal** do preflight da E4.9.

```text
DESTRUCTIVE_AUTHORITY_CONTRACT      = AUTHORIZED_NOT_IMPLEMENTED
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = CLOSED_CANDIDATE_BY_AUTHORIZATION
POSTHUMOUS_SUCCESSION_AUTHORITY     = SEPARATE_FUTURE_MODULE
E4_9_IMPLEMENTATION                 = NOT_STARTED
```

---

## 1. Fatos da baseline

### 1.1 O fato decisivo

O próprio código, em `app/memory/schemas/memory_context.py`, declara
`actor_ref` como *"Quem opera — **entrada descritiva**, não ator
autorizado"*, com `ACTOR PRESENCE != AUTHORIZATION`. Isto foi escrito na
E4.2, sobreviveu à E4.3.4 que tornou os campos de contexto obrigatórios,
e continua verdadeiro na cadeia 73.

`actor_ref` é **texto declarado pelo chamador**. Não prova identidade,
sessão, consentimento nem poder sobre o alvo.

### 1.2 Existe *estrutura* de autenticação; não existe autenticador

Este é o ponto onde uma leitura apressada erraria, e por isso vai
medido:

```text
PIA-7001 AUTHENTICATION_ERROR   declarado em app/core/error_codes.py
AuthenticationException          declarada em app/exceptions/api.py
TAG_AUTHENTICATION               placeholder=True em app/docs/tags.py
app/security/                    11 arquivos
```

E, ainda assim:

- `AuthenticationException` **nunca é levantada** em `backend/app` —
  a classe existe, nenhum código a usa;
- `app/security/__init__.py` diz, no próprio docstring: *"Sem login,
  usuários, OAuth, JWT ou permissões — isso pertence a módulos
  futuros"*. O módulo entrega cabeçalhos, CORS, hosts confiáveis,
  validação de requisição, sanitização, rate limiting e gestão de
  segredos. **Nenhum autenticador de principal**;
- a tag OpenAPI é explicitamente `placeholder`;
- `jwt` aparece só num validador de configuração; `password` só na
  montagem da URL do banco e na lista de campos redigidos em log;
- as 20 ocorrências de `identity` são **identidade cognitiva**
  (COID/CLID, integridade, contexto), não identidade de principal —
  `memory_context.py` chega a congelar `CONTEXT != IDENTITY`.

```text
ERROR CODE EXISTS != AUTHENTICATOR EXISTS
SECURITY MIDDLEWARE != IDENTITY PROVIDER
```

Nenhuma tabela de identidade, principal ou aprovação existe:
`to_regclass` devolve `NULL` para `approval_records`,
`destructive_approvals`, `identities`, `principals`, e segue `NULL`
para `retention_policies` e `erasure_records`.

### 1.3 `LEGAL_ERASURE` é representável e não é poder

```text
CognitiveOperation = read, reference, derive, transform, expose,
                     synchronize, consolidate, accessibility_transition,
                     retention_assessment, retention_disposition,
                     legal_erasure
```

A E4.3.5 tornou a operação **nomeável** para que a governança pudesse
resolvê-la. Nomear não executa.

```text
OPERATION IS REPRESENTABLE != OPERATION IS PERMITTED
POLICY RESOLVES != HUMAN APPROVES
```

`governance_enums.py` já registra, desde a E4.3.5.1, que *nenhum
executor foi autorizado ou implementado*.

---

## 2. As seis equivalências proibidas

O contrato existe para impedir seis atalhos, cada um plausível e cada um
falso:

```text
actor_ref PRESENT   == authenticated principal   → FALSO
session PRESENT     == destructive authority     → FALSO
policy ALLOWS       == human consent             → FALSO
voice command       == identity proof            → FALSO
saved preference    == current approval          → FALSO
expiry              == permission to erase       → FALSO
```

**A E4.9.4 não pode "promover" `actor_ref`.** A tentação é óbvia: o
campo já existe, já é obrigatório, já viaja em todo contexto. Promovê-lo
custaria uma linha e destruiria a única garantia que o sistema tem hoje
— a de que não confunde presença com autorização.

A autoridade precisa vir de **fronteira externa**, e o gap fecha por
contrato: ele diz o que a fronteira deve entregar, não a constrói.

---

## 3. Principal autorizador

```text
DELETE_DECISION_OWNER     = USER
DESTRUCTIVE_APPROVER      = AUTHENTICATED_PRESENT_USER
AI_MODEL_DELETE_AUTHORITY = NONE
```

**"Presente"** significa participação operacional na confirmação atual —
não sessão aberta, não login de ontem, não janela do navegador ainda
carregada.

**"Apto a confirmar"** significa capaz de revisar e responder ao impacto
apresentado. O PIA **não diagnostica capacidade civil** e não presume
competência por comportamento.

Para patrimônio organizacional futuro, só um principal humano
autenticado com **poder verificado sobre domínio, operação e alvo** pode
aprovar.

```text
NAME != POWER          EMAIL != POWER         GROUP != POWER
KINSHIP != POWER       ROLE STRING != VERIFIED POWER
actor_ref != PRINCIPAL
```

**Dual control não é imposto universalmente.** Policy ou risco futuro
podem exigir aprovação adicional — sempre de humanos identificados e com
poderes separados, nunca duas confirmações do mesmo principal nem uma
segunda aprovação fabricada pelo sistema.

---

## 4. Cinco estados separados

```text
ASSESS != PROPOSE != AUTHORIZE != EXECUTE != RECEIPT
```

| Estado | O que é | O que **não** é |
|---|---|---|
| `ASSESS` | elegibilidade, policies, retenção, conflitos, riscos | não propõe nem materializa lote |
| `PROPOSE` | materialização dos alvos, alternativas, impacto | não é pedido de confirmação implícito |
| `AUTHORIZE` | confirmação humana autenticada e vinculada | **não** é execução |
| `EXECUTE` | futura chamada à porta de efeito após verificações frescas | não é prova de que o efeito ocorreu |
| `RECEIPT` | `ErasureRecord` após tentativa observada | não pode nascer antes do efeito |

**Nenhum estado implica o seguinte.** Aprovação pode ser revogada ou
expirar sem execução. Execução pode falhar. Recibo criado antes do
efeito é uma mentira sobre o mundo — e é a ameaça nº 16 do §17.

Isto estende, para a autoridade, a mesma disciplina que a E4.9.1 já
impôs ao alvo:

```text
REFERENCE != RESOLVED TARGET != DELETION AUTHORITY != EFFECT != RECORD
```

---

## 5. Fronteira de identidade

```text
IDENTITY_PROVIDER      != AI_MODEL
AUTHENTICATION_EVIDENCE != CREDENTIAL
SESSION_PRESENCE       != STEP_UP
VOICE                  != IDENTITY_PROOF
ROLE_LABEL             != VERIFIED_POWER
```

O domínio cognitivo **consome prova** emitida por subsistema
independente. Não recebe nem persiste senha, passkey, biometria, fator
MFA, token bruto, chave ou segredo. Isto é continuidade direta da
E4.9.3.1: `CREDENTIALS != INHERITABLE_CONTENT` lá, `CREDENTIALS NEVER
ENTER THE COGNITIVE DOMAIN` aqui.

**Exclusão permanente exige step-up fresco.** Lixeira reversível pode
usar confirmação proporcional — mas continua exigindo identidade
adequada ao risco, porque restaurar da lixeira é possível e ter itens
enviados à lixeira por terceiro não é aceitável.

**Nenhuma tecnologia ou fornecedor é escolhido.** Senha, passkey, MFA,
assinatura, dispositivo confiável e provedor de identidade são decisões
de segurança futuras.

**Falha ou indisponibilidade do provedor bloqueia.** Sem fallback para
`actor_ref`, voz, sessão antiga ou pergunta de conhecimento.

```text
IDP UNAVAILABLE = BLOCK, NEVER DEGRADE
```

Um fallback permissivo quando o IdP falha é o modo mais provável de
todo este contrato ser contornado sem má-fé — alguém precisará apagar
algo com urgência num dia em que o provedor está fora, e a exceção
"só desta vez" vira o caminho normal.

---

## 6. Envelope conceitual de aprovação

Requisitos para um futuro `DestructiveApprovalEnvelope` **ou
equivalente**. Nenhuma classe, schema, serialização, assinatura,
algoritmo ou banco é escolhido.

| Elemento | Exigência |
|---|---|
| identificador | **opaco**; não deriva de alvo, conteúdo ou principal |
| principal | autenticado, com **nível de assurance** explícito |
| tenant/domínio e finalidade | vinculados; aprovação não atravessa fronteira |
| operação | `TRASH` reversível **ou** erasure definitiva — nunca ambíguo |
| lote | **materializado**, com versão/estado de cada alvo |
| policy | a `GovernanceResolution` **exata** que foi aplicada |
| custódia | resultado da **resolução fresca**, não de resolução anterior |
| impacto | o que foi apresentado, com quantidade e volume **conhecido/desconhecido** |
| impedimentos | dependências, holds, conflitos, provedores externos |
| canal | **apenas proveniência**; nunca concede autoridade |
| tempo | emissão, expiração, janela de frescor |
| uso | nonce, uso único, estado conceitual de consumo/revogação |
| prova | confirmação **sem conteúdo, localizador ou segredo** |

Volume desconhecido é registrado como desconhecido. A E4.9.3 já
proibiu inventar tamanho para alvo externo; um envelope que declare
"12 GB" quando o provedor não informou apresenta impacto falso ao
humano que está autorizando — e o impacto apresentado é justamente o
que ele está confirmando.

---

## 7. Binding e invalidação

Nova aprovação é **obrigatória** se mudar: item, lista ou filtro;
ordenação que determine o lote; quantidade ou volume; versão, estado ou
proteção de legado; policy ou resolution; custódia, conector ou
provedor; lixeira versus erasure; dependência, legal hold ou conflito;
impacto apresentado; identidade, tenant, domínio ou finalidade; janela
de frescor.

```text
CHANGED_SCOPE     = NEW_APPROVAL_REQUIRED
STALE_APPROVAL    = INVALID
REPLAYED_APPROVAL = INVALID
REVOKED_APPROVAL  = INVALID
CONSUMED_APPROVAL = INVALID_FOR_REUSE
```

**Proteção de legado entra na lista** por decisão desta entrega: um item
protegido pela E4.9.3.1 que perca a proteção entre a aprovação e a
execução mudou de natureza, e a aprovação anterior descrevia outro
mundo.

Um **hash de escopo** pode ser autorizado conceitualmente:

```text
APPROVAL_SCOPE_HASH != CONTENT_HASH
APPROVAL_SCOPE_HASH != LOCATOR
```

A E4.9.2 já classificou hash usável como chave de relocalização como
**alvo do apagamento**, não rastro. Um hash de escopo que permita
localizar ou inferir conteúdo reintroduziria, dentro do registro de
aprovação, exatamente o que o erasure deveria ter eliminado.
Canonicalização e algoritmo ficam para a implementação.

---

## 8. Texto e voz

Convergem ao **mesmo envelope**. Voz é captura de intenção e
proveniência, não prova de identidade. **Biometria de voz não é
autorizada nesta entrega.**

Fluxo futuro para erasure definitiva por voz:

```text
speech
→ reviewable transcription
→ normalized intent
→ exact materialized selection
→ impact presentation
→ independent secure step-up
→ scope-bound explicit confirmation
→ future execution
→ separate receipt
```

Bloqueiam: baixa confiança, ruído, **homófono**, **alvo pronominal**
("apague isso"), transcrição alterada após revisão, falha de step-up.

**O mesmo comando digitado recebe as mesmas exigências.** Texto não é
mais confiável que voz — é apenas menos ruidoso. Governança
assimétrica entre canais criaria um caminho preferencial, e o caminho
preferencial vira o caminho único.

### 8.1 Exemplos paralelos

**Digitado:** `excluir permanentemente as 10 maiores imagens da lixeira`
**Falado:** *"Excluir permanentemente as dez maiores imagens da lixeira."*

Ambos produzem: a mesma lista materializada com versão de cada item; o
mesmo impacto, com volume desconhecido marcado como desconhecido; o
mesmo step-up independente; a mesma confirmação vinculada àquela lista.
O canal entra no envelope só como proveniência.

Se, entre a apresentação e a confirmação, uma décima primeira imagem
for enviada à lixeira e alterar quem são "as dez maiores", a seleção
mudou — **nova aprovação**, nos dois canais.

**Digitado:** `apague isso` — **Falado:** *"Apague isso."*
Alvo pronominal. Bloqueia nos dois canais, com a mesma pergunta.

---

## 9. Uso único, revogação e concorrência

A aprovação é **fresca, curta e de uso único**. Revogação antes do
consumo impede a execução. **Depois de efeito irreversível, revogar não
restaura conteúdo** — e dizer o contrário ao usuário seria a mentira
que a E4.9.2 já proibiu ao tratar `PARTIAL`.

Requisitos futuros, sem inventar queue, saga, outbox ou worker: consumo
atômico; proteção contra replay; lock ou version check antes do efeito;
**re-resolução fresca do alvo**; bloqueio se snapshot, versão ou impacto
divergir; idempotência que **não** repita apagamento cegamente; estado
auditável quando efeito e recibo falharem de forma não atômica.

A janela entre `AUTHORIZE` e `EXECUTE` é onde mora o TOCTOU. A
aprovação descreve um mundo observado num instante; a execução age sobre
o mundo de outro instante. A re-resolução fresca não é zelo excessivo —
é a única coisa que impede a aprovação de um lote virar a destruição de
outro.

---

## 10. Registro de aprovação × `ErasureRecord`

```text
APPROVAL_RECORD   != ERASURE_RECORD
APPROVAL          != EXECUTION
POLICY_RESOLUTION != HUMAN_APPROVAL
```

O registro de aprovação prova **quem autorizou qual escopo e quando**.
O `ErasureRecord` prova **tentativa e resultado observado**. São
separados porque respondem a perguntas diferentes, e um sistema que os
funda perde a capacidade de dizer "foi autorizado, mas não executado" —
que é precisamente o estado a auditar depois de uma falha.

Nenhum dos dois pode conter conteúdo, trecho, localizador vivo, segredo
ou credencial. Nenhum dos dois é implementado aqui; o `ErasureRecord`
continua apenas autorizado pela E4.9.0.

---

## 11. Automações proibidas

Nenhum destes concede autoridade destrutiva: expiração; policy ou
`GovernanceResolution` permissiva; preferência salva; tamanho, idade ou
ausência de uso; IA, scheduler ou worker; `actor_ref` preenchido; sessão
ativa sem step-up; voz ou transcrição; aprovação passada de lote
semelhante; vínculo familiar; papel autodeclarado; diretiva pós-morte.

```text
NOTHING IN THIS LIST IS A PRINCIPAL
```

---

## 12. Recusas conceituais

Respostas tipadas **conceituais** — nenhum código de erro é criado, e
`PIA-8041` segue livre:

| Situação | Recusa |
|---|---|
| identidade ausente ou assurance insuficiente | bloqueio; não indica qual fator faltou |
| principal sem poder sobre o alvo | bloqueio; não enumera quem teria |
| step-up ausente ou falho | bloqueio; sem fallback |
| aprovação expirada, revogada, consumida ou repetida | bloqueio; motivo declarado sem expor o envelope |
| escopo, versão ou impacto alterado | bloqueio com **nova apresentação**, não nova confirmação automática |
| transcrição ambígua | bloqueio com pedido de desambiguação |
| alvo ou custódia não verificados | recusa tipada (E4.9.1), nunca best effort |
| conflito ou legal hold | bloqueio explicado, escalado a humano |
| serviço de identidade indisponível | bloqueio; **jamais** degradação |
| sucessão ou incapacidade | fora de escopo; recusa que aponta módulo futuro |

```text
REFUSAL EXPLAINS THE REASON, NEVER THE SECURITY DETAIL
```

---

## 13. Alternativas descartadas

| # | Alternativa | Por que foi rejeitada |
|---|---|---|
| 1 | promover `actor_ref` a principal autenticado | custa uma linha e destrói a única garantia real; contradiz o próprio código |
| 2 | tratar sessão ativa como autoridade | sessão prova continuidade, não presença nem intenção atual |
| 3 | `GovernanceResolution` permissiva basta | policy diz o que é permitido, não que um humano quis |
| 4 | preferência salva ("sempre apagar definitivo") | consentimento passado para lote futuro é consentimento genérico |
| 5 | dual control universal | segurança teatral; encarece tudo sem endereçar o risco real, que é identidade |
| 6 | biometria de voz como step-up | escolhe tecnologia, e voz é o canal mais fácil de reproduzir |
| 7 | fallback para pergunta de conhecimento quando o IdP cai | é a porta dos fundos que anula o contrato inteiro |
| 8 | aprovação de longa duração reutilizável no lote | scope swapping e replay ficam triviais |
| **9** | **aprovação específica, fresca, vinculada, de uso único, com identidade de fronteira externa** | **adotada** |

---

## 14. Os vinte casos obrigatórios

| # | Caso | Decisão / binding / limite atual |
|---|---|---|
| 1 | autenticado envia arquivo comum à lixeira | permitido com confirmação **proporcional** e identidade adequada ao risco; reversível. Nada implementado |
| 2 | erasure definitiva com step-up concluído | permitido no contrato: seleção materializada + impacto + step-up fresco + confirmação vinculada. **Executor não existe**; termina em recusa por ausência de capacidade |
| 3 | `actor_ref="owner"` sem identidade | **bloqueio**. `actor_ref` é texto do chamador; `ACTOR PRESENCE != AUTHORIZATION` |
| 4 | sessão antiga sem step-up | **bloqueio**. `SESSION_PRESENCE != STEP_UP` |
| 5 | voz com transcrição ambígua | **bloqueio** com desambiguação; ambiguidade nunca vira consentimento |
| 6 | voz correta + step-up independente | segue o fluxo de nove passos do §8; o step-up é **independente do ASR** |
| 7 | lista de dez imagens muda após confirmação | `CHANGED_SCOPE = NEW_APPROVAL_REQUIRED`; a confirmação anterior descrevia outro lote |
| 8 | versão do alvo muda entre aprovação e execução | **bloqueio** na re-resolução fresca; TOCTOU tratado, não tolerado |
| 9 | policy muda depois da aprovação | aprovação vinculada à `GovernanceResolution` exata; mudou, invalidou |
| 10 | aprovação expirada | `STALE_APPROVAL = INVALID`; janela de frescor é curta por desenho |
| 11 | replay de aprovação consumida | `CONSUMED_APPROVAL = INVALID_FOR_REUSE`; nonce e uso único |
| 12 | revogação antes do consumo | impede a execução; nenhum efeito ocorre |
| 13 | revogação depois de efeito irreversível | **não restaura**. O sistema diz a verdade: revogado para o futuro, sem desfazer o passado |
| 14 | legal hold descoberto na re-resolução | **bloqueio** e escalada humana, mesmo com aprovação válida em mãos |
| 15 | provedor externo muda de capacidade | custódia mudou → nova aprovação; declaração de capacidade nunca substitui verificação (E4.9.1) |
| 16 | organizacional sem poder no domínio | **bloqueio**; poder é verificado sobre domínio, operação e alvo, não deduzido de papel |
| 17 | policy exige segunda aprovação humana | permitido: humanos **identificados** com poderes separados; segunda aprovação fabricada é ameaça, não recurso |
| 18 | identity provider indisponível | **bloqueio**. Sem degradação, sem exceção "só desta vez" |
| 19 | beneficiário tenta usar diretiva pós-morte | **fora de escopo**. `POSTHUMOUS_SUCCESSION_AUTHORITY = SEPARATE_FUTURE_MODULE` |
| 20 | efeito ocorreu, recibo falhou | **não** vira sucesso limpo nem repetição cega: estado auditável e recuperável, resultado conservador (`PARTIAL` antes de `SUCCEEDED`) |

Os vinte terminam **hoje** em recusa por ausência de capacidade: não há
identidade, step-up, envelope, orquestrador, executor nem recibo.

---

## 15. As dezenove ameaças

| # | Ameaça | Contenção declarada |
|---|---|---|
| 1 | `actor_ref` promovido a identidade | proibição explícita; o código já congela o contrário |
| 2 | sessão promovida a consentimento | `SESSION_PRESENCE != STEP_UP` |
| 3 | voz como biometria implícita | biometria de voz **não autorizada** |
| 4 | IA confirma em nome do usuário | `AI_MODEL_DELETE_AUTHORITY = NONE` |
| 5 | policy substitui aprovação humana | `POLICY_RESOLUTION != HUMAN_APPROVAL` |
| 6 | aprovação genérica ou longeva | específica, fresca, curta, uso único |
| 7 | scope swapping | binding ao lote materializado com versões |
| 8 | replay | nonce, consumo atômico, `REPLAYED_APPROVAL = INVALID` |
| 9 | TOCTOU entre aprovação e efeito | re-resolução fresca e version check antes do efeito |
| 10 | downgrade de step-up | assurance level explícito no envelope; queda invalida |
| 11 | vazamento de credencial no registro | segredo nunca entra no domínio cognitivo nem no envelope |
| 12 | hash que relocaliza conteúdo | `APPROVAL_SCOPE_HASH != CONTENT_HASH != LOCATOR` |
| 13 | lote externo com impacto inventado | volume desconhecido é registrado como desconhecido |
| 14 | fallback permissivo quando IdP falha | bloqueio obrigatório; sem caminho alternativo |
| 15 | segunda aprovação fabricada | humanos identificados com poderes separados; sistema não aprova por ninguém |
| 16 | recibo criado antes do efeito | `RECEIPT` só após tentativa observada |
| 17 | repetição cega após falha parcial | estado auditável; nunca repetir apagamento por reflexo |
| 18 | sucessão entrando pela E4.9.4 | `NOT_INHERITED_FROM_E4_9_4` |
| 19 | conflito ou legal hold ignorado | bloqueio na avaliação **e** na re-resolução |

As dezenove são **modeladas, não mitigadas**. Não há identidade,
envelope, orquestrador ou executor para mitigá-las — e chamar isto de
mitigação repetiria a alegação falsa que a E4.9.1 recusou.

---

## 16. Riscos que declaro por conta própria

**(a) O contrato fecha o gap sem construir nada — e essa é sua maior
fragilidade.** `CLOSED_CANDIDATE_BY_AUTHORIZATION` significa que a
decisão está tomada, não que o sistema esteja seguro. Existe uma
distância enorme entre "definimos que step-up é obrigatório" e "há um
step-up". Enquanto ela existir, o gap está fechado no papel e aberto na
prática, e o placar não deve ser lido como progresso de segurança.

**(b) A estrutura de autenticação já presente convida ao erro.**
`PIA-7001`, `AuthenticationException` e `app/security/` existem desde os
módulos de plataforma. Uma implementação futura pode olhar para eles e
concluir que "a autenticação já está lá, basta ligar". Não está: a
exceção nunca é levantada e o pacote de segurança declara, por escrito,
que não faz login nem permissões. Registro isto porque o achado é fácil
de interpretar ao contrário.

**(c) O step-up será o primeiro item cortado por atrito de produto.**
Autenticação reforçada a cada exclusão permanente é friccional por
desenho — é esse o ponto. A pressão para "lembrar do step-up por 30
minutos" aparecerá, e uma janela de 30 minutos transforma uma aprovação
específica em autorização ambiente. Se essa janela algum dia for
concedida, ela precisa ser tratada como mudança de contrato, com EDR
próprio, não como ajuste de usabilidade.

**(d) A re-resolução fresca pode ser cara o bastante para ser
sacrificada.** Reconsultar custódia, versão e impedimentos antes de cada
efeito custa latência contra provedores externos. É exatamente a
verificação que alguém proporá pular "quando nada mudou desde a
aprovação" — e é a única defesa contra TOCTOU. Uma implementação que a
torne condicional reintroduz o risco inteiro por otimização.

---

## 17. Relação com as decisões anteriores

Preservado sem alteração:

```text
RETENTION_OPERATION_AUTHORITY_GAP   = CLOSED_FINAL
RETENTION_RETRIEVAL_COMPOSITION_GAP = CLOSED_FINAL
ON_EXPIRY_ACTION_UNRESOLVED         = CLOSED_FINAL
ERASURE_AUDIT_PRIMITIVE_GAP         = CLOSED_CANDIDATE_BY_AUTHORIZATION
ERASURE_TARGET_OWNERSHIP_GAP        = CLOSED_CANDIDATE_BY_AUTHORIZATION
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = CLOSED_CANDIDATE_CONDITIONAL
EXCEPTIONAL_CAUSAL_RECORD_ERASURE   = DEFERRED_STOP_CONDITION
```

A E4.9.4 fecha **apenas** a decisão normal de autoridade do usuário
presente. Não fecha a exceção causal, não implementa nenhuma autorização
anterior e não reconhece morte, incapacidade ou beneficiário.

```text
POSTHUMOUS_SUCCESSION_AUTHORITY = SEPARATE_FUTURE_MODULE
NOT_INHERITED_FROM_E4_9_4
```

Isto confirma, do lado da E4.9.4, o que a E4.9.3.1 havia declarado do
lado do legado: este módulo pressupõe **usuário presente**, e presença é
justamente a premissa que falha na sucessão.

---

## 18. O que a E4.9 ainda precisa antes de existir

Fechar os sete contratos não constrói o módulo. Para a E4.9 sair do
papel faltam, em runtime: fronteira de identidade e autenticação;
step-up; envelope de aprovação persistido com consumo atômico;
orquestrador que ligue os cinco estados; `ErasureRecord`; resolvedor de
alvo; `ArtifactStorage` e conectores; e `RetentionPolicy`.

```text
CONTRACTS CLOSED != MODULE READY
E4_9_IMPLEMENTATION = NOT_STARTED
```
