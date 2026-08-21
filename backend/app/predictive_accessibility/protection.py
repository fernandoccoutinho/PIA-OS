"""`E5.o` — candidatos protetivos e materialidade **derivada**.

Três conjuntos separados. O status **não** é aceito pronto do chamador: é
calculado a partir da assertividade `E5.n`, da avaliação `CLAIM_EVALUATION_RESULT`
e da referência de autoridade de materialidade.

```text
SUPPORTED requer autoridade VÁLIDA + owner + tempo + reversibilidade + gatilhos
NO_COMPETENT_BASIS -> UNRESOLVED  (não se inventa limiar)
UNRESOLVED_BRANCH -> COMPLETE_ANSWER = FORBIDDEN
```
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from app.predictive_accessibility.assertiveness import (
    PredictiveAssertiveness,
    PredictiveAuthorityState,
)
from app.predictive_accessibility.epistemic import PredictiveClaimEvaluationResult
from app.predictive_accessibility.piap.authority import ApprovalBinding
from app.predictive_accessibility.piap.enums import ApprovalValidationOutcome


class PredictiveMaterialityStatus(StrEnum):
    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class PredictiveMaterialityAuthority:
    """Autoridade competente. **Não** declara a própria validade.

    O campo `valid: bool` da R1 era autocertificação: o chamador afirmava que a
    autoridade valia e `E5.o` acreditava. Agora a validade é derivada da
    aprovação já calculada no `CLAIM_EVALUATION_RESULT` e destes metadados
    verificáveis.

    ```text
    SELF_DECLARED_VALIDITY = NOT_VALIDATION
    E5_VALIDATES_AUTHORITY_BUT_NEVER_GRANTS_IT
    ```
    """

    reference: str
    authority: str
    jurisdiction: str
    version: int
    scope: tuple[str, ...]
    valid_from: datetime | None
    valid_until: datetime | None


@dataclass(frozen=True)
class PredictiveProtectionCandidateInput:
    """Candidato proposto. Não declara o próprio status."""

    identifier: str
    reason: str
    provenance: str
    material_effect_claimed: bool
    authority: PredictiveMaterialityAuthority | None = None
    owner: str | None = None
    time_window: str | None = None
    reversibility: str | None = None
    triggers: tuple[str, ...] = ()
    incompatible_with: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.identifier or not self.reason or not self.provenance:
            raise ValueError("candidato exige identificador, razão e proveniência")
        if self.identifier in self.incompatible_with:
            raise ValueError("candidato não pode ser incompatível consigo mesmo")
        if len(set(self.incompatible_with)) != len(self.incompatible_with):
            raise ValueError("incompatibilidades não admitem duplicata")


@dataclass(frozen=True)
class PredictiveProtectionCandidate:
    """Candidato já classificado, com a razão da classificação preservada."""

    identifier: str
    reason: str
    provenance: str
    materiality: PredictiveMaterialityStatus
    classification_reason: str
    owner: str | None = None
    authority: PredictiveMaterialityAuthority | None = None
    time_window: str | None = None
    reversibility: str | None = None
    triggers: tuple[str, ...] = ()
    incompatible_with: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.materiality is PredictiveMaterialityStatus.SUPPORTED:
            if self.authority is None:
                raise ValueError("ramo aceito exige referência de autoridade")
            faltando = [
                nome
                for nome in ("owner", "time_window", "reversibility")
                if getattr(self, nome) is None
            ]
            if faltando or not self.triggers:
                raise ValueError(f"ramo aceito precisa preservar {faltando or ['triggers']}")


@dataclass(frozen=True)
class PredictiveProtectionSet:
    """Os três conjuntos, sempre presentes, nunca fundidos."""

    accepted: tuple[PredictiveProtectionCandidate, ...]
    rejected: tuple[PredictiveProtectionCandidate, ...]
    unresolved: tuple[PredictiveProtectionCandidate, ...]
    assertiveness: PredictiveAssertiveness
    evaluation: PredictiveClaimEvaluationResult
    conflict_assessment: object
    coverage_unresolved_reason: str | None = None

    @property
    def has_unresolved_branch(self) -> bool:
        return bool(self.unresolved) or self.coverage_unresolved_reason is not None

    @property
    def complete_answer_allowed(self) -> bool:
        return not self.has_unresolved_branch


def predictive_materiality_authority_failure(
    authority: PredictiveMaterialityAuthority | None,
    *,
    evaluation: PredictiveClaimEvaluationResult,
    approval_binding: ApprovalBinding | None,
    at: datetime,
    required_scope: tuple[str, ...],
) -> str | None:
    """Devolve o motivo da recusa, ou `None` quando a autoridade se sustenta."""
    if evaluation.approval_validation_outcome is not ApprovalValidationOutcome.VALID:
        return (
            f"aprovação PIAP {evaluation.approval_validation_outcome.value}: "
            "materialidade não sustentada"
        )
    if authority is None:
        return "sem referência de autoridade de materialidade"
    if approval_binding is None:
        return "aprovação PIAP validada sem vínculo preservado no coordenador"
    if not authority.reference.strip() or not authority.authority.strip():
        return "referência ou autoridade vazia"
    if authority.reference != approval_binding.approval_reference:
        return "referência de autoridade não vinculada à aprovação PIAP"
    if authority.version < 1 or authority.version != approval_binding.approval_version:
        return "versão de autoridade divergente da aprovação PIAP"
    if authority.jurisdiction != approval_binding.approval_jurisdiction:
        return "jurisdição de autoridade divergente da aprovação PIAP"
    if not set(authority.scope) <= set(approval_binding.approval_scope):
        return "escopo declarado pela autoridade excede a aprovação PIAP"
    if not set(required_scope) <= set(authority.scope):
        return "escopo de autoridade insuficiente"
    if authority.valid_from is None or authority.valid_until is None:
        return "janela de autoridade ausente"
    if authority.valid_until <= authority.valid_from:
        return "janela de autoridade incoerente"
    if at < authority.valid_from or at >= authority.valid_until:
        return "autoridade fora da janela de vigência"
    if (
        approval_binding.approval_expiry is not None
        and authority.valid_until > approval_binding.approval_expiry
    ):
        return "janela de autoridade excede a aprovação PIAP"
    return None


def _classificar(
    entrada: PredictiveProtectionCandidateInput,
    *,
    assertiveness: PredictiveAssertiveness,
    evaluation: PredictiveClaimEvaluationResult,
    approval_binding: ApprovalBinding | None,
    conflict_assessment: object,
    at: datetime,
    required_scope: tuple[str, ...],
) -> PredictiveProtectionCandidate:
    falha = predictive_materiality_authority_failure(
        entrada.authority,
        evaluation=evaluation,
        approval_binding=approval_binding,
        at=at,
        required_scope=required_scope,
    )
    if not entrada.material_effect_claimed:
        status = PredictiveMaterialityStatus.NOT_SUPPORTED
        motivo = "nenhum efeito material alegado"
    elif falha is not None:
        status = PredictiveMaterialityStatus.UNRESOLVED
        motivo = falha
    elif getattr(conflict_assessment, "blocks_material_support", False):
        status = PredictiveMaterialityStatus.UNRESOLVED
        motivo = "conflito real entre alegações impede sustentar materialidade"
    elif assertiveness.authority_state is not PredictiveAuthorityState.AUTHORIZED:
        status = PredictiveMaterialityStatus.UNRESOLVED
        motivo = "assertividade sem estado de autoridade"
    elif (
        entrada.owner is None
        or entrada.time_window is None
        or entrada.reversibility is None
        or not entrada.triggers
    ):
        status = PredictiveMaterialityStatus.UNRESOLVED
        motivo = "faltam owner, janela, reversibilidade ou gatilhos"
    else:
        status = PredictiveMaterialityStatus.SUPPORTED
        motivo = "efeito material sustentado por autoridade válida"
    return PredictiveProtectionCandidate(
        identifier=entrada.identifier,
        reason=entrada.reason,
        provenance=entrada.provenance,
        materiality=status,
        classification_reason=motivo,
        owner=entrada.owner,
        authority=entrada.authority,
        time_window=entrada.time_window,
        reversibility=entrada.reversibility,
        triggers=entrada.triggers,
        incompatible_with=entrada.incompatible_with,
    )


def predictive_protection_set(
    candidates: tuple[PredictiveProtectionCandidateInput, ...],
    *,
    assertiveness: PredictiveAssertiveness,
    evaluation: PredictiveClaimEvaluationResult,
    approval_binding: ApprovalBinding | None,
    conflict_assessment: object,
    at: datetime,
    required_scope: tuple[str, ...] = (),
    required_identifiers: tuple[str, ...] = (),
    inventory_reference: str | None = None,
) -> PredictiveProtectionSet:
    classificados = tuple(
        _classificar(
            c,
            assertiveness=assertiveness,
            evaluation=evaluation,
            approval_binding=approval_binding,
            conflict_assessment=conflict_assessment,
            at=at,
            required_scope=required_scope,
        )
        for c in candidates
    )
    identificadores = {c.identifier for c in classificados}
    faltantes = tuple(i for i in required_identifiers if i not in identificadores)
    cobertura: str | None = None
    if not candidates and not required_identifiers:
        cobertura = "cobertura protetiva não avaliada: nenhum candidato nem evidência negativa"
    elif required_identifiers and not inventory_reference:
        cobertura = "inventário de frentes protetivas sem proveniência"
    elif faltantes:
        cobertura = "frentes protetivas requeridas ausentes: " + ", ".join(faltantes)

    aceitos = [c for c in classificados if c.materiality is PredictiveMaterialityStatus.SUPPORTED]
    ids_aceitos = {c.identifier for c in aceitos}
    ids_incompativeis = {
        c.identifier
        for c in aceitos
        if any(i in ids_aceitos for i in c.incompatible_with)
        or any(c.identifier in outro.incompatible_with for outro in aceitos)
    }
    reclassificados = {
        c.identifier: replace(
            c,
            materiality=PredictiveMaterialityStatus.UNRESOLVED,
            classification_reason="ação protetiva incompatível sem critério decisivo validado",
        )
        for c in aceitos
        if c.identifier in ids_incompativeis
    }
    finais = tuple(reclassificados.get(c.identifier, c) for c in classificados)
    return PredictiveProtectionSet(
        accepted=tuple(c for c in finais if c.materiality is PredictiveMaterialityStatus.SUPPORTED),
        rejected=tuple(
            c for c in finais if c.materiality is PredictiveMaterialityStatus.NOT_SUPPORTED
        ),
        unresolved=tuple(
            c for c in finais if c.materiality is PredictiveMaterialityStatus.UNRESOLVED
        ),
        assertiveness=assertiveness,
        evaluation=evaluation,
        conflict_assessment=conflict_assessment,
        coverage_unresolved_reason=cobertura,
    )
