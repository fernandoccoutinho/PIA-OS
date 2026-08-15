# EDR E4.3.3 — Explicit Accessibility Transition Authority

**Natureza:** decisão de ampliação do vocabulário fechado de governança.
**Exigido por:** o próprio contrato da E4.3 — ampliar `CognitiveOperation`
exige EDR.
**Complementa, sem reescrever:** `EDR_COUT_PIA_E4.md`,
`E4_3_GOVERNANCE_POLICY.md`, `E4_3_1_GOVERNANCE_SAFETY_RESOLUTION.md`.

---

## 1. A lacuna confirmada

O preflight canônico da E4.7 devolveu:

```text
STOP_CONDITION = GOVERNANCE_OPERATION_GAP
```

`CognitiveOperation` tinha sete membros — `READ`, `REFERENCE`, `DERIVE`,
`TRANSFORM`, `EXPOSE`, `SYNCHRONIZE`, `CONSOLIDATE` — e **nenhum**
representa mover o `AccessibilityState` de um `CognitiveObject`.

Sem uma operação explícita, a E4.7 não teria como responder à pergunta
que justifica sua existência: *quem pode mover o quê, sob qual
autoridade*.

---

## 2. A nova operação e seu token

```python
CognitiveOperation.ACCESSIBILITY_TRANSITION = "accessibility_transition"
```

Token persistido exato, minúsculo com sublinhado, como os sete
anteriores. O vocabulário permanece **fechado**.

---

## 3. `ACCESSIBILITY_TRANSITION != TRANSFORM`

`TRANSFORM` está documentado como "transformar, produzindo nova versão
ou derivação". Uma transição de acessibilidade altera um estado do
**mesmo** objeto e não produz:

```text
COID · CLID · derivação · revisão
TransformationRecord · LineageEdge
```

Não reescreve proveniência, não apaga história causal, não altera
existência.

```text
ACCESSIBILITY TRANSITION != COGNITIVE TRANSFORMATION
ACCESSIBILITY != EXISTENCE
INACCESSIBLE != NONEXISTENT
CAUSALLY_EXTINCT != HISTORICAL_ERASURE
```

Reusar `TRANSFORM` teria um efeito concreto: toda policy que hoje admite
transformação cognitiva — pensando em derivação e revisão — passaria a
admitir também mudança de acessibilidade, incluindo extinção causal.

```text
AUTHORIZATION TO TRANSFORM != AUTHORIZATION TO CHANGE ACCESSIBILITY
```

---

## 4. `EMPTY_OPERATIONS_SCOPE_V1`

O curinga histórico passa a ter alcance **positivo e congelado**:

```python
EMPTY_OPERATIONS_SCOPE_V1 = frozenset({
    READ, REFERENCE, DERIVE, TRANSFORM, EXPOSE, SYNCHRONIZE, CONSOLIDATE
})
```

```python
if self.operations:
    if operation not in self.operations:
        return False
elif operation not in EMPTY_OPERATIONS_SCOPE_V1:
    return False
```

Uma regra publicada com `operations=frozenset()` foi escrita quando o
vocabulário tinha **estas sete**. Ela continua alcançando todas elas — e
apenas elas.

```text
EMPTY OPERATIONS != ALL FUTURE OPERATIONS
FUTURE OPERATION DEFAULT = EXPLICIT OPT-IN REQUIRED
```

O conjunto é **enumerado literalmente**. `set(CognitiveOperation)`
reintroduziria o defeito: cresceria sozinho a cada operação nova.

O sufixo `V1` marca que este é o envelope de autoridade das policies
publicadas até a cadeia 53. Incluir uma operação futura aqui ampliaria
retroativamente o alcance de versões imutáveis — exige EDR próprio, não
é manutenção de rotina.

---

## 5. Por que blacklist foi rejeitada

Uma lista de "operações sensíveis" depende de alguém lembrar de
classificar cada operação futura. Esquecer uma devolveria a autorização
retroativa em silêncio — o default inseguro voltaria pela porta dos
fundos. O conjunto positivo torna o default seguro **automático**: o que
não está no escopo histórico exige opt-in, sem depender de memória
humana.

---

## 6. Policies antigas não ganham capacidades novas

```text
OLD AUTHORIZATION != CONSENT TO A NEW CAPABILITY
MISSING EXPLICIT OPT-IN != AUTHORIZATION
POLICY IMMUTABILITY INCLUDES PRESERVING ITS AUTHORITY ENVELOPE
```

Versões publicadas são imutáveis (`PIA-8028`), então o **texto** da
policy nunca mudou. O que este corretivo impede é que o **significado**
dela mudasse sozinho quando o enum crescesse — ampliação de autoridade
sem novo ato de publicação.

---

## 7. Nenhuma versão publicada é modificada

Nenhuma migração, reserialização, atualização ou remoção. Um payload
histórico `{"operations": []}` continua armazenado exatamente assim, e a
releitura o devolve idêntico.

Para autorizar ou negar a nova operação, o administrador **publica uma
versão nova**. É o caminho legítimo, e há teste de integração que o
demonstra: versão 1 com curinga não autoriza; versão 2 com opt-in
autoriza; a versão 1 permanece intacta.

---

## 8. Nenhuma transição é executada aqui

```text
PERMISSION != EXECUTION
AUTHORITY VOCABULARY != ACCESSIBILITY MANAGER
E4.3.3 != E4.7
```

Este corretivo cria **autoridade representável**. Nenhum
`AccessibilityManager`, nenhuma porta de transição, nenhuma escrita em
`CognitiveObject.accessibility`.

## 9. A E4.7 continua responsável pela aplicação

Aplicar a policy, verificar evidência causal para `CAUSALLY_EXTINCT` e
executar a transição pela porta sancionada da E3 permanecem sendo
responsabilidade da E4.7, que segue `NOT_STARTED`.

## 10. E4.8 não foi iniciada

Nenhum arquivo, teste ou linha de Memory Isolation neste patch.

## 11. SOPHIA

Marca futura de front-end, sem efeito no backend. Nenhum pacote,
namespace, classe, tabela ou rota renomeada. `PIA-OS` continua sendo o
nome do sistema e do código.

## 12. Ampliar de novo exige novo EDR

`CognitiveOperation` permanece fechado. Qualquer membro futuro nasce
**fora** de `EMPTY_OPERATIONS_SCOPE_V1` e precisa de opt-in explícito.
