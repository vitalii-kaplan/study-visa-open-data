# AGENTS.md

This repository builds a reproducible cross-national collection of public student visa and study permit statistics.

## Project intent

The project studies the administrative stage after admission or eligibility to study and before study begins: visa or permit applications and government responses. Keep work focused on public data, provenance, normalization, validation, and responsible comparison.

Do not shift the project toward university rankings, admission criteria, program or scholarship search, general study-abroad marketing, or individual visa advice.

## Current repository state

- `data/` is the intended standalone data artifact. Large artifact content is distributed separately from the GitHub code repository (DOI forthcoming) and is ignored by Git.
- `data/country-schema.json` is the machine-readable source inventory and data dictionary. Keep it valid JSON.
- `data/RETRIEVAL.md` records source retrieval and provenance.
- `data/original/<country-slug>/` contains preserved downloads when the separate data artifact is unpacked or retrieval has been run.
- `data/csv/<country-slug>/` contains source-level CSV extractions created by the build or supplied in the separate data artifact.
- Current country slugs are `australia`, `canada`, `new-zealand`, `united-kingdom`, and `united-states`.
- `data/student_visa_common_long.csv` is the rebuilt common long table; it is supplied in the separate data artifact or recreated by the scripts.
- `data/student_visa.sqlite` is the strict query database, supplied in the separate data artifact or recreated by the scripts. It also contains a documented Canada French-speaking/bilingual subset that is intentionally SQLite-only.
- `data/UNSD — Methodology.csv` is the preserved UN M49 reference used for origin-country normalization.
- `data/country_aliases.csv` contains reviewed aliases and non-country classifications.
- `log/unmatched_origin_labels.csv` is the persistent normalization audit and is not part of the data artifact.
- `tmp/processed/canada/` contains generated Canadian intermediates. Full rebuilds recreate them; do not publish them as source data.
- Country-split common tables are no longer generated or retained.

## Working rules

- Preserve raw source files exactly as obtained. Never clean or edit files in `data/original/` in place.
- Prefer official government sources. Clearly label and justify any exception.
- Keep retrieval, extraction, transformation, normalization, loading, and validation separate when practical.
- Record source URL, access date, publisher, reporting period, format, official definitions, and relevant limitations.
- Represent materially different schemas or releases as separate source records instead of forcing one schema across them.
- Use reproducible scripts rather than manual spreadsheet edits.
- Avoid hard-coded absolute paths.
- Keep generated intermediates and logs outside `data/` unless they are part of the intended published artifact.
- If adding a source, preserve it under the matching `data/original/<country-slug>/` directory and update `data/country-schema.json` and `data/RETRIEVAL.md`.

## Meaning and comparability

Do not silently combine or relabel incompatible measures, including:

- applications lodged or received;
- decisions or finalizations;
- grants, approvals, or issued permits;
- refusals or declines;
- withdrawals;
- permit holders; and
- reported or calculated rates.

Make missingness explicit. Do not infer, fill, or impute values unless the method is documented. A value calculated from other published fields must be labelled as derived and must retain its formula and denominator.

Keep these distinctions visible:

- nationality versus country of residence;
- principal applicants versus dependants or inseparable populations;
- offshore versus onshore cases;
- calendar, fiscal, financial, quarterly, monthly, and snapshot periods;
- all-applicant populations versus top-country, language, or other subsets;
- rounded, suppressed, aggregate, unknown, and unmatched values; and
- legal or statistical category changes over time.

When uncertain, preserve the source category and add a note rather than forcing comparability.

## Country-specific cautions

- **New Zealand:** 2023–2025 provide applications, approvals, declines, and rates for offshore or overseas student visas. The 2022 schema is different and lacks application volume and approval rate.
- **Australia:** workbooks report lodgements, grants, and decision-based grant rates. Generated records retain primary applicants only. Grant rate is grants divided by grants plus refusals. Current content runs through 30 April 2026 even though preserved local workbook names contain `2026-02-28`.
- **United Kingdom:** filter entry-clearance data to study categories. Applications and outcomes may describe different cohorts, so do not derive a naïve quarterly approval rate by dividing one table by the other. Course-level data cover main applicants matched to CAS records.
- **Canada:** keep permit-holder volumes, older all-country outcomes, recent top-country snapshots, aggregate tables, and French-speaking/bilingual subsets distinct. Do not present a restricted subset as national all-applicant coverage.
- **United States:** generated data retain F1 and M1 issuances by nationality and fiscal year. They do not provide nationality-level applications, refusals, or approval rates.

## Normalization and generated data

- Use `un_m49_country` for normalized origin matching when available.
- Preserve the original source label alongside its normalized value.
- Retain `normalization_status` distinctions: `matched`, `alias_matched`, `aggregate`, `unknown`, and `unmatched`.
- Do not treat aggregate or unknown labels as countries.
- Do not add SQLite-only subset rows to the common CSV unless the user explicitly requests that change.
- Final provenance fields must point to packaged source files under `data/original/` or `data/csv/`, not to `tmp/` intermediates.

## Validation

After editing the source inventory, validate it while keeping temporary output under the ignored `tmp/` directory:

```sh
mkdir -p tmp
python3 -m json.tool data/country-schema.json >tmp/country-schema.validated.json
```

The full reproducible build and validation entry point is:

```sh
python3 scripts/rebuild_database.py
```

For a derived-only rebuild that reuses source-level CSV extractions:

```sh
python3 scripts/rebuild_database.py --skip-extraction
```

Relevant checks also include:

```sh
python3 scripts/validate_database.py
python3 -m unittest discover -s tests
```

When database content or documentation changes, keep `data/country-schema.json`, `data/RETRIEVAL.md`, the root `README.md`, and the article consistent with the actual artifacts.
