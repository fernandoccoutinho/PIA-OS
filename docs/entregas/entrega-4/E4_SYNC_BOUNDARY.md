# E4_SYNC_BOUNDARY — o que viaja, o que fica, o que não persiste

**Módulo:** E4.0 — Architecture & Contract Freeze
**Natureza:** identificação, sem implementação. **E3 Sync não é
alterado.**

---

## 1. Regra de fronteira

```
E3 Synchronization permanece dona do transporte do patrimônio E3.
E4.0 identifica estados novos; não implementa transporte para nenhum.
```

O Sync da E3 transporta exatamente sete seções, congeladas em
`SECTION_BY_TABLE`:

```
cognitive_objects       → objects
transformation_records  → transformations
causal_histories        → causal_histories
lineage_edges           → lineage
provenance_records      → provenance
relationships           → relationships
causal_history_events   → causal_events
```

**Nenhuma seção nova é adicionada pela E4.0.** Qualquer estado novo da
E4 que venha a viajar exigirá decisão explícita em módulo próprio, com
seu próprio gate — e provavelmente um envelope próprio, e não a
extensão do envelope da E3.

---

## 2. As três classes de estado

| Classe | Definição | Sobrevive a export/import | Sobrevive a restart |
|---|---|---|---|
| **PORTABLE** | faz parte do patrimônio ou o acompanha significativamente | sim | sim |
| **LOCAL** | pertence a esta instalação; transportá-lo seria impor configuração alheia | **não** | sim |
| **TRANSIENT** | existe durante uma operação | não | **não** |

A distinção que mais importa é PORTABLE × LOCAL, e o critério é uma
pergunta única:

> Se este estado viajasse para outra instalação, ele descreveria
> **o patrimônio** ou imporia **as decisões de quem exportou**?

O primeiro caso viaja. O segundo, não. Uma policy que viaja é uma
policy que a instalação de destino não escolheu, não pode auditar e
possivelmente não pode cumprir — e que, pior, chegaria com aparência
de fato sobre o patrimônio.

---

## 3. Matriz F — PORTABLE vs LOCAL vs TRANSIENT

### 3.1 Estado da E3 (congelado, referência)

| Estado | Classe | Observação |
|---|---|---|
| `CognitiveObject` | **PORTABLE** | é o patrimônio |
| COID / CLID | **PORTABLE** | identidade e continuidade preservadas no transporte |
| `LineageEdge` | **PORTABLE** | provado em E3.12 G3 |
| `TransformationRecord` | **PORTABLE** | com perdas declaradas |
| `Relationship` | **PORTABLE** | incluindo retiradas |
| `ProvenanceRecord` | **PORTABLE** | incluindo provider/model `NULL` |
| `CausalHistory` / `Event` | **PORTABLE** | incluindo predecessor entre histórias |
| `exported_at` | **TRANSIENT** | único campo de transporte permitido a divergir |
| Index | **LOCAL** | derivado e reconstruível — nunca viaja |
| Integrity findings | **TRANSIENT** | resultado de avaliação |
| `SyncReport` / `SyncConflict` | **TRANSIENT** | não persistidos |

### 3.2 Estado candidato da E4

| Estado | Classe proposta | Justificativa |
|---|---|---|
| `MemoryDomain` | **decisão aberta** — ver §4 | é recorte do patrimônio, mas também organização local |
| `DomainMembership` | **decisão aberta** — segue o domínio | pertencimento acompanha o recorte |
| `ContextDefinition` | **LOCAL** | configuração de trabalho de quem opera |
| `MemoryContext` | **TRANSIENT** | instância de operação; não persiste |
| `GovernancePolicy` | **LOCAL** | ver §5 — nunca viaja |
| `AccessibilityPolicy` | **LOCAL** | ver §5 — nunca viaja |
| `RetentionPolicy` | **LOCAL** | ver §5 e §6 |
| `ComplianceFinding` | **TRANSIENT** | diagnóstico datado contra policy versionada |
| `ValidatedExperience` | **decisão aberta** — ver §7 | é evidência sobre o patrimônio |
| vista admissível (resultado) | **TRANSIENT** | é `Memory(Context)`, calculada por definição |

---

## 4. Questão aberta — `MemoryDomain` viaja? (Q12 parcial)

A E4.0 **não decide**. Registra a análise para a E4.1.

**A favor de PORTABLE:** um domínio ("livro X", "projeto Y") descreve
um recorte do próprio patrimônio. Exportar objetos sem os domínios que
os organizam entrega um saco de objetos, e reconstruir a organização
manualmente é trabalho perdido e propenso a divergência.

**A favor de LOCAL:** domínios são também a forma como *esta*
instalação organiza o trabalho. Importar domínios alheios pode
colidir com a organização do destino, e um domínio importado pode
carregar semântica implícita de acesso.

**Direção provável:** PORTABLE, mas **em envelope próprio da E4**, não
como oitava seção do pacote da E3 — de modo que importar patrimônio
sem importar organização continue sendo uma operação válida, e a
escolha permaneça de quem importa.

O critério decisivo, quando a E4.1 decidir: se `MemoryDomain` carregar
qualquer semântica de *acesso*, ele deixa de ser recorte e vira policy
— e aí a resposta é LOCAL, sem discussão.

---

## 5. Policies não viajam (Q12)

**Congelado na E4.0:**

```
GOVERNANCE_POLICY_PORTABLE    = FALSE
ACCESSIBILITY_POLICY_PORTABLE = FALSE
```

Três razões, e as três são independentes:

1. **Autoridade não é transferível.** Uma policy expressa decisões de
   uma organização. Aplicá-la em outra instalação é impor governança
   que ninguém ali escolheu.
2. **Contexto de execução difere.** Atores, papéis e escopos não são
   os mesmos entre instalações; uma regra sobre "o ator X" não tem
   significado estável do outro lado.
3. **Risco de silêncio.** Uma policy importada que restrinja acesso
   produziria objetos invisíveis no destino sem que ninguém ali tenha
   decidido isso — indistinguível, para o operador do destino, de
   objetos que não chegaram.

A terceira é a decisiva, e é a mesma preocupação de
`INACCESSIBLE != NONEXISTENT` vista do lado do transporte.

**Consequência obrigatória:** importar patrimônio **nunca** importa a
governança que o acompanhava na origem. O destino aplica sua própria
governança ao patrimônio recebido. Isso é deliberado, e não é lacuna —
é o que impede que sincronização vire canal de imposição de política.

---

## 6. Retention policy é local ou portable? (Q13)

**LOCAL** — pela mesma razão das demais policies, e com um agravante:
obrigações de retenção e exclusão são **jurisdicionais**. Uma regra
válida em uma jurisdição pode ser ilegal em outra. Transportar
automaticamente política de retenção é transportar exposição
regulatória.

**Consequência que precisa ser dita:** o destino de um import é
responsável por aplicar **suas próprias** obrigações de retenção ao
patrimônio recebido. O pacote não carrega e não pode carregar essa
responsabilidade.

---

## 7. Questão aberta — `ValidatedExperience` viaja? (E4.11)

**A favor de PORTABLE:** é evidência sobre o patrimônio — o registro
de que algo foi validado, por quem, contra qual critério. Isso é
estruturalmente próximo de `ProvenanceRecord`, que viaja.

**A favor de LOCAL:** validação foi feita sob critérios locais, por
atores locais. Importada, poderia ser lida como validação *desta*
instalação, o que seria falso.

**Direção provável:** PORTABLE **com atribuição de origem
preservada** — como a proveniência já faz. O registro viaja dizendo
quem validou e sob qual critério, e o destino sabe que a validação é
de outro. Perder a atribuição na travessia transformaria evidência
alheia em evidência própria, o que é exatamente o tipo de colapso que
`COUT-P3` proíbe.

**Não congelado.** Decidido em E4.11.

---

## 8. O que a E4.0 congela sobre Sync

```
E3_SYNC_MODIFIED_IN_E4_0        = NO
NEW_SYNC_SECTIONS_IN_E4_0       = NONE
POLICY_PORTABLE                 = FALSE  (governance, accessibility, retention)
CONTEXT_INSTANCE_PORTABLE       = FALSE  (transiente por definição)
COMPLIANCE_FINDING_PORTABLE     = FALSE  (transiente por definição)
MEMORY_DOMAIN_PORTABILITY       = OPEN   → E4.1
VALIDATED_EXPERIENCE_PORTABILITY= OPEN   → E4.11
```

E a garantia que atravessa tudo: qualquer estado novo que venha a
viajar deverá preservar as mesmas propriedades que a E3 provou —
`canonical(destino) == canonical(origem)`, conflito explícito sem
vencedor, zero escritas em conflito, e rejeição de pacote inválido
antes de qualquer escrita.
