# Country-to-Visa

## Public Student Visa and Study Permit Data

This project brings together official statistics on student visas and study permits for Australia, Canada, New Zealand, the United Kingdom, and the United States.

It focuses on the period between becoming eligible to study and beginning study: applications, government decisions, grants, refusals, issued visas or permits, and reported approval rates. The collection contains **9,510,731 aggregate measure records** in a common long-form database while preserving the meaning and limitations of each national source.

[Read the project paper](article/article.pdf) · [Published paper (DOI: 10.5281/zenodo.21453632)](https://doi.org/10.5281/zenodo.21453632) · [Explore the source catalogue](data/country-schema.json) · [Review data provenance](data/RETRIEVAL.md)

## Why this project exists

Public student-visa statistics are scattered across government websites, spreadsheets, web tables, and PDFs. Countries also describe different events: an application lodged is not the same as a decision made, and a visa granted is not always equivalent to a permit holder.

This project collects those sources in one place, standardizes their structure, reconciles country names, and keeps the original definitions visible. It is intended for researchers, policy analysts, journalists, and others studying educational migration or the transparency of public administrative data.

## Countries and coverage

| Destination | Coverage in this collection | What the source data mainly describes |
| --- | --- | --- |
| Australia | Financial year 2005–06 to 30 April 2026 | Student visa lodgements, grants, and decision-based grant rates |
| Canada | 2015–2026, with outcome subsets for 2019–April 2024 | Study permit holders, applications, outcomes, and selected applicant subsets |
| New Zealand | 2022–2025 | Offshore or overseas student visa applications and decisions |
| United Kingdom | 2005–first quarter of 2026 | Entry-clearance study applications and outcomes, plus sponsored-study course-level data |
| United States | Fiscal year 1997–2024 | F1 and M1 student visa issuances by nationality |

Coverage is not equally complete across countries. Canada combines several explicitly labelled populations and reporting snapshots. United States data provide issuances but not a nationality-level applications or refusals denominator. New Zealand’s 2022 release contains fewer measures than later years.

## What is available

- `data/student_visa.sqlite` — the main query-ready collection.
- `data/student_visa_common_long.csv` — the common long-form table in CSV format.
- `data/csv/` — country-specific tables extracted from the official sources.
- `data/original/` — the preserved source files as downloaded.
- [`data/country-schema.json`](data/country-schema.json) — the source catalogue, field descriptions, coverage notes, and comparability warnings.

The large data files and directories listed above are not committed to the GitHub code repository. They are available from the separate data artifact under DOI [`10.5281/zenodo.21446641`](https://doi.org/10.5281/zenodo.21446641). Alternatively, retrieve the preserved sources by following [`data/RETRIEVAL.md`](data/RETRIEVAL.md), then recreate the extracted CSV files, common long table, and SQLite database with `python3 scripts/rebuild_database.py`.

The accompanying [paper](article/article.pdf), published under DOI [`10.5281/zenodo.21453632`](https://doi.org/10.5281/zenodo.21453632), explains how the collection was assembled, how country names were reconciled, where fields are structurally absent, and which comparisons are defensible.

## How to interpret the data

Each row is an **aggregate reported measure**, not an individual applicant or visa case. A single official breakdown can produce many rows across periods, nationalities, visa categories, education sectors, applicant types, and other dimensions.

The collection deliberately does not treat applications, decisions, grants, approvals, issuances, and permit holders as interchangeable. Before comparing destinations, check the measure, reporting period, applicant population, origin concept (nationality or residence), and any coverage note.

Australia contributes about 98% of database rows because its official workbooks contain unusually detailed multidimensional breakdowns. This does not mean that 98% of the world’s student visa applicants apply to Australia.

## Scope

This is a data and reproducibility project. It does not rank universities, model admission chances, provide personal visa advice, or make causal claims about national visa systems.

The collection is based on public government sources and retains their terminology, gaps, revisions, suppression rules, and historical category changes rather than hiding those differences.
