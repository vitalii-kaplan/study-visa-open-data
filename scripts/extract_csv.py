#!/usr/bin/env python3
"""Extract source-level CSV files from downloaded raw student visa sources."""

from __future__ import annotations

import csv
import html
import re
import unicodedata
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "original"
OUT = ROOT / "data" / "csv"
XLSX_NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def ensure_dirs() -> None:
    for country in ("new-zealand", "australia", "united-kingdom", "canada"):
        (OUT / country).mkdir(parents=True, exist_ok=True)


def slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def clean_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_cell = False
        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._in_table = True
            self._current_table = []
        elif self._in_table and tag == "tr":
            self._current_row = []
        elif self._in_table and tag in ("td", "th"):
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if self._in_table and tag in ("td", "th"):
            self._current_row.append(clean_text("".join(self._current_cell)))
            self._in_cell = False
        elif self._in_table and tag == "tr":
            if any(cell for cell in self._current_row):
                self._current_table.append(self._current_row)
        elif self._in_table and tag == "table":
            self.tables.append(self._current_table)
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)


def write_csv(path: Path, header: list[str], rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def extract_new_zealand() -> list[tuple[Path, int]]:
    mapping = [
        (2022, RAW / "new-zealand" / "offshore-student-visa-application-decisions-2022.html"),
        (2023, RAW / "new-zealand" / "offshore-student-visa-application-decisions-2023.html"),
        (2024, RAW / "new-zealand" / "overseas-student-visa-application-decisions-2024.html"),
        (2025, RAW / "new-zealand" / "overseas-student-visa-application-decisions-2025.html"),
    ]
    results = []
    for year, source in mapping:
        parser = TableParser()
        parser.feed(source.read_text(encoding="utf-8", errors="replace"))
        table = next(t for t in parser.tables if t and "Country/Territory" in t[0][0])
        headers = ["year"] + [slug(h) for h in table[0]]
        rows = ([year] + row for row in table[1:] if len(row) == len(table[0]))
        out = OUT / "new-zealand" / f"student_visa_decisions_{year}.csv"
        results.append((out, write_csv(out, headers, rows)))
    return results


def xlsx_shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.findall(".//a:t", XLSX_NS)) for si in root.findall("a:si", XLSX_NS)]


def xlsx_sheet_paths(z: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
    paths = {}
    for sheet in workbook.find("a:sheets", XLSX_NS):
        name = sheet.attrib["name"]
        rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = rid_to_target[rid]
        paths[name] = "xl/" + target if not target.startswith("/") else target[1:]
    return paths


def xlsx_cell_text(cell: ET.Element, shared: list[str]) -> str:
    if cell.attrib.get("t") == "inlineStr":
        return clean_text("".join(t.text or "" for t in cell.findall(".//a:t", XLSX_NS)))
    value = cell.find("a:v", XLSX_NS)
    if value is None:
        return ""
    text = value.text or ""
    if cell.attrib.get("t") == "s":
        return shared[int(text)] if text.isdigit() and int(text) < len(shared) else text
    return text


def col_number(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref or "")
    if not match:
        return 0
    number = 0
    for char in match.group(1):
        number = number * 26 + ord(char) - 64
    return number


def xlsx_rows(z: zipfile.ZipFile, sheet_path: str):
    shared = xlsx_shared_strings(z)
    with z.open(sheet_path) as fh:
        context = ET.iterparse(fh, events=("end",))
        for _, elem in context:
            if elem.tag.endswith("}row"):
                row = []
                last = 0
                for cell in elem.findall("a:c", XLSX_NS):
                    idx = col_number(cell.attrib.get("r", ""))
                    while last + 1 < idx:
                        row.append("")
                        last += 1
                    row.append(xlsx_cell_text(cell, shared))
                    last = idx
                yield row
                elem.clear()


def extract_xlsx_dataset_sheet(source: Path, sheet_name: str, out: Path) -> tuple[Path, int]:
    with zipfile.ZipFile(source) as z:
        sheet_path = xlsx_sheet_paths(z)[sheet_name]
        iterator = iter(xlsx_rows(z, sheet_path))
        for row in iterator:
            if row and row[0] == "Year":
                header = [slug(h) for h in row]
                break
        else:
            raise ValueError(f"No header row found in {source}:{sheet_name}")
        return out, write_csv(out, header, iterator)


def extract_united_kingdom() -> list[tuple[Path, int]]:
    sources = [
        (
            RAW / "united-kingdom" / "entry-clearance-visa-outcomes-datasets-mar-2026.xlsx",
            "Data_Vis_D01",
            "entry_clearance_visa_applications_2005_2026q1.csv",
        ),
        (
            RAW / "united-kingdom" / "entry-clearance-visa-outcomes-datasets-mar-2026.xlsx",
            "Data_Vis_D02",
            "entry_clearance_visa_outcomes_2005_2026q1.csv",
        ),
        (
            RAW / "united-kingdom" / "education-visas-datasets-mar-2026.xlsx",
            "Data_Edu_D01",
            "sponsored_study_applications_by_course_level_2018_2026q1.csv",
        ),
        (
            RAW / "united-kingdom" / "education-visas-datasets-mar-2026.xlsx",
            "Data_Edu_D02",
            "sponsored_study_grants_by_course_level_2018_2026q1.csv",
        ),
    ]
    return [
        extract_xlsx_dataset_sheet(source, sheet, OUT / "united-kingdom" / filename)
        for source, sheet, filename in sources
    ]


def pivot_cache_fields(z: zipfile.ZipFile) -> tuple[list[str], list[list[str]]]:
    definition = next(n for n in z.namelist() if n.startswith("xl/pivotCache/pivotCacheDefinition"))
    root = ET.fromstring(z.read(definition))
    fields = []
    shared_values = []
    for field in root.findall(".//a:cacheField", XLSX_NS):
        fields.append(field.attrib["name"])
        items = []
        shared = field.find("a:sharedItems", XLSX_NS)
        if shared is not None:
            for item in shared:
                tag = item.tag.split("}")[-1]
                if tag in ("s", "n", "b", "e"):
                    items.append(item.attrib.get("v", ""))
                elif tag == "m":
                    items.append("")
                else:
                    items.append(item.attrib.get("v", ""))
        shared_values.append(items)
    return fields, shared_values


def pivot_record_value(cell: ET.Element, field_index: int, shared_values: list[list[str]]) -> str:
    tag = cell.tag.split("}")[-1]
    value = cell.attrib.get("v", "")
    if tag == "x":
        items = shared_values[field_index]
        return items[int(value)] if value.isdigit() and int(value) < len(items) else value
    if tag in ("n", "s", "b", "e"):
        return value
    return ""


def extract_pivot_cache(source: Path, out: Path, computed_grant_rate: bool = False) -> tuple[Path, int]:
    with zipfile.ZipFile(source) as z:
        fields, shared_values = pivot_cache_fields(z)
        record_path = next(n for n in z.namelist() if n.startswith("xl/pivotCache/pivotCacheRecords"))
        output_fields = fields[:]
        if computed_grant_rate and "Grant Rate" in output_fields:
            output_fields.remove("Grant Rate")
        header = [slug(h) for h in output_fields]
        if computed_grant_rate:
            header.append("computed_grant_rate")
        out.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with out.open("w", newline="", encoding="utf-8") as csv_file, z.open(record_path) as xml_file:
            writer = csv.writer(csv_file)
            writer.writerow(header)
            context = ET.iterparse(xml_file, events=("end",))
            for _, elem in context:
                if not elem.tag.endswith("}r"):
                    continue
                row = []
                for idx, cell in enumerate(list(elem)):
                    if idx >= len(fields):
                        continue
                    if computed_grant_rate and fields[idx] == "Grant Rate":
                        continue
                    row.append(pivot_record_value(cell, idx, shared_values))
                while len(row) < len(output_fields):
                    row.append("")
                if computed_grant_rate:
                    try:
                        grant_total = float(row[output_fields.index("Grant Total")] or 0)
                        total = float(row[output_fields.index("Total")] or 0)
                        row.append(str(grant_total / total) if total else "0")
                    except (ValueError, IndexError):
                        row.append("")
                writer.writerow(row)
                count += 1
                elem.clear()
        return out, count


def extract_australia() -> list[tuple[Path, int]]:
    sources = [
        (
            RAW / "australia" / "bp0015l-student-visas-lodged-report-locked-at-2026-02-28-v100.xlsx",
            OUT / "australia" / "student_visas_lodged_2005_2026-02-28.csv",
            False,
        ),
        (
            RAW / "australia" / "bp0015l-student-visas-granted-report-locked-at-2026-02-28-v100.xlsx",
            OUT / "australia" / "student_visas_granted_2005_2026-02-28.csv",
            False,
        ),
        (
            RAW / "australia" / "bp0015l-student-visa-grant-rates-locked-at-2026-02-28-v100.xlsx",
            OUT / "australia" / "student_visa_grant_rates_2005_2026-02-28.csv",
            True,
        ),
    ]
    return [extract_pivot_cache(source, out, has_rate) for source, out, has_rate in sources]


def extract_canada_tab_csv() -> tuple[Path, int]:
    source = RAW / "canada" / "ODP-TR-Study-IS_CITZ.csv"
    out = OUT / "canada" / "study_permit_holders_by_citizenship_monthly.csv"
    with source.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter="\t")
        raw_header = next(reader)
        header = [slug(h) for h in raw_header]
        return out, write_csv(out, header, reader)


def fill_forward(values: list[str]) -> list[str]:
    filled = []
    current = ""
    for value in values:
        if value:
            current = value
        filled.append(current)
    return filled


def extract_canada_wide_xlsx() -> tuple[Path, int]:
    source = RAW / "canada" / "EN_ODP-TR-Study-IS_CITZ_sign_date.xlsx"
    out = OUT / "canada" / "study_permit_holders_by_citizenship_permits_effective_2015_2026q1.csv"
    with zipfile.ZipFile(source) as z:
        sheet_path = xlsx_sheet_paths(z)["TR - SP CITZ"]
        rows = list(xlsx_rows(z, sheet_path))
    years = fill_forward(rows[2])
    quarters = fill_forward(rows[3])
    months = rows[4]
    output_rows = []
    for row in rows[5:]:
        if not row or not row[0]:
            continue
        country = row[0]
        for idx, value in enumerate(row[1:], start=1):
            if not value:
                continue
            month = months[idx] if idx < len(months) else ""
            year = years[idx] if idx < len(years) else ""
            quarter = quarters[idx] if idx < len(quarters) else ""
            if not year or not month:
                continue
            period_type = "quarter_total" if "Total" in month else "month"
            output_rows.append([country, year, quarter, month, period_type, value])
    header = ["country_of_citizenship", "year", "quarter", "month", "period_type", "total"]
    return out, write_csv(out, header, output_rows)


def extract_canada() -> list[tuple[Path, int]]:
    results = [
        extract_canada_tab_csv(),
        extract_canada_wide_xlsx(),
        extract_canada_cimm_approval_rates_2019_2022jan(),
        extract_canada_cimm_2024_received_top10(),
        extract_canada_cimm_2024_issued_top10(),
        extract_canada_cimm_2024_outcomes_top10(),
        extract_canada_cimm_2023_received_top10(),
        extract_canada_cimm_2023_issued_top10(),
        extract_canada_cimm_2023_outcomes_top10(),
        extract_canada_ollo_2024_intake_aggregate(),
        extract_canada_ollo_2024_processed_aggregate(),
        extract_canada_ollo_2024_language_destination_rates(),
    ]
    return results


def html_tables(source: Path) -> list[list[list[str]]]:
    parser = TableParser()
    parser.feed(source.read_text(encoding="utf-8", errors="replace"))
    return parser.tables


def extract_canada_cimm_approval_rates_2019_2022jan() -> tuple[Path, int]:
    source = RAW / "canada" / "cimm-student-approval-rates-country-residence-2019-2022-jan.html"
    out = OUT / "canada" / "study_permit_approval_rates_by_country_residence_2019_2022jan.csv"
    tables = html_tables(source)
    periods = [
        ("2019", "2019", "calendar_year"),
        ("2020", "2020", "calendar_year"),
        ("2021", "2021", "calendar_year"),
        ("2022-01", "Jan-2022", "partial_month"),
    ]
    rows = []
    for table, (year, period_label, period_type) in zip(tables[:4], periods):
        for row in table[1:]:
            if len(row) < 5:
                continue
            rows.append([year, period_label, period_type, row[0], row[1], row[3], "", row[2], row[4]])
    header = [
        "year",
        "period_label",
        "period_type",
        "country_of_residence",
        "approved",
        "refused",
        "withdrawn",
        "approval_rate",
        "total",
    ]
    return out, write_csv(out, header, rows)


def canada_top10_received_rows(tables: list[list[list[str]]], table_index: int, source_snapshot: str):
    table = tables[table_index]
    periods = table[0][1:]
    for row in table[1:]:
        if len(row) < 2:
            continue
        country = row[0]
        for period, value in zip(periods, row[1:]):
            yield [source_snapshot, country, period, value]


def canada_top10_issued_rows(tables: list[list[list[str]]], table_specs, source_snapshot: str):
    for table_index, period_label, has_grand_total in table_specs:
        table = tables[table_index]
        for row in table[2:]:
            if len(row) < 4:
                continue
            base = [source_snapshot, row[0], period_label, row[1], row[2], row[3]]
            if has_grand_total and len(row) > 4:
                base.append(row[4])
            else:
                base.append("")
            yield base


def canada_top10_outcome_rows(tables: list[list[list[str]]], table_specs, source_snapshot: str):
    for table_index, period_label, has_grand_total, order in table_specs:
        table = tables[table_index]
        for row in table[2:]:
            if len(row) < 6:
                continue
            values = dict(zip(order, row[1:]))
            yield [
                source_snapshot,
                row[0],
                period_label,
                values.get("approved", ""),
                values.get("refused", ""),
                values.get("withdrawn", ""),
                values.get("approval_rate", ""),
                values.get("total", ""),
                values.get("grand_total", "") if has_grand_total else "",
            ]


def extract_canada_cimm_2024_received_top10() -> tuple[Path, int]:
    source = RAW / "canada" / "cimm-international-students-intake-output-issued-2024-02-28.html"
    out = OUT / "canada" / "study_permit_applications_received_top10_country_residence_2022_2024jan_snapshot_2024-02-28.csv"
    header = ["source_snapshot", "country_of_residence", "period_label", "applications_received"]
    return out, write_csv(out, header, canada_top10_received_rows(html_tables(source), 0, "2024-02-28"))


def extract_canada_cimm_2024_issued_top10() -> tuple[Path, int]:
    source = RAW / "canada" / "cimm-international-students-intake-output-issued-2024-02-28.html"
    out = OUT / "canada" / "study_permit_applications_issued_top10_country_residence_2022_2024jan_snapshot_2024-02-28.csv"
    specs = [
        (1, "2022", False),
        (2, "2023", False),
        (3, "2024 until January 31", True),
    ]
    header = ["source_snapshot", "country_of_residence", "period_label", "authorized", "confirmed", "total", "grand_total"]
    return out, write_csv(out, header, canada_top10_issued_rows(html_tables(source), specs, "2024-02-28"))


def extract_canada_cimm_2024_outcomes_top10() -> tuple[Path, int]:
    source = RAW / "canada" / "cimm-international-students-intake-output-issued-2024-02-28.html"
    out = OUT / "canada" / "study_permit_outcomes_top10_country_residence_2022_2024jan_snapshot_2024-02-28.csv"
    specs = [
        (4, "2022", False, ["approved", "refused", "withdrawn", "approval_rate", "total"]),
        (5, "2023", False, ["approved", "refused", "withdrawn", "approval_rate", "total"]),
        (6, "2024 until January 31", True, ["approved", "refused", "withdrawn", "approval_rate", "total", "grand_total"]),
    ]
    header = ["source_snapshot", "country_of_residence", "period_label", "approved", "refused", "withdrawn", "approval_rate", "total", "grand_total"]
    return out, write_csv(out, header, canada_top10_outcome_rows(html_tables(source), specs, "2024-02-28"))


def extract_canada_cimm_2023_received_top10() -> tuple[Path, int]:
    source = RAW / "canada" / "cimm-sp-intake-output-issued-2023-06-14.html"
    out = OUT / "canada" / "study_permit_applications_received_top10_country_residence_2022_2023apr_snapshot_2023-06-14.csv"
    header = ["source_snapshot", "country_of_residence", "period_label", "applications_received"]
    return out, write_csv(out, header, canada_top10_received_rows(html_tables(source), 0, "2023-06-14"))


def extract_canada_cimm_2023_issued_top10() -> tuple[Path, int]:
    source = RAW / "canada" / "cimm-sp-intake-output-issued-2023-06-14.html"
    out = OUT / "canada" / "study_permit_applications_issued_top10_country_residence_2022_2023apr_snapshot_2023-06-14.csv"
    specs = [
        (1, "2022", False),
        (2, "2023 to April 30", True),
    ]
    header = ["source_snapshot", "country_of_residence", "period_label", "authorized", "confirmed", "total", "grand_total"]
    return out, write_csv(out, header, canada_top10_issued_rows(html_tables(source), specs, "2023-06-14"))


def extract_canada_cimm_2023_outcomes_top10() -> tuple[Path, int]:
    source = RAW / "canada" / "cimm-sp-intake-output-issued-2023-06-14.html"
    out = OUT / "canada" / "study_permit_outcomes_top10_country_residence_2022_2023apr_snapshot_2023-06-14.csv"
    specs = [
        (3, "2022", False, ["refused", "approved", "withdrawn", "approval_rate", "total"]),
        (4, "2023 to April 30", True, ["refused", "approved", "withdrawn", "approval_rate", "total", "grand_total"]),
    ]
    header = ["source_snapshot", "country_of_residence", "period_label", "approved", "refused", "withdrawn", "approval_rate", "total", "grand_total"]
    return out, write_csv(out, header, canada_top10_outcome_rows(html_tables(source), specs, "2023-06-14"))


def extract_canada_ollo_2024_intake_aggregate() -> tuple[Path, int]:
    source = RAW / "canada" / "ollo-international-student-program-at-a-glance-2024-11-04.html"
    out = OUT / "canada" / "study_permit_applications_received_aggregate_2023_2024sep_snapshot_2024-11-04.csv"
    table = html_tables(source)[0]
    rows = []
    for row in table[1:]:
        for period, value in zip(table[0][1:], row[1:]):
            rows.append(["2024-11-04", row[0], period, value])
    header = ["source_snapshot", "application_type", "period_label", "applications_received"]
    return out, write_csv(out, header, rows)


def extract_canada_ollo_2024_processed_aggregate() -> tuple[Path, int]:
    source = RAW / "canada" / "ollo-international-student-program-at-a-glance-2024-11-04.html"
    out = OUT / "canada" / "study_permit_applications_processed_aggregate_2023_2024sep_snapshot_2024-11-04.csv"
    tables = html_tables(source)
    rows = []
    for table_index, application_type in [(1, "Study Permit"), (2, "Study Permit Extension")]:
        table = tables[table_index]
        for row in table[1:]:
            outcome = row[0]
            for period, value in zip(table[0][1:], row[1:]):
                match = re.match(r"^(.+?)\s*\(([^()]*)\)$", value)
                percent = match.group(1).strip() if match else value
                count = match.group(2).strip() if match and match.group(2) else ""
                rows.append(["2024-11-04", application_type, outcome, period, percent, count])
    header = ["source_snapshot", "application_type", "outcome", "period_label", "outcome_percent", "outcome_count"]
    return out, write_csv(out, header, rows)


def extract_canada_ollo_2024_language_destination_rates() -> tuple[Path, int]:
    source = RAW / "canada" / "ollo-international-student-program-at-a-glance-2024-11-04.html"
    out = OUT / "canada" / "study_permit_approval_rates_by_official_language_destination_2020_2024sep_snapshot_2024-11-04.csv"
    table = html_tables(source)[9]
    rows = []
    for row in table[1:]:
        match = re.match(r"^(.+)\s+\((.+)\)$", row[0])
        official_language = match.group(1) if match else row[0]
        destination_region = match.group(2) if match else ""
        for period, value in zip(table[0][1:], row[1:]):
            rows.append(["2024-11-04", official_language, destination_region, period, value])
    header = ["source_snapshot", "official_language", "destination_region", "period_label", "approval_rate"]
    return out, write_csv(out, header, rows)


def main() -> None:
    ensure_dirs()
    results = []
    results.extend(extract_new_zealand())
    results.extend(extract_united_kingdom())
    results.extend(extract_australia())
    results.extend(extract_canada())
    for path, count in results:
        print(f"{path.relative_to(ROOT)}: {count} rows")


if __name__ == "__main__":
    main()
