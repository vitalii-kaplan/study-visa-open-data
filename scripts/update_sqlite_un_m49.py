#!/usr/bin/env python3
"""Refresh shared country normalization fields in an existing SQLite build."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from country_normalization import normalize_country


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "student_visa.sqlite"
TABLE = "student_visa_common_long"


def column_names(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE}")')]


def main() -> None:
    conn = sqlite3.connect(DB)
    try:
        columns = column_names(conn)
        if "un_m49_country" not in columns:
            conn.execute(f'ALTER TABLE "{TABLE}" ADD COLUMN "un_m49_country" TEXT')
            columns = column_names(conn)
        if "normalization_status" not in columns:
            conn.execute(f'ALTER TABLE "{TABLE}" ADD COLUMN "normalization_status" TEXT')

        origins = [
            (row[0], row[1])
            for row in conn.execute(
                f'SELECT DISTINCT destination_country, origin_country FROM "{TABLE}"'
            )
        ]
        for destination, origin in origins:
            normalized = normalize_country(origin or "", destination or "")
            conn.execute(
                f'UPDATE "{TABLE}" SET un_m49_country = ?, normalization_status = ? '
                'WHERE destination_country IS ? AND origin_country IS ?',
                (normalized.country or None, normalized.status, destination, origin),
            )
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS idx_student_visa_un_m49_country ON "{TABLE}" (un_m49_country)'
        )
        conn.commit()
        conn.execute("ANALYZE")
        conn.commit()

        total = conn.execute(f'SELECT COUNT(*) FROM "{TABLE}"').fetchone()[0]
        unmatched = conn.execute(
            f'SELECT COUNT(*) FROM "{TABLE}" WHERE normalization_status = ?',
            ("unmatched",),
        ).fetchone()[0]
        print(f"{DB.relative_to(ROOT)}: {total} rows")
        print(f"normalization_status = unmatched: {unmatched} rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
