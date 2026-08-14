# E4_GOVERNANCE_BOUNDARIES — o que governança pode e não pode

**Módulo:** E4.0 — Architecture & Contract Freeze
**Natureza:** documento normativo. Nenhuma implementação.

---

## 1. O princípio operacional da E4

```
GOVERNANCE MAY RESTRICT ACCESS.
GOVERNANCE MUST NOT REWRITE EXISTENCE.
```

Esta é a única adição da E4 ao conjunto de princípios COUT. Os dez
princípios congelados na E3 (`COUT-P1` a `COUT-P10`) são herdados
integralmente e **a E4 não pode reinterpretá-los**.

O princípio novo é operacional, não uma reinterpretação: ele diz onde
governança age. Age na coluna "acessibilidade/relevância" da Matriz A.
Nunca na coluna "existência/persistência".

Uma policy pode legitimamente afirmar:

```
actor X cannot access object Y in context C
```

E dessa afirmação **nunca** se infere:

```
object Y does not exist
```

Esse salto inferencial é o modo de falha central que este documento
existe para proibir. Ele é sedutor porque é conveniente: é mais simples
retornar "não encontrado" do que retornar "existe, mas você não pode
ver". A conveniência custa a integridade epistêmica do sistema inteiro,
porque uma vez que "não posso ver" e "não existe" produzem a mesma
resposta, nenhuma inferência a jusante consegue separá-las de novo.

---

## 2. O que governança não é

```
GOVERNANCE != TRUTH ENGINE
GOVERNANCE != LEARNING ENGINE
GOVERNANCE != REPAIR ENGINE
GOVERNANCE != COUT DECISION ENGINE
```

- **Não é motor de verdade.** Uma policy diz o que é *permitido*, não
  o que é *verdadeiro*. Negar acesso a um objeto não o torna falso, e
  conceder acesso não o torna verdadeiro.
- **Não é motor de aprendizado.** Policies não se ajustam sozinhas por
  observar padrões de uso.
- **Não é motor de reparo.** Encontrar um estado que viola policy
  produz diagnóstico, nunca correção automática. A E3 já congelou
  `REPAIR_IMPLEMENTED = NO` para Integrity; a E4 estende a mesma
  disciplina para Compliance.
- **Não é motor decisório COUT.** `COUT-P9` (COUT informa, não decide)
  vale para governança tanto quanto para o resto. Governança decide
  *acesso*; não decide o que é cognitivamente verdadeiro, relevante ou
  equivalente.

---

## 3. Matriz D — INTEGRITY vs GOVERNANCE vs COMPLIANCE vs LEARNING vs REPAIR

| | Integrity | Governance | Compliance | Learning | Repair |
|---|---|---|---|---|---|
| **Compara o quê** | estado × invariantes estruturais | ação × permissão | estado/ação × policy | experiência validada × seleção | — |
| **Produz** | findings | decisão de acesso | diagnóstico/evidência | nada nesta entrega | nada — proibido |
| **Altera patrimônio?** | não | **não** | **não** | não | seria sim — por isso proibido |
| **Altera vista?** | não | **sim** | não | não | — |
| **Decide?** | não | sim, sobre acesso | não | não | — |
| **Módulo** | E3.10 (congelado) | **E4.3** | E4.10 | E4.11 (só registro) | **nenhum** |
| **Status na E4** | herdado intacto | a definir | fronteira apenas | fronteira apenas | `FORBIDDEN` |

A distinção Integrity/Compliance é a que mais facilmente se perde:

```
INTEGRITY:  estado vs invariantes estruturais
COMPLIANCE: estado/ação vs policy
```

Um ciclo causal é falha de **integridade** — viola uma invariante
estrutural, e seria falha em qualquer instalação do PIA-OS. Um objeto
retido além do prazo é falha de **conformidade** — viola uma policy
específica, e uma instalação com outra policy não teria falha alguma.

```
COMPLIANCE != INTEGRITY
COMPLIANCE != REPAIR
COMPLIANCE != LEARNING
```

Compliance produz diagnóstico e evidência. Não altera patrimônio nem
Kernel automaticamente.

---

## 4. Fronteira de aprendizado

Reafirmado da E3, sem alteração:

```
ERROR_IS_LEARNING     = FALSE
ERROR_IS_EVIDENCE     = TRUE
PIA_LEARNING_SOURCE   = VALIDATED_EXPERIENCE
```

Acrescentado pela E4.0, e igualmente obrigatório:

```
SUCCESS_IS_NOT_AUTOMATIC_LEARNING
REPETITION_IS_NOT_AUTOMATIC_LEARNING
```

A simetria importa. Já estava congelado que erro não é aprendizado —
mas a assimetria deixava aberta a leitura de que *sucesso* seria. Não
é. Nem repetição. Um resultado que funcionou uma vez é evidência de
que funcionou uma vez; cem repetições são evidência de cem
repetições. Nenhuma quantidade de sucesso se converte
automaticamente em conhecimento validado, porque validação é um ato
deliberado com critério explícito, não um limiar de contagem.

**A E4 não implementa learning engine.** A E4.11 prepara somente o
*registro* de experiência validada — uma estrutura de evidência, não
um mecanismo que muda comportamento.

### 4.1 O princípio evolutivo (registro para uso futuro)

```
variation → experience → evidence → validation → selection → possible persistence
```

Algumas variantes desaparecem. Algumas permanecem. Algumas demonstram
vantagem. Mas:

```
VARIATION                != KERNEL MUTATION
VALIDATED EXPERIENCE     != AUTOMATIC KERNEL CHANGE
AUTONOMOUS_KERNEL_MUTATION = FORBIDDEN
```

Note o "*possible* persistence" no fim da cadeia. Não é decorativo:
mesmo experiência validada e selecionada **pode** persistir, não
**deve**. O elo entre validação e persistência permanece deliberado e
externo, nunca automático.

Também herdado da E3, sem alteração:

```
VARIATION     != ERROR
NON_SELECTION != ERROR
SELECTION     != TRUTH
DISUSE        != HISTORICAL_ERASURE
```

---

## 5. Consolidação

```
CONSOLIDATION != DELETION
SUMMARY       != SOURCE REPLACEMENT
```

Se `M1, M2, M3 → S1`, então deve permanecer possível rastrear
`S1 ← {M1, M2, M3}`. Nenhuma síntese apaga silenciosamente suas
fontes.

**Diretriz de implementação (E4.5):** usar as primitivas E3 existentes
sempre que suficiente. Uma consolidação é, estruturalmente, uma
transformação com múltiplas entradas e uma saída — exatamente o que
`TransformationRecord` (`input_refs` / `output_refs`,
`declared_preservations` / `declared_losses`) e `LineageEdge` com
`relation_type=MERGE` já representam. A E3 provou esse caminho no
teste G1 da E3.12, que constrói `{O2, O3} → O4` com perda declarada.

**Não criar nova linhagem sem necessidade demonstrada.** Se a resposta
para "por que a linhagem da E3 não representa isto?" for insuficiente,
não se cria a entidade.

O ponto mais delicado da consolidação é `declared_losses`: uma síntese
que não declara o que perdeu está afirmando não ter perdido nada, o
que é quase sempre falso. A E4.5 deve tornar a declaração de perda
obrigatória na consolidação, não opcional.

---

## 6. Esquecimento e retenção

Conceitos a serem mantidos **distintos**, nunca colapsados:

| Conceito | Definição | Afeta existência? |
|---|---|---|
| **forgetting** | não recuperado em contexto; a distinção deixa de ser alcançada | não |
| **inaccessibility** | acesso inadmissível por estado ou policy | não |
| **causal extinction** | a distinção deixou de existir no presente; a história permanece | não |
| **deletion** | remoção física de registro | **sim** |
| **retention** | obrigação/decisão de manter por período | — |
| **legal erasure** | obrigação externa de remover | **sim** |

A E4.0 **não implementa política** de nenhum destes.

### 6.1 O ponto obrigatório

```
PRESERVATION = RETENTION FOREVER   ← FALSO
```

**COUT não autoriza retenção ilimitada contra política legítima ou
obrigação de exclusão.**

Este ponto é obrigatório e merece ser dito sem rodeio, porque todo o
resto do sistema empurra na direção oposta: a E3 inteira foi
construída para não perder nada, e é fácil deslizar de "não apagamos
por conveniência" para "não apagamos nunca". A segunda afirmação não
decorre da primeira e não é defensável.

Quando existe obrigação legítima de exclusão — legal, contratual ou do
titular — o PIA-OS deve poder cumpri-la. O que COUT exige não é
retenção eterna; é que a exclusão seja **explícita, registrada e
distinguível** de todas as outras coisas que se parecem com ela:
inacessibilidade, extinção causal, não-recuperação. Apagar por
obrigação é legítimo; apagar e fingir que nunca existiu não é.

### 6.2 A tensão real: legal erasure vs CausalHistory (Q14)

Esta é a questão arquitetural mais difícil da E4 e a E4.0 **não a
resolve** — registra a tensão honestamente e a defere para a E4.9.

A dificuldade: `CausalHistoryEvent` é imutável por contrato (`PIA-8020`)
e é o que sustenta `COUT-P4`. Uma obrigação de apagamento que atinja
conteúdo referenciado por eventos causais coloca dois compromissos
legítimos em rota de colisão.

Direções candidatas, **nenhuma congelada aqui**:

- **Apagar o referente, preservar a referência.** A E3 já armazena
  referências (`payload_ref`, `evidence_refs`, `source_ref`), nunca
  conteúdo. Se o conteúdo referenciado vive fora do domínio cognitivo,
  apagá-lo não quebra a cadeia causal — a referência passa a apontar
  para algo removido, o que é um estado *representável* e distinto de
  "nunca existiu". Esta é a direção mais promissora e é consequência
  direta de uma decisão que a E3 já tomou por outros motivos.
- **Tombstone explícito**, registrando que houve remoção obrigatória,
  sua autoridade e sua data — sem reconstituir o conteúdo.
- **Reconhecer o limite.** Pode haver casos em que a obrigação legal
  exija remover o próprio registro causal. Se ocorrer, isso deve ser
  uma exceção nomeada, autorizada e auditável — não um caminho normal
  de código, e nunca silenciosa.

A E4.9 deve escolher com o problema à vista, e não descobrir a tensão
durante a implementação.

---

## 7. Defense in depth (§10)

```
DB ACCESS CONTROL != COGNITIVE ACCESSIBILITY
```

Camadas onde políticas *poderão* ser impostas — decisão arquitetural
registrada, **implementação deferida**:

| Camada | Papel | Status |
|---|---|---|
| service/application | **política cognitiva explícita** — fonte da decisão | **E4.3** |
| repository | ponto de composição da vista admissível | E4.6 / E4.7 / E4.8 |
| database (RLS) | defesa em profundidade, nunca substituto | investigação apenas |

Se RLS for adotado no futuro: **a política de aplicação permanece
explícita**; a imposição no banco é defesa adicional. Nunca o inverso —
uma política que só existe como predicado de RLS é uma política que
não pode ser auditada, versionada nem explicada.

Antes de qualquer decisão sobre RLS, é obrigatório considerar:

- **owner e `BYPASSRLS`** — o dono da tabela ignora RLS por padrão em
  PostgreSQL, e a aplicação frequentemente conecta como dono; uma
  imposição que o caminho normal ignora não é imposição;
- **backup e restore** — `pg_dump` sob RLS pode produzir dumps
  parciais silenciosos, o que é um risco de perda mascarada;
- **integridade referencial** — checagens de FK atravessam RLS, o que
  pode vazar existência por mensagem de erro; e restrições que tornam
  linhas invisíveis podem tornar violações de FK indiagnosticáveis.

O terceiro item é especialmente relevante para este sistema: um
mecanismo que vaza existência por erro de FK contradiz exatamente
`INACCESSIBLE != NONEXISTENT` na direção oposta à esperada — revelando
o que deveria estar oculto.

---

## 8. Modelo de segurança — matriz de fronteiras (§23)

| Conceito | Pergunta que responde | Camada | Status na E4.0 |
|---|---|---|---|
| **cognitive accessibility** | isto é admissível neste contexto? | domínio cognitivo | definido, não implementado |
| **authorization** | este ator pode executar esta ação? | aplicação | fora do escopo E4.0 |
| **authentication** | este ator é quem diz ser? | infra | fora do escopo E4.0 |
| **confidentiality** | o dado está protegido em trânsito/repouso? | infra | fora do escopo E4.0 |
| **database permissions** | este papel SQL pode ler esta tabela? | banco | defesa em profundidade |

Os cinco são **distintos** e não se substituem. Em particular,
acessibilidade cognitiva não é autorização: um ator plenamente
autorizado pode legitimamente não ter certo objeto admissível em certo
contexto, e isso não é uma falha de permissão.

**E4.0 não implementa** auth, RLS, encryption nem secrets management.

---

## 9. Propriedade do patrimônio (§24)

```
USER/ORGANIZATION OWNS ITS COGNITIVE PATRIMONY
PIA MANAGES PERSISTENCE
```

O termo "owns" exige cuidado e **não é conclusão jurídica**. No
documento técnico usa-se:

- **logical/control ownership** — quem determina o destino do
  patrimônio: quais políticas se aplicam, o que é exportado, o que é
  retido, o que é removido. É isto que a arquitetura implementa e é o
  único sentido usado nos documentos da E4.
- **legal ownership** — titularidade de direitos sobre conteúdo,
  dados pessoais e obras. Depende de jurisdição, contrato e da
  natureza do conteúdo. **Não é decidido por arquitetura de software**
  e nenhum documento desta entrega afirma nada a respeito.

A separação não é formalidade. O sentido técnico é o que o sistema
pode garantir: que ninguém além do titular do controle determine o que
acontece com o patrimônio, e que nenhum fornecedor de modelo adquira
essa posição por participar da proveniência (`COUT-P10`). O sentido
jurídico é uma questão distinta, e tratá-los como um só produziria
tanto arquitetura ruim quanto direito ruim.
