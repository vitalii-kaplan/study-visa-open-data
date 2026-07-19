from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from country_normalization import normalize_country  # noqa: E402


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


class ReferenceTests(unittest.TestCase):
    def test_reference_schema_names_codes_and_count(self) -> None:
        with (ROOT / "data" / "UNSD — Methodology.csv").open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            self.assertTrue(REFERENCE_FIELDS.issubset(reader.fieldnames or []))
            rows = list(reader)
        self.assertEqual(EXPECTED_COUNTRY_COUNT, len(rows))
        self.assertEqual(EXPECTED_COUNTRY_COUNT, len({row["Country or Area"] for row in rows}))
        self.assertTrue(all(len(row["M49 Code"]) == 3 and row["M49 Code"].isdigit() for row in rows))


class AustralianAliasTests(unittest.TestCase):
    CASES = {
        "China, Peoples Republic of (excl SARs)": "China",
        "Republic of South Sudan": "South Sudan",
        "Cote d'Ivoire": "Côte d’Ivoire",
        "Korea, North": "Democratic People's Republic of Korea",
        "Germany, Fed Republic of": "Germany",
        "St Kitts and Nevis": "Saint Kitts and Nevis",
        "Swaziland": "Eswatini",
        "Turkiye": "Türkiye",
    }

    def test_reviewed_aliases(self) -> None:
        for source, expected in self.CASES.items():
            with self.subTest(source=source):
                result = normalize_country(source, "Australia")
                self.assertEqual(expected, result.country)
                self.assertEqual("alias_matched", result.status)

    def test_non_countries_have_no_canonical_target(self) -> None:
        for source, status in [("Not Specified", "unknown"), ("Refugee", "unknown")]:
            result = normalize_country(source, "Australia")
            self.assertEqual("", result.country)
            self.assertEqual(status, result.status)

    def test_territory_remains_distinct(self) -> None:
        result = normalize_country("Hong Kong (SAR of the PRC)", "Australia")
        self.assertEqual("China, Hong Kong Special Administrative Region", result.country)


if __name__ == "__main__":
    unittest.main()
