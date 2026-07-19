# Data Retrieval

This document describes how to reproduce retrieval of the original data files from official sources.

The accompanying code and documentation are maintained in the [`vitalii-kaplan/study-visa-open-data`](https://github.com/vitalii-kaplan/study-visa-open-data) GitHub project. Unless an absolute location is explicitly given, every file and directory path in this document is relative to the root of that project.

The goal is to preserve raw source files under `data/original/` exactly as downloaded, then describe their schemas in `data/country-schema.json`. CSV extraction from those raw files is a later step handled by `scripts/extract_csv.py` for New Zealand, Australia, the United Kingdom, and most Canadian sources; `scripts/extract_us.py` handles the United States workbook, and `scripts/extract_canada_recent.py` handles the Canadian Q-2700 subset.

The large `data/original/` and `data/csv/` directories, `data/student_visa_common_long.csv`, and `data/student_visa.sqlite` are not committed to the GitHub code repository. They are distributed in a separate data artifact under DOI [`10.5281/zenodo.21446641`](https://doi.org/10.5281/zenodo.21446641). This document and the repository scripts provide the alternative path: retrieve the official sources, then recreate all derived files with `python3 scripts/rebuild_database.py`.

## Principles

- Use official government sources whenever possible.
- Save raw files without editing them.
- Store each source under `data/original/<country-slug>/`.
- Keep source URLs, local file paths, formats, schemas, and caveats in `data/country-schema.json`.
- If a source changes schema by year or release, document it as a separate source record.
- Do not infer applications, refusals, approvals, or rates from another measure unless the method is documented.

## Requirements

Use a shell with `curl` and Python 3.

The UN M49 source used for country-name normalization was downloaded on 19 July 2026 as `data/UNSD — Methodology.csv` from `https://unstats.un.org/unsd/methodology/m49/overview/`. The normalization scripts use this official semicolon-delimited CSV directly.

The final artifact can be rebuilt from the preserved raw sources with one command:

```sh
python3 scripts/rebuild_database.py
```

Validate the source inventory after editing it:

```sh
mkdir -p tmp
python3 -m json.tool data/country-schema.json >tmp/country-schema.validated.json
```

Regenerate the New Zealand, Australian, United Kingdom, and main Canadian source-level CSV files from downloaded raw files:

```sh
python3 scripts/extract_csv.py
```

## Directory Setup

Create country directories before downloading:

```sh
mkdir -p \
  data/original/new-zealand \
  data/original/australia \
  data/original/united-kingdom \
  data/original/canada \
  data/original/united-states
```

## New Zealand

Publisher: Immigration New Zealand.

Source type: annual HTML tables for offshore or overseas student visa application decisions.

These pages are official Immigration New Zealand pages. They are stored as HTML because the decision table is embedded directly in each page.

```sh
curl -L 'https://www.immigration.govt.nz/study/for-education-providers/data-and-processing-times-for-international-student-visas/offshore-student-visa-application-decision-data/offshore-student-visa-application-decisions-for-2022/' \
  -o data/original/new-zealand/offshore-student-visa-application-decisions-2022.html

curl -L 'https://www.immigration.govt.nz/study/for-education-providers/data-and-processing-times-for-international-student-visas/offshore-student-visa-application-decision-data/offshore-student-visa-application-decisions-for-2023/' \
  -o data/original/new-zealand/offshore-student-visa-application-decisions-2023.html

curl -L 'https://www.immigration.govt.nz/study/for-education-providers/data-and-processing-times-for-international-student-visas/offshore-student-visa-application-decision-data/overseas-student-visa-application-decisions-for-2024/' \
  -o data/original/new-zealand/overseas-student-visa-application-decisions-2024.html

curl -L 'https://www.immigration.govt.nz/study/for-education-providers/data-and-processing-times-for-international-student-visas/offshore-student-visa-application-decision-data/overseas-student-visa-application-decisions-for-2025/' \
  -o data/original/new-zealand/overseas-student-visa-application-decisions-2025.html
```

Important schema note: 2022 differs from 2023-2025. The 2022 table has country, approved, declined, and decline rate. The 2023-2025 tables also include application volume and approval rate.

## Australia

Publisher: Australian Government Department of Home Affairs via data.gov.au.

Landing page:

`https://data.gov.au/data/en/dataset/student-visas`

CKAN metadata API:

`https://data.gov.au/data/en/api/3/action/package_show?id=324aa4f7-46bb-4d56-bc2d-772333a2317e`

Retrieve the metadata and current XLSX workbooks:

```sh
curl -L 'https://data.gov.au/data/en/api/3/action/package_show?id=324aa4f7-46bb-4d56-bc2d-772333a2317e' \
  -o data/original/australia/student-visas-package-show.json

curl -L 'https://data.gov.au/data/dataset/324aa4f7-46bb-4d56-bc2d-772333a2317e/resource/ef31b2b4-a894-484b-99bc-e35d62ace777/download/bp0015l-student-visas-lodged-report-locked-at-2026-04-30-v100.xlsx' \
  -o data/original/australia/bp0015l-student-visas-lodged-report-locked-at-2026-02-28-v100.xlsx

curl -L 'https://data.gov.au/data/dataset/324aa4f7-46bb-4d56-bc2d-772333a2317e/resource/dfc7a893-0523-4b8e-bc5a-829e35bec90f/download/bp0015l-student-visas-granted-report-locked-at-2026-04-30-v100.xlsx' \
  -o data/original/australia/bp0015l-student-visas-granted-report-locked-at-2026-02-28-v100.xlsx

curl -L 'https://data.gov.au/data/dataset/324aa4f7-46bb-4d56-bc2d-772333a2317e/resource/b4775919-d0f5-4beb-8901-6384342774c6/download/bp0015l-student-visa-grant-rates-locked-at-2026-04-30-v100.xlsx' \
  -o data/original/australia/bp0015l-student-visa-grant-rates-locked-at-2026-02-28-v100.xlsx

curl -L 'https://data.gov.au/data/dataset/324aa4f7-46bb-4d56-bc2d-772333a2317e/resource/4c157925-d84f-4c9d-a95b-da8ce2580bc1/download/student-visa-program-resources.csv' \
  -o data/original/australia/student-visa-program-resources.csv
```

Important schema note: the Australian XLSX files are pivot workbooks. The full data are in XLSX pivot cache records. `scripts/extract_csv.py` reads those cache records directly.

Snapshot filename note: the three preserved local filenames contain `2026-02-28`, but their downloaded bytes are the 30 April 2026 resources. The saved CKAN package metadata names all three resources as 30 April 2026, and their pivot caches contain the period `2025-26 to 30 April 2026`. The raw local files remain unchanged; generated records carry `source_snapshot=2026-04-30`.

The common schema retains `lodgement_channel` for every Australian workbook and `last_visa_held` for the grants workbook. These dimensions explain the former repeated visible keys; records are unique on the complete pivot-cache dimensions.

Applicant-scope note: source-level Australian CSVs preserve both `Primary` and `Secondary` records, but `scripts/build_common_table.py` includes only `Primary` applicants in generated common tables and SQLite.

Grant rate definition: the grant-rate workbook defines grant rate as grants divided by grants plus refusals. Do not treat it as grants divided by lodgements.

## United Kingdom

Publisher: UK Home Office via GOV.UK Immigration system statistics.

Landing page:

`https://www.gov.uk/government/statistical-data-sets/immigration-system-statistics-data-tables`

Retrieve the landing page and the relevant XLSX workbooks:

```sh
curl -L 'https://www.gov.uk/government/statistical-data-sets/immigration-system-statistics-data-tables' \
  -o data/original/united-kingdom/immigration-system-statistics-data-tables.html

curl -L 'https://assets.publishing.service.gov.uk/media/6a1d5a9f916cd732dcdaad5c/entry-clearance-visa-outcomes-datasets-mar-2026.xlsx' \
  -o data/original/united-kingdom/entry-clearance-visa-outcomes-datasets-mar-2026.xlsx

curl -L 'https://assets.publishing.service.gov.uk/media/6a05e19c5f39105e0848a2c3/education-visas-datasets-mar-2026.xlsx' \
  -o data/original/united-kingdom/education-visas-datasets-mar-2026.xlsx
```

Relevant sheets:

- `Data_Vis_D01`: entry clearance visa applications by year, quarter, nationality, region, visa type group, visa type, visa type subgroup, applicant type, and applications.
- `Data_Vis_D02`: entry clearance visa outcomes by year, quarter, nationality, region, visa type group, visa type, visa type subgroup, applicant type, case outcome, and decisions.
- `Data_Edu_D01`: sponsored study applications by course level.
- `Data_Edu_D02`: sponsored study grants by course level.

Important schema note: entry clearance data is broader than student visas. Filter to study visa categories before treating it as student visa data. The course-level workbook is main-applicant-only and excludes records not matched to Confirmation of Acceptance for Studies data.

Applicant-scope note: source-level UK entry-clearance CSVs preserve `All`, `Main Applicant`, and `Dependant` rows. Generated common tables retain only `Main Applicant`; the separate course-level study tables are already main-applicant-only.

## Canada

Publisher: Immigration, Refugees and Citizenship Canada.

Main statistics/open-data page:

`https://www.canada.ca/en/immigration-refugees-citizenship/corporate/reports-statistics/statistics-open-data.html`

Student and temporary worker page:

`https://www.canada.ca/en/immigration-refugees-citizenship/corporate/reports-statistics/statistics-open-data/immigration-stats/students-workers.html`

Open Canada dataset:

`https://open.canada.ca/data/en/dataset/90115b00-f9b8-49e8-afa3-b4cff8facaee`

The Open Canada page may be difficult to access from some automated environments. The retrieval used an official IRCC direct file URL and also saved a catalogue mirror page for provenance.

```sh
curl -L 'https://www.canada.ca/en/immigration-refugees-citizenship/corporate/reports-statistics/statistics-open-data.html' \
  -o data/original/canada/statistics-open-data.html

curl -L 'https://www.canada.ca/en/immigration-refugees-citizenship/corporate/reports-statistics/statistics-open-data/immigration-stats/students-workers.html' \
  -o data/original/canada/students-workers.html

curl -L 'https://data.urbandatacentre.ca/catalogue/gov-canada-90115b00-f9b8-49e8-afa3-b4cff8facaee' \
  -o data/original/canada/study-permit-holders-cudc-catalogue.html

curl -L 'https://www.ircc.canada.ca/opendata-donneesouvertes/data/ODP-TR-Study-IS_CITZ.csv' \
  -o data/original/canada/ODP-TR-Study-IS_CITZ.csv

curl -L 'https://www.ircc.canada.ca/opendata-donneesouvertes/data/EN_ODP-TR-Study-IS_CITZ_sign_date.xlsx' \
  -o data/original/canada/EN_ODP-TR-Study-IS_CITZ_sign_date.xlsx
```

### Canada Approval and Outcome Sources

The IRCC/Open Canada files above are mainly permit-holder or permit-effective volume files. Canada also publishes some study permit application outcome data through official parliamentary and committee transparency pages.

Retrieve the currently used Canada approval/outcome pages:

```sh
curl -L 'https://www.canada.ca/en/immigration-refugees-citizenship/corporate/transparency/committees/cimm-mar-24-2022/student-approval-rates.html' \
  -o data/original/canada/cimm-student-approval-rates-country-residence-2019-2022-jan.html

curl -L 'https://www.canada.ca/en/immigration-refugees-citizenship/corporate/transparency/committees/cimm-may-12-2022/student-approval-rates-country-residence.html' \
  -o data/original/canada/cimm-student-approval-rates-country-residence-2019-2022-mar.html

curl -L 'https://www.canada.ca/en/immigration-refugees-citizenship/corporate/transparency/committees/cimm-feb-28-2024/intake-output-issued.html' \
  -o data/original/canada/cimm-international-students-intake-output-issued-2024-02-28.html

curl -L 'https://www.canada.ca/en/immigration-refugees-citizenship/corporate/transparency/committees/cimm-june-14-2023/intake.html' \
  -o data/original/canada/cimm-sp-intake-output-issued-2023-06-14.html

curl -L 'https://www.canada.ca/en/immigration-refugees-citizenship/corporate/transparency/committees/ollo-november-4-2024/international-student-population.html' \
  -o data/original/canada/ollo-international-student-program-at-a-glance-2024-11-04.html
```

Retrieve newer Canada transparency pages used for recent/context data:

```sh
curl -L 'https://www.canada.ca/en/immigration-refugees-citizenship/corporate/transparency/committees/ollo-november-4-2024/order-paper-question-q2700.html' \
  -o data/original/canada/ollo-order-paper-q2700-2024-11-04.html

curl -L 'https://www.canada.ca/en/immigration-refugees-citizenship/corporate/transparency/committees/cimm-oct-21-2025/q-78.html' \
  -o data/original/canada/cimm-question-q78-2025-10-21.html

curl -L 'https://www.canada.ca/en/immigration-refugees-citizenship/corporate/transparency/committees/cow-jun-9-2025/international-students.html' \
  -o data/original/canada/cow-international-students-2025-06-09.html
```

Important schema note: the Canada approval/outcome pages use country of residence, not citizenship. The IRCC/Open Canada permit-holder files use country of citizenship. Keep this distinction explicit in downstream processing.

The strongest currently retrieved Canada approval-rate source is:

`data/original/canada/cimm-student-approval-rates-country-residence-2019-2022-jan.html`

It provides all-country study permit applications excluding extensions processed by IRCC for 2019, 2020, 2021, and January 2022, with approved, refused, total, and approval rate.

The later CIMM pages provide useful recent snapshots for 2022-2024, but only for top 10 countries of residence plus `Other Countries` and `Grand Total`.

The OLLO page provides aggregate 2023/2024 intake and processed-outcome data, plus approval rates by official language and destination region. It is not country-of-origin data.

The OLLO Q-2700 page provides country-of-residence approval outcomes for French-speaking or bilingual study permit applicants for 2023 and January-April 2024. These rows are a language subset, not all applicants. Generate the source and SQLite-only common CSVs with:

```sh
python3 scripts/extract_canada_recent.py
```

The full rebuild loads this subset automatically. To replace it in an existing database without a full rebuild, run `python3 scripts/extract_canada_recent.py --insert-sqlite`.

The CIMM Q-78 and COW pages are preserved as raw context files in the current run. Q-78 contains later French/bilingual summary statements, but the downloaded English HTML did not expose the full Annex A country table. The COW page provides aggregate 2024/2025 context, not country-level rows.

Important schema note: the original Open Canada files are study permit holder or permit-effective counts. They do not directly provide study permit applications, refusals, or approval rates by citizenship. Do not compare them directly to New Zealand or Australia approval rates.

The `ODP-TR-Study-IS_CITZ.csv` file uses tab delimiters even though the extension is `.csv`. Country names may contain commas, so parse it as tab-delimited text.

## United States

Publisher: U.S. Department of State, Bureau of Consular Affairs.

Source type: official nonimmigrant visa statistics.

Landing page:

`https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/nonimmigrant-visa-statistics.html`

Retrieve the landing page and currently used source files:

```sh
curl -L 'https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/nonimmigrant-visa-statistics.html' \
  -o data/original/united-states/nonimmigrant-visa-statistics.html

curl -L 'https://travel.state.gov/content/dam/visas/Statistics/Non-Immigrant-Statistics/NIVDetailTables/FYs97-24_NIVDetailTable.xlsx' \
  -o data/original/united-states/FYs97-24_NIVDetailTable.xlsx

curl -L 'https://travel.state.gov/content/dam/visas/Statistics/Non-Immigrant-Statistics/NIVWorkload/FY2024NIVWorkloadbyVisaCategory.pdf' \
  -o data/original/united-states/FY2024NIVWorkloadbyVisaCategory.pdf

curl -L 'https://travel.state.gov/content/dam/visas/Statistics/Non-Immigrant-Statistics/NIVWorkload/FY2023NIVWorkloadbyVisaCategory.pdf' \
  -o data/original/united-states/FY2023NIVWorkloadbyVisaCategory.pdf
```

Important schema note: the raw United States workbook contains F1, F2, M1, and M2 visa classes. The extraction keeps only the primary student classes F1 and M1; dependent classes F2 and M2 are excluded. This source gives issuances by nationality and visa class. It does not give nationality-level applications, refusals, or approval rates.

The downloaded workload PDFs may support worldwide application/refusal/issuance totals by visa category, but they do not solve nationality-level approval rates. They were preserved for provenance and future parsing.

## Verification

After retrieval, verify that expected files exist:

```sh
find data/original -maxdepth 2 -type f -print
```

Validate the source inventory:

```sh
mkdir -p tmp
python3 -m json.tool data/country-schema.json >tmp/country-schema.validated.json
```

Generate the New Zealand, Australian, United Kingdom, and main Canadian source-level CSVs:

```sh
python3 scripts/extract_csv.py
```

Generate the United States source-level file:

```sh
python3 scripts/extract_us.py
```

Generate the Canadian processed intermediates required by the common-table builder:

```sh
python3 scripts/combine_canada.py
```

Generate the Canadian Q-2700 source-level CSV and its SQLite-only common-schema intermediate:

```sh
python3 scripts/extract_canada_recent.py
```

Rebuild the common long table:

```sh
python3 scripts/build_common_table.py
```

Load the strict SQLite database, including the Canadian SQLite-only subset, and create its indexes:

```sh
python3 scripts/load_sqlite.py
```

Run the final validation and regenerate the unmatched-origin audit:

```sh
python3 scripts/validate_database.py
```

These manual commands must be run in the order shown. For the supported end-to-end workflow, prefer `python3 scripts/rebuild_database.py`; it runs the same extraction, combination, transformation, SQLite loading, indexing, and validation stages in order.

Expected CSV output directories:

```text
data/csv/new-zealand/
data/csv/australia/
data/csv/united-kingdom/
data/csv/canada/
data/csv/united-states/
```

## Instructions For AI/LLM Agents

When updating retrieval:

1. Read `AGENTS.md`, `README.md`, `data/country-schema.json`, and this file first.
2. Use current official government pages as the source of truth.
3. If using web search, prefer official domains:
   - `immigration.govt.nz`
   - `data.gov.au`
   - `gov.uk`
   - `canada.ca`
   - `ircc.canada.ca`
   - `open.canada.ca`
   - `travel.state.gov`
4. Download raw files to `data/original/<country-slug>/`.
5. Do not rewrite raw files after download.
6. If a URL changed, update both `data/RETRIEVAL.md` and `data/country-schema.json`.
7. If a schema changed, add a new source record or release-specific entry instead of overwriting old schema notes.
8. If a source is not an applications/outcomes source, say so explicitly.
9. Run JSON validation after editing `data/country-schema.json`.
10. Run `python3 scripts/extract_csv.py` after retrieval if Commonwealth CSV outputs need to be refreshed.
11. Run `python3 scripts/extract_us.py` after updating United States raw files.

When uncertain, preserve the raw file, document the uncertainty, and avoid normalizing the measure into applications, approvals, refusals, or rates until the source definition is clear.
