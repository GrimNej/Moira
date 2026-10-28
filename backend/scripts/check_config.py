"""Fail if .env.example, config.py and docs/reference/CONFIG.md list different variables (§13.9)."""

import re
import sys
from pathlib import Path

from moira.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    in_config = {name.upper() for name in Settings.model_fields}
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    in_example = set(re.findall(r"^#? ?([A-Z][A-Z0-9_]+)=", example, re.MULTILINE))
    doc = (ROOT / "docs/reference/CONFIG.md").read_text(encoding="utf-8")
    first_cells = re.findall(r"^\| ([^|]+) \|", doc, re.MULTILINE)
    in_doc = {name for cell in first_cells for name in re.findall(r"`([A-Z][A-Z0-9_]+)`", cell)}
    ok = True
    for label, names in ((".env.example", in_example), ("CONFIG.md", in_doc)):
        if names != in_config:
            ok = False
            print(f"{label} differs from config.py:")
            print(f"  missing: {sorted(in_config - names)}")
            print(f"  extra:   {sorted(names - in_config)}")
    if ok:
        print(f"config OK: {len(in_config)} variables")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
