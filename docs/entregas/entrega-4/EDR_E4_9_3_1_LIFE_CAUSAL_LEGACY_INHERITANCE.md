# EDR E4.9.3.1 — Legado causal de vida e herança dirigida pelo usuário

**Natureza:** decisão arquitetural **exclusivamente documental**.
**Baseline:** cadeia 72 (`6c759f05`), auditada como `E4_9_3_AUDIT = PASS_FINAL`.
**Complementa, sem reabrir:** `EDR_E4_9_3_DELETE_TIMING_TRASH_DISPOSITIONS.md`,
`E4_9_2_LEGAL_ERASURE_CAUSAL_HISTORY_AUTHORIZATION.md`,
`E4_9_1_ERASURE_TARGET_CUSTODY_CONTRACT.md`.

```text
LIFE_CAUSAL_LEGACY_CONTRACT    = AUTHORIZED_NOT_IMPLEMENTED
USER_DIRECTED_INHERITANCE_PLAN = AUTHORIZED_NOT_IMPLEMENTED
LEGACY_LIBRARY_VIEW            = AUTHORIZED_NOT_IMPLEMENTED
POSTHUMOUS_EXECUTION_AUTHORITY = NOT_AUTHORIZED
LEGAL_INSTRUMENT_INTEGRATION   = DEFERRED
CURRENT_IMPLEMENTATION_CLAIM   = NONE
```

---

## 1. O problema

O patrimônio cognitivo do usuário **não começa no dia da instalação**. A
E4.9.3 decidiu quem manda sobre o que existe no sistema. Falta decidir o
que acontece com o que existiu **antes** dele, e com o que deve
sobreviver **depois** do usuário.

O caso motivador é concreto: alguém que passou por seis organizações de
naturezas distintas — grande, pequena, multinacional, adquirida ou
vendida, familiar —, criou negócios, exerceu profissões diferentes,
concluiu graduação, pós-graduação e mestrado, iniciou doutorado,
escreveu livros e artigos, criou sites e acumulou produção. Esse rastro
está disperso entre memória pessoal, documentos, correspondência, mídias,
organizações que já não existem e serviços de terceiros.

O sistema deve ajudar essa pessoa a **localizar, conectar, validar e
preservar** essa trajetória — e a decidir o que acontece com ela.

---

## 2. O que este documento **não** é

```text
LEGACY_CAUSAL_HISTORY != CV
LEGACY_CAUSAL_HISTORY != FILE_BACKUP
LEGACY_CAUSAL_HISTORY != AI_GENERATED_BIOGRAPHY
```

Currículo lista posições e omite o porquê. Backup guarda bytes e perde o
sentido. Biografia automática **inventa** o que não foi confirmado — e é
o modo mais provável de esta decisão dar errado.

O legado causal conecta:

```text
experiência → aprendizado → decisão → produção → consequência → nova etapa
```

A narrativa pertence ao usuário. O PIA propõe, pergunta, relaciona e
organiza; não autoriza a si mesmo a contar a vida de ninguém.

---

## 3. Alternativas consideradas

| # | Alternativa | Por que foi rejeitada |
|---|---|---|
| 1 | módulo de currículo/perfil | reduz causalidade a lista de cargos; perde decisão, aprendizado e consequência |
| 2 | importador que gera biografia automática | inferência viraria fato; é exatamente a ameaça nº 1 do §18 |
| 3 | storage separado para o legado | duplicaria patrimônio e criaria segunda fonte de verdade sobre os mesmos objetos |
| 4 | enum persistido de modalidades de legado | escolhe schema numa entrega documental e congela vocabulário antes do desenho |
| 5 | gatilho por inatividade (`N` meses sem login) | inatividade não é morte; automatiza a decisão mais irreversível que existe |
| 6 | tratar o plano como testamento | promete validade jurídica que arquitetura de software não pode entregar |
| 7 | herdar a conta (credenciais) em vez do conteúdo | confunde acesso com titularidade e transforma segredo em patrimônio |
| **8** | **contrato conceitual: visão da Biblioteca + plano revogável + poderes separados, nada implementado** | **adotada** |

As alternativas 5 e 7 merecem registro porque são as **soluções
naturais** — e as duas erram no mesmo ponto: substituem autoridade
verificada por conveniência técnica.

---

## 4. A decisão

### 4.1 História causal de vida

Autoriza-se **conceitualmente** uma trajetória que conecte evento ou
período, papel exercido, organização e contexto, competências e
aprendizados, decisões e consequências, obras e artefatos associados,
pessoas e organizações relacionadas (respeitada a privacidade), relações
com etapas anteriores e posteriores, fontes e grau de confirmação, e
visibilidade com intenção de legado.

**Nenhuma tabela, coluna, enum ou modelo é escolhido.** A E3 não é
tocada. `CausalEventType` permanece com os quatro membros medidos na
baseline (`created`, `transformed`, `compared`, `accessed`), e nada aqui
propõe um quinto.

### 4.2 Evidência e certeza

Vocabulário **conceitual, não persistido**:

```text
DOCUMENT_VERIFIED
USER_ATTESTED
THIRD_PARTY_ATTESTED
PIA_INFERRED_UNCONFIRMED
DISPUTED
UNKNOWN
```

A regra que sustenta tudo o mais:

```text
PIA_INFERRED_UNCONFIRMED != FACT
INFERENCE ASKS A QUESTION, IT DOES NOT ANSWER ONE
```

Inferência serve para **perguntar, relacionar e sugerir pesquisa**.
Relato pessoal sem documento continua legítimo — e continua marcado como
relato. Documento comprova o que contém, não a interpretação nem o
mérito. Divergência entre fontes é **preservada**, não resolvida pela IA
por conveniência: `DISPUTED` é um estado terminal aceitável.

Afirmações sobre terceiros exigem proveniência e respeito à privacidade
de quem não é o usuário.

### 4.3 Biblioteca do Legado

```text
LEGACY_LIBRARY           = COGNITIVE_LIBRARY_USER_VIEW
LEGACY_LIBRARY          != NEW_STORAGE
LEGACY_VIEW_MEMBERSHIP  != CONTENT_DUPLICATION
```

É uma **visão** da Biblioteca Cognitiva. Um mesmo objeto pode aparecer em
projeto, pesquisa e legado sem cópia física — precedente já estabelecido
pela E4.9.3, que tratou pastas como vistas organizacionais e não como
propriedade ou storage.

Categorias iniciais e **extensíveis pelo usuário**: trajetória
profissional; formação acadêmica; empresas e negócios; profissões e
atividades; projetos e realizações; livros, artigos e pesquisas; sites e
produção digital; decisões, aprendizados e contribuições; memórias e
relatos pessoais; instruções autorais e de legado.

### 4.4 Proteção contra esquecimento indevido

```text
OLD         != DISPOSABLE
INACTIVE    != VALUELESS
SUPERSEDED  != WITHOUT_HISTORICAL_VALUE
LEGACY_ITEM != AUTOMATIC_CLEANUP_CANDIDATE
```

Item marcado como legado **não entra** em sugestão de limpeza por idade,
tamanho ou ausência de uso. Isto **não reabre** a E4.9.3: aquela entrega
já decidiu que tamanho, idade e ausência de uso são sinal informativo e
nunca bastam para excluir. A E4.9.3.1 acrescenta uma disposição de
proteção — e a proteção é do usuário, não do sistema.

**Retirar a proteção e excluir são decisões distintas**, e nenhuma delas
é do PIA. O sistema pode informar conflito legal, existência de cópia
externa, dependência ou risco; não redefine sozinho valor histórico.

### 4.5 Narrativa autoral

```text
USER_CONFIRMED_NARRATIVE != AI_DRAFT
CORRECTION               != HISTORICAL_ERASURE
QUALITY_REVIEW_NOTE      != CONTENT_BACKUP
```

A interface deve distinguir texto escrito pelo usuário, texto importado
com fonte, texto proposto pela IA, texto confirmado pelo usuário e texto
contestado ou não verificado. Cada revisão segue a `QUALITY_REVIEW_NOTE`
da E4.9.3, com o mesmo limite qualitativo:

```text
IF THE NOTE CAN RECOMPOSE THE CONTENT, IT IS CONTENT
```

### 4.6 Plano de legado

Vocabulário **conceitual e revogável**, sem enum:

```text
PRESERVE_PRIVATE
SHARE_DURING_LIFETIME
TRANSFER_READ_ONLY
TRANSFER_STEWARDSHIP
AUTHORIZE_PUBLICATION
ERASE_ON_VERIFIED_TRIGGER
NO_POSTHUMOUS_TRANSFER
```

Os poderes são **rigorosamente separados** — visualizar; custodiar e
organizar; publicar; licenciar; transferir titularidade quando
juridicamente possível; excluir:

```text
READ_ACCESS          != STEWARDSHIP
STEWARDSHIP          != PUBLICATION_AUTHORITY
PUBLICATION_AUTHORITY != OWNERSHIP
BENEFICIARY          != AUTHOR
```

Uma pessoa pode administrar sem herdar; outra pode ler sem publicar;
outra pode receber direito sobre uma obra específica e nada mais.
**Vínculo familiar não é autoridade** e não infere papel algum.

### 4.7 Morte, incapacidade e inatividade

```text
INACTIVITY           != DEATH
ABSENCE              != INCAPACITY
AI_INFERENCE         != SUCCESSION_PROOF
BENEFICIARY_MESSAGE  != VERIFIED_TRIGGER
SCHEDULER_TIMEOUT    != POSTHUMOUS_AUTHORITY
```

**Nenhum** período sem login, modelo, comando de voz, e-mail ou
afirmação de terceiro ativa transmissão ou apagamento. Um processo
futuro exigirá evidência externa verificável, revisão humana, prevenção
contra fraude, coação e conflito, e compatibilidade jurídica.

Esta entrega **não escolhe** jurisdição, documento, cartório, autoridade
ou fornecedor. `ERASE_ON_VERIFIED_TRIGGER` nomeia uma intenção do
usuário; o gatilho verificado que a acionaria **não existe**, e enquanto
não existir a modalidade é inerte.

### 4.8 Limites jurídicos

```text
PIA_LEGACY_PLAN   != LEGAL_WILL
OPERATIONAL_INTENT != AUTOMATIC_RIGHT_TRANSFER
```

O PIA registra a vontade e organiza o patrimônio. Eficácia jurídica
depende de instrumentos e autoridades aplicáveis, fora desta entrega.
Conflito com legal hold, ordem válida, propriedade de terceiro, contrato
ou instrumento sucessório **bloqueia** e exige tratamento humano e
jurídico.

Este documento **não fornece aconselhamento jurídico** e não promete
validade universal. A distinção entre *logical/control ownership* e
*legal ownership* do §9 do `E4_GOVERNANCE_BOUNDARIES.md` continua
valendo integralmente: arquitetura de software decide a primeira e não
decide a segunda.

### 4.9 Credenciais e segredos

```text
CREDENTIALS     != INHERITABLE_CONTENT
SECRET_TRANSFER != LEGACY_TRANSFER
ACCOUNT_ACCESS  != CONTENT_INHERITANCE
```

Senhas, tokens, chaves privadas, sessões, segredos e certificados de
autenticação **nunca** entram como conteúdo comum de herança, nota
causal, narrativa, recibo ou exportação. Recuperação ou delegação de
conta exige arquitetura de segurança própria, fora daqui.

Acesso a uma conta externa pode depender dos termos do provedor e **não
equivale** a propriedade do conteúdo — mesma ressalva já registrada na
E4.9.1 para `AUTHORIZED_CONNECTOR_REFERENT`.

### 4.10 Revogação e versão vigente

```text
LATEST_DIRECTIVE_TIMESTAMP        != VALID_DIRECTIVE
VALIDATED_CURRENT_LEGACY_DIRECTIVE = GOVERNING_INTENT
REVOCATION = NEW_CAUSAL_EVENT_NOT_HISTORICAL_ERASURE
```

Enquanto capaz e autorizado, o usuário mantém controle final. Mudanças
são versionadas, datadas, atribuídas e confirmadas. A diretiva vigente
governa ação futura; versões anteriores permanecem para auditoria **sem
continuar executáveis** — revogar não apaga história, cria evento novo.

`VALIDATED_CURRENT_LEGACY_DIRECTIVE` é **conceitual**. Medido na
baseline: `RevisionStatus = ['current', 'superseded']`, e
`VALIDATED_CURRENT` **não existe**. Reutilizar `RevisionStatus.CURRENT`
como se fosse validação do usuário confundiria "revisão corrente da
cadeia" com "vontade confirmada" — a mesma armadilha já registrada na
E4.9.3, agravada aqui porque o objeto em questão decide o destino de um
acervo.

**Capacidade civil não é decidida por este sistema.** Verificação futura
é Stop Condition própria.

### 4.11 Portabilidade

Exportação futura, humana e estruturada, contendo apenas conteúdo no
escopo autorizado, relações causais e proveniência admissíveis, notas
qualitativas permitidas, instruções vigentes e limitações.

```text
EXPORT != RIGHT_TRANSFER
EXPORT != SOURCE_ERASURE
```

Nunca inclui credenciais, segredos, itens privados fora do escopo ou
conteúdo de terceiro sem autoridade. Formato não é escolhido e nenhum
exportador é implementado.

---

## 5. Os dezesseis casos obrigatórios

| # | Caso | Decisão e limite atual |
|---|---|---|
| 1 | trajetória a partir de seis empresas e múltiplas profissões | o usuário reconstrói e confirma; o PIA propõe conexões marcadas como `PIA_INFERRED_UNCONFIRMED` até confirmação. Nada implementado |
| 2 | diploma verificado, doutorado iniciado declarado | diploma `DOCUMENT_VERIFIED`; doutorado `USER_ATTESTED`. Os dois convivem na mesma trajetória sem que o segundo seja promovido |
| 3 | negócio com documentação parcial | parte `DOCUMENT_VERIFIED`, parte `USER_ATTESTED`; lacuna fica visível como lacuna, não é preenchida por inferência |
| 4 | livro publicado, rascunhos e notas de revisão | obra e rascunhos são artefatos distintos; notas seguem `QUALITY_REVIEW_NOTE` e não podem recompor versões apagadas |
| 5 | site antigo offline com valor histórico | valor histórico é declaração do usuário; offline não é ausência de valor. Se o conteúdo original não é alcançável, o registro é honesto quanto a isso |
| 6 | inferência do PIA sobre relação causal não confirmada | apresentada **como pergunta**, nunca como fato; permanece `PIA_INFERRED_UNCONFIRMED` até o usuário confirmar, negar ou marcar `DISPUTED` |
| 7 | item de legado aparecendo em limpeza por tamanho | **não aparece**. `LEGACY_ITEM != AUTOMATIC_CLEANUP_CANDIDATE`. Não há limpeza automática implementada de todo modo |
| 8 | beneficiário com leitura, sem publicação | `READ_ACCESS != PUBLICATION_AUTHORITY`. Concessão futura seria explícita e separada. Nada implementado |
| 9 | administrador sem titularidade nem autoria | `STEWARDSHIP != OWNERSHIP`; `BENEFICIARY != AUTHOR`. Custodiar não converte em proprietário por decurso de prazo ou uso |
| 10 | usuário revogando diretiva anterior | revogação é **evento causal novo**; a versão anterior fica auditável e deixa de ser executável |
| 11 | vinte e quatro meses sem login | `INACTIVITY != DEATH`. Nada acontece. Nenhuma transmissão, nenhum apagamento, nenhuma sugestão de sucessão |
| 12 | terceiro alegando morte do usuário | `BENEFICIARY_MESSAGE != VERIFIED_TRIGGER`. Alegação não é prova; exigiria evidência externa verificável e revisão humana, que não existem |
| 13 | conflito entre plano do PIA e ordem ou legal hold | **bloqueia** e escala para tratamento humano e jurídico. A IA não decide conflito jurídico |
| 14 | tentativa de transmitir senha ou chave privada | recusada. `CREDENTIALS != INHERITABLE_CONTENT`; segredo não entra em legado, nota, narrativa ou exportação |
| 15 | conversa privada fora da herança | escopo é do usuário, item por item; `CONVERSATION != ARTIFACT` (E4.9.3). Ausência de marcação **não** presume inclusão |
| 16 | pesquisa e manuscrito autorizados para publicação futura | `AUTHORIZE_PUBLICATION` registra intenção; a autoridade de publicar exige executor e verificação que não existem. Hoje termina em recusa explicada |

Os casos 8 a 14 e 16 terminam, **hoje**, em recusa explicada — porque
`DESTRUCTIVE_EXECUTION_AUTHORITY_GAP` e a autoridade de sucessão
continuam abertas. Registrar a intenção é possível; agir sobre ela não.

---

## 6. As dezessete ameaças

| # | Ameaça | Contenção declarada |
|---|---|---|
| 1 | IA inventa biografia | narrativa é do usuário; proposta da IA é sempre rotulada e nunca confirmada por omissão |
| 2 | inferência vira fato | `PIA_INFERRED_UNCONFIRMED` é estado distinto e não se promove por tempo, repetição ou silêncio |
| 3 | idade vira dispensabilidade | `OLD != DISPOSABLE` |
| 4 | item de legado em limpeza automática | `LEGACY_ITEM != AUTOMATIC_CLEANUP_CANDIDATE` |
| 5 | narrativa da IA suplanta a autoria | `USER_CONFIRMED_NARRATIVE != AI_DRAFT` |
| 6 | beneficiário se autoatribui acesso | acesso decorre de diretiva do usuário, nunca de pedido do interessado |
| 7 | vínculo familiar tratado como autoridade | parentesco não infere papel, escopo nem poder |
| 8 | inatividade vira prova de morte | `INACTIVITY != DEATH` |
| 9 | incapacidade inferida pelo modelo | `AI_INFERENCE != SUCCESSION_PROOF`; capacidade civil não é decidida aqui |
| 10 | diretiva revogada continua ativa | só a vigente governa ação futura; anteriores ficam auditáveis e inertes |
| 11 | custodiante vira proprietário | `STEWARDSHIP != OWNERSHIP` |
| 12 | leitura vira permissão de publicação | `READ_ACCESS != PUBLICATION_AUTHORITY` |
| 13 | credencial exportada como herança | `CREDENTIALS != INHERITABLE_CONTENT` |
| 14 | propriedade de terceiro transmitida | conteúdo de terceiro não é patrimônio do usuário; exige autoridade própria |
| 15 | plano apresentado como testamento | `PIA_LEGACY_PLAN != LEGAL_WILL` |
| 16 | conflito jurídico decidido pela IA | bloqueia e escala; a IA informa, não arbitra |
| 17 | transferência ou apagamento sem executor autorizado | `POSTHUMOUS_EXECUTION_AUTHORITY = NOT_AUTHORIZED`; nenhum executor existe |

As dezessete são **modeladas, não mitigadas**: não há beneficiário,
diretiva, gatilho, custódia, publicação ou executor em runtime. Chamar
isto de mitigação seria a mesma alegação falsa que a E4.9.1 recusou.

---

## 7. Riscos que declaro por conta própria

Nenhum deles está no prompt. Registro porque a decisão fica pior sem
eles.

**(a) A Biblioteca do Legado pode virar autobiografia assistida.** O
sistema que ajuda a reconstruir trinta anos de trajetória é, por
construção, um sistema que **preenche lacunas** — e preencher lacuna é a
função de que a inferência mais gosta. A distinção entre
`PIA_INFERRED_UNCONFIRMED` e `USER_ATTESTED` é fácil de escrever num
documento e difícil de sustentar numa interface que quer parecer útil.
O ponto de falha não será um módulo mentindo; será uma sugestão aceita
sem leitura, mês após mês, até a trajetória inteira ser da IA com
carimbo do usuário. Uma implementação honesta precisa tornar a
confirmação **custosa o bastante para ser real** e mostrar, a qualquer
momento, quanto da narrativa nasceu de inferência.

**(b) O plano de legado será lido como testamento, por mais que se diga
o contrário.** Quem organiza o próprio acervo e nomeia beneficiários
acredita ter resolvido algo. `PIA_LEGACY_PLAN != LEGAL_WILL` protege a
arquitetura, não a expectativa da pessoa — e a descoberta de que o plano
não tinha eficácia jurídica ocorreria no pior momento possível: quando o
usuário já não está para corrigir. Esta ressalva precisa sobreviver até
a interface, em linguagem que uma pessoa leiga entenda, e não apenas
num EDR.

**(c) `ERASE_ON_VERIFIED_TRIGGER` é a modalidade mais perigosa do
conjunto.** É a única que combina irreversibilidade com ausência do
usuário — exatamente quando ninguém pode desfazer um engano. Enquanto o
gatilho verificado não existir, ela é inerte e isso é bom. Quando
existir, ela merecerá autoridade **mais** estrita que a exclusão
comum, não igual: o critério da E4.9.3 pressupõe um humano competente
disponível para decidir, e essa premissa é precisamente a que falha
aqui.

**(d) Terceiros aparecem no legado sem terem escolhido aparecer.** Uma
trajetória de trinta anos nomeia sócios, chefes, alunos, familiares e
desafetos. O prompt trata privacidade de terceiros em uma linha (§5) e
uma ameaça (§18, propriedade de terceiro), mas o problema é maior: um
relato `USER_ATTESTED` sobre outra pessoa é, para essa pessoa, um dado
pessoal que ela não forneceu e talvez conteste. Transmitir esse relato a
um beneficiário amplia o alcance sem que o terceiro saiba. Não proponho
solução aqui — proponho que a E4.9.4, ou o módulo que tratar de
publicação, **não** trate isso como caso de borda.

---

## 8. Relação com E4.9.3 e E4.9.4

Preservado sem alteração:

```text
E4_9_3_AUDIT                        = PASS_FINAL
ON_EXPIRY_ACTION_UNRESOLVED         = CLOSED_FINAL
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
EXCEPTIONAL_CAUSAL_RECORD_ERASURE   = DEFERRED_STOP_CONDITION
E4_9_IMPLEMENTATION                 = NOT_STARTED
```

A E4.9.3.1 **acrescenta** uma disposição de proteção histórica. Não
reabre `on_expiry`, não materializa `VALIDATED_CURRENT` e não autoriza a
E4.9.4.

E, explicitamente: **a autoridade de sucessão não é atribuída à E4.9.4
por herança de escopo.** A E4.9.4 trata de comandos, aprovação e
execução por um usuário presente e competente. Executar disposições de
alguém que morreu ou perdeu capacidade envolve prova externa,
jurisdição e revisão humana que aquele módulo não contém. Presumir que
"o executor da E4.9.4 servirá" seria repetir, em escala maior, o erro de
tratar presença descritiva como autoridade.

```text
POSTHUMOUS_SUCCESSION_AUTHORITY = SEPARATE_FUTURE_MODULE
NOT_INHERITED_FROM_E4_9_4
```

---

## 9. Estado

```text
LIFE_CAUSAL_LEGACY_CONTRACT    = AUTHORIZED_NOT_IMPLEMENTED
USER_DIRECTED_INHERITANCE_PLAN = AUTHORIZED_NOT_IMPLEMENTED
LEGACY_LIBRARY_VIEW            = AUTHORIZED_NOT_IMPLEMENTED
POSTHUMOUS_EXECUTION_AUTHORITY = NOT_AUTHORIZED
LEGAL_INSTRUMENT_INTEGRATION   = DEFERRED
CURRENT_IMPLEMENTATION_CLAIM   = NONE
```

Nenhum código, teste, migração ou schema foi alterado. Não se declara
`PASS_FINAL`, validade testamentária, implementação ou autoridade
póstuma.
