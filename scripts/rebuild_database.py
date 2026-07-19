#!/usr/bin/env python3
"""Rebuild every derived artifact and the final strict student-visa database."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(script: str, *arguments: str) -> None:
    command = [sys.executable, str(ROOT / "scripts" / script), *arguments]
    print(f"\n$ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Reuse existing source-level CSVs and rebuild only processed/common/SQLite artifacts.",
    )
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    if not args.skip_extraction:
        run("extract_csv.py")
        run("extract_us.py")
    run("combine_canada.py")
    run("extract_canada_recent.py")
    run("build_common_table.py")
    run("load_sqlite.py")
    if not args.skip_validation:
        run("validate_database.py")


if __name__ == "__main__":
    main()
