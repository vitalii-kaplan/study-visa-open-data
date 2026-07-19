#!/usr/bin/env python3
"""Validate reference data, common CSVs, Australian measures, and SQLite."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from country_normalization import ALLOWED_STATUSES, NORMALIZER, normalize_country


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
COMMON = DATA / "student_visa_common_long.csv"
DB = DATA / "student_visa.sqlite"
TABLE = "student_visa_common_long"
AUDIT = ROOT / "log" / "unmatched_origin_labels.csv"
REFERENCE = DATA / "UNSD — Methodology.csv"
EXPECTED_COUNTRY_COUNT = 248
REFERENCE_FIELDS = {
    "Country or Area",
    "M49 Code",
    "Region Name",
    "Sub-region Name",
    "Intermediate Region Name",
    "ISO-alpha2 Code",
    "ISO-alpha3 Code",
}


def validate_reference() -> None:
    with REFERENCE.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if not REFERENCE_FIELDS.issubset(reader.fieldnames or []):
            raise AssertionError(f"{REFERENCE} does not have the required M49 reference fields")
        rows = list(reader)
    if len(rows) != EXPECTED_COUNTRY_COUNT:
        raise AssertionError(f"expected {EXPECTED_COUNTRY_COUNT} UN M49 countries/areas")
    names = [row["Country or Area"].strip() for row in rows]
    if len(set(names)) != EXPECTED_COUNTRY_COUNT or any(not name for name in names):
        raise AssertionError("UN M49 reference country/area names must be non-empty and unique")
    for row in rows:
        code = row["M49 Code"].strip()
        if len(code) != 3 or not code.isdigit():
            raise AssertionError(f"invalid M49 code for {row['Country or Area']!r}: {code!r}")


def validate_csv_mapping(path: Path) -> dict[tuple[str, str], tuple[str, str]]:
    mappings: dict[tuple[str, str], tuple[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        indexes = [
            header.index(name)
            for name in (
                "destination_country",
                "origin_country",
                "un_m49_country",
                "normalization_status",
                "applicant_type",
                "visa_category_source",
            )
        ]
        for row in reader:
            destination, origin, country, status, applicant_type, category_source = (
                row[index] for index in indexes
            )
            if applicant_type in {"Secondary", "Dependant", "dependent", "All"}:
                raise AssertionError(f"explicit dependant or mixed applicant row remains in {path}")
            if category_source in {"F2", "M2"}:
                raise AssertionError(f"dependent US visa class remains in {path}")
            key = (destination, origin)
            value = (country, status)
            previous = mappings.get(key)
            if previous is not None and previous != value:
                raise AssertionError(f"inconsistent mapping in {path}: {key}")
            if previous is None:
                expected = normalize_country(*reversed(key))
                expected_value = (expected.country, expected.status)
                if value != expected_value:
                    raise AssertionError(
                        f"normalization mismatch in {path}: {key} -> {value}, expected {expected_value}"
                    )
                mappings[key] = value
    return mappings


def validate_artifact_consistency() -> dict[tuple[str, str], tuple[str, str]]:
    return validate_csv_mapping(COMMON)


def integer_count(value: str) -> bool:
    try:
        return int(value) >= 0 and str(int(value)) == value
    except ValueError:
        return False


def validate_australia_sources() -> None:
    files = [
        DATA / "csv" / "australia" / "student_visas_lodged_2005_2026-02-28.csv",
        DATA / "csv" / "australia" / "student_visas_granted_2005_2026-02-28.csv",
        DATA / "csv" / "australia" / "student_visa_grant_rates_2005_2026-02-28.csv",
    ]
    for path in files:
        with path.open(newline="", encoding="utf-8") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), 2):
                count_fields = [name for name in ("total", "grant_total", "refused_total") if name in row]
                for name in count_fields:
                    if not integer_count(row[name]):
                        raise AssertionError(f"{path}:{line_number}: invalid non-negative integer {name}={row[name]!r}")
                if "grant_total" in row:
                    if int(row["grant_total"]) + int(row["refused_total"]) != int(row["total"]):
                        raise AssertionError(f"{path}:{line_number}: grants + refusals != decisions")

    # The reported collision slice is unique once both omitted source dimensions are retained.
    for path in files:
        seen: set[tuple[str, ...]] = set()
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            dimension_fields = [
                name for name in reader.fieldnames or []
                if name not in {"total", "grant_total", "refused_total", "computed_grant_rate"}
            ]
            for row in reader:
                if row.get("sector") != "Higher Education Sector" or row.get("applicant_type") != "Primary":
                    continue
                key = tuple(row[name] for name in dimension_fields)
                if key in seen:
                    raise AssertionError(f"{path}: duplicate full pivot-cache dimensional key")
                seen.add(key)


def write_unmatched_audit(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        f"""
        SELECT destination_country, origin_country, origin_country_type, source_file,
               COUNT(*) AS row_count, MIN(period_label), MAX(period_label)
        FROM {TABLE}
        WHERE normalization_status = 'unmatched'
        GROUP BY destination_country, origin_country, origin_country_type, source_file
        ORDER BY destination_country, row_count DESC, origin_country
        """
    ).fetchall()
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "destination_country",
                "origin_country",
                "origin_country_type",
                "source_file",
                "row_count",
                "first_period",
                "last_period",
            ]
        )
        writer.writerows(rows)
    return len(rows)


def validate_sqlite(common_mappings: dict[tuple[str, str], tuple[str, str]]) -> None:
    conn = sqlite3.connect(DB)
    try:
        expected_mappings = dict(common_mappings)
        sqlite_only = ROOT / "tmp" / "processed" / "canada" / "study_permit_french_bilingual_common_long_sqlite_only.csv"
        expected_mappings.update(validate_csv_mapping(sqlite_only))
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
        required = {"un_m49_country", "normalization_status", "lodgement_channel", "last_visa_held"}
        if not required.issubset(columns):
            raise AssertionError(f"SQLite is missing columns: {sorted(required - columns)}")
        statuses = {row[0] for row in conn.execute(f"SELECT DISTINCT normalization_status FROM {TABLE}")}
        if not statuses <= ALLOWED_STATUSES:
            raise AssertionError(f"unexpected normalization statuses: {sorted(statuses - ALLOWED_STATUSES)}")
        bad_non_countries, bad_units, missing_sources, invalid_counts, invalid_rates = conn.execute(
            f"""
            SELECT
              SUM(CASE WHEN normalization_status IN ('aggregate','unknown','unmatched') AND un_m49_country IS NOT NULL THEN 1 ELSE 0 END),
              SUM(CASE WHEN measure_unit NOT IN ('count','percent') OR measure_unit IS NULL THEN 1 ELSE 0 END),
              SUM(CASE WHEN source_file IS NULL OR source_file = '' THEN 1 ELSE 0 END),
              SUM(CASE WHEN measure_unit = 'count' AND (measure_value IS NULL OR measure_value = '' OR measure_value GLOB '*[^0-9]*') THEN 1 ELSE 0 END),
              SUM(CASE WHEN measure_unit = 'percent' AND (CAST(measure_value AS REAL) < 0 OR CAST(measure_value AS REAL) > 100) THEN 1 ELSE 0 END)
            FROM {TABLE}
            """
        ).fetchone()
        if bad_non_countries:
            raise AssertionError(f"{bad_non_countries} non-country rows have a canonical UN M49 country")
        if bad_units:
            raise AssertionError(f"{bad_units} rows have an invalid measure unit")
        if missing_sources:
            raise AssertionError(f"{missing_sources} rows lack source_file metadata")
        if invalid_counts:
            raise AssertionError(f"{invalid_counts} count rows are not non-negative integers")
        if invalid_rates:
            raise AssertionError(f"{invalid_rates} percentage rows are outside 0..100")
        dependant_rows = conn.execute(
            f"""
            SELECT COUNT(*) FROM {TABLE}
            WHERE applicant_type IN ('Secondary', 'Dependant', 'dependent', 'All')
               OR visa_category_source IN ('F2', 'M2')
            """
        ).fetchone()[0]
        if dependant_rows:
            raise AssertionError(f"{dependant_rows} explicit dependant or mixed applicant rows remain in SQLite")

        conn.execute(
            "CREATE TEMP TABLE expected_normalization ("
            "destination_country TEXT NOT NULL, origin_country TEXT NOT NULL, "
            "un_m49_country TEXT NOT NULL, normalization_status TEXT NOT NULL, "
            "PRIMARY KEY (destination_country, origin_country)) WITHOUT ROWID"
        )
        conn.executemany(
            "INSERT INTO expected_normalization VALUES (?, ?, ?, ?)",
            (
                (destination, origin, country, status)
                for (destination, origin), (country, status) in expected_mappings.items()
            ),
        )
        uncovered = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE} AS s LEFT JOIN expected_normalization AS e "
            "ON s.destination_country = e.destination_country AND s.origin_country = e.origin_country "
            "WHERE e.destination_country IS NULL"
        ).fetchone()[0]
        if uncovered:
            raise AssertionError(f"{uncovered} SQLite rows have no mapping represented in generated CSV artifacts")
        mapping_mismatches = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE} AS s JOIN expected_normalization AS e "
            "ON s.destination_country = e.destination_country AND s.origin_country = e.origin_country "
            "WHERE COALESCE(s.un_m49_country, '') <> e.un_m49_country "
            "OR s.normalization_status <> e.normalization_status"
        ).fetchone()[0]
        if mapping_mismatches:
            raise AssertionError(f"{mapping_mismatches} SQLite rows disagree with generated CSV normalization")

        canonical = NORMALIZER.canonical_names
        exact_unmatched = [
            origin for (origin,) in conn.execute(
                f"SELECT DISTINCT origin_country FROM {TABLE} WHERE normalization_status = 'unmatched'"
            ) if origin in canonical
        ]
        if exact_unmatched:
            raise AssertionError(f"exact UN M49 names remain unmatched: {exact_unmatched}")
        audit_rows = write_unmatched_audit(conn)
        print(f"{AUDIT.relative_to(ROOT)}: {audit_rows} unmatched label/source groups")
        print(f"{DB.relative_to(ROOT)}: {conn.execute(f'SELECT COUNT(*) FROM {TABLE}').fetchone()[0]} rows validated")
    finally:
        conn.close()


def main() -> None:
    validate_reference()
    validate_australia_sources()
    mappings = validate_artifact_consistency()
    validate_sqlite(mappings)
    print("all validation checks passed")


if __name__ == "__main__":
    main()
