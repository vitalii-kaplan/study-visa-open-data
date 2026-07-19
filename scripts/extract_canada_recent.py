#!/usr/bin/env python3
"""Extract newer Canada study permit transparency data and load it to SQLite."""

from __future__ import annotations

import csv
import argparse
import sqlite3
from pathlib import Path

from build_common_table import FIELDS
from country_normalization import normalize_country
from extract_csv import ROOT, RAW, OUT, html_tables, write_csv


DB = ROOT / "data" / "student_visa.sqlite"
TABLE = "student_visa_common_long"
PROCESSED = ROOT / "tmp" / "processed" / "canada"
Q2700_SOURCE = RAW / "canada" / "ollo-order-paper-q2700-2024-11-04.html"
Q2700_CSV = OUT / "canada" / "study_permit_french_bilingual_outcomes_by_country_residence_2023_2024apr_snapshot_2024-11-04.csv"
Q2700_SQLITE_CSV = PROCESSED / "study_permit_french_bilingual_common_long_sqlite_only.csv"


def clean_number(value: str) -> str:
    value = (value or "").strip()
    if value in {"", "--"}:
        return ""
    return value.replace(",", "").replace("%", "")


def add_numbers(*values: str) -> str:
    nums = [clean_number(value) for value in values]
    if any(value == "" for value in nums):
        return ""
    return str(sum(int(value) for value in nums))


def extract_q2700_source_csv() -> tuple[Path, int]:
    table = html_tables(Q2700_SOURCE)[0]
    rows = []
    for row in table[3:]:
        if len(row) < 8:
            continue
        country = row[0]
        rows.append(["2024-11-04", country, "2023", row[1], row[2], row[3], add_numbers(row[1], row[3]), row[7]])
        rows.append(["2024-11-04", country, "2024 January-April", row[4], row[5], row[6], add_numbers(row[4], row[6]), row[7]])
    header = [
        "source_snapshot",
        "country_of_residence",
        "period_label",
        "approved",
        "approval_rate",
        "refused",
        "processed_applications",
        "total_processed_component",
    ]
    return Q2700_CSV, write_csv(Q2700_CSV, header, rows)


def q2700_common_rows():
    with Q2700_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            year = "2023" if r["period_label"] == "2023" else "2024"
            period_type = "calendar_year" if r["period_label"] == "2023" else "partial_year"
            country = r["country_of_residence"]
            coverage = "aggregate" if country == "Grand Total" else "official_language_french_bilingual_country_residence"
            normalized = normalize_country(country, "Canada")
            base = {field: "" for field in FIELDS}
            base.update(
                {
                    "destination_country": "Canada",
                    "origin_country": country,
                    "un_m49_country": normalized.country,
                    "normalization_status": normalized.status,
                    "origin_country_type": "country_of_residence",
                    "period_label": r["period_label"],
                    "period_type": period_type,
                    "calendar_year": year,
                    "visa_category": "study permit",
                    "visa_category_source": "study permit excluding extensions; French-speaking or bilingual applicants",
                    "measure_unit": "count",
                    "coverage_type": coverage,
                    "source_snapshot": r["source_snapshot"],
                    "source_file": Q2700_CSV.relative_to(ROOT).as_posix(),
                    "source_notes": "OLLO Q-2700 Annex A; official language French or bilingual only; country of residence; excludes extensions.",
                }
            )
            for measure_type, source_column, unit, denominator in [
                ("approvals", "approved", "count", ""),
                ("refusals", "refused", "count", ""),
                ("processed_applications", "processed_applications", "count", ""),
                ("approval_rate", "approval_rate", "percent", "source_reported"),
            ]:
                value = clean_number(r[source_column])
                if value == "":
                    continue
                row = base.copy()
                row["measure_type"] = measure_type
                row["measure_value"] = value
                row["measure_unit"] = unit
                row["rate_denominator_type"] = denominator
                yield row


def write_sqlite_only_common_csv() -> tuple[Path, int]:
    Q2700_SQLITE_CSV.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with Q2700_SQLITE_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in q2700_common_rows():
            writer.writerow(row)
            count += 1
    return Q2700_SQLITE_CSV, count


def sqlite_columns(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE}")')]


def insert_sqlite() -> int:
    rows = list(q2700_common_rows())
    conn = sqlite3.connect(DB)
    try:
        columns = sqlite_columns(conn)
        placeholders = ",".join("?" for _ in columns)
        conn.execute(
            f'DELETE FROM "{TABLE}" WHERE source_file = ?',
            (Q2700_CSV.relative_to(ROOT).as_posix(),),
        )
        conn.executemany(
            f'INSERT INTO "{TABLE}" VALUES ({placeholders})',
            ([row.get(column, "") for column in columns] for row in rows),
        )
        conn.commit()
        conn.execute("ANALYZE")
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--insert-sqlite",
        action="store_true",
        help="Replace Q-2700 rows in an existing database. A full load includes this subset automatically.",
    )
    args = parser.parse_args()
    results = [extract_q2700_source_csv(), write_sqlite_only_common_csv()]
    for path, count in results:
        print(f"{path.relative_to(ROOT)}: {count} rows")
    if args.insert_sqlite:
        print(f"{DB.relative_to(ROOT)}: inserted {insert_sqlite()} Q-2700 rows")


if __name__ == "__main__":
    main()
