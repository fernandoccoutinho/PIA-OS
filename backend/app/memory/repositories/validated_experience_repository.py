"""
`ValidatedExperienceRepository` — append e leitura auditável (`E4.11`).

```text
append · get · list_by_subject · list_by_criterion
update · delete · soft_delete · bulk_*   ->  RECUSAM
```

Segunda das três camadas append-only. A primeira é o value object
congelado; a terceira é a trigger PostgreSQL, que recusa também o SQL
que não passa por aqui.

## Idempotência é por identidade, não por semântica

```text
REPLAY_SAME_ID + SAME_CANONICAL_PAYLOAD      -> devolve o existente
REPLAY_SAME_ID + DIFFERENT_CANONICAL_PAYLOAD -> PIA-8050, zero overwrite
DIFFERENT_ID   + SAME_VALUES                 -> permitido
```

A terceira linha é decisão medida, não omissão: **repetição pode ser
evidência**. Duas validações do mesmo sujeito, contra o mesmo critério,
pelo mesmo validador, em instantes diferentes, são dois fatos — e uma
constraint semântica de unicidade apagaria a distinção que a repetição
constitui.

## O que este repositório não faz

```text
NO_AUTOMATIC_PROMOTION
NO_HOOK · NO_OBSERVER · NO_TRIGGER_ON_ERROR_OR_SUCCESS
```

Nada aqui observa erro, sucesso, repetição ou `ComplianceFinding` para
criar registro sozinho. Todo append tem um chamador explícito que
declarou o que está registrando.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.memory.errors.exceptions import (
    ValidatedExperienceConflictError,
    ValidatedExperienceImmutableError,
)
from app.memory.models.validated_experience import ValidatedExperience
from app.memory.models.validated_experience_enums import ExperienceSubjectKind
from app.memory.schemas.validated_experience import (
    CriterionReference,
    ValidatedExperienceAppend,
)

CAMPOS_CANONICOS: tuple[str, ...] = (
    "subject_kind",
    "subject_ref",
    "outcome_token",
    "observed_at",
    "primary_evidence_kind",
    "primary_evidence_ref",
    "validator_kind",
    "validator_ref",
    "criterion_key",
    "criterion_version",
    "criterion_origin",
    "evidence_refs",
    "validated_at",
    "origin_ref",
)
"""O conteúdo canônico comparado num replay.

Enumerado literalmente, e não derivado das colunas do mapper: uma coluna
nova entraria na comparação sem que ninguém decidisse, e `id`,
`created_at` e `updated_at` precisam ficar **fora** — são metadados da
linha, não do fato registrado, e compará-los faria todo replay parecer
conflito.
"""


CODIGO_VIOLACAO_DE_UNICIDADE = "23505"
"""`unique_violation` no catálogo SQLSTATE do PostgreSQL."""

RESTRICAO_DE_IDENTIDADE = "validated_experiences_pkey"
"""A chave primária — a única colisão que significa replay.

Qualquer outra violação de unicidade descreveria outro invariante, e
tratá-la como replay esconderia dado incoerente numa tabela append-only.
"""


def _e_colisao_de_identidade(erro: IntegrityError) -> bool:
    """A violação é exatamente a da chave primária esperada?

    ```text
    ANY_INTEGRITY_ERROR != IDENTITY_COLLISION
    ```

    Lê `sqlstate` e o nome da restrição do driver. Sem os dois, a
    resposta é **não**: na dúvida, o erro é real e sobe.
    """
    original = getattr(erro, "orig", None)
    if getattr(original, "sqlstate", None) != CODIGO_VIOLACAO_DE_UNICIDADE:
        return False
    diagnostico = getattr(original, "diag", None)
    return getattr(diagnostico, "constraint_name", None) == RESTRICAO_DE_IDENTIDADE


class ValidatedExperienceRepository:
    """Registro append-only de experiências validadas.

    Recebe a `Session` por injeção, como todo repositório do projeto.
    Não abre transação nem commita: quem controla a fronteira
    transacional é a `UnitOfWork` do chamador.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Append
    # ------------------------------------------------------------------

    def append(self, entrada: ValidatedExperienceAppend) -> ValidatedExperience:
        """Registra uma validação, ou devolve a existente se for replay.

        Duas rotas chegam ao mesmo lugar: a leitura prévia resolve o
        replay sequencial, e o `IntegrityError` resolve o replay
        **concorrente** — duas sessões que passaram juntas pela leitura e
        chegaram juntas ao INSERT. Sem a segunda rota, a corrida
        apareceria como erro de banco cru em vez de idempotência.
        """
        if not isinstance(entrada, ValidatedExperienceAppend):
            raise TypeError(
                f"append exige ValidatedExperienceAppend validado, recebido "
                f"{type(entrada).__name__} — dicionário livre admitiria campo "
                "não declarado"
            )

        existente = self.get(entrada.experience_id)
        if existente is not None:
            return self._reconciliar(existente, entrada)

        registro = self._materializar(entrada)
        try:
            # ```text
            # SAVEPOINT_SCOPE != TRANSACTION_SCOPE
            # ```
            #
            # CORRIGIDO NA AUDITORIA DA CADEIA 96 (achado A1). A versão
            # anterior chamava `Session.rollback()` no caminho da corrida,
            # o que desfazia a transação INTEIRA do chamador — inclusive
            # escritas anteriores e não relacionadas, medidas em zero pela
            # auditoria. O repositório declara que a `UnitOfWork` é dona
            # da transação, e desfazê-la aqui contradizia o próprio
            # contrato.
            #
            # O `begin_nested` abre um SAVEPOINT: a falha do INSERT
            # tentativo desfaz **apenas** ele, e a transação externa
            # continua exatamente como estava.
            with self._session.begin_nested():
                self._session.add(registro)
                self._session.flush()
        except IntegrityError as exc:
            if not _e_colisao_de_identidade(exc):
                # Violação de OUTRO invariante não é replay. Mascará-la
                # como idempotência esconderia um dado incoerente numa
                # tabela append-only, onde nada se corrige depois.
                raise
            concorrente = self.get(entrada.experience_id)
            if concorrente is None:
                # A linha vencedora existe no banco e este snapshot não a
                # enxerga — típico de `REPEATABLE READ`. Não há leitura
                # segura possível aqui, e inventar um desfecho seria pior:
                # o sinal é propagado para o chamador repetir a operação
                # numa transação nova.
                raise
            return self._reconciliar(concorrente, entrada)
        return registro

    def _materializar(self, entrada: ValidatedExperienceAppend) -> ValidatedExperience:
        """Monta a linha a partir do contrato já validado."""
        return ValidatedExperience(
            id=entrada.experience_id,
            subject_kind=entrada.subject_ref.kind,
            subject_ref=entrada.subject_ref.ref,
            outcome_token=entrada.outcome_observed.outcome_token,
            observed_at=entrada.outcome_observed.observed_at,
            primary_evidence_kind=entrada.outcome_observed.primary_evidence_ref.kind,
            primary_evidence_ref=entrada.outcome_observed.primary_evidence_ref.ref,
            validator_kind=entrada.validated_by.validator_kind,
            validator_ref=entrada.validated_by.validator_ref,
            criterion_key=entrada.criterion_ref.criterion_key,
            criterion_version=entrada.criterion_ref.criterion_version,
            criterion_origin=entrada.criterion_ref.criterion_origin,
            evidence_refs=entrada.evidence_refs,
            validated_at=entrada.validated_at,
            origin_ref=entrada.origin.origin_ref,
        )

    def _reconciliar(
        self, existente: ValidatedExperience, entrada: ValidatedExperienceAppend
    ) -> ValidatedExperience:
        """Replay idêntico devolve; divergente recusa com zero escrita."""
        # O candidato é **transitório**: existe só para comparar, nunca
        # entra na sessão e nunca é gravado. Um `session.add` aqui
        # transformaria a verificação de conflito numa escrita, que é
        # exatamente o oposto de `ZERO_OVERWRITE`.
        candidato = self._materializar(entrada)
        divergentes = tuple(
            campo
            for campo in CAMPOS_CANONICOS
            if getattr(existente, campo) != getattr(candidato, campo)
        )
        if divergentes:
            raise ValidatedExperienceConflictError(entrada.experience_id, divergentes)
        return existente

    # ------------------------------------------------------------------
    # Leitura auditável
    # ------------------------------------------------------------------

    def get(self, experience_id: uuid.UUID) -> ValidatedExperience | None:
        if not isinstance(experience_id, uuid.UUID):
            raise TypeError("experience_id deve ser UUID")
        return self._session.get(ValidatedExperience, experience_id)

    def list_by_subject(
        self,
        subject_kind: ExperienceSubjectKind,
        subject_ref: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ValidatedExperience]:
        """Todas as validações registradas sobre um sujeito.

        Ordem canônica `(validated_at, id)` — duas linhas com o mesmo
        instante precisam sair sempre na mesma sequência, senão a
        listagem não é reproduzível.
        """
        if not isinstance(subject_kind, ExperienceSubjectKind):
            raise TypeError("subject_kind deve ser um ExperienceSubjectKind")
        if not isinstance(subject_ref, uuid.UUID):
            raise TypeError("subject_ref deve ser UUID")
        return self._listar(
            ValidatedExperience.subject_kind == subject_kind,
            ValidatedExperience.subject_ref == subject_ref,
            limit=limit,
            offset=offset,
        )

    def list_by_criterion(
        self,
        criterion: CriterionReference,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ValidatedExperience]:
        """Todas as validações feitas contra **um** critério exato.

        ```text
        PARTIAL_REFERENCE_QUERY != EXACT_CRITERION_BINDING
        ```

        CORRIGIDO NA AUDITORIA DA CADEIA 96 (achado A4). A versão anterior
        filtrava só por chave e versão, e misturava critérios `PUBLISHED`
        com `DECLARED` de mesma chave e versão — dois critérios
        diferentes, apresentados como um.

        A assinatura passou a receber a `CriterionReference` **integral**,
        e não três argumentos soltos: o tipo já garante que as três
        dimensões viajam juntas, e nenhum chamador consegue omitir a
        origem por engano.
        """
        if not isinstance(criterion, CriterionReference):
            raise TypeError(
                f"criterion deve ser um CriterionReference, recebido "
                f"{type(criterion).__name__} — a identidade do critério é "
                "chave, versão E origem"
            )
        return self._listar(
            ValidatedExperience.criterion_key == criterion.criterion_key,
            ValidatedExperience.criterion_version == criterion.criterion_version,
            ValidatedExperience.criterion_origin == criterion.criterion_origin,
            limit=limit,
            offset=offset,
        )

    def _listar(self, *criterios: object, limit: int, offset: int) -> list[ValidatedExperience]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit deve ser int >= 1")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset deve ser int >= 0")
        comando = (
            select(ValidatedExperience)
            .where(*criterios)  # type: ignore[arg-type]
            .order_by(ValidatedExperience.validated_at, ValidatedExperience.id)
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.execute(comando).scalars().all())

    # ------------------------------------------------------------------
    # Mutação — recusada
    # ------------------------------------------------------------------

    def update(self, entity: ValidatedExperience) -> ValidatedExperience:
        """Recusa: alterar uma validação faria o passado responder por um
        critério que não era o dele."""
        raise ValidatedExperienceImmutableError("update")

    def delete(self, entity: ValidatedExperience) -> None:
        raise ValidatedExperienceImmutableError("delete")

    def soft_delete(self, entity: ValidatedExperience) -> None:
        """Recusa também o apagamento lógico.

        ```text
        SOFT_DELETE_IS_STILL_A_WRITE
        ```

        Marcar como removido mudaria o que uma leitura auditável devolve,
        e uma evidência que some sem deixar rastro não é append-only.
        """
        raise ValidatedExperienceImmutableError("soft_delete")

    def bulk_update(self, *args: object, **kwargs: object) -> None:
        raise ValidatedExperienceImmutableError("bulk_update")

    def bulk_delete(self, *args: object, **kwargs: object) -> None:
        raise ValidatedExperienceImmutableError("bulk_delete")
