# EDR E4.3.4 — Governance Resolution Context Binding

**Natureza:** ampliação do contrato de `GovernanceResolution` e
`GovernanceDecision` para vincular a decisão ao contexto avaliado.
**Exigido por:** preflight canônico da E4.8
(`STOP_CONDITION = GOVERNANCE_RESOLUTION_CONTEXT_BINDING_GAP`).

---

## 1. A lacuna

O preflight da E4.8 demonstrou empiricamente, contra a cadeia 58:

```text
resolution(context=D1) == resolution(context=D2)   →   True
campos de contexto em GovernanceResolution         →   NENHUM
```

Logo:

```text
MATCHED RULE ID      != EVALUATED CONTEXT
POLICY ID            != EVALUATED CONTEXT
EXECUTION_AUTHORIZED != PROOF OF THE QUESTION THAT WAS AUTHORIZED
```

`matched_rule_id` identifica **qual regra** casou, não **para qual
domínio** a resolução foi emitida: uma regra que enumera `{D1}` devolve
o mesmo id para o singleton `D1` e para o contexto `{D1, D2}`.

## 2. Por que isso importa além da E4.8

A E4.6 e a E4.7 já verificavam operação e policy da resolução recebida —
correções que a E4.6.1 e a E4.7.1 pagaram caro. Mas nenhuma das duas
conseguia verificar **sob qual pergunta** a autorização foi emitida. Foi
reproduzido: uma governança que recebe `C1` e devolve resolução
produzida sob `C2` passava, e o Retrieval executava memberships e
Search; a E4.7 chegava a ler o sujeito.

A lacuna não é exclusiva da E4.8 — ela só se tornou visível ali.

## 3. As três dimensões, e só elas

`GovernanceRule.matches()` consome `domain_ids`, `actor_ref` e
`purpose`. São exatamente essas que a resolução passa a carregar.

**`session_id` fica de fora**, deliberadamente:

```text
CONTEXT != SESSION
SESSION PRESENCE != AUTHORIZATION
SESSION DIFFERENCE != GOVERNANCE DIFFERENCE
```

Ele não participa do casamento. Duas perspectivas que diferem só por
sessão devem continuar produzindo resoluções estruturalmente iguais —
há teste de integração provando isso com o manager real. Acrescentá-lo
como se tivesse fundamentado a decisão seria proveniência falsa.

## 4. Sem defaults

Os três campos são **obrigatórios**, sem default:

```text
OMITTED CONTEXT != EXPLICITLY EMPTY CONTEXT
```

Um contexto legitimamente vazio se declara passando `()`, `None`,
`None`. Com defaults, omissão e vazio explícito produziriam o mesmo
objeto — foi exatamente o estado em que `GovernanceDecision` estava, e
por isso ela foi endurecida no mesmo corretivo.

## 5. Todos os outcomes vinculam

Inclusive `PROHIBITED` e `NOT_APPLICABLE`:

```text
NO LOCAL POLICY CONSULTED != NO CONTEXT RECEIVED
CONTEXT BINDING != LOCAL POLICY PROVENANCE
```

A fronteira de segurança não consulta policy local, e a ausência de
policy não consulta regra alguma — mas as duas **receberam uma
pergunta**. Vincular o contexto não preenche `policy_key`,
`policy_version`, `policy_id` nem `matched_rule_id`: a proveniência
local continua ausente onde deve estar ausente.

## 6. Uma implementação, não duas

`_contexto_avaliado()` é o único ponto de canonicalização e validação,
compartilhado por `Decision` e `Resolution`. `resolucao_vincula_contexto()`
é o único ponto de comparação, compartilhado pelos managers da E4.6/E4.7
e pelos respectivos value objects.

Duas cópias da mesma regra divergem com o tempo — foi o que a E4.5.1
encontrou ao achar duas verificações da mesma coisa, e o que a E4.7.3
evitou ao recusar uma guarda duplicada.

O manager verifica a fronteira; o value object impede que o construtor
público contorne a mesma garantia. Mesma disciplina das E4.5.1, E4.6.1 e
E4.7.1.

## 7. O que este corretivo NÃO faz

```text
E4.3.4 ENABLES E4.8
E4.3.4 DOES NOT IMPLEMENT E4.8
```

Ele **não** fecha o vazamento multidomínio. `GovernanceRule.matches()`
continua casando domínios por interseção, e a E4.6 continua compondo o
escopo por união — nada disso foi alterado. O que muda é que agora
existe a prova contratual que permitirá à E4.8 resolver autoridade
domínio a domínio e **verificar** cada resolução.

Também não altera: `DENY_OVERRIDES`, `EMPTY_OPERATIONS_SCOPE_V1`, a
fronteira de segurança, a imutabilidade de policies publicadas, a
vigência `[from, until)`, `execution_authorized` derivado só de
`ADMISSIBLE`, a paginação/filtros da E4.6, a máquina de estados e o lock
da E4.7, ou qualquer schema persistente.

## 8. Persistência

```text
NEW_PERSISTENT_ENTITY = NO   NEW_TABLE = NO
NEW_COLUMN = NO              NEW_MIGRATION = NO
```

Os campos são transitórios em dataclasses. Nenhum JSON de policy e
nenhuma linha de banco muda.

## 9. Limite honesto

O vínculo é **verificável**, não **inforjável**: um colaborador
malicioso que construísse uma `GovernanceResolution` diretamente com o
contexto certo e o outcome errado passaria pelas três comparações. O que
este corretivo fecha é a classe de defeito real — resolução emitida sob
outra pergunta sendo apresentada como resposta a esta — não um modelo de
ameaça de adversário interno.
