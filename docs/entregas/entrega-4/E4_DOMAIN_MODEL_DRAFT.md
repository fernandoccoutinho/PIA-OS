# E4_DOMAIN_MODEL_DRAFT — rascunho do modelo de domínio

**Módulo:** E4.0 — Architecture & Contract Freeze
**Natureza:** **rascunho**. Nenhuma tabela, enum, migração ou API.

> Este documento descreve entidades **candidatas**. Nada aqui está
> implementado e nada aqui está congelado como esquema. Campos são
> ilustrativos e servem para expor decisões, não para serem
> transcritos em `models/`. Cada entidade só existe porque respondeu à
> pergunta obrigatória de `E4_PRIMITIVE_OWNERSHIP.md` §1.

---

## 1. O que a E4 **não** modela

Antes das candidatas, o que fica de fora — e por quê isso é a parte
mais importante do documento:

| Não modelado | Razão |
|---|---|
| qualquer entidade "Memory" | memória é função de contexto sobre patrimônio |
| qualquer duplicação de entidade E3 | `§21` — fonte da verdade única |
| relevância materializada | julgamento contextual, nunca fato persistido |
| qualquer score | `COUT-P8`, `COUT-P9` |
| transcript | `TRANSCRIPT_AUTO_STORAGE = NONE` |
| artefatos/arquivos | `ARTIFACT_STORAGE = DEFERRED` |

**Nenhuma entidade da E3 é estendida, herdada, envolvida ou espelhada.**
A E4 referencia COID; não o redefine, não o reinterpreta e não o
copia.

---

## 2. `MemoryDomain` (E4.1)

Segmentação lógica do patrimônio.

```
MemoryDomain
    id            identidade própria (não é COID)
    name          nome legível
    description   opcional
    created_at / updated_at
```

**Contrato:**

```
MEMORY_DOMAIN != FILESYSTEM_FOLDER
MEMORY_DOMAIN != DATABASE
MEMORY_DOMAIN != COGNITIVE_OBJECT
```

Um domínio **não é** um objeto cognitivo: não tem linhagem, não tem
história causal, não tem proveniência, não participa de
transformações. É configuração de recorte.

Exemplos ilustrativos, sem valor normativo: projeto, pesquisa, livro,
empresa, pessoal, científico. **Nenhum é enum.** Domínios são dados
criados pelo usuário, não um vocabulário fechado — congelar uma lista
aqui seria decidir pelo usuário como ele organiza o próprio patrimônio.

---

## 3. `DomainMembership` (E4.1)

Associação N:N entre `CognitiveObject` e `MemoryDomain`.

```
DomainMembership
    id            ver E4_PRIMITIVE_OWNERSHIP §5 — recomendado: sim
    coid          FK → cognitive_objects.id   (NUNCA duplica o objeto)
    domain_id     FK → memory_domains.id
    joined_at
    left_at       nullable — saída não apaga o histórico
```

**Cardinalidade:** um objeto pertence a **zero, um ou vários**
domínios. Zero é válido e não é estado degenerado.

**`left_at` nullable em vez de DELETE** é a mesma decisão que a E3
tomou em `Relationship.retired_at`, pela mesma razão:
`RETIRE != DELETE_HISTORY`. Sair de um domínio não pode apagar ter
estado nele.

**Invariante obrigatória:** a associação **não pode duplicar COID**.
Nenhum atributo do objeto é copiado para cá. Se a implementação
precisar de um campo do objeto, ela faz join — não cópia.

---

## 4. `ContextDefinition` e `MemoryContext` (E4.2)

Distinção proposta, **não congelada** (ver `E4_PRIMITIVE_OWNERSHIP` §6).

```
ContextDefinition          ← configuração persistida, reutilizável
    id
    name                   "revisão do livro", "auditoria trimestral"
    scope_spec             quais domínios/critérios compõem a vista
    created_at / updated_at

MemoryContext              ← instância efêmera, NÃO persistida
    definition             opcional — pode ser ad hoc
    actor                  quem
    purpose                para quê
    domain_scope           recorte efetivo
    task / session         opcional
```

**Congelado:**

```
CONTEXT != IDENTITY
CONTEXT != MEMORY
CONTEXT != POLICY
CONTEXT != SESSION
```

**A E4.0 não congela os campos de `MemoryContext`.** Os listados são
candidatos vindos do §7 do prompt canônico (`actor`, `subject`,
`purpose`, `domain`, `task`, `session`, `scope`) e nenhum entra sem
necessidade demonstrada pelo módulo que o exigir. Congelar campos
agora seria decidir sem evidência — e campos de contexto são
exatamente o tipo de coisa que, uma vez congelada, é usada para todo
tipo de propósito não previsto.

Uma sessão **participa** de um contexto; não o define. A E3 já registra
`session_id` em `provenance_records`, o que confirma o desenho: sessão
é uma dimensão entre outras, não a moldura.

---

## 5. Policies (E4.3 / E4.7 / E4.9)

Desenho comum às três.

```
<Tipo>Policy
    id
    name
    version            policies são versionadas, nunca editadas em silêncio
    rules              forma NÃO decidida — ver §5.1
    effective_from / effective_until
    created_at / updated_at
```

**Contrato comum:**

- policy é **configuração**, não patrimônio cognitivo;
- policy é **versionada** — avaliar hoje contra a policy de ontem deve
  ser possível, senão nenhum diagnóstico de conformidade é auditável;
- policy **não viaja** no Sync da E3 (ver `E4_SYNC_BOUNDARY.md`);
- policy **restringe acesso; nunca reescreve existência**.

### 5.1 A forma de `rules` não é decidida — de propósito

Tentação a evitar: escolher um motor de policy (OPA/Rego, Cedar, DSL
própria, expressões em JSON) porque é tecnologicamente atraente. A
Stop Condition 12 do prompt canônico nomeia exatamente isso:
*"escolher policy engine por conveniência tecnológica"*.

A ordem correta é: primeiro os módulos E4.3/E4.7/E4.9 estabelecem
**quais decisões** precisam ser expressas; só então se escolhe a forma
capaz de expressá-las. Escolher o motor antes é deixar a ferramenta
definir a semântica.

### 5.2 O caso específico de `AccessibilityPolicy`

A E3 deixou uma lacuna documentada e agora fechável. O
`AccessibilityManager` registra:

> "a exigência formal do Draft — 'sempre tem um evento causal
> associado' — depende de `CausalHistoryEvent`, que é `E3.9` (ainda
> não implementado). Como proxy interino, honesto e genuinamente
> aplicável hoje, a transição para `CAUSALLY_EXTINCT` exige um
> `reason` não-vazio."

**`E3.9` foi implementado.** O proxy interino pode ser substituído
pela exigência formal — transição para `CAUSALLY_EXTINCT` referenciando
um `CausalHistoryEvent` real.

**Importante:** isso é trabalho de E4.7 (ou E4.3, conforme a emenda de
sequência), **não da E4.0**, e exigiria mudar código da E3. Está
registrado aqui como item conhecido, com a advertência de que qualquer
alteração em `app/cognitive/` durante a E4 aciona a Stop Condition 1
(*"modificar E3 para fazer E4 fechar"*) e precisa de decisão explícita
sua — provavelmente como corretivo próprio da E3, fora da E4.

---

## 6. `ComplianceFinding` (E4.10) — transitório

```
ComplianceFinding          ← NÃO persistido
    code                   código diagnóstico próprio
    severity
    subject_ref            o que foi avaliado
    policy_ref + version   contra o quê, em qual versão
    evaluated_at
    evidence
```

Segue o desenho já provado de `IntegrityFinding` na E3: **finding não é
exceção**, e não é persistido. A E3 mantém deliberadamente os códigos
de Integrity (`INTEGRITY-*`) fora do catálogo de exceções
(`PIA-8xxx`) por essa razão exata, e a E4 herda a distinção.

Compliance **detecta e não repara** — a mesma disciplina de
`REPAIR_IMPLEMENTED = NO`.

---

## 7. `ValidatedExperience` (E4.11) — imutável

```
ValidatedExperience        ← registro, não motor
    id
    subject_ref            o que foi experimentado (COID ou evento causal)
    outcome_observed       o que se observou — fato, não julgamento
    validated_by           quem validou
    criterion_ref          contra qual critério explícito
    evidence_refs          referências, nunca conteúdo
    validated_at
```

**Imutável**, como `ProvenanceRecord` e `CausalHistoryEvent`.

**A fronteira:** nenhum campo aqui pode expressar generalização,
confiança numérica, recomendação ou peso. Todos são inferência, e
inferência automática sobre experiência é o learning engine proibido.

O teste prático permanece o de `E4_PRIMITIVE_OWNERSHIP` §7: se remover
o registro mudaria o **comportamento** do sistema, virou learning
engine.

---

## 8. Consolidação — sem entidade nova (E4.5)

`M1, M2, M3 → S1` mapeia integralmente para primitivas E3 existentes:

| Necessidade | Primitiva E3 | Já provado em |
|---|---|---|
| `S1` é um objeto | `CognitiveObject` | E3.1 |
| `S1` deriva de M1..M3 | `LineageEdge` × 3, `relation_type=MERGE` | E3.3 |
| o que foi preservado/perdido | `TransformationRecord.declared_preservations` / `declared_losses` | E3.4 |
| M1..M3 continuam existindo | nada a fazer — nada os apaga | E3.12 G1 |
| rastrear `S1 ← {M1,M2,M3}` | `LineageRepository.list_parents(S1)` | E3.3 |
| registro causal da consolidação | `CausalHistoryEvent` | E3.9 |

**Nenhuma entidade nova é necessária.** A E3.12 já demonstrou este
padrão exato funcionando ponta a ponta, incluindo travessia de
sincronização.

O que a E4.5 acrescenta é **disciplina**, não estrutura: tornar
`declared_losses` obrigatório na consolidação. Uma síntese que declara
não ter perdido nada está quase sempre errada, e o campo opcional
convida a esse erro.

---

## 9. Retenção (E4.9) — deliberadamente incompleto

```
RetentionPolicy
    id / name / version
    scope_spec
    duration_spec
    on_expiry_action       ← NÃO DECIDIDO
```

`on_expiry_action` é o ponto onde a tensão entre `COUT` e obrigação
legal se materializa. As direções candidatas estão em
`E4_GOVERNANCE_BOUNDARIES.md` §6.2 e **nenhuma está congelada**.

A E4.0 registra a tensão em vez de resolvê-la, porque resolvê-la aqui
significaria decidir sem os módulos que precisam viver com a decisão.

---

## 10. Resumo — entidades persistentes candidatas

| Entidade | Módulo | Persistida | Identidade | Imutável | Viaja no Sync |
|---|---|---|---|---|---|
| `MemoryDomain` | E4.1 | sim | própria | não | ver `E4_SYNC_BOUNDARY` |
| `DomainMembership` | E4.1 | sim | recomendada | não (`left_at`) | ver `E4_SYNC_BOUNDARY` |
| `ContextDefinition` | E4.2 | provável | própria | não | não |
| `MemoryContext` | E4.2 | **não** | — | — | não |
| `GovernancePolicy` | E4.3 | sim | própria | versionada | não |
| `AccessibilityPolicy` | E4.7 | sim | própria | versionada | não |
| `RetentionPolicy` | E4.9 | sim | própria | versionada | não |
| `ComplianceFinding` | E4.10 | **não** | — | — | não |
| `ValidatedExperience` | E4.11 | sim | própria | **sim** | ver `E4_SYNC_BOUNDARY` |

Total de entidades persistentes candidatas: **6**, contra 7 na E3
inteira. Três módulos (E4.5, E4.6, E4.8) não introduzem nenhuma.
