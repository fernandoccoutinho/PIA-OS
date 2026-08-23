"""
`HandoffAttribution` — quem alegou ter respondido (`E7.2`).

```text
ROLE != PROVIDER != MODEL != INSTANCE != PRINCIPAL != AUTHORITY
SELF_DECLARED != VERIFIED_IDENTITY
```

Uma linha por tentativa importada, criada na **mesma transação** do
resultado, inclusive quando ele é rejeitado. Atribuir só o que passou
deixaria a pergunta mais útil da auditoria sem resposta: *qual IA errou?*

Os três campos declarados são **alegações do cliente**, não identidade
verificada. A E7 não tem como provar que o texto veio do modelo que o
cliente diz — e fingir que tem seria pior que não registrar. Por isso
`self_declared` é `TRUE` obrigatório, e não um sinalizador que alguém
possa desligar para fazer a alegação parecer verificação.

Nenhum enum, catálogo de marcas, allowlist ou teto de provedores. Um
Schedule pode usar quantas IAs distintas seu cliente declarar: o papel
descreve o trabalho, não o fornecedor.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel
from app.orchestration.schemas.envelope import MAX_REF_LENGTH, MAX_ROLE_LENGTH


class HandoffAttribution(BaseModel):
    """Atribuição declarada de uma tentativa, imutável desde a criação."""

    __tablename__ = "handoff_attributions"

    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_handoff_attributions_attempt"),
        CheckConstraint("self_declared", name="ck_handoff_attributions_self_declared_true"),
        CheckConstraint("length(btrim(role)) > 0", name="ck_handoff_attributions_role_not_blank"),
        CheckConstraint(
            "length(btrim(declared_instance_id)) > 0",
            name="ck_handoff_attributions_instance_not_blank",
        ),
        Index("ix_handoff_attributions_provider", "declared_provider_id"),
    )
    """`CHECK (self_declared)` é uma constante imposta pelo banco.

    Uma coluna booleana que só admite `TRUE` parece redundante e não é: o
    dia em que existir atribuição **verificada**, ela virá com outro
    mecanismo e outra migration, e as linhas antigas continuarão dizendo
    corretamente que eram alegações. Sem a constraint, bastaria um UPDATE
    para reescrever o passado como verificado — e nem isso é possível,
    porque a tabela é append-only.
    """

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handoff_attempts.id", name="fk_handoff_attributions_attempt"), nullable=False
    )

    role: Mapped[str] = mapped_column(String(MAX_ROLE_LENGTH), nullable=False)
    """Papel da etapa, **derivado** — nunca aceito do cliente.

    Deixar o cliente declarar o papel permitiria que a atribuição
    contasse uma história diferente da composição do Schedule.
    """

    declared_provider_id: Mapped[str | None] = mapped_column(String(MAX_REF_LENGTH), nullable=True)
    declared_model_id: Mapped[str | None] = mapped_column(String(MAX_REF_LENGTH), nullable=True)
    declared_instance_id: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Strings opacas. Provider e model são opcionais; a instância não.

    Sem a instância não há a quem atribuir o retorno, e uma atribuição
    sem sujeito não é atribuição.
    """

    declared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """Instante em que a alegação foi recebida, pelo relógio do banco."""

    self_declared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    provenance_record_ref: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    """Referência **opaca** e opcional a proveniência — nunca escrita pela E7.

    ```text
    E7_REFERENCES_PROVENANCE = TRUE
    E7_WRITES_PROVENANCE = FALSE
    PROVENANCE_RECORD_WRITE = FORBIDDEN
    REFERENCE != FOREIGN_KEY
    ```

    **Sem chave estrangeira, e a causa é de camada.** Uma FK do ORM exige
    que `provenance_records` esteja no mesmo `MetaData` no momento do
    flush, o que obrigaria `app.orchestration` a importar
    `app.cognitive` — precisamente o que o escopo negativo da E7 proíbe, e
    o que a guarda estática `e71b02` reprova.

    ```text
    E7_NEVER: ciência (E5), memória (E4), cognição (E3)
    ```

    Uma restrição de integridade cujo preço é dissolver a fronteira da
    camada custa mais do que entrega: o precedente do programa para
    referência entre domínios é a referência opaca, exatamente como
    `Schedule.control_principal_ref` aponta para um principal técnico sem
    FK. Custo declarado: não há integridade referencial verificada pelo
    banco entre esta coluna e `provenance_records`.

    A coluna existe para que um consumidor futuro — com autoridade para
    produzir proveniência — possa ligar as duas coisas. A API da E7.2 não
    a aceita na entrada, não a preenche, e o repositório sequer a expõe
    como parâmetro.
    """
