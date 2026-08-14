# EDR_COUT_PIA_E4 — decisões congeladas da Entrega 4

**Módulo:** E4.0 — Architecture & Contract Freeze
**Baseline:** E3 FROZEN em `014455f9` / tree `83217c40`.

> Este EDR **não reescreve** nenhuma decisão da E3. `EDR_COUT_PIA_E3.md`
> permanece válido e vigente. Aqui ficam apenas as decisões que a E4
> acrescenta, e a declaração explícita do que ela herda sem tocar.

---

## 1. Herança integral

Os dez princípios congelados na E3 são herdados **sem
reinterpretação**:

```
COUT-P1   DISTINCTION PRESERVATION
COUT-P2   CONTINUITY PRESERVATION
COUT-P3   PROVENANCE PRESERVATION
COUT-P4   MULTIPLE HISTORY PRESERVATION
COUT-P5   TRANSFORMATION PRESERVATION / DECLARED LOSS
COUT-P6   ACCESSIBILITY != EXISTENCE
COUT-P7   EQUIVALENCE != DESTRUCTIVE COLLAPSE
COUT-P8   INCOMPARABLE / UNRESOLVED ARE VALID
COUT-P9   COUT INFORMS; DOES NOT DECIDE
COUT-P10  PERSISTENT COGNITIVE MEMORY BELONGS TO PIA-OS
```

Também herdadas sem alteração, as regras transversais da E3
(`SAME CURRENT STATE != SAME CAUSAL HISTORY`,
`TEMPORAL PRECEDENCE != CAUSALITY`,
`HISTORY BOUNDARY != CAUSAL BOUNDARY`, `DIVERGENCE != INVALIDITY`,
`TRANSMISSION != OVERWRITE`,
`DISTINCTION EXTINCTION != HISTORICAL ERASURE`,
`MISSING EVIDENCE != AUTHORIZATION TO FABRICATE`,
`INTERNAL CONSISTENCY != TRUTH ABOUT REALITY`) e a classificação da
matriz de garantias do DAG.

**A E4 não pode reinterpretar nenhuma delas.** Reinterpretação seria
Stop Condition.

---

## 2. Princípio operacional acrescentado pela E4

```text
GOVERNANCE MAY RESTRICT ACCESS.
GOVERNANCE MUST NOT REWRITE EXISTENCE.
```

Não é reinterpretação de `COUT-P6` — é sua consequência operacional.
`COUT-P6` diz que acessibilidade não é existência; este princípio diz
**quem** pode mexer em qual das duas. Governança age em
acessibilidade e relevância; nunca em existência e persistência.

Corolário proibido:

```text
policy(actor X cannot access Y in context C)
    ⊬  Y does not exist
```

---

## 3. Definição arquitetural de memória

```text
Memory(Context) = Admissible_Context( Persistent( CognitivePatrimony ) )

MEMORY != STORAGE
MEMORY != TRANSCRIPT
MEMORY != SEARCH
MEMORY != INDEX
MEMORY != CACHE
MEMORY != VECTOR DATABASE
MEMORY != CURRENT STATE ONLY

MEMORY_IS_A_FUNCTION_NOT_A_TABLE = TRUE
MEMORY_AS_SCORE                  = FORBIDDEN
```

`Admissible_Context` **filtra**. Não cria, não altera, não apaga, não
reordena por importância inventada.

---

## 4. As quatro distinções fundamentais

```text
EXISTENCE     != PERSISTENCE
PERSISTENCE   != ACCESSIBILITY
ACCESSIBILITY != RELEVANCE
RELEVANCE     != EXISTENCE

NOT_RETRIEVED != FORGOTTEN
INACCESSIBLE  != NONEXISTENT
IRRELEVANT    != DELETED
```

Existência e persistência **não dependem de contexto**.
Acessibilidade e relevância **dependem**. Governança só alcança as
duas últimas.

---

## 5. LOP e CLEO — delimitação

```text
LOP = PERSISTENCE PRINCIPLE, NOT A METRIC

persistence_score         = NONE
universal survival score  = NONE
global importance score   = NONE
automatic promotion score = NONE

PERSISTENCE != POPULARITY
PERSISTENCE != RECENCY
PERSISTENCE != FREQUENCY
```

Persistência é tratada por estados, relações, evidências, continuidade
e contexto — nunca por métrica universal inventada.

```text
CLEO = CONTEXTUAL ADMISSIBILITY PRINCIPLE, NOT COSMOLOGY

EXISTING_PATRIMONY != ADMISSIBLE_PATRIMONY_IN_CONTEXT

NO GR — NO COSMOLOGY — NO FRIEDMANN — NO EINSTEIN EQUATIONS
NO DE SITTER — NO HORIZON THERMODYNAMICS — NO COSMOLOGICAL KERNELS
PHYSICS_IN_APP = NONE
```

A analogia que atravessa é estrutural e única: **o que é observável
depende de onde se observa, e isso não altera o que existe.** Mesma
disciplina já exercida na E3 com "Galaxy Trace".

---

## 6. Fonte da verdade

```text
E3 = SOURCE OF TRUTH FOR COGNITIVE PATRIMONY
E4 = SOURCE OF TRUTH ONLY FOR NEW MEMORY/GOVERNANCE STATE

DUPLICATED CognitiveObject   = FORBIDDEN
DUPLICATED Provenance        = FORBIDDEN
DUPLICATED CausalHistory     = FORBIDDEN
DUPLICATED Lineage           = FORBIDDEN
DUPLICATED Relationship      = FORBIDDEN
DUPLICATED Transformation    = FORBIDDEN

E4 CONSUMES E3. E4 DOES NOT REPLACE E3.
E4 DOES NOT CREATE A SECOND COGNITIVE LIBRARY.
```

Regra de admissão de primitiva: toda entidade persistente nova
responde *"por que a E3 não representa isto?"*. Resposta insuficiente
→ entidade não é criada.

---

## 7. Fronteiras de motor

```text
GOVERNANCE != TRUTH ENGINE
GOVERNANCE != LEARNING ENGINE
GOVERNANCE != REPAIR ENGINE
GOVERNANCE != COUT DECISION ENGINE

COMPLIANCE != INTEGRITY
COMPLIANCE != REPAIR
COMPLIANCE != LEARNING

INTEGRITY  : state vs structural invariants
COMPLIANCE : state/action vs policy

COMPLIANCE DETECTS. COMPLIANCE DOES NOT REPAIR.
```

---

## 8. Fronteira de aprendizado

Reafirmado da E3:

```text
ERROR_IS_LEARNING   = FALSE
ERROR_IS_EVIDENCE   = TRUE
PIA_LEARNING_SOURCE = VALIDATED_EXPERIENCE
```

**Acrescentado pela E4** — fechando a assimetria:

```text
SUCCESS_IS_NOT_AUTOMATIC_LEARNING
REPETITION_IS_NOT_AUTOMATIC_LEARNING
```

Já estava congelado que erro não é aprendizado. Faltava dizer que
sucesso e repetição também não são. Validação é ato deliberado com
critério explícito, nunca limiar de contagem.

Princípio evolutivo, registrado para uso futuro:

```text
variation → experience → evidence → validation → selection
          → POSSIBLE persistence

VARIATION            != KERNEL MUTATION
VALIDATED EXPERIENCE != AUTOMATIC KERNEL CHANGE
AUTONOMOUS_KERNEL_MUTATION = FORBIDDEN
```

O "*possible*" não é decoração: o elo entre validação e persistência
permanece deliberado e externo.

Teste operacional da fronteira: **se remover o registro mudaria o
comportamento do sistema, virou learning engine.**

---

## 9. Consolidação

```text
CONSOLIDATION != DELETION
SUMMARY       != SOURCE REPLACEMENT

M1, M2, M3 → S1   ⟹   S1 ← {M1, M2, M3}  DEVE PERMANECER RASTREÁVEL

NO SILENT SOURCE ERASURE
CONSOLIDATION_USES_E3_PRIMITIVES = TRUE
NEW_CONSOLIDATION_LINEAGE        = NOT AUTHORIZED
DECLARED_LOSS_ON_CONSOLIDATION   = MANDATORY
```

Consolidação é transformação com múltiplas entradas e perda declarada —
padrão que a E3 já demonstrou ponta a ponta.

---

## 10. Retenção e esquecimento

```text
PRESERVATION = RETENTION FOREVER   ← FALSE

COUT DOES NOT AUTHORIZE UNLIMITED RETENTION AGAINST
LEGITIMATE POLICY OR ERASURE OBLIGATION

forgetting != deletion
inaccessibility != deletion
causal extinction != deletion
retention != preservation
legal erasure = LEGITIMATE, MUST BE EXPLICIT AND DISTINGUISHABLE
```

O que COUT exige não é retenção eterna; é que a exclusão seja
**explícita, registrada e distinguível** de inacessibilidade, extinção
causal e não-recuperação. Apagar por obrigação é legítimo; apagar e
fingir que nunca existiu não é.

Tensão `legal erasure × CausalHistory`: **registrada, não resolvida**.
Direções candidatas em `E4_GOVERNANCE_BOUNDARIES.md` §6.2. Decisão em
E4.9.

---

## 11. Transporte

```text
POLICY_PORTABLE = FALSE   (governance, accessibility, retention)

IMPORTING PATRIMONY NEVER IMPORTS THE GOVERNANCE THAT ACCOMPANIED IT
THE DESTINATION APPLIES ITS OWN GOVERNANCE

E3_SYNC_MODIFIED_IN_E4_0  = NO
NEW_SYNC_SECTIONS_IN_E4_0 = NONE
```

Sincronização não é canal de imposição de política.

---

## 12. Neutralidade de provider e fronteira de transcript

```text
PROVIDER_NEUTRALITY = TRUE

PROVIDER/MODEL MAY PARTICIPATE IN PROVENANCE
PROVIDER/MODEL MAY NOT OWN COGNITIVE IDENTITY

TRANSCRIPT_AUTO_STORAGE = NONE
TRANSCRIPT_AS_MEMORY    = FALSE

SEARCH RESULT        != MEMORY
TOP_K                != TRUTH
EMBEDDING_SIMILARITY != COGNITIVE_EQUIVALENCE
VECTOR_DATABASE_AS_SOURCE_OF_TRUTH = FALSE
```

`EMBEDDING_SIMILARITY != COGNITIVE_EQUIVALENCE` é proteção direta de
`COUT-P7`: dois objetos com vetores quase idênticos e histórias
diferentes continuam sendo dois objetos.

---

## 13. Propriedade

```text
USER/ORGANIZATION OWNS ITS COGNITIVE PATRIMONY
PIA MANAGES PERSISTENCE

LOGICAL/CONTROL OWNERSHIP != LEGAL OWNERSHIP
NO LEGAL CONCLUSION IS ASSERTED BY THIS ARCHITECTURE
```

Documentos técnicos usam exclusivamente o sentido de controle lógico.
Titularidade jurídica depende de jurisdição, contrato e natureza do
conteúdo, e **não é decidida por arquitetura de software**.

---

## 14. Teste arquitetural forte — resultado

Demonstrado **em execução**, contra a E3 congelada, sem modificar uma
linha dela:

```text
Accessible(P, C1) != Accessible(P, C2)   ✓
Accessible(P, C1) != Accessible(P, C3)   ✓
Patrimony(P, C1)  == Patrimony(P, C2)    ✓  (censo idêntico byte a byte)

CONTEXT CHANGES VIEW
CONTEXT DOES NOT SILENTLY REWRITE PATRIMONY

objeto INACCESSIBLE      permanece existente          ✓
objeto CAUSALLY_EXTINCT  permanece existente          ✓
sua história causal      preservada                   ✓
sua linhagem             preservada                   ✓
invisível em C1 e C2, recuperável por COID direto     ✓

NOT_RETRIEVED != FORGOTTEN                            ✓

COUT_STRONG_ARCHITECTURAL_TEST = PASS
E3_MODIFIED = NO
```

Achado relevante: a admissibilidade contextual foi demonstrada com
**contexto puramente em memória** — nenhuma tabela nova foi necessária
para separar vista de patrimônio. Isso é evidência de que a E4 pode
ser construída como camada de composição sobre a E3, e não como
segunda biblioteca.

---

## 15. Estado do congelamento

```text
E4.0_ARCHITECTURE_GATE = PASS
E4_ARCHITECTURE        = FROZEN
READY_FOR_E4_1         = TRUE

E4_SEQUENCE = AUDITED — EMENDA PROPOSTA, PENDENTE DE DECISÃO
```

A sequência da E4 foi auditada e **duas inversões de dependência
reais** foram encontradas (ver `E4_IMPLEMENTATION_SEQUENCE.md` §2–§4).
A emenda proposta aguarda decisão do titular do Plano Mestre. Tudo o
mais nesta entrega está congelado.

E4.1 **não** é iniciada automaticamente.
