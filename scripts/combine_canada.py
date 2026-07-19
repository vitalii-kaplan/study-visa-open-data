#!/usr/bin/env python3
"""Combine Canada source-level CSVs into processed analysis-ready groups."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "csv" / "canada"
OUT = ROOT / "tmp" / "processed" / "canada"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def clean_number(value: str) -> str:
    value = (value or "").strip()
    if value in {"", "--"}:
        return ""
    return value.replace(",", "")


def clean_percent(value: str) -> str:
    value = (value or "").strip()
    if value in {"", "--"}:
        return ""
    return value.rstrip("%")


def parse_period(period_label: str) -> tuple[str, str, str, str]:
    label = period_label.strip()
    if re.fullmatch(r"\d{4}", label):
        return label, "calendar_year", label, ""
    if label == "Jan-2022":
        return "2022-01", "partial_month", "2022", "Jan"
    if "2023 to April 30" in label:
        return "2023-01-01/2023-04-30", "partial_year", "2023", ""
    if "2024 until January 31" in label:
        return "2024-01-01/2024-01-31", "partial_year", "2024", ""
    if "2023 (full year)" in label:
        return "2023", "calendar_year", "2023", ""
    if "2023 (up to sept 30)" in label.lower():
        return "2023-01-01/2023-09-30", "partial_year", "2023", ""
    if "2024 (up to sept" in label.lower():
        return "2024-01-01/2024-09-30", "partial_year", "2024", ""
    return label, "source_period", "", ""


def country_coverage(country: str, source_file: str) -> str:
    if country == "Grand Total":
        return "grand_total"
    if country == "Other Countries":
        return "other_countries"
    if "top10" in source_file:
        return "top10_country"
    return "all_countries"


def combine_outcomes_by_country_residence() -> tuple[Path, int]:
    rows: list[dict[str, str]] = []
    files = [
        (
            "study_permit_approval_rates_by_country_residence_2019_2022jan.csv",
            "cimm-student-approval-rates-country-residence-2019-2022-jan",
            "2019-Jan 2022 all-country CIMM table",
            "all_countries",
        ),
        (
            "study_permit_outcomes_top10_country_residence_2022_2023apr_snapshot_2023-06-14.csv",
            "cimm-sp-intake-output-issued-2023-06-14",
            "2022-Apr 2023 CIMM top-10 snapshot",
            "top10_plus_other_and_total",
        ),
        (
            "study_permit_outcomes_top10_country_residence_2022_2024jan_snapshot_2024-02-28.csv",
            "cimm-international-students-intake-output-issued-2024-02-28",
            "2022-Jan 2024 CIMM top-10 snapshot",
            "top10_plus_other_and_total",
        ),
    ]
    for filename, source_id, description, coverage_type in files:
        for row in read_rows(SRC / filename):
            period_label = row["period_label"]
            if filename.startswith("study_permit_approval_rates"):
                source_snapshot = ""
                period_key = period_label
                period_type = row["period_type"]
                year = row["year"]
                month = ""
                grand_total = ""
            else:
                source_snapshot = row["source_snapshot"]
                period_key, period_type, year, month = parse_period(period_label)
                grand_total = clean_number(row.get("grand_total", ""))
            rows.append(
                {
                    "destination_country": "Canada",
                    "origin_country_type": "country_of_residence",
                    "country_of_residence": row["country_of_residence"],
                    "country_coverage": country_coverage(row["country_of_residence"], filename),
                    "coverage_type": coverage_type,
                    "period_label": period_label,
                    "period_key": period_key,
                    "period_type": period_type,
                    "year": year,
                    "month": month,
                    "approved": clean_number(row.get("approved", "")),
                    "refused": clean_number(row.get("refused", "")),
                    "withdrawn": clean_number(row.get("withdrawn", "")),
                    "approval_rate_percent": clean_percent(row.get("approval_rate", "")),
                    "total": clean_number(row.get("total", "")),
                    "grand_total": grand_total,
                    "source_snapshot": source_snapshot,
                    "source_id": source_id,
                    "source_file": filename,
                    "source_description": description,
                }
            )
    out = OUT / "study_permit_outcomes_by_country_residence.csv"
    fields = [
        "destination_country",
        "origin_country_type",
        "country_of_residence",
        "country_coverage",
        "coverage_type",
        "period_label",
        "period_key",
        "period_type",
        "year",
        "month",
        "approved",
        "refused",
        "withdrawn",
        "approval_rate_percent",
        "total",
        "grand_total",
        "source_snapshot",
        "source_id",
        "source_file",
        "source_description",
    ]
    write_rows(out, fields, rows)
    return out, len(rows)


def combine_intake_issued_by_country_residence() -> tuple[Path, int]:
    rows: list[dict[str, str]] = []

    received_files = [
        ("study_permit_applications_received_top10_country_residence_2022_2023apr_snapshot_2023-06-14.csv", "cimm-sp-intake-output-issued-2023-06-14"),
        ("study_permit_applications_received_top10_country_residence_2022_2024jan_snapshot_2024-02-28.csv", "cimm-international-students-intake-output-issued-2024-02-28"),
    ]
    issued_files = [
        ("study_permit_applications_issued_top10_country_residence_2022_2023apr_snapshot_2023-06-14.csv", "cimm-sp-intake-output-issued-2023-06-14"),
        ("study_permit_applications_issued_top10_country_residence_2022_2024jan_snapshot_2024-02-28.csv", "cimm-international-students-intake-output-issued-2024-02-28"),
    ]

    def add_measure(row: dict[str, str], filename: str, source_id: str, measure_type: str, value: str, grand_total: str = "") -> None:
        period_key, period_type, year, month = parse_period(row["period_label"])
        rows.append(
            {
                "destination_country": "Canada",
                "origin_country_type": "country_of_residence",
                "country_of_residence": row["country_of_residence"],
                "country_coverage": country_coverage(row["country_of_residence"], filename),
                "period_label": row["period_label"],
                "period_key": period_key,
                "period_type": period_type,
                "year": year,
                "month": month,
                "measure_type": measure_type,
                "measure_value": clean_number(value),
                "grand_total": clean_number(grand_total),
                "source_snapshot": row["source_snapshot"],
                "source_id": source_id,
                "source_file": filename,
            }
        )

    for filename, source_id in received_files:
        for row in read_rows(SRC / filename):
            add_measure(row, filename, source_id, "applications_received", row["applications_received"])

    for filename, source_id in issued_files:
        for row in read_rows(SRC / filename):
            add_measure(row, filename, source_id, "issued_authorized", row["authorized"], row.get("grand_total", ""))
            add_measure(row, filename, source_id, "issued_confirmed", row["confirmed"], row.get("grand_total", ""))
            add_measure(row, filename, source_id, "issued_total", row["total"], row.get("grand_total", ""))

    out = OUT / "study_permit_intake_issued_by_country_residence.csv"
    fields = [
        "destination_country",
        "origin_country_type",
        "country_of_residence",
        "country_coverage",
        "period_label",
        "period_key",
        "period_type",
        "year",
        "month",
        "measure_type",
        "measure_value",
        "grand_total",
        "source_snapshot",
        "source_id",
        "source_file",
    ]
    write_rows(out, fields, rows)
    return out, len(rows)


def combine_volumes_by_citizenship() -> tuple[Path, int]:
    rows: list[dict[str, str]] = []

    monthly_file = "study_permit_holders_by_citizenship_monthly.csv"
    for row in read_rows(SRC / monthly_file):
        rows.append(
            {
                "destination_country": "Canada",
                "origin_country_type": "citizenship",
                "country_of_citizenship": row["en_country_of_citizenship"],
                "country_of_citizenship_fr": row["fr_pays_de_citoyennete"],
                "year": row["en_year"],
                "quarter": row["en_quarter"],
                "month": row["en_month"],
                "period_type": "month",
                "measure_type": "study_permit_holders_monthly",
                "measure_value": clean_number(row["total"]),
                "source_file": monthly_file,
            }
        )

    effective_file = "study_permit_holders_by_citizenship_permits_effective_2015_2026q1.csv"
    for row in read_rows(SRC / effective_file):
        rows.append(
            {
                "destination_country": "Canada",
                "origin_country_type": "citizenship",
                "country_of_citizenship": row["country_of_citizenship"],
                "country_of_citizenship_fr": "",
                "year": row["year"],
                "quarter": row["quarter"],
                "month": row["month"],
                "period_type": row["period_type"],
                "measure_type": "permits_effective",
                "measure_value": clean_number(row["total"]),
                "source_file": effective_file,
            }
        )

    out = OUT / "study_permit_volumes_by_citizenship.csv"
    fields = [
        "destination_country",
        "origin_country_type",
        "country_of_citizenship",
        "country_of_citizenship_fr",
        "year",
        "quarter",
        "month",
        "period_type",
        "measure_type",
        "measure_value",
        "source_file",
    ]
    write_rows(out, fields, rows)
    return out, len(rows)


def main() -> None:
    results = [
        combine_outcomes_by_country_residence(),
        combine_intake_issued_by_country_residence(),
        combine_volumes_by_citizenship(),
    ]
    for path, count in results:
        print(f"{path.relative_to(ROOT)}: {count} rows")


if __name__ == "__main__":
    main()
