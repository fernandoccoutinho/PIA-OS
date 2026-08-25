"""Mutantes reais do adaptador local B3-Free, todos sem banco de dados."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = "tests/unit/authorization/test_ollama_classifier.py"


@dataclass(frozen=True)
class Mutant:
    name: str
    path: str
    old: str
    new: str


MUTANTS = (
    Mutant(
        "M-LOCAL-DEFAULT",
        "app/authorization/ollama_classifier.py",
        'ambiente.get(MODEL_ENV, "").strip()',
        'ambiente.get(MODEL_ENV, "gpt-oss:20b").strip()',
    ),
    Mutant(
        "M-REMOTE-ENDPOINT",
        "app/authorization/ollama_classifier.py",
        "analisado.hostname not in LOOPBACK_HOSTS",
        "False",
    ),
    Mutant(
        "M-DIGEST-LOOSE",
        "app/authorization/ollama_classifier.py",
        're.compile(r"^[0-9a-f]{64}$")',
        're.compile(r".*")',
    ),
    Mutant(
        "M-DIGEST-UNBOUND",
        "app/authorization/ollama_classifier.py",
        'f"{PROVIDER}:{self._model}@{self._model_digest[:12]}"',
        'f"{PROVIDER}:{self._model}@fixed-digest"',
    ),
    Mutant(
        "M-STREAMING",
        "app/authorization/ollama_classifier.py",
        '"stream": False,',
        '"stream": True,',
    ),
    Mutant(
        "M-SCHEMA-OPEN",
        "app/authorization/ollama_classifier.py",
        '"format": RESPONSE_SCHEMA,',
        '"format": "json",',
    ),
    Mutant(
        "M-TEMPERATURE",
        "app/authorization/ollama_classifier.py",
        '"options": {"temperature": 0},',
        '"options": {"temperature": 1},',
    ),
    Mutant(
        "M-INCOMPLETE-ACCEPTED",
        "app/authorization/ollama_classifier.py",
        'if resposta.get("done") is not True:',
        'if resposta.get("done") is None:',
    ),
    Mutant(
        "M-COVERAGE-EMPTY",
        "app/authorization/ollama_classifier.py",
        "return frozenset(CriticalCapability)",
        "return frozenset()",
    ),
)


def run_test() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-cov", TEST],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    ).returncode


def main() -> int:
    baseline = run_test()
    if baseline != 0:
        print(f"BASELINE=FAIL exit={baseline}")
        return 2

    killed = 0
    for mutant in MUTANTS:
        path = ROOT / mutant.path
        original = path.read_text(encoding="utf-8")
        if original.count(mutant.old) != 1:
            print(f"{mutant.name}=INVALID_TARGET count={original.count(mutant.old)}")
            return 3
        try:
            path.write_text(original.replace(mutant.old, mutant.new), encoding="utf-8")
            code = run_test()
        finally:
            path.write_text(original, encoding="utf-8")
        status = "KILLED" if code != 0 else "SURVIVED"
        print(f"{mutant.name}={status}")
        if code != 0:
            killed += 1

    print(f"B3FREE_MUTANTS={killed}/{len(MUTANTS)} KILLED")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
