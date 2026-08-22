"""
Produz o snapshot canônico do OpenAPI da Chain107-R1.

```text
LIVE_OPENAPI -> CANONICAL_JSON_SNAPSHOT
CANONICAL = UTF8 + SORTED_KEYS + COMPACT_SEPARATORS + TRAILING_NEWLINE
VOLATILE_FIELDS = STRIPPED_EXPLICITLY
```

## Por que existe um passo de canonicalização

`app.openapi()` da Chain107-R1 inclui `info.x-metadata.generated_at`, um
instante de geração. Ele muda a cada processo, então o documento vivo
**não é** byte-estável. Congelar o timestamp no snapshot faria
`REGENERATION_DIFF = ZERO` falhar em qualquer reexecução, e o gate viraria
ruído até alguém desligá-lo.

A remoção é explícita e enumerada: um campo volátil novo não é ignorado em
silêncio — passa a divergir e obriga uma decisão. Nenhum campo de contrato
é tocado.

```text
STRIP_VOLATILE != STRIP_CONTRACT
SILENT_NORMALIZATION = FORBIDDEN
```

Uso:

    python -m tools.snapshot_openapi          # escreve o snapshot
    python -m tools.snapshot_openapi --check  # compara sem escrever
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "schema" / "openapi_chain107_r1.json"

# Único campo volátil da Chain107-R1. Lista fechada e revisável: se o
# backend passar a emitir outro campo instável, o `--check` acusa em vez
# de normalizar por conta própria.
VOLATILE_POINTERS: tuple[tuple[str, ...], ...] = (("info", "x-metadata", "generated_at"),)


def strip_volatile(documento: dict[str, Any]) -> dict[str, Any]:
    """Remove apenas os ponteiros enumerados. Não toca em contrato."""
    copia: dict[str, Any] = json.loads(json.dumps(documento))
    for ponteiro in VOLATILE_POINTERS:
        no: Any = copia
        for chave in ponteiro[:-1]:
            if not isinstance(no, dict) or chave not in no:
                no = None
                break
            no = no[chave]
        if isinstance(no, dict):
            no.pop(ponteiro[-1], None)
    return copia


def canonicalize(documento: dict[str, Any]) -> str:
    return (
        json.dumps(
            strip_volatile(documento),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _openapi_vivo() -> dict[str, Any]:
    """Importa o backend SOMENTE nesta ferramenta, nunca no runtime do SDK.

    ```text
    RUNTIME_IMPORT_FROM_BACKEND_APP = FORBIDDEN
    TOOLING_IMPORT_FOR_DERIVATION = ALLOWED
    ```
    """
    import main  # noqa: PLC0415  (import local e deliberado)

    documento: dict[str, Any] = main.app.openapi()
    return documento


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="snapshot_openapi")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    texto = canonicalize(_openapi_vivo())
    digest = hashlib.sha256(texto.encode("utf-8")).hexdigest()

    if args.check:
        if not DESTINO.exists():
            print("FAIL: snapshot ausente", file=sys.stderr)
            return 1
        if DESTINO.read_text(encoding="utf-8") != texto:
            print("FAIL: snapshot diverge do OpenAPI vivo", file=sys.stderr)
            return 1
        print("OK: snapshot == OpenAPI vivo (voláteis removidos)")
        print(f"sha256 = {digest}")
        return 0

    DESTINO.write_text(texto, encoding="utf-8")
    print(f"snapshot : {DESTINO}")
    print(f"sha256   : {digest}")
    print(f"volateis : {[' -> '.join(p) for p in VOLATILE_POINTERS]}")
    return 0


if __name__ == "__main__":  # pragma: no cover - entrypoint
    raise SystemExit(main())
