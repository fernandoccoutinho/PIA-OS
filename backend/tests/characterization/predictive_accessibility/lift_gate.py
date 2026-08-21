"""Instrumento do gate de lift do Patch 3 — externo aos testes unitários.

Recalcula baseline, AR(1), bootstrap e placebo PELO CÓDIGO DA FATIA. Os números
de referência do manifesto são sonda de sanidade, nunca evidência de aceitação.

```text
REFERENCE_SANITY_CHECK != ACCEPTANCE_EVIDENCE
```
"""

from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from app.predictive_accessibility.epistemic import (  # noqa: E402
    PredictiveEpistemicState,
    predictive_classify_epistemic_state,
)
from app.predictive_accessibility.estimator import (  # noqa: E402
    predictive_fit_ar1,
    predictive_fit_baseline,
    predictive_per_event_gains,
)
from app.predictive_accessibility.power import (  # noqa: E402
    PredictivePowerOutcome,
    predictive_circular_block_bootstrap,
    predictive_deterministic_placebo,
)

FIXTURES = RAIZ / "tests" / "fixtures" / "predictive_accessibility"
CSV = FIXTURES / "e5_patch3_internal_gate_fixture_v1.csv"
MANIFESTO = FIXTURES / "e5_patch3_internal_gate_fixture_v1_manifest.json"


def carregar() -> tuple[dict, dict]:
    manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    digest = hashlib.sha256(CSV.read_bytes()).hexdigest()
    if digest != manifesto["sha256"]:
        raise SystemExit(f"DATASET_HASH_MISMATCH {digest}")
    braços: dict[str, dict[str, list[tuple[float, float]]]] = {}
    with CSV.open(encoding="utf-8", newline="") as fh:
        for linha in csv.DictReader(fh):
            braço = braços.setdefault(linha["arm"], {"train": [], "calibration": [], "blind": []})
            braço[linha["split"]].append((float(linha["predictor"]), float(linha["target"])))
    return manifesto, braços


def avaliar(nome: str, dados: dict, estat: dict) -> tuple[PredictivePowerOutcome, str]:
    treino = tuple(dados["train"])
    cego = tuple(dados["blind"])
    alfa = estat["alpha_corrected"]
    baseline = predictive_fit_baseline(tuple(y for _, y in treino))
    ar1 = predictive_fit_ar1(treino)
    ganhos = predictive_per_event_gains(baseline, ar1, cego)
    inferior, superior = predictive_circular_block_bootstrap(
        ganhos,
        replicates=estat["bootstrap_replicates"],
        seed=estat["bootstrap_seeds"][nome],
        alpha_corrected=alfa,
    )
    logs_baseline = tuple(baseline.log_density(y) for _, y in cego)
    p, g_real, p95 = predictive_deterministic_placebo(
        logs_baseline,
        ar1.log_density,
        cego,
        permutations=2000,
        seed=estat["placebo_seeds"][nome],
    )
    # A*_worst = máximo dos quantis superiores corrigidos na biblioteca S.
    # A baseline contra ela mesma tem ganho identicamente zero.
    a_star_worst = max(superior, 0.0)
    evidencia = PredictivePowerOutcome(
        a_minus=inferior,
        a_upper=superior,
        a_star_worst=a_star_worst,
        mean_gain=sum(ganhos) / len(ganhos),
        placebo_p=p,
        g_real=g_real,
        g_shuffled_p95=p95,
        sample_size=len(cego),
        alpha_corrected=alfa,
    )
    confirmatorio = p < alfa and g_real > p95
    estado = predictive_classify_epistemic_state(
        evidencia, a_rel=estat["A_rel_nats_per_event"], confirmatory_pass=confirmatorio
    )
    return evidencia, estado


def main() -> int:
    manifesto, braços = carregar()
    estat = manifesto["frozen_statistics"]
    a_rel = estat["A_rel_nats_per_event"]
    resultados = {}
    for nome in ("positive", "negative", "unresolved"):
        evid, estado = avaliar(nome, braços[nome], estat)
        resultados[nome] = (evid, estado)
        print(
            f"{nome:<11} A_minus={evid.a_minus:+.6f} A_upper={evid.a_upper:+.6f} "
            f"A_star_worst={evid.a_star_worst:+.6f} placebo_p={evid.placebo_p:.6f} "
            f"G_real={evid.g_real:+.6f} p95={evid.g_shuffled_p95:+.6f} n={evid.sample_size} "
            f"state={estado.value}"
        )
    pos, neg, unr = (resultados[k][0] for k in ("positive", "negative", "unresolved"))
    condicoes = {
        "positive.A_lower>0": pos.a_minus > 0,
        "positive.placebo_p<alpha": pos.placebo_p < estat["alpha_corrected"],
        "positive.G_real>p95": pos.g_real > pos.g_shuffled_p95,
        "negative.A_lower<=0": neg.a_minus <= 0,
        "negative.A_upper<A_rel": neg.a_upper < a_rel,
        "unresolved.A_lower<=0": unr.a_minus <= 0,
        "unresolved.A_upper>=A_rel": unr.a_upper >= a_rel,
        "states": (
            resultados["positive"][1] is PredictiveEpistemicState.PREDICTABLE
            and resultados["negative"][1] is PredictiveEpistemicState.PREDICTIVELY_INACCESSIBLE
            and resultados["unresolved"][1] is PredictiveEpistemicState.UNRESOLVED
        ),
    }
    print()
    for k, v in condicoes.items():
        print(f"  {k:<28} {v}")
    ok = all(condicoes.values())
    print(f"\nPATCH_3_MINIMAL_SLICE_LIFT_OUTCOME = {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
