"""
`ContinuityEvidenceRepository` — leitura das fontes de continuidade (E4.4).

**Estritamente read-only.** Nenhum caminho deste módulo emite
`INSERT`, `UPDATE`, `DELETE` ou `TRUNCATE`.

## A fronteira de import, do lado da leitura

O gate `G17` da E3.12 proíbe qualquer import de `app.cognitive` em
módulos sob `backend/app/` fora do próprio pacote. A E4.1 resolveu
isso do lado da **escrita**, declarando a FK por nome de tabela; aqui
está o análogo do lado da **leitura**: descritores leves
(`sqlalchemy.table()`/`column()`) que referenciam as tabelas da E3
**por nome**, sem importar um único símbolo.

Custo assumido e declarado: este módulo conhece nomes de tabela e de
coluna da E3. É acoplamento por **nome**, não por tipo — o mesmo que a
E4.1 aceitou, e o que mantém a fronteira E3/E4 estrutural em vez de
documental. Importar os modelos quebraria `G17` e produziria
`E3_REGRESSION_DELTA != 0`.

A E3 continua sendo a única fonte da verdade sobre estes fatos. Nada
aqui os copia, deriva ou reinterpreta.
"""

import uuid
from typing import Any

from sqlalchemy import column, select, table
from sqlalchemy.orm import Session

_cognitive_objects = table(
    "cognitive_objects",
    column("id"),
    column("clid"),
    column("revision_status"),
    column("deleted_at"),
)
_lineage_edges = table(
    "lineage_edges",
    column("id"),
    column("parent_coid"),
    column("child_coid"),
    column("relation_type"),
)
_transformation_records = table(
    "transformation_records",
    column("id"),
    column("input_refs"),
    column("output_refs"),
)
_causal_histories = table("causal_histories", column("id"), column("subject_coid"))
_causal_history_events = table(
    "causal_history_events",
    column("id"),
    column("history_id"),
    column("event_type"),
    column("created_at"),
)


class ContinuityEvidenceRepository:
    """Consultas de leitura sobre as quatro fontes canônicas.

    Não estende `BaseRepository`: não existe modelo E4 por trás — o
    patrimônio é da E3, e este repositório apenas o lê. Vive em
    `repositories/` porque é ali que o projeto autoriza acesso direto
    ao SQLAlchemy (M2.3).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def subject_snapshot(self, coid: uuid.UUID) -> tuple[uuid.UUID | None, str | None, bool] | None:
        """`(clid, revision_status, soft_deleted)`, ou `None` se não há linha.

        **Corretivo E4.4.1.** A versão anterior filtrava
        `deleted_at IS NULL` e devolvia `None` para objetos com exclusão
        lógica, transformando-os em `SUBJECT_NOT_FOUND`:

        ```
        SOFT_DELETED != NEVER EXISTED
        SOFT_DELETED != SUBJECT_NOT_FOUND
        SOFT_DELETED != HISTORICAL ERASURE
        ```

        Eu havia justificado o filtro como "política de leitura da
        E3.1.1", e a justificativa estava errada: a E3.1.1 filtra por
        padrão nas **listagens** e oferece `include_deleted=True`
        precisamente para **consumidores de auditoria**. Um avaliador
        de continuidade histórica é esse consumidor — soft delete
        existe na E3 justamente para não destruir identidade nem
        história, e o COID permanece ocupado para sempre.

        `SUBJECT_NOT_FOUND` passa a significar o que o nome diz:
        nenhuma linha com aquele COID.
        """
        stmt = select(
            _cognitive_objects.c.clid,
            _cognitive_objects.c.revision_status,
            _cognitive_objects.c.deleted_at,
        ).where(_cognitive_objects.c.id == coid)
        linha = self._session.execute(stmt).first()
        if linha is None:
            return None
        return (linha[0], linha[1], linha[2] is not None)

    def lineage_as_child(self, coid: uuid.UUID) -> list[tuple[Any, Any, Any]]:
        """Arestas em que o sujeito é filho — `(id, parent_coid, relation_type)`."""
        stmt = (
            select(
                _lineage_edges.c.id,
                _lineage_edges.c.parent_coid,
                _lineage_edges.c.relation_type,
            )
            .where(_lineage_edges.c.child_coid == coid)
            .order_by(_lineage_edges.c.id)
        )
        return [tuple(linha) for linha in self._session.execute(stmt)]

    def lineage_as_parent(self, coid: uuid.UUID) -> list[tuple[Any, Any, Any]]:
        """Arestas em que o sujeito é pai — `(id, child_coid, relation_type)`."""
        stmt = (
            select(
                _lineage_edges.c.id,
                _lineage_edges.c.child_coid,
                _lineage_edges.c.relation_type,
            )
            .where(_lineage_edges.c.parent_coid == coid)
            .order_by(_lineage_edges.c.id)
        )
        return [tuple(linha) for linha in self._session.execute(stmt)]

    def transformations_citing(self, coid: uuid.UUID) -> tuple[list[Any], list[Any]]:
        """Transformações que citam o COID como entrada e como saída.

        **Varredura `O(n)`, e ela fica.** `input_refs`/`output_refs` são
        colunas `JSON` sem FK e sem índice, porque a integridade
        referencial desses campos está `DEFERRED` desde a E3 e
        reafirmada em `E4_DEFERRED_INVENTORY.md`.

        Criar índice, tabela auxiliar ou coluna derivada para acelerar
        seria criar entidade persistente nova e segunda fonte da
        verdade — as Stop Conditions 3 e 4 deste módulo. O custo é
        consequência de uma decisão congelada da E3, e o lugar de
        revisá-la é um corretivo da E3, não este módulo.

        A comparação é feita sobre o **texto** do COID porque é assim
        que a E3 os grava nesses campos.
        """
        alvo = str(coid)
        stmt = select(
            _transformation_records.c.id,
            _transformation_records.c.input_refs,
            _transformation_records.c.output_refs,
        ).order_by(_transformation_records.c.id)

        como_entrada: list[Any] = []
        como_saida: list[Any] = []
        for registro_id, entradas, saidas in self._session.execute(stmt):
            if alvo in (entradas or []):
                como_entrada.append(registro_id)
            if alvo in (saidas or []):
                como_saida.append(registro_id)
        return como_entrada, como_saida

    def causal_events(self, coid: uuid.UUID) -> list[tuple[Any, Any]]:
        """Eventos da história causal do sujeito — `(id, event_type)`.

        Ordenados por `created_at, id`, a ordem determinística canônica
        do projeto desde E3.1.2. Nenhum evento é inferido: se a história
        não existe, a lista é vazia — ler nunca cria.
        """
        stmt = (
            select(_causal_history_events.c.id, _causal_history_events.c.event_type)
            .select_from(
                _causal_history_events.join(
                    _causal_histories,
                    _causal_history_events.c.history_id == _causal_histories.c.id,
                )
            )
            .where(_causal_histories.c.subject_coid == coid)
            .order_by(_causal_history_events.c.created_at, _causal_history_events.c.id)
        )
        return [tuple(linha) for linha in self._session.execute(stmt)]
