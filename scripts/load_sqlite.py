#!/usr/bin/env python3
"""Load the common long CSV into SQLite."""

from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "student_visa_common_long.csv"
DB_PATH = ROOT / "data" / "student_visa.sqlite"
BUILD_PATH = ROOT / "data" / "student_visa.sqlite.building"
SQLITE_ONLY_PATHS = [
    ROOT / "tmp" / "processed" / "canada" / "study_permit_french_bilingual_common_long_sqlite_only.csv",
]
TABLE = "student_visa_common_long"
BATCH_SIZE = 50000


def include_in_strict_database(row: dict[str, str]) -> bool:
    destination = row["destination_country"]
    category = row["visa_category"]
    return (
        (destination == "Australia" and category == "student visa" and row["applicant_type"] == "Primary")
        or (destination == "Canada" and category == "study permit")
        or (destination == "New Zealand" and category == "student visa")
        or (
            destination == "United Kingdom"
            and category == "Study"
            and row["applicant_type"] in {"Main Applicant", "main_applicant_only"}
        )
        or (destination == "United States" and row["applicant_type"] == "primary")
    )


def csv_rows(path: Path, expected_header: list[str], strict_filter: bool):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected_header:
            raise ValueError(f"{path} header does not match the common schema")
        for row in reader:
            if strict_filter and not include_in_strict_database(row):
                continue
            row["un_m49_country"] = row["un_m49_country"] or None
            yield [row[column] for column in expected_header]


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(CSV_PATH)

    if BUILD_PATH.exists():
        BUILD_PATH.unlink()

    conn = sqlite3.connect(BUILD_PATH)
    try:
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -1000000")

        with CSV_PATH.open(newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))
            columns_sql = ",\n  ".join(f'"{column}" TEXT' for column in header)
            conn.execute(f'DROP TABLE IF EXISTS "{TABLE}"')
            conn.execute(f'CREATE TABLE "{TABLE}" (\n  {columns_sql}\n)')

            placeholders = ",".join("?" for _ in header)
            insert_sql = f'INSERT INTO "{TABLE}" VALUES ({placeholders})'
            batch: list[list[str | None]] = []
            total = 0
            inputs = [(CSV_PATH, True)] + [(path, False) for path in SQLITE_ONLY_PATHS]
            for path, strict_filter in inputs:
                if not path.exists():
                    raise FileNotFoundError(path)
                for row in csv_rows(path, header, strict_filter):
                    batch.append(row)
                    if len(batch) >= BATCH_SIZE:
                        conn.executemany(insert_sql, batch)
                        total += len(batch)
                        print(f"inserted {total} rows")
                        batch.clear()
            if batch:
                conn.executemany(insert_sql, batch)
                total += len(batch)
                print(f"inserted {total} rows")
            conn.commit()

        indexes = [
            ("idx_student_visa_destination", "destination_country"),
            ("idx_student_visa_origin", "origin_country"),
            ("idx_student_visa_origin_type", "origin_country_type"),
            ("idx_student_visa_period", "calendar_year, financial_year, period_label"),
            ("idx_student_visa_measure", "measure_type"),
            ("idx_student_visa_category", "visa_category"),
            ("idx_student_visa_dest_origin_measure", "destination_country, origin_country, measure_type"),
            ("idx_student_visa_un_m49_country", "un_m49_country"),
            ("idx_student_visa_normalization_status", "normalization_status"),
        ]
        for name, columns in indexes:
            print(f"creating index {name}")
            conn.execute(f'CREATE INDEX "{name}" ON "{TABLE}" ({columns})')
        conn.commit()
        conn.execute("ANALYZE")
        conn.commit()

        count = conn.execute(f'SELECT COUNT(*) FROM "{TABLE}"').fetchone()[0]
        print(f"{DB_PATH.relative_to(ROOT)}: {count} rows")
    finally:
        conn.close()
    os.replace(BUILD_PATH, DB_PATH)


if __name__ == "__main__":
    main()
