# EDR E4.9.7 — Target Resolution Ports and Descriptors

**Natureza:** primeira fatia de runtime da resolução de alvo. Materializa
contratos tipados, transitórios e **observacionais**. Não implementa efeito.
**Baseline:** cadeia 79 (`4ec4aa49`), `E4_9_6_3_AUDIT = PASS_FINAL`,
`E4_9_7 = AUTHORIZED_NOT_STARTED`.

```text
REFERENCE          != RESOLVED_TARGET
TARGET_RESOLUTION  != DELETION_AUTHORITY
DELETION_AUTHORITY != EFFECT
EFFECT             != ERASURE_RECORD
RESOLUTION_IS_OBSERVATIONAL = TRUE
```

```text
E4_9_7 = COMPLETE_CANDIDATE
TARGET_RESOLUTION_CONTRACTS = IMPLEMENTED
TARGET_RESOLVER_ADAPTER = NONE
ERASURE_EFFECT = NONE
E4_9_READY = FALSE
```

---

## 1. Conformidade documental — quatro camadas

O §3.1 do prompt exige as quatro tratadas **separadamente**, sem uma substituir
a outra. A omissão de qualquer uma é Stop Condition documental.

### 1.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas (Master v1.9 §0.4)

```text
├── USER_AUTHORITY_PRESERVED ................ SIM. Nada aqui decide, aprova
│     ou executa. `RESOLUTION != AUTHORITY` está no tipo: o descritor não
│     tem campo de aprovação nem de permissão de agir.
├── SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED .. SIM. Nenhum identificador de
│     marca no código; tudo é PIA-OS.
├── MODULE_SCOPE_AND_DEFERRED_CAPABILITIES ... Escopo: taxonomia reutilizada,
│     contratos tipados e uma porta observacional. Diferidos: adaptador,
│     `ErasureEffectPort`, envelope da E4.9.8, avaliador, lixeira, efeito.
├── SCHEDULE_MODE_DECLARED ................... NOT_APPLICABLE — não há
│     Schedule nesta fatia.
├── AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED NOT_APPLICABLE — sem multi-IA.
├── PROVIDER_CONNECTION_METHOD_DECLARED ...... NOT_APPLICABLE — nenhum
│     conector concreto; `CustodyNamespace` DECLARA provedor, não conecta.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA. Sem relógio, sem
│     scheduler, sem consumidor (`s10`, `s15`).
├── APPROVAL_GATES_DECLARED .................. NOT_APPLICABLE — nada executa,
│     logo não há portão a definir.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ NENHUMA. Zero ORM, zero
│     migração, zero repositório. Descritor é transitório por contrato.
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED ..... NOT_APPLICABLE.
├── DIVERGENCE_PRESERVATION_DECLARED ......... SIM. `validar_texto_opaco`
│     não normaliza; sequências Unicode distintas não são fundidas (`u12`).
├── CONCURRENT_WORK_ISOLATION_DECLARED ....... SIM. Workspace, tenant e
│     principal fazem parte da identidade do descritor; reúso entre
│     contextos vira recusa `CONTROL_SCOPE_MISMATCH` (`u35`).
├── BACKGROUND_EXECUTION_AUTHORIZATION ....... NOT_APPLICABLE — nada executa.
├── RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED .. NOT_APPLICABLE — sem chamada
│     externa, não há cota nem custo a expor.
├── REMOTE_RESOURCE_SCOPE_DECLARED ........... NENHUM acesso remoto. Provedor
│     e namespace são campos declarativos, não conexões.
├── OBSERVATION_PREPARATION_EXECUTION ........ Distinguidos: esta fatia é
│     OBSERVAÇÃO. Preparação e execução pertencem a fatias futuras.
├── CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED .. SIM. 29 nomes proibidos como
│     campo (`u25`); capacidade verificada é afirmação, não credencial.
├── FAILURE_ROLLBACK_AND_CONCURRENCY ......... Sem escrita, nada a reverter.
│     A recusa é valor, não exceção, então não há caminho de erro parcial.
├── CURRENT_CAPABILITY_NOT_OVERSTATED ........ Ver §9: o que NÃO existe está
│     enumerado, e `E4_9_READY = FALSE`.
└── FROZEN_MODULES_UNCHANGED ................. `app/cognitive` e
      `backend/alembic` byte a byte idênticos.
```

### 1.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas (Parte I §13)

Este é o bloco **omitido** nas E4.9.6.2 e E4.9.6.3, registrado pela auditoria
como `DUAL_COMPATIBILITY_BLOCK_OMISSION` não bloqueante e promovido a Stop
Condition explícita nesta fatia.

```text
├── USER_AUTHORITY_PRESERVED ................. SIM — ver §1.1.
├── SCHEDULE_MODE_DECLARED ................... NOT_APPLICABLE.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ NENHUMA.
├── PROVIDER_NEUTRALITY_PRESERVED ............ SIM. `CustodyNamespace` não
│     tem provedor padrão, lista fechada ou default; nenhum provedor é
│     fonte da verdade.
├── PERSONALIZATION_REVERSIBLE ............... NOT_APPLICABLE — sem workspace
│     visual, preferência ou perfil.
├── CONCURRENT_WORK_ISOLATION_DECLARED ....... SIM — `ControlScope`.
├── BACKGROUND_EXECUTION_AUTHORIZATION ....... NOT_APPLICABLE.
├── RESOURCE_LIMITS_AND_QUEUE_DECLARED ....... NOT_APPLICABLE.
├── AI_ROLE_CONTROL_DECLARED ................. NOT_APPLICABLE — sem funções
│     de IA nesta camada.
├── ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED .. NOT_APPLICABLE.
├── PIA_SEQUENCE_SUGGESTION_BEHAVIOR ......... NOT_APPLICABLE — nada sugere.
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED ..... NOT_APPLICABLE.
├── PIA_INTEGRATION_DIVERGENCE_PRESERVATION .. NOT_APPLICABLE — sem síntese.
├── POST_RESULT_USER_COMMAND_DECLARED ........ NOT_APPLICABLE — sem comando.
├── RESULT_APPROVAL_AND_PERSISTENCE ......... Distinguidos por ausência:
│     descritor não é aprovação nem persistência, e nenhum dos dois existe.
└── FROZEN_MODULES_UNCHANGED ................. SIM.
```

### 1.3 `MULTICHANNEL_COMMAND_COMPATIBILITY_v1_3` — 10 marcadores

```text
├── INPUT_CHANNELS_DECLARED ................. TEXT | VOICE, ambos FUTUROS.
│     Esta fatia é neutra ao canal e não implementa nenhum.
├── COMMAND_ENVELOPE_DECLARED ............... Os contratos são utilizáveis
│     pelo envelope tipado futuro, qualquer que seja o canal de origem.
│     O envelope em si é da E4.9.8 e NÃO foi criado.
├── CHANNEL_NORMALIZATION_DECLARED .......... NOT_APPLICABLE — sem canal.
├── IDENTITY_CONTEXT_AND_SCOPE_DECLARED ..... PARCIAL e declarado como tal:
│     `ControlScope` transporta workspace, tenant e principal, mas eles são
│     DECLARADOS PELA FRONTEIRA e não autenticados. É por isso que a classe
│     não se chama `AuthorizedContext` — ver §5.
├── VOICE_CONFIDENCE_AND_CORRECTION ......... NOT_APPLICABLE — sem voz.
├── CONFIRMATION_POLICY_DECLARED ............ NOT_APPLICABLE — nada executa,
│     logo não há o que confirmar.
├── DESTRUCTIVE_INTENT_BINDING_DECLARED ..... SIM, na parte que cabe aqui:
│     um descritor representa EXATAMENTE UM alvo. Não há campo de conjunto,
│     curinga ou padrão, então `target expansion` é impossível por forma
│     (`u38`), e não por verificação.
├── GOVERNANCE_PARITY_ACROSS_CHANNELS ....... SIM. Nenhum campo de origem
│     vira autoridade (`u39`): mudar `origin` não altera capacidade nem
│     escopo, seja qual for o canal que produziu a referência.
├── AUDIT_AND_RECEIPT_DECLARED .............. NOT_APPLICABLE — sem recibo.
│     E o localizador é proibido de aparecer no `ErasureRecord` futuro.
└── CURRENT_CAPABILITY_NOT_OVERSTATED ....... SIM — §9.
```

### 1.4 Parte II §12 — 8 obrigações, 11 Stop Conditions, 11 provas

**As oito obrigações do plano**, todas cumpridas: (1) a diretriz é citada;
(2) o implementado está na §4; (3) o diferido está na §9; (4) observação,
preparação, aprovação e execução são separadas — esta fatia é só a primeira;
(5) a autoridade competente é o usuário ou principal humano autorizado, e
nenhum contrato aqui a substitui; (6) sem escrita não há rollback, e a
concorrência é irrelevante para value objects imutáveis; (7) compatibilidade
com E3/E4 congeladas verificada por regressão delta zero; (8) nenhuma Stop
Condition disparou.

**As onze Stop Conditions mínimas — nenhuma disparou:**

```text
entidade persistente ou migração ......... NÃO (s02, s07)
ownership de Workspace/Schedule/conector . NÃO — ControlScope descreve, não possui
armazenamento de credenciais ............. NÃO (u25, 29 nomes proibidos)
execução externa irreversível ............ NÃO (s04)
ampliação silenciosa de autoridade ....... NÃO — nenhum campo concede poder
assinatura de provedor não suportada ..... NÃO — sem conector
sincronização destrutiva de arquivos ..... NÃO — sem I/O
perda de proveniência ou origem .......... NÃO — `origin` é campo obrigatório
colapso entre múltiplos Schedules ........ NOT_APPLICABLE
execução sem rollback declarado .......... NOT_APPLICABLE — nada executa
alteração de congelados por conveniência . NÃO — trees idênticas
```

**As onze provas mínimas:**

```text
nenhuma chamada externa quando recusado .. PROVADA (u34, s04)
nenhum acesso fora do escopo autorizado .. PROVADA (u35)
nenhuma escrita durante observação ....... PROVADA (u34 — dublê conta 0)
aprovação antes de ação crítica .......... NOT_APPLICABLE — sem ação
rollback sob falha injetada .............. NOT_APPLICABLE — sem escrita
proteção contra estado obsoleto .......... MODELADA, não executável:
                                           `resolved_at` + `version_etag` +
                                           recusa `STALE_RESOLUTION`
comportamento concorrente determinístico . NOT_APPLICABLE — value objects
                                           congelados, sem estado partilhado
preservação de origem, versão e histórico  PROVADA (u39, u40)
recibo fiel ao pedido e à execução ....... NOT_APPLICABLE — sem recibo
cancelamento sem estado parcial oculto ... NOT_APPLICABLE — sem operação
isolamento entre Schedules e Workspaces .. PROVADA (u35, u40)
```

---

## 2. Achado de preflight — a taxonomia já existia

O §4 do prompt manda materializar um vocabulário fechado com quatro classes de
custódia. **Elas já estão no repositório desde a E4.9.5**, em
`app/memory/models/erasure_enums.py::ErasureTargetClass`, com os quatro tokens
exatos da E4.9.1 e um `CHECK` de vocabulário no banco.

Reutilizei em vez de recriar. Um segundo enum com os mesmos membros criaria
duas fontes da verdade sobre classificação, e a divergência apareceria no dia
em que o recibo registrasse uma classe que o resolvedor não reconhece — a
mesma classe de defeito que a E4.9.6.3 fechou ao unificar o contrato de
`rules` em três fronteiras.

Divergência entre a letra do prompt e o código real, registrada e resolvida
pelo código, conforme a hierarquia de autoridade do projeto. `s08` cai se
alguém declarar um segundo enum com esses membros.

---

## 3. A decisão central — resultado discriminado por classes disjuntas

```text
TargetResolutionResult = ErasureTargetDescriptor | TargetResolutionRefusal
```

### 3.1 Alternativas rejeitadas

| # | Alternativa | Por que foi rejeitada |
|---|---|---|
| 1 | `None` para não resolução | O §5.3 proíbe, e com razão: `None` obriga o chamador a inventar o motivo, e um `if resultado is None` silencia seis recusas distintas numa só |
| 2 | Exceção para não resolução | Recusa é **resultado esperado** — hoje é o caso mais comum. Exceção obrigaria `try/except` no caminho normal e transformaria o previsto em excepcional |
| 3 | Um objeto com `success: bool` | Admite estado inconsistente por construção. A E4.7.2 já pagou por resultado que não era máquina de estados exaustiva |
| 4 | `dict` ou string livre | Sem narrowing estático; o consumidor precisaria de `cast`, vedado pelo §14.4 |
| **5** | **união de duas classes disjuntas** | **adotada** — não há quinto desfecho porque não há onde escrevê-lo |

`u27` prova a disjunção e `u28` prova o narrowing por `isinstance` sem `Any`,
`cast` ou ignore.

### 3.2 Uma porta, não duas

A E4.9.1 autorizou `ErasureTargetResolverPort` **e** `ErasureEffectPort`, e
exigiu que ficassem separadas. Materializei só a primeira.

A ausência é deliberada, não esquecimento. Declarar a fronteira de efeito ao
lado da de resolução convidaria a compor as duas no mesmo consumidor, e a
separação existe justamente porque resolver não pode ter efeito colateral: se
tivesse, uma consulta exploratória já seria uma ação destrutiva parcial, e
nenhuma aprovação posterior a desfaria.

`s09` prova a ausência varrendo todo `app/`, e a guarda `s08` da E4.9.5
continua fixando a mesma ausência do outro lado — duas guardas independentes.

---

## 4. Tabela campo → necessidade → risco → persistência

| Campo | Por que é necessário | Risco se mal usado | Persistência permitida |
|---|---|---|---|
| `target_class` | decide se há conteúdo apagável | promover metadado a alvo | **sim** — já persiste no `ErasureRecord` |
| `subject_coid` | distingue *removido* de *nunca existiu* | confundir com localizador | **sim** — identidade histórica, não capacidade |
| `control_scope.workspace_id` / `tenant_id` | vínculo contextual | cross-tenant | **sim** — identidade, não segredo |
| `control_scope.control_principal_ref` | a quem o alvo se vincula | tomar por autenticação | **sim** — descritivo, como `actor_ref` da E3 |
| `custody_namespace.provider` / `namespace` | onde o conteúdo vive | credential confusion | **sim** |
| `capability.operation` / `scope` | o que a conta realmente pode | capacidade presumida | **sim** — é afirmação, não credencial |
| `capability.verified` | separa observado de suposto | tratar `False` como sucesso | **sim** |
| `resolved_at` | detecta resolução obsoleta | executar sobre estado velho | **sim** |
| `version_etag` | idem, quando o provedor oferece | idem | **sim** |
| `origin` | rastreabilidade | virar autoridade | **sim** |
| **`transient_locator`** | **o adaptador futuro agir** | **efeito sobre alvo errado; vazamento** | **NUNCA** |

A última linha é a razão de existir da §6.2 do prompt. Todos os demais campos
poderiam, em princípio, aparecer num recibo. O localizador é o único que não
pode sobreviver ao efeito.

---

## 5. Por que `ControlScope` não se chama `AuthorizedContext`

O §5.1 do prompt é explícito: o nome não pode sugerir autorização que o runtime
não consegue provar. Não há autenticador, IdP, step-up ou aprovação em lugar
algum do repositório, e a E4.9.4 autorizou o **contrato** de autoridade
destrutiva, não o autenticador.

`ControlScope` diz o que é verdade: um escopo de controle **declarado pela
fronteira**. Chamá-lo de contexto autorizado seria a mesma classe de mentira
que a E4.9.6.1 cometeu ao afirmar uma garantia mais completa do que o código
entregava — e a terceira vez que eu cometesse essa forma de erro na mesma
sequência de fatias.

Pelo mesmo raciocínio, `VerifiedDeletionCapability.verified` é um campo, e não
uma pré-condição implícita: `verified=False` é construível e significativo,
porque significa "o resolvedor observou e **não** se confirmou". Sumir com esse
caso faria capacidade não verificada parecer capacidade ausente.

---

## 6. Modelo de ameaças — as seis da E4.9.1

| Ameaça | O que o contrato faz | O que ele **não** faz |
|---|---|---|
| **Confused deputy** | `capability.verified` obrigatório no descritor de sucesso; capacidade presumida vira recusa tipada | não verifica a capacidade — não há conector para verificar |
| **Cross-tenant** | workspace/tenant/principal na identidade do descritor; divergência vira `CONTROL_SCOPE_MISMATCH` | não impede que um adaptador futuro ignore o campo |
| **Locator leakage** | `repr=False` + `__repr__` próprio + ausência de serializer, logger, coluna e `to_dict` | não impede que um consumidor leia o atributo e o imprima |
| **Stale resolution** | `resolved_at` obrigatório e tz-aware, `version_etag` opcional, recusa `STALE_RESOLUTION` | não mede idade — sem executor não há janela real |
| **Credential confusion** | provedor e namespace explícitos, sem default | não valida a credencial, que não existe aqui |
| **Target expansion** | um descritor = um alvo, sem campo de conjunto ou curinga | não cobre expansão pós-aprovação, que é da E4.9.8 |

A coluna da direita é o ponto. As seis continuam **modeladas, não mitigadas**,
exatamente como a E4.9.1 declarou — e apresentar contrato como mitigação seria
alegar capacidade falsa.

---

## 7. Invariantes executáveis

```text
classe fora das duas de conteúdo         → ValueError            (u04)
capacidade não verificada                → ValueError            (u07)
`verified` não-bool                      → TypeError             (u08)
texto opaco vazio, branco ou tipo errado → TypeError/ValueError  (u09)
Cc/Cf/Zl/Zp em texto opaco               → ValueError            (u10)
Unicode visível preservado byte a byte   → devolvido idêntico    (u11, u12)
`resolved_at` ingênuo                    → ValueError            (u14)
UUID falso em qualquer identidade        → TypeError             (u15, u41-u44)
value object mutado                      → FrozenInstanceError   (u20)
motivo de recusa fora do enum            → TypeError             (u31)
```

Todos no construtor direto, não em factory — a lição repetida desde a E4.2.1 e
provada em `u19`.

---

## 8. Duas guardas da E4.9.5 envelheceram

Nenhuma por regressão. As duas fizeram exatamente o que deviam: acusaram a
chegada da fatia seguinte.

**`s01`** não conhecia `schemas/erasure_target.py`, que importa
`ErasureTargetClass`. Acrescentei-o aos permitidos com nota: conhecer o
vocabulário de classificação **não** é conhecer a primitiva de recibo, e
`test_erasure_target_isolation` prova que nada ali importa `ErasureRecord`,
repositório ou writer.

**`s08`** listava `ErasureTargetResolverPort` e `ErasureTargetDescriptor` como
ausentes. Saíram porque a E4.9.1 os autorizou e esta fatia os materializou.
**`ErasureEffectPort` permaneceu**, junto de `DestructiveApprovalEnvelope` e
`ApprovalRecord`.

É o mesmo movimento que a E4.9.6 fez com `gi435`: preservar o que a guarda
passa a proteger, em vez de removê-la.

### 8.1 Uma guarda minha nasceu frágil — pela sexta vez, e a correção foi outra

`s06` procurou `# type: ignore` no texto bruto e acusou a docstring que
**declara** não haver supressão. Mesma forma de `gv16` (E4.3.1), `s02`/`s11`
(E4.9.6), `s15` (E4.9.6.1) e `u76` (E4.9.6.3).

Mas a correção reflexa — comparar código executável por AST — **estaria
errada aqui**: `ast.unparse` descarta comentários, e uma supressão real ficaria
invisível. Uma guarda que não pode falhar não é uma guarda.

A correção certa separa as duas buscas: `tokenize` lê os comentários, onde
supressão vive; AST lê o código, onde `Any` e `cast` vivem. A lição que registro
não é "use AST", e sim: **a guarda tem de olhar onde a coisa proibida realmente
mora**.

---

## 9. O que esta fatia NÃO faz

```text
MIGRATION_DELTA = 0            DATABASE_SCHEMA_DELTA = 0
E3_DELTA = 0                   RETENTION_EVALUATOR_DELTA = 0
RETRIEVAL_DELTA = 0            API_DELTA = 0
AUTHENTICATION_DELTA = 0       APPROVAL_DELTA = 0
EFFECT_DELTA = 0               ERASURE_RECORD_WRITER_DELTA = 0
```

Não existe: adaptador de resolução, storage, conector, chamada externa, I/O,
deleção, lixeira, purge, autenticação, MFA, step-up, aprovação, envelope de
cinco estados, avaliador de policy, notificação, composição com Retrieval,
escritor de `ErasureRecord`, API, CLI, UI, parser de texto ou voz.

```text
CONTRACTS_CLOSED != MODULE_READY
E4_9_READY = FALSE
```

---

## 10. Gates medidos

Clone limpo, PostgreSQL recriado e **pré-migrado**:

```text
FULL_SUITE       2984 passed / 1 skipped / 0 failed   (cadeia 79: 2868/1/0)
RAW_SUITE        2517 passed / 468 skipped / 0 failed (cadeia 79: 2401/468/0)
GLOBAL_COVERAGE  99,25%   (era 99,24% — subiu)
  target_resolution_enums.py   100%
  schemas/erasure_target.py    100%
  ports/erasure_target.py      100%
RUFF PASS   BLACK PASS (387 arquivos)
MYPY app    7 históricos — registry.py 4, base_repository.py 2, handlers.py 1
            NEW = 0
supressões novas em produção e testes: 0   ·   `cast`: 0   ·   `Any`: 0
ALEMBIC single head c8a3f5017e94 — INALTERADO
git diff --check CLEAN
```

**Regressões, delta 0:**

```text
E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 · E4.4 = 74 · E4.5 = 187
E4.6 = 275 · E4.7 = 240 · E4.8 = 146 · E4.9.5 = 113 · E4.9.6 = 309
```

`E4.9.6 = 309` exatamente como o §12 exige. Fatia nova: **E4.9.7 = 116**
(100 unitários + 16 estáticos), rodados três vezes com resultado idêntico.

### 10.1 Cinco fronteiras descobertas pela exigência de 100%

Recusas de tipo em `workspace_id`, `tenant_id`, `subject_coid` da referência e
da recusa, `control_scope` e `classified_as` não eram tocadas por nenhum teste.
Não eram linhas mortas: cada uma é uma entrada inválida que alguém pode
escrever. Fechadas com `u41`–`u45`.

O corpo `...` do `Protocol` recebeu `# pragma: no cover`, que já consta do
`exclude_lines` do `coverage.ini` — configuração **não** alterada, mesmo
procedimento da E4.5.

---

## 11. Arquivos

```text
NOVOS
  app/memory/models/target_resolution_enums.py     6 motivos de recusa
  app/memory/schemas/erasure_target.py             6 value objects congelados
  app/memory/ports/erasure_target.py               1 Protocol
  tests/unit/memory/test_erasure_target.py         100 casos
  tests/static/test_erasure_target_isolation.py    16 guardas
  docs/entregas/entrega-4/EDR_E4_9_7_...md
ALTERADOS
  app/memory/models/__init__.py                    reexport
  app/memory/ports/__init__.py                     reexport
  tests/static/test_erasure_record_isolation.py    2 guardas envelhecidas
```

Nenhum código de erro novo. Nada em migration, schema, `BaseRepository`, E3,
Sync, Retrieval, policies antigas ou enums congelados.

---

## 12. Riscos que declaro

**(a) Contrato sem adaptador é socialmente frágil.** É o mesmo risco da E4.9.5
e da E4.9.6, e agora acumulado: existem uma tabela de recibo que ninguém
escreve, uma policy que ninguém avalia e uma porta que ninguém implementa. Cada
uma convida a "só ligar o adaptador", e as guardas por AST protegem apenas
enquanto ninguém as alterar.

**(b) O localizador é protegido na representação, não no acesso.** `repr` e
`str` o redigem, e não há serializer nem logger neste módulo. Um consumidor que
leia `descriptor.transient_locator` e o imprima vaza — e tem de ser assim,
porque o adaptador futuro precisa lê-lo. A proteção é contra vazamento
**acidental e idiomático**, não contra decisão deliberada de expor.

**(c) `verified=True` é uma afirmação de quem resolveu.** O contrato exige o
campo; não verifica o mundo. Um adaptador que sempre devolvesse `True`
satisfaria o `Protocol` e produziria descritores falsos. Esta é a razão de a
E4.9.1 exigir adaptador **autorizado**, e a autorização não é implementável
nesta fatia.

**(d) `ControlScope` é declarado, não autenticado.** Repetido aqui como risco,
e não só como nota de nomenclatura: se uma fatia futura tratar esses campos
como prova de identidade, o confused deputy volta pela porta da frente.

**(e) Seis motivos de recusa podem não bastar.** O vocabulário é fechado e sem
membro genérico, de propósito. Se um adaptador real encontrar um caso que não
cabe em nenhum, a resposta correta é EDR e membro novo — não um `OTHER`, que
seria o *best effort* proibido com outro nome.

---

## 13. Estado

```text
PATCH_CHAIN = 80
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_7_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_9_7_STATUS         = AWAITING_INDEPENDENT_AUDIT
TARGET_RESOLUTION_CONTRACTS = IMPLEMENTED
TARGET_RESOLVER_ADAPTER = NONE
ERASURE_EFFECT = NONE
ERASURE_RECORD_WRITER = NOT_COMPOSED
E4_9_READY = FALSE
E4_9_8 = NOT_STARTED
```

`git am` do patch isolado sobre a cadeia 79 reproduz a TREE exata. O bundle
carrega `HEAD` e `refs/heads/audit/e3-final-validation`, sem refs residuais.

Não se declara `PASS_FINAL`, e a E4.9.8 não foi iniciada.
