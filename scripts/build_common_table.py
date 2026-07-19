#!/usr/bin/env python3
"""Build one common long table across all extracted student visa sources."""

from __future__ import annotations

import csv
from pathlib import Path

from country_normalization import normalize_country


ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "csv"
PROCESSED = ROOT / "tmp" / "processed"
OUT = ROOT / "data" / "student_visa_common_long.csv"

FIELDS = [
    "destination_country",
    "origin_country",
    "un_m49_country",
    "normalization_status",
    "origin_country_type",
    "period_label",
    "period_type",
    "calendar_year",
    "financial_year",
    "quarter",
    "month",
    "visa_category",
    "visa_category_source",
    "applicant_location",
    "lodgement_channel",
    "applicant_type",
    "education_sector",
    "education_level",
    "gender",
    "age_group",
    "provider_state",
    "last_visa_held",
    "measure_type",
    "measure_value",
    "measure_unit",
    "rate_denominator_type",
    "coverage_type",
    "source_snapshot",
    "source_file",
    "source_notes",
]

def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def clean_number(value: str) -> str:
    value = (value or "").strip()
    if value in {"", "--"}:
        return ""
    return value.replace(",", "").replace("%", "")


def base_row(destination: str, source_file: str, **kwargs) -> dict[str, str]:
    row = {field: "" for field in FIELDS}
    row["destination_country"] = destination
    row["source_file"] = source_file
    row.update({k: str(v) for k, v in kwargs.items() if k in row and v is not None})
    if not row["normalization_status"]:
        normalized = normalize_country(row["origin_country"], destination)
        row["un_m49_country"] = normalized.country
        row["normalization_status"] = normalized.status
    return row


def emit_measure(writer: csv.DictWriter, row: dict[str, str], measure_type: str, value: str, unit: str = "count", denominator: str = "") -> int:
    value = clean_number(value)
    if value == "":
        return 0
    out = row.copy()
    out["measure_type"] = measure_type
    out["measure_value"] = value
    out["measure_unit"] = unit
    out["rate_denominator_type"] = denominator
    writer.writerow(out)
    return 1


def add_new_zealand(writer: csv.DictWriter) -> int:
    count = 0
    for path in sorted((CSV / "new-zealand").glob("student_visa_decisions_*.csv")):
        for r in read_csv(path):
            row = base_row(
                "New Zealand",
                path.relative_to(ROOT).as_posix(),
                origin_country=r["country_territory_special_administrative_region"],
                origin_country_type="country_or_territory",
                period_label=r["year"],
                period_type="calendar_year",
                calendar_year=r["year"],
                visa_category="student visa",
                visa_category_source="INZ offshore/overseas student visa decision table",
                applicant_location="outside_destination",
                coverage_type="all_reported_countries",
                source_notes="2022 lacks explicit application volume and approval rate in the visible source table.",
            )
            count += emit_measure(writer, row, "applications_completed", r.get("volume_of_visa_applications", ""))
            count += emit_measure(writer, row, "approvals", r.get("number_approved", ""))
            count += emit_measure(writer, row, "declines", r.get("number_declined", ""))
            count += emit_measure(writer, row, "approval_rate", r.get("approval_rate", ""), "percent", "source_reported")
            count += emit_measure(writer, row, "decline_rate", r.get("decline_rate", ""), "percent", "source_reported")
    return count


def add_australia(writer: csv.DictWriter) -> int:
    count = 0
    lodged = CSV / "australia" / "student_visas_lodged_2005_2026-02-28.csv"
    for r in read_csv(lodged):
        if r["applicant_type"] != "Primary":
            continue
        row = base_row(
            "Australia",
            lodged.relative_to(ROOT).as_posix(),
            origin_country=r["citizenship_country"],
            origin_country_type="citizenship",
            period_label=" ".join(x for x in [r["financial_year_of_visa_lodged"], r["financial_year_quarter"], r["month"]] if x),
            period_type="financial_month",
            financial_year=r["financial_year_of_visa_lodged"],
            quarter=r["financial_year_quarter"],
            month=r["month"],
            visa_category="student visa",
            visa_category_source="subclass 500 and legacy student subclasses",
            applicant_location=r["client_location"],
            lodgement_channel=r["lodgement_channel"],
            applicant_type=r["applicant_type"],
            education_sector=r["sector"],
            gender=r["gender"],
            age_group=r["age_group"],
            provider_state=r["education_provider_registered_state"],
            coverage_type="pivot_cache_records",
            source_snapshot="2026-04-30",
            source_notes="Local raw/work CSV filename says 2026-02-28, but official package metadata and pivot-cache period identify this as the 2026-04-30 snapshot.",
        )
        count += emit_measure(writer, row, "applications_lodged", r["total"])

    granted = CSV / "australia" / "student_visas_granted_2005_2026-02-28.csv"
    for r in read_csv(granted):
        if r["applicant_type"] != "Primary":
            continue
        row = base_row(
            "Australia",
            granted.relative_to(ROOT).as_posix(),
            origin_country=r["citizenship_country"],
            origin_country_type="citizenship",
            period_label=" ".join(x for x in [r["financial_year_of_visa_grant"], r["financial_year_quarter"], r["month"]] if x),
            period_type="financial_month",
            financial_year=r["financial_year_of_visa_grant"],
            quarter=r["financial_year_quarter"],
            month=r["month"],
            visa_category="student visa",
            visa_category_source="subclass 500 and legacy student subclasses",
            applicant_location=r["client_location"],
            lodgement_channel=r["lodgement_channel"],
            applicant_type=r["applicant_type"],
            education_sector=r["sector"],
            gender=r["gender"],
            age_group=r["age_group"],
            provider_state=r["education_provider_registered_state"],
            last_visa_held=r.get("last_visa_held_visa_category", ""),
            coverage_type="pivot_cache_records",
            source_snapshot="2026-04-30",
            source_notes="Local raw/work CSV filename says 2026-02-28, but official package metadata and pivot-cache period identify this as the 2026-04-30 snapshot.",
        )
        count += emit_measure(writer, row, "grants", r["total"])

    rates = CSV / "australia" / "student_visa_grant_rates_2005_2026-02-28.csv"
    for r in read_csv(rates):
        if r["applicant_type"] != "Primary":
            continue
        row = base_row(
            "Australia",
            rates.relative_to(ROOT).as_posix(),
            origin_country=r["citizenship_country"],
            origin_country_type="citizenship",
            period_label=" ".join(x for x in [r["financial_year_of_decision"], r["financial_year_quarter"], r["month"]] if x),
            period_type="financial_month",
            financial_year=r["financial_year_of_decision"],
            quarter=r["financial_year_quarter"],
            month=r["month"],
            visa_category="student visa",
            visa_category_source="subclass 500 and legacy student subclasses",
            applicant_location=r["client_location"],
            lodgement_channel=r["lodgement_channel"],
            applicant_type=r["applicant_type"],
            education_sector=r["sector"],
            gender=r["gender"],
            age_group=r["age_group"],
            provider_state=r["education_provider_registered_state"],
            coverage_type="pivot_cache_records",
            source_snapshot="2026-04-30",
            source_notes="Local raw/work CSV filename says 2026-02-28, but official package metadata and pivot-cache period identify this as the 2026-04-30 snapshot.",
        )
        count += emit_measure(writer, row, "grants", r["grant_total"])
        count += emit_measure(writer, row, "refusals", r["refused_total"])
        count += emit_measure(writer, row, "decisions", r["total"])
        rate = str(float(r["computed_grant_rate"]) * 100) if r.get("computed_grant_rate") else ""
        count += emit_measure(writer, row, "grant_rate", rate, "percent", "grants_plus_refusals")
    return count


def add_united_kingdom(writer: csv.DictWriter) -> int:
    count = 0
    apps = CSV / "united-kingdom" / "entry_clearance_visa_applications_2005_2026q1.csv"
    for r in read_csv(apps):
        if r["applicant_type"] != "Main Applicant":
            continue
        row = base_row(
            "United Kingdom",
            apps.relative_to(ROOT).as_posix(),
            origin_country=r["nationality"],
            origin_country_type="nationality",
            period_label=r["quarter"],
            period_type="calendar_quarter",
            calendar_year=r["year"],
            quarter=r["quarter"],
            visa_category=r["visa_type_group"],
            visa_category_source="entry clearance visa type group",
            applicant_type=r["applicant_type"],
            coverage_type="all_entry_clearance_categories",
            source_notes=f"region={r['region']}; visa_type={r['visa_type']}; visa_type_subgroup={r['visa_type_subgroup']}",
        )
        count += emit_measure(writer, row, "applications", r["applications"])

    outcomes = CSV / "united-kingdom" / "entry_clearance_visa_outcomes_2005_2026q1.csv"
    for r in read_csv(outcomes):
        if r["applicant_type"] != "Main Applicant":
            continue
        outcome = r["case_outcome"].strip().lower().replace(" ", "_")
        row = base_row(
            "United Kingdom",
            outcomes.relative_to(ROOT).as_posix(),
            origin_country=r["nationality"],
            origin_country_type="nationality",
            period_label=r["quarter"],
            period_type="calendar_quarter",
            calendar_year=r["year"],
            quarter=r["quarter"],
            visa_category=r["visa_type_group"],
            visa_category_source="entry clearance visa type group",
            applicant_type=r["applicant_type"],
            coverage_type="all_entry_clearance_categories",
            source_notes=f"region={r['region']}; visa_type={r['visa_type']}; visa_type_subgroup={r['visa_type_subgroup']}; case_outcome={r['case_outcome']}",
        )
        count += emit_measure(writer, row, f"decisions_{outcome}", r["decisions"])

    edu_apps = CSV / "united-kingdom" / "sponsored_study_applications_by_course_level_2018_2026q1.csv"
    for r in read_csv(edu_apps):
        row = base_row(
            "United Kingdom",
            edu_apps.relative_to(ROOT).as_posix(),
            origin_country=r["nationality"],
            origin_country_type="nationality",
            period_label=r["quarter"],
            period_type="calendar_quarter",
            calendar_year=r["year"],
            quarter=r["quarter"],
            visa_category="Study",
            visa_category_source=r["visa_type_subgroup"],
            education_level=r["course_level"],
            applicant_type="main_applicant_only",
            coverage_type="cas_matched_course_level",
            source_notes=f"region={r['region']}; excludes CAS-unmatched records",
        )
        count += emit_measure(writer, row, "applications", r["applications"])

    edu_grants = CSV / "united-kingdom" / "sponsored_study_grants_by_course_level_2018_2026q1.csv"
    for r in read_csv(edu_grants):
        row = base_row(
            "United Kingdom",
            edu_grants.relative_to(ROOT).as_posix(),
            origin_country=r["nationality"],
            origin_country_type="nationality",
            period_label=r["quarter"],
            period_type="calendar_quarter",
            calendar_year=r["year"],
            quarter=r["quarter"],
            visa_category="Study",
            visa_category_source=r["visa_type_subgroup"],
            education_level=r["course_level"],
            applicant_type="main_applicant_only",
            coverage_type="cas_matched_course_level",
            source_notes=f"region={r['region']}; excludes CAS-unmatched records",
        )
        count += emit_measure(writer, row, "grants", r["grants"])
    return count


def add_canada(writer: csv.DictWriter) -> int:
    count = 0
    outcomes = PROCESSED / "canada" / "study_permit_outcomes_by_country_residence.csv"
    for r in read_csv(outcomes):
        row = base_row(
            "Canada",
            f"data/csv/canada/{r['source_file']}",
            origin_country=r["country_of_residence"],
            origin_country_type="country_of_residence",
            period_label=r["period_label"],
            period_type=r["period_type"],
            calendar_year=r["year"],
            month=r["month"],
            visa_category="study permit",
            visa_category_source="study permit excluding extensions where specified",
            coverage_type=r["coverage_type"],
            source_snapshot=r["source_snapshot"],
            source_notes=f"country_coverage={r['country_coverage']}; source_id={r['source_id']}; {r['source_description']}",
        )
        count += emit_measure(writer, row, "approvals", r["approved"])
        count += emit_measure(writer, row, "refusals", r["refused"])
        count += emit_measure(writer, row, "withdrawals", r["withdrawn"])
        count += emit_measure(writer, row, "approval_rate", r["approval_rate_percent"], "percent", "source_reported")
        count += emit_measure(writer, row, "processed_applications", r["total"])

    intake = PROCESSED / "canada" / "study_permit_intake_issued_by_country_residence.csv"
    for r in read_csv(intake):
        row = base_row(
            "Canada",
            f"data/csv/canada/{r['source_file']}",
            origin_country=r["country_of_residence"],
            origin_country_type="country_of_residence",
            period_label=r["period_label"],
            period_type=r["period_type"],
            calendar_year=r["year"],
            month=r["month"],
            visa_category="study permit",
            visa_category_source="CIMM intake/output/issued tables",
            coverage_type=r["country_coverage"],
            source_snapshot=r["source_snapshot"],
            source_notes=f"source_id={r['source_id']}; grand_total={r['grand_total']}",
        )
        count += emit_measure(writer, row, r["measure_type"], r["measure_value"])

    volumes = PROCESSED / "canada" / "study_permit_volumes_by_citizenship.csv"
    for r in read_csv(volumes):
        row = base_row(
            "Canada",
            f"data/csv/canada/{r['source_file']}",
            origin_country=r["country_of_citizenship"],
            origin_country_type="citizenship",
            period_label=" ".join(x for x in [r["year"], r["quarter"], r["month"]] if x),
            period_type=r["period_type"],
            calendar_year=r["year"],
            quarter=r["quarter"],
            month=r["month"],
            visa_category="study permit",
            visa_category_source="IRCC/Open Canada permit holder dataset",
            coverage_type="all_reported_citizenships",
            source_notes=f"country_of_citizenship_fr={r['country_of_citizenship_fr']}",
        )
        count += emit_measure(writer, row, r["measure_type"], r["measure_value"])

    aggregate_received = CSV / "canada" / "study_permit_applications_received_aggregate_2023_2024sep_snapshot_2024-11-04.csv"
    for r in read_csv(aggregate_received):
        row = base_row(
            "Canada",
            aggregate_received.relative_to(ROOT).as_posix(),
            period_label=r["period_label"],
            period_type="source_period",
            visa_category=r["application_type"],
            visa_category_source="OLLO aggregate table",
            coverage_type="aggregate",
            source_snapshot=r["source_snapshot"],
        )
        count += emit_measure(writer, row, "applications_received", r["applications_received"])

    aggregate_processed = CSV / "canada" / "study_permit_applications_processed_aggregate_2023_2024sep_snapshot_2024-11-04.csv"
    for r in read_csv(aggregate_processed):
        row = base_row(
            "Canada",
            aggregate_processed.relative_to(ROOT).as_posix(),
            period_label=r["period_label"],
            period_type="source_period",
            visa_category=r["application_type"],
            visa_category_source="OLLO aggregate table",
            coverage_type="aggregate",
            source_snapshot=r["source_snapshot"],
            source_notes=f"outcome={r['outcome']}",
        )
        count += emit_measure(writer, row, f"{r['outcome'].strip().lower()}_count", r["outcome_count"])
        count += emit_measure(writer, row, f"{r['outcome'].strip().lower()}_percent", r["outcome_percent"], "percent", "processed_applications")

    language_rates = CSV / "canada" / "study_permit_approval_rates_by_official_language_destination_2020_2024sep_snapshot_2024-11-04.csv"
    for r in read_csv(language_rates):
        row = base_row(
            "Canada",
            language_rates.relative_to(ROOT).as_posix(),
            period_label=r["period_label"],
            period_type="calendar_year_or_partial",
            calendar_year=r["period_label"][:4],
            visa_category="study permit",
            visa_category_source="OLLO official language/destination table",
            coverage_type="official_language_destination_group",
            source_snapshot=r["source_snapshot"],
            source_notes=f"official_language={r['official_language']}; destination_region={r['destination_region']}",
        )
        count += emit_measure(writer, row, "approval_rate", r["approval_rate"], "percent", "approved_plus_refused")
    return count


def add_united_states(writer: csv.DictWriter) -> int:
    count = 0
    source = CSV / "united-states" / "us_niv_student_issuances_by_nationality_fy1997_2024.csv"
    if not source.exists():
        return count
    category = {
        "F1": ("student visa", "primary"),
        "M1": ("vocational student visa", "primary"),
    }
    for r in read_csv(source):
        if r["visa_class"] not in category:
            continue
        visa_category, applicant_type = category[r["visa_class"]]
        row = base_row(
            "United States",
            source.relative_to(ROOT).as_posix(),
            origin_country=r["nationality"],
            origin_country_type="nationality",
            period_label=f"FY{r['fiscal_year']}",
            period_type="fiscal_year",
            financial_year=r["fiscal_year"],
            visa_category=visa_category,
            visa_category_source=r["visa_class"],
            applicant_type=applicant_type,
            coverage_type="visa_issuances_by_class_and_nationality",
            source_notes="US official source provides visa issuances by nationality and class; nationality-level applications/refusals were not found in the public source.",
        )
        count += emit_measure(writer, row, "issuances", r["issued"])
    return count


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for name, fn in [
            ("new-zealand", add_new_zealand),
            ("australia", add_australia),
            ("united-kingdom", add_united_kingdom),
            ("canada", add_canada),
            ("united-states", add_united_states),
        ]:
            count = fn(writer)
            total += count
            print(f"{name}: {count} measure rows")
    print(f"{OUT.relative_to(ROOT)}: {total} measure rows")


if __name__ == "__main__":
    main()
