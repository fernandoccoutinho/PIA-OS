# EDR — E3 Cognitive Packaging

**Tipo:** Engineering Decision Record
**Módulo:** E3.0 — Baseline Intake & Interface Freeze (correção E3.0.1)
**Status:** Aceito
**Referenciado por:** `EDR_COUT_PIA_E3.md`

## Contexto

A versão original de `E3_DEPENDENCY_MAP.md` (E3.0) propôs
`app.cognitive` como namespace da Biblioteca Cognitiva sem apresentar
essa escolha como decisão explícita — foi introduzida como se fosse
consequência automática da arquitetura de E1/E2. Este documento
corrige isso: registra a comparação formal entre as duas opções de
empacotamento e a decisão tomada, com justificativa.

## Opções avaliadas

### Opção H — Horizontal (segue o padrão de E1/E2 ao pé da letra)

```text
app/models/cognitive_object.py
app/models/cognitive_distinction.py
app/repositories/cognitive_object_repository.py
app/services/coid_manager.py
app/services/clid_manager.py
app/schemas/cognitive.py
```

Cada camada horizontal já existente (`app/models`, `app/repositories`,
`app/services`, `app/schemas`) ganha arquivos novos para o domínio
cognitivo, misturados aos arquivos de infraestrutura de E2 (hoje
`app/services/` já existe, vazio).

### Opção B — Bounded Context (`app.cognitive`)

```text
app/cognitive/
    models/
    repositories/
    services/
    schemas/
```

Um novo pacote de topo, paralelo a `app/database`, `app/api`, etc.,
contendo sua própria subdivisão em camadas internamente — mas isolado
dos arquivos de infraestrutura de E1/E2.

## Avaliação por critério

| Critério | Opção H (Horizontal) | Opção B (Bounded Context) |
|---|---|---|
| Consistência com o projeto existente | Segue literalmente o padrão atual (camadas horizontais únicas) | Introduz um padrão novo, mas usa as mesmas subcamadas *dentro* do bounded context — não é uma ruptura de convenção, é uma composição dela |
| Coesão | Baixa a médio prazo — 11 features (`LIB-01`–`LIB-11`) resultam em ~9 modelos, ~11 serviços, N repositórios, todos misturados a `base_repository.py`, `unit_of_work.py`, etc. em `app/repositories/` | Alta — todo o domínio cognitivo fica localizável em um único diretório |
| Isolamento do domínio cognitivo | Fraco — nada impede um import cruzado acidental entre um arquivo de infraestrutura e um de domínio na mesma pasta | Forte — a fronteira do pacote é a fronteira do domínio |
| Dependências | Idênticas nas duas opções (ver `E3_DEPENDENCY_MAP.md`) — `app.cognitive.*`/arquivos horizontais dependem de `app.{database,models,repositories,exceptions,core,logging,utils,config,schemas,api}` de E1/E2 | Idênticas |
| Risco de import circular | Nenhum risco adicional em nenhuma das duas opções — a direção de dependência (E3 → E1/E2, nunca o inverso) é a mesma independentemente do layout de pastas | Nenhum risco adicional |
| Manutenção futura | Piora conforme `LIB-01`–`LIB-11` crescem — `app/repositories/` passaria a conter simultaneamente `base_repository.py` (infraestrutura genérica) e `cognitive_object_repository.py`, `provenance_repository.py`, etc. (domínio), sem fronteira visível | Melhora — cada `LIB-XX` some dentro de `app/cognitive/{camada}/`, sem competir por espaço com infraestrutura genérica |
| Evolução E4–E7 | E4 (políticas de memória/ACL), E7 (Hypervisor) adicionam ainda mais arquivos ao mesmo domínio cognitivo — Opção H tornaria as camadas horizontais cada vez mais dominadas por arquivos de domínio, obscurecendo a infraestrutura genérica de E1/E2 que continua ali | Escala naturalmente — novos módulos de E4/E7 relacionados ao domínio cognitivo entram no mesmo bounded context; os que não forem (ex.: autenticação de E4) merecem seu próprio bounded context, mesmo raciocínio replicado |
| Testabilidade | Igual nas duas — `tests/unit/`, `tests/integration/` já espelham a estrutura de `app/` por camada; o mesmo espelhamento funciona apontando para `app/cognitive/` | Igual |
| Impacto sobre E1/E2 | Nenhum nas duas opções — nenhum arquivo de `app/core`, `app/database`, `app/logging`, `app/api`, `app/security`, `app/middleware` (ou equivalente) é movido ou alterado | Nenhum |

Nenhuma incompatibilidade concreta com o projeto existente foi
encontrada para a Opção B durante a inspeção de E3.0 — a base já
importa por identidade/interface (Protocols, `BaseRepository`
genérico), não por localização de arquivo, então introduzir um pacote
de topo novo não quebra nenhuma convenção estrutural em vigor.

## Decisão

**`E3_PACKAGING_DECISION = BOUNDED_CONTEXT_APP_COGNITIVE`**

Justificativa: a Biblioteca Cognitiva tende a crescer
substancialmente nas entregas futuras (11 features só em E3, mais
E4/E7 pela frente) — Opção H degradaria a legibilidade das camadas
horizontais de infraestrutura de E1/E2 conforme esse crescimento
acontece, enquanto Opção B mantém a fronteira do domínio visível
independentemente de quantos módulos `LIB-XX` forem adicionados. Não
houve incompatibilidade concreta identificada que justificasse manter
a Opção H apesar dessa desvantagem.

## O que esta decisão não autoriza

Confirmado explicitamente (não é ambíguo): adotar `app.cognitive` como
bounded context **não** significa reorganizar `app/core`,
`app/database`, `app/logging`, `app/api`, `app/security`,
`app/middleware` ou equivalentes. Nenhum componente existente de E1/E2
é movido. `app.cognitive` é criado do zero, ao lado da estrutura
horizontal existente, e a consome como qualquer outro consumidor
externo consumiria — por import de interface pública, nunca por
reorganização de onde essas interfaces moram.

Internamente, `app/cognitive/` replica a mesma separação de camadas já
em uso no projeto (`models/`, `repositories/`, `services/`,
`schemas/`) — não introduz um estilo arquitetural diferente, apenas
delimita onde essas camadas específicas do domínio cognitivo residem.
