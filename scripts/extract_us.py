#!/usr/bin/env python3
"""Extract United States official student-visa data into project formats."""

from __future__ import annotations

import re
import zipfile
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from extract_csv import ROOT, RAW, OUT, write_csv, xlsx_rows, xlsx_sheet_paths

US_STUDENT_CLASSES = {
    "F1": ("student visa", "primary"),
    "M1": ("vocational student visa", "primary"),
}
US_REGION_ROWS = {
    "AFRICA",
    "ASIA",
    "EUROPE",
    "GRAND TOTAL",
    "NORTH AMERICA",
    "OCEANIA",
    "SOUTH AMERICA",
}


def normalize_visa_class(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def clean_count(value: str) -> str:
    value = (value or "").strip()
    if value in {"", "-", "--", "*"}:
        return ""
    value = value.replace(",", "")
    try:
        # The workbook displays count cells with an integer number format. A few
        # FY2015 formula/cache values contain fractional residues (for example
        # 136.24); reproduce the displayed official count rather than storing a
        # fractional visa.
        return str(int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
    except InvalidOperation as error:
        raise ValueError(f"invalid visa count {value!r}") from error


def fiscal_year_from_sheet(sheet: str) -> int:
    match = re.search(r"FY(\d{2})", sheet.upper())
    if not match:
        raise ValueError(f"Cannot parse fiscal year from sheet {sheet!r}")
    year = int(match.group(1))
    return 1900 + year if year >= 90 else 2000 + year


def extract_us_source_csv() -> tuple[Path, int]:
    source = RAW / "united-states" / "FYs97-24_NIVDetailTable.xlsx"
    out = OUT / "united-states" / "us_niv_student_issuances_by_nationality_fy1997_2024.csv"
    rows = []
    with zipfile.ZipFile(source) as z:
        sheets = xlsx_sheet_paths(z)
        for sheet in sorted(sheets, key=fiscal_year_from_sheet):
            fiscal_year = fiscal_year_from_sheet(sheet)
            sheet_rows = list(xlsx_rows(z, sheets[sheet]))
            if not sheet_rows:
                continue
            header = sheet_rows[0]
            class_columns = {
                idx: normalize_visa_class(name)
                for idx, name in enumerate(header)
                if normalize_visa_class(name) in US_STUDENT_CLASSES
            }
            for row in sheet_rows[1:]:
                if not row or not (row[0] or "").strip():
                    continue
                nationality = row[0].strip()
                upper_nationality = nationality.upper()
                if (
                    upper_nationality in US_REGION_ROWS
                    or upper_nationality.startswith("TOTALS FOR ")
                    or upper_nationality == "GRAND TOTALS"
                ):
                    continue
                if not any((row[idx] if idx < len(row) else "").strip() for idx in class_columns):
                    continue
                for idx, visa_class in class_columns.items():
                    value = row[idx] if idx < len(row) else ""
                    rows.append([fiscal_year, nationality, visa_class, clean_count(value)])
    header = ["fiscal_year", "nationality", "visa_class", "issued"]
    return out, write_csv(out, header, rows)


def main() -> None:
    (OUT / "united-states").mkdir(parents=True, exist_ok=True)
    path, count = extract_us_source_csv()
    print(f"{path.relative_to(ROOT)}: {count} rows")


if __name__ == "__main__":
    main()
