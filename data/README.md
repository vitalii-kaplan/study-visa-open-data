# Country-to-Visa Data Artifact

This data artifact contains a reproducible cross-national collection of public student visa and study permit statistics for Australia, Canada, New Zealand, the United Kingdom, and the United States. It covers government-reported applications, decisions, grants, refusals, issuances, permit holders, and rates while preserving differences in source definitions, populations, origin concepts, and reporting periods.

Each record represents an aggregate published measure, not an individual applicant or visa case. Measures with different meanings must not be treated as interchangeable. Consult `country-schema.json` and `RETRIEVAL.md` before making comparisons across sources or destinations.

The large data files are distributed separately from the GitHub code repository as a data artifact under DOI [`10.5281/zenodo.21446641`](https://doi.org/10.5281/zenodo.21446641). They can also be recreated from the documented sources using the scripts in the [`vitalii-kaplan/study-visa-open-data`](https://github.com/vitalii-kaplan/study-visa-open-data) project. All paths mentioned here are relative to that project’s `data/` directory.

## Top-level contents

| Entry | Description |
| --- | --- |
| `README.md` | This overview of the data artifact and its top-level contents. |
| `RETRIEVAL.md` | Retrieval instructions, official source URLs, provenance notes, schema cautions, and the reproducible build sequence. |
| `UNSD — Methodology.csv` | Preserved United Nations Statistics Division M49 reference used to normalize origin-country and area names. |
| `country-schema.json` | Machine-readable source inventory and data dictionary, including coverage, fields, source locations, definitions, and comparability limitations. |
| `country_aliases.csv` | Reviewed mappings from source-specific origin labels to M49 names, together with explicit aggregate, unknown, and unmatched classifications. |
| `csv/` | Source-level CSV extractions generated from the preserved official sources. These retain source-specific schemas and are inputs to later transformation stages. |
| `original/` | Preserved official source downloads in their original formats. These files are the provenance inputs for reproducible extraction. |
| `student_visa_common_long.csv` | Common 30-field long-form table across the five destinations. It retains distinguishable source categories and excludes explicitly identifiable dependant cohorts; the documented Canadian French-speaking or bilingual subset is intentionally not included. |
| `student_visa.sqlite` | Strict query-ready SQLite database. It applies the documented student/study and applicant-scope filters and includes the separately labelled Canadian French-speaking or bilingual SQLite-only subset. |

Missing values are not imputed. Original origin labels are retained alongside normalized M49 names and normalization statuses. Aggregate, unknown, and unmatched labels must not be interpreted as countries.
