# E3 — Implementation Sequence

Módulo E3.0. **Correção E3.0.1**: esta versão substitui a sequência
proposta originalmente em E3.0, que continha um módulo extra
("E3.1 — Fundamentos de domínio") não previsto na sequência oficial.
Nenhum destes módulos é implementado por E3.0 — esta é a ordem
canônica para autorização módulo a módulo.

## Sequência canônica (13 módulos)

```text
E3.0  — Baseline Intake & Interface Freeze        [CONCLUÍDO, em correção]
E3.1  — LIB-01  Cognitive Object + Object Repository
E3.2  — LIB-02  COID Manager
E3.3  — LIB-03  CLID Manager + Lineage
E3.4  — LIB-04  Version Manager + TransformationRecord
E3.5  — LIB-05  Relationship Engine
E3.6  — LIB-06  Metadata Manager + Provenance + Accessibility
E3.7  — LIB-07  Index Manager
E3.8  — LIB-08  Search Engine
E3.9  — LIB-09  Knowledge Provenance Engine + CausalHistory
E3.10 — LIB-10  Integrity Manager
E3.11 — LIB-11  Synchronization Manager
E3.12 — Integration & Gate E3 → E4
```

13 módulos no total: `E3.0` + 11 módulos funcionais (`LIB-01`–`LIB-11`)
+ `E3.12` (Integration & Gate). **Não existe** um módulo separado de
"fundamentos de domínio" — os modelos/schemas mínimos necessários
(`CognitiveObject`, estrutura mínima de `CognitiveDistinction` se o
contrato exigir) nascem dentro do próprio `E3.1 = LIB-01`.

## Ownership das primitivas por módulo

Registra a propriedade inicial de cada primitiva de
`E3_DOMAIN_MODEL_DRAFT.md` — cada primitiva é implementada uma única
vez, no módulo que a possui; módulos posteriores a consomem por
referência, nunca a reimplementam.

| Módulo | Feature | Primitivas de propriedade inicial |
|---|---|---|
| **E3.1** | `LIB-01` Cognitive Object + Object Repository | `CognitiveObject`; estrutura mínima de `CognitiveDistinction`, se necessária ao contrato de `CognitiveObject` |
| **E3.2** | `LIB-02` COID Manager | `COID` (geração, unicidade, imutabilidade) |
| **E3.3** | `LIB-03` CLID Manager + Lineage | `CLID`; `LineageEdge` |
| **E3.4** | `LIB-04` Version Manager + TransformationRecord | `Version`; `TransformationRecord` |
| **E3.5** | `LIB-05` Relationship Engine | Tipos de relacionamento; `CausalClassRef`, se necessário como referência relacional |
| **E3.6** | `LIB-06` Metadata Manager + Provenance + Accessibility | `Metadata`; `ProvenanceRecord`; `AccessibilityState` |
| **E3.7** | `LIB-07` Index Manager | — (consome `Metadata`/`CognitiveObject` já existentes; nenhuma primitiva nova) |
| **E3.8** | `LIB-08` Search Engine | — (consome o índice de E3.7; nenhuma primitiva nova) |
| **E3.9** | `LIB-09` Knowledge Provenance Engine + CausalHistory | `CausalHistory`; `CausalHistoryEvent` |
| **E3.10** | `LIB-10` Integrity Manager | — (valida consistência do que já existe; nenhuma primitiva nova) |
| **E3.11** | `LIB-11` Synchronization Manager | — (sincroniza o que já existe; nenhuma primitiva nova) |
| **E3.12** | Integration & Gate E3 → E4 | — (integração/consolidação; nenhuma primitiva nova) |

**`CausalComparison`** é intencionalmente **não atribuída** a nenhum
módulo nesta tabela. Seu contrato já está preparado em
`E3_DOMAIN_MODEL_DRAFT.md` (pode ser refinado antes da implementação),
mas a atribuição de qual módulo a implementa fica em aberto até que um
módulo concreto precise dela — provavelmente próximo a `E3.9`, dado
seu uso natural em conjunto com `CausalHistory`/`ProvenanceRecord`,
mas isso não é decidido aqui. Sua implementação, onde quer que caia,
deve permanecer desacoplada de qualquer ranking ou seleção automática
(ver `EDR_COUT_PIA_E3.md`) — isso não é negociável independentemente
do módulo escolhido. Não antecipar lógica pertencente a E4 (políticas
de acessibilidade/memória) ou E7 (Hypervisor/orquestração multi-IA).

## Racional da ordenação

1. **`LIB-01` antes de tudo** — nenhuma outra feature tem o que
   consumir sem `CognitiveObject` e seu repositório existirem.
2. **Identidade (`COID` → `CLID`+`Lineage`) antes de versão** —
   `Version Manager` (E3.4) precisa de `CLID` estável para agrupar
   versões da mesma linhagem conceitual.
3. **`TransformationRecord` entra em E3.4** — versionamento e
   transformação são operações correlatas (uma nova versão é, em
   geral, o resultado de uma transformação registrada).
4. **`Relationship Engine` (E3.5) antes de Metadata/Index/Search** —
   buscar e indexar fazem mais sentido sobre um grafo de relações já
   existente do que sobre objetos isolados.
5. **`Provenance`+`Accessibility` entram em E3.6, junto de Metadata** —
   correção desta versão: originalmente `ProvenanceRecord` estava
   planejado apenas para o módulo de Knowledge Provenance Engine
   (E3.9); a sequência canônica o atribui a E3.6, mais cedo, porque
   metadata e proveniência compartilham o mesmo momento natural de
   captura (na escrita/edição de um objeto).
6. **`CausalHistory`/`CausalHistoryEvent` ficam em E3.9** — só fazem
   sentido pleno depois que provenance (E3.6) e relacionamento (E3.5)
   já existem para alimentar os eventos históricos.
7. **Integridade e sincronização por último (E3.10–E3.11)** — são
   cross-cutting por natureza; não há o que validar/sincronizar antes
   das features de dados existirem.
8. **`E3.12` fecha a entrega** — Integration & Gate valida a entrega
   completa antes da transição para E4, análogo ao papel de
   `BASELINE_FREEZE.md` ao final de E2.

## Regra de avanço

Cada módulo `E3.n` só é autorizado a começar depois que `E3.(n-1)` for
declarado `PASS` — mesma disciplina usada em E2 (Módulo 2.1 → 2.13).
Nenhum módulo desta lista é implementado automaticamente em sequência;
cada um aguarda autorização explícita. `E3.0` ainda está em correção
neste documento — `E3.1` não está autorizado a começar enquanto
`E3.0` não for declarado `PASS` sem Stop Condition aberta.

## Stop Conditions que podem reordenar esta sequência

Se, ao longo da implementação, `E3.9` (Knowledge Provenance Engine)
revelar necessidade de campos em `ProvenanceRecord` (propriedade de
E3.6) que exijam migração destrutiva em `CognitiveObject` (propriedade
de E3.1), isso é uma Stop Condition (necessidade de migração
destrutiva) e deve suspender a sequência, não ser resolvida
silenciosamente ajustando um schema já implementado em módulo anterior.
