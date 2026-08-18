"""
Vocabulário fechado da recusa de resolução de alvo (`E4.9.7`).

```text
RESOLUTION_IS_OBSERVATIONAL = TRUE
UNRESOLVED REFERENCE = TYPED REFUSAL, NEVER BEST EFFORT
```

Um único `StrEnum`, no padrão da E3 e da E4.3: ampliar exige EDR.

**Por que um arquivo próprio, e não um membro novo em
`erasure_enums.py`.** Aquele módulo é da E4.9.5, auditado `PASS_FINAL`, e
descreve o vocabulário do **recibo** — o que uma tentativa material
observou. Motivo de recusa descreve por que uma resolução **não
aconteceu**, e nenhuma tentativa material existiu. Misturar os dois faria
o recibo herdar estados que ele proíbe desde a E4.9.0.

```text
REFUSAL_REASON != ERASURE_OUTCOME
NO_RESOLUTION != FAILED_ATTEMPT
```

`ErasureTargetClass` **não** é reeditada aqui. Ela já existe em
`erasure_enums.py` desde a E4.9.5, com exatamente as quatro classes da
E4.9.1 e os mesmos tokens. Um segundo enum com os mesmos membros criaria
duas fontes da verdade sobre classificação, e a divergência apareceria no
dia em que o recibo registrasse uma classe que o resolvedor não
reconhece.
"""

from enum import StrEnum


class TargetResolutionRefusalReason(StrEnum):
    """Por que uma referência **não** produziu alvo resolvido.

    Cada membro é uma recusa que o §5.3 do prompt da E4.9.7 exige
    distinguível. Nenhum deles é um sucesso degradado, e não existe
    membro genérico: um `UNKNOWN` ou `OTHER` seria o `best effort` que a
    E4.9.1 proibiu, com outro nome.

    ```text
    NO_GENERIC_FALLBACK_MEMBER
    REFUSAL IS A RESULT, NOT AN ERROR PATH
    ```
    """

    UNRESOLVED_OPAQUE_REFERENCE = "unresolved_opaque_reference"
    """A referência existe e não foi resolvida por adaptador autorizado.

    O caso **mais comum** hoje, e por isso o mais perigoso de tratar como
    degenerado: `payload_ref`, `source_ref`, `evidence_refs`,
    `input_refs` e `output_refs` são strings opacas sem FK e sem
    capacidade. Uma string sintaticamente válida nunca é autoridade.
    """

    COGNITIVE_METADATA_IS_NOT_CONTENT = "cognitive_metadata_is_not_content"
    """O alvo é linha ou estrutura local da E3/E4, não conteúdo.

    ```text
    METADATA REMOVAL != CONTENT ERASURE
    ```

    Remover metadado tem semântica e autoridade próprias. Promovê-lo a
    alvo apagável seria exatamente a afirmação falsa que o §6.1 do
    `E4_GOVERNANCE_BOUNDARIES.md` proíbe.
    """

    CONTROL_SCOPE_MISMATCH = "control_scope_mismatch"
    """Workspace, tenant ou principal de controle divergem do declarado.

    Endereça o *cross-tenant* da tabela de ameaças da E4.9.1: o contrato
    obriga a recusa quando o contexto diverge, e nenhuma das cinco
    dimensões divergentes pode devolver descritor de sucesso.

    ```text
    CONTRACT_AND_FAKE_ISOLATION_PROOF = IMPLEMENTED
    EXTERNAL_RUNTIME_CROSS_TENANT_CLOSURE = DEFERRED
    ```

    Corrigido na E4.9.7.2: a cadeia 81 dizia "fecha o cross-tenant". Não
    fecha — não existe adaptador, e um resolvedor real que ignore
    `ControlScope` satisfaz o `Protocol` mesmo assim. Fechamento em
    runtime externo pertence ao adaptador autorizado.
    """

    DELETION_CAPABILITY_NOT_VERIFIED = "deletion_capability_not_verified"
    """A conta ou conector não comprovou poder excluir naquele escopo.

    Capacidade **presumida** é a forma mais silenciosa do *confused
    deputy*: o PIA-OS usaria a própria credencial para agir sobre algo
    de outro titular por não ter verificado o que ela realmente permite.
    """

    PROVIDER_NAMESPACE_OUT_OF_SCOPE = "provider_namespace_out_of_scope"
    """Provedor ou namespace fora do escopo autorizado.

    Fecha a *credential confusion*: credencial de um provedor não vale
    no namespace de outro, ainda que a referência pareça compatível.
    """

    STALE_RESOLUTION = "stale_resolution"
    """A resolução envelheceu ou a versão/etag observada é incompatível.

    Modelado, não mitigado em runtime: não há executor, então não há
    janela real entre resolução e efeito. O contrato existe para que a
    recusa seja obrigatória quando houver.
    """


class RefusalDimension(StrEnum):
    """Qual dimensão do contexto divergiu, quando a recusa observou uma.

    ```text
    SAFE_DIAGNOSTIC != FREE_TEXT
    ```

    Acrescentado pela `E4.9.7.1`. A cadeia 80 tinha um campo
    `diagnostic: str | None` validado apenas como texto opaco — e a
    auditoria mediu o resultado: ele **aceitava o próprio localizador**, e
    a representação padrão da dataclass o revelava.

    Redigir a representação não teria resolvido, porque o valor proibido
    já estaria dentro do objeto. A correção é estrutural: o contexto
    seguro passa a ser um vocabulário **fechado** que nomeia a dimensão
    observada, e por construção não tem onde transportar localizador,
    segredo ou conteúdo.

    ```text
    REDACTED_REPR != SECRET_FREE_OBJECT
    ```

    Não existe membro genérico. Uma dimensão nova exige EDR, como em todo
    vocabulário fechado deste projeto.
    """

    WORKSPACE = "workspace"
    TENANT = "tenant"
    CONTROL_PRINCIPAL = "control_principal"
    PROVIDER = "provider"
    NAMESPACE = "namespace"
    REFERENCE = "reference"
    CAPABILITY = "capability"
    RESOLUTION_FRESHNESS = "resolution_freshness"


class ReferenceOrigin(StrEnum):
    """De qual campo da E3 veio a referência que motivou a resolução.

    ```text
    ORIGIN = CLOSED_TYPED_PROVENANCE
    INTENDED_FIELD_NAME != ENFORCED_FIELD_NAME
    ```

    Acrescentado pela `E4.9.7.2`. Até a cadeia 81, `origin` era `str` livre
    nos três value objects, e a auditoria mediu a consequência: o próprio
    localizador e uma URL assinada entravam pelo campo e a representação
    da recusa os revelava. O nome do campo dizia "origem"; o tipo aceitava
    qualquer coisa.

    Os cinco membros são os campos de referência **reais** da E3,
    conferidos no repositório antes de congelar este vocabulário e não
    presumidos da documentação:

    ```text
    causal_history_events.payload_ref       String(512), nullable
    provenance_records.source_ref           String(512), nullable
    provenance_records.evidence_refs        JSON list
    transformation_records.input_refs       JSON list
    transformation_records.output_refs      JSON list
    ```

    A E3 **não é tocada** por este enum. Ele nomeia uma fonte que já
    existe; não a redefine, não a lê e não cria coluna.

    Não existe membro genérico. Uma origem nova exige EDR — e, antes
    disso, um campo novo na E3, que é congelada.
    """

    PAYLOAD_REF = "payload_ref"
    SOURCE_REF = "source_ref"
    EVIDENCE_REFS = "evidence_refs"
    INPUT_REFS = "input_refs"
    OUTPUT_REFS = "output_refs"


ORIGENS_PLURAIS = frozenset(
    {
        ReferenceOrigin.EVIDENCE_REFS,
        ReferenceOrigin.INPUT_REFS,
        ReferenceOrigin.OUTPUT_REFS,
    }
)
"""As três origens que são listas JSON, e só elas admitem posição.

`payload_ref` e `source_ref` são colunas escalares: uma posição ali não
significaria nada, e aceitá-la deixaria o contrato dizer algo que a E3
não sustenta.
"""
