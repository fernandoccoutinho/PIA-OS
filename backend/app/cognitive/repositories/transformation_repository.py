"""
TransformationRepository — repositório concreto de
`TransformationRecord` (`E3.4`/`LIB-04`).

Reutiliza `BaseRepository` sem reimplementar CRUD genérico. Único
comportamento adicionado: garantir que o histórico é append-only de
verdade — `update()`/`delete()` são sobrescritos e sempre rejeitam,
mesma disciplina aplicada a `LineageRepository` na correção E3.3.1
(débito C2) — não repetir aqui o mesmo erro de deixar "append-only"
apenas como documentação não aplicada.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cognitive.errors.exceptions import TransformationRecordImmutableError
from app.cognitive.models.transformation_record import TransformationRecord
from app.repositories.base_repository import BaseRepository


class TransformationRepository(BaseRepository[TransformationRecord]):
    """Repositório de `TransformationRecord`.

    **Append-only garantido pelo contrato público**: `update()`/
    `delete()` sempre levantam `TransformationRecordImmutableError`
    (`PIA-8010`) antes de tocar a sessão — nenhuma query é executada.
    Nenhum outro método público deste repositório muta ou remove um
    registro existente.
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, TransformationRecord)

    def list_by_input_coid(self, coid: object) -> list[TransformationRecord]:
        """Transformações que tiveram `coid` (como string) em
        `input_refs` — ordenadas deterministicamente por
        `created_at ASC, id ASC` (mesma convenção de E3.1.2/E3.3, não
        repete o débito lá corrigido).

        Nota de implementação: como `input_refs` é `JSON` (lista
        polimórfica, não uma coluna relacional), o filtro é feito em
        memória sobre os registros ordenados — aceitável no volume
        esperado desta fase; um índice dedicado é candidato natural
        para `LIB-07 Index Manager` (E3.7), não para este módulo.
        """
        stmt = select(TransformationRecord).order_by(
            TransformationRecord.created_at.asc(), TransformationRecord.id.asc()
        )
        coid_str = str(coid)
        return [
            record
            for record in self._session.execute(stmt).scalars().all()
            if coid_str in record.input_refs
        ]

    def list_by_output_coid(self, coid: object) -> list[TransformationRecord]:
        """Idem, para `output_refs`."""
        stmt = select(TransformationRecord).order_by(
            TransformationRecord.created_at.asc(), TransformationRecord.id.asc()
        )
        coid_str = str(coid)
        return [
            record
            for record in self._session.execute(stmt).scalars().all()
            if coid_str in record.output_refs
        ]

    def update(self, entity: TransformationRecord) -> TransformationRecord:
        """Sempre rejeita — ver docstring da classe."""
        raise TransformationRecordImmutableError(entity.id, operation="update")

    def delete(self, entity: TransformationRecord) -> None:
        """Sempre rejeita — ver docstring da classe."""
        raise TransformationRecordImmutableError(entity.id, operation="delete")
