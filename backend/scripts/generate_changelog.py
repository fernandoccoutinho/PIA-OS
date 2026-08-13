#!/usr/bin/env python3
"""
Regenera CHANGELOG_API.md a partir de `app.docs.changelog.API_CHANGELOG`
(fonte única). Rodar após adicionar uma nova entrada:

    PYTHONPATH=. python scripts/generate_changelog.py
"""

from pathlib import Path

from app.docs.changelog import render_changelog_markdown

if __name__ == "__main__":
    output_path = Path(__file__).resolve().parents[1] / "CHANGELOG_API.md"
    output_path.write_text(render_changelog_markdown())
    print(f"Gerado: {output_path}")
