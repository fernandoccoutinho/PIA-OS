# EDR E4.8 — Memory Isolation

**Natureza:** decisão de arquitetura para isolamento cognitivo entre
domínios no caminho de leitura.

---

## 1. O vazamento por composição

Duas semânticas corretas isoladamente produzem uma lacuna quando
combinadas:

1. `GovernanceRule.matches()` casa domínios por **interseção**;
2. `MemoryRetrievalManager` interpreta contexto multidomínio como
   **união** das memberships.

Reproduzido contra PostgreSQL real, com os managers reais, na cadeia 60:

```text
policy vigente admite READ somente em D1
contexto solicitado = {D1, D2}

resolução (D1,D2) → admissible, authorized=True, rule="so-d1"
vista     (D1,D2) → A (de D1)=True | B (de D2)=True
controle    (D1)  → A=True | B=False
```

```text
FULL-CONTEXT INTERSECTION MATCH != AUTHORITY OVER EVERY DOMAIN IN THE UNION
```

## 2. Por que `GovernanceRule.matches()` não foi alterado

A interseção é semântica **congelada** da E4.3, com auditoria própria, e
está correta no que se propõe: uma regra sobre `D1` de fato se aplica a
um contexto que inclui `D1`. O que ela não afirma — e nunca afirmou — é
autoridade sobre todos os outros domínios do mesmo contexto.

Mudá-la aqui alteraria o comportamento de todo consumidor da E4.3, para
resolver um problema que é de **composição**. A E4.8 fecha a lacuna no
ponto onde ela nasce, sem tocar em módulo congelado.

## 3. Por que a autorização é domínio a domínio

```text
EXPLICIT MULTI-DOMAIN ISOLATED SCOPE
= EVERY DECLARED DOMAIN INDIVIDUALLY AUTHORIZED
```

A E4.8 deriva um `MemoryContext` **singleton** por domínio declarado e
resolve `READ` para cada um, verificando com
`resolucao_vincula_contexto()` — a função compartilhada que a E4.3.4
criou — que cada resolução foi emitida para aquele singleton exato.

Não aceita "uma regra casou algum domínio" como autorização do conjunto.

Sem a E4.3.4 isso seria impossível de verificar: o preflight anterior
interrompeu com `GOVERNANCE_RESOLUTION_CONTEXT_BINDING_GAP` justamente
porque `resolução(D1) == resolução(D2)` sob policy curinga.

## 4. Por que o pedido é atômico

Se qualquer domínio declarado não é autorizado, o pedido inteiro não
executa.

```text
PARTIAL AUTHORITY != AUTHORITY TO REWRITE REQUESTED SCOPE
```

## 5. Por que o contexto não é estreitado em silêncio

Remover os domínios recusados e executar o resto responderia a uma
**pergunta diferente** da que o usuário fez, e devolveria um resultado
que parece completo sem ser. O usuário declarou o escopo; alterá-lo sem
dizer é a expansão-por-omissão que este módulo existe para impedir.

```text
USER-REQUESTED DOMAIN SCOPE = UPPER BOUND
NO SILENT SCOPE EXPANSION
PIA MAY SUGGEST; USER DECIDES
```

## 6. Por que objeto multi-domínio não é contaminado

Um item que pertence a `D1` autorizado **e** a `D2` não solicitado
continua admissível por `D1`. Membership adicional não é contaminação —
tratá-la assim tornaria patrimônio legítimo inalcançável por associações
que o usuário nem mencionou.

```text
Domain membership != existence
Domain membership != authorization
```

## 7. Por que contexto vazio válido não é boundary de isolamento

```text
EMPTY MEMORY CONTEXT IS VALID
ZERO-DOMAIN OBJECT IS VALID
EMPTY DOMAIN SCOPE IS NOT AN ISOLATION BOUNDARY
```

Contexto vazio continua válido na E4.2, e a E4.6 continua funcionando
com ele. O que a E4.8 recusa — com `PIA-8039`, antes de governança,
memberships e Retrieval — é tratar "sem domínio" como "todos os domínios
isolados". Isso **não** significa inexistência de patrimônio, e não
altera o comportamento geral da E4.6 nem torna objetos zero-domain
globalmente inalcançáveis.

## 8. Garantia e limite temporal do snapshot

A união das memberships dos domínios autorizados é capturada **uma vez**,
**depois** da autoridade, e a pós-condição exige que todo COID devolvido
pertença a ela.

A garantia é a do **instante observado**: nenhum lock de escrita é
adquirido e nenhum isolamento serializável é prometido. Uma membership
criada por outra transação entre o snapshot e a Retrieval produziria, no
pior caso, `PIA-8040` — uma recusa conservadora, nunca um vazamento.

```text
LEAK DETECTED != AUTHORIZATION TO SILENTLY FILTER
AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN
```

Vazamento detectado **não** é filtrado em silêncio, não vira página
parcial e não repara membership.

## 9. Por que não há RLS nesta etapa

Row-Level Security seria uma garantia do banco, aplicável a **todo**
acesso — inclusive fora do caminho da E4.8. Adotá-la exigiria política
de sessão, papéis de banco e migração, todos fora do escopo autorizado, e
mudaria o modelo de segurança do sistema inteiro.

A E4.8 entrega uma garantia de **camada de aplicação, escopo explícito,
caminho de leitura**. Dizer mais que isso seria overclaim.

## 10. Limite entre isolamento cognitivo, autenticação e confidencialidade

```text
ISOLATION GUARANTEE = APPLICATION-LEVEL, EXPLICIT-SCOPE, READ-PATH
RLS GUARANTEE = NONE
AUTHENTICATION GUARANTEE = NONE
CONFIDENTIALITY AT REST/IN TRANSIT = OUT OF SCOPE
GLOBAL GUARANTEE OUTSIDE THE E4.8 PATH = NONE
```

`actor_ref` é **descritor**, não credencial: presença de ator não implica
autenticação nem autorização. `session_id` não é fronteira de segurança e
não foi promovido a tenancy.

Chamadas diretas a repositórios ou à E4.6 **não** foram magicamente
impedidas. Quem chamar a E4.6 diretamente com contexto multidomínio
continuará obtendo a união — a E4.8 é o caminho isolado, não um guarda
global.

## 11. Compatibilidade futura com schedules independentes

O manager não tem estado mutável de instância e nada é compartilhado
entre chamadas:

```text
PARALLEL WORKLOADS MUST NOT SHARE MUTABLE ISOLATION STATE
CONCURRENT_WORK_ISOLATION = CALL_LOCAL_NO_SHARED_MUTABLE_STATE
```

Isso permite que, no futuro, trabalhos independentes mantenham escopos
cognitivos independentes. **Nada disso foi implementado aqui**: não há
`Workspace`, `Schedule`, `Workstream`, `Connector`, `RemoteResource`,
provider, papel de IA ou frontend. SOPHIA é marca de produto; o código
continua integralmente PIA-OS.

Compatibilidade significa não criar contratos que impeçam o isolamento
futuro entre trabalhos — não antecipar o produto.
