#!/usr/bin/env python3
"""Shared UN M49 country/area normalization for every generated artifact."""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "UNSD — Methodology.csv"
ALIASES = ROOT / "data" / "country_aliases.csv"

ALLOWED_STATUSES = {"matched", "alias_matched", "aggregate", "unknown", "unmatched"}


def normalized_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = value.casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


@dataclass(frozen=True)
class NormalizationResult:
    country: str
    status: str


class CountryNormalizer:
    def __init__(self, reference: Path = REFERENCE, aliases: Path = ALIASES) -> None:
        with reference.open(newline="", encoding="utf-8-sig") as handle:
            reference_rows = list(csv.DictReader(handle, delimiter=";"))
        required = {
            "Country or Area",
            "M49 Code",
            "Region Name",
            "Sub-region Name",
            "Intermediate Region Name",
            "ISO-alpha2 Code",
            "ISO-alpha3 Code",
        }
        if not reference_rows or not required.issubset(reference_rows[0]):
            raise ValueError(f"{reference} does not have the official UNSD M49 schema")
        self.canonical_names = {row["Country or Area"] for row in reference_rows}
        self.canonical_by_key = {normalized_key(name): name for name in self.canonical_names}
        if len(self.canonical_by_key) != len(self.canonical_names):
            raise ValueError("UN M49 canonical names collide after normalization")

        self.aliases: dict[tuple[str, str], NormalizationResult] = {}
        with aliases.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                destination = normalized_key(row["destination_country"])
                label = normalized_key(row["source_label"])
                status = row["normalization_status"].strip()
                country = row["canonical_country"].strip()
                if status not in ALLOWED_STATUSES - {"matched"}:
                    raise ValueError(f"invalid alias status {status!r} for {row['source_label']!r}")
                if status == "alias_matched" and country not in self.canonical_names:
                    raise ValueError(f"alias target is not an exact UN M49 name: {country!r}")
                if status != "alias_matched" and country:
                    raise ValueError(f"non-country label must not have a canonical target: {row['source_label']!r}")
                key = (destination, label)
                if key in self.aliases:
                    raise ValueError(f"duplicate alias key: {key}")
                self.aliases[key] = NormalizationResult(country, status)

    def normalize(self, origin_country: str, destination_country: str = "") -> NormalizationResult:
        raw = (origin_country or "").strip()
        label_key = normalized_key(raw)
        destination_key = normalized_key(destination_country)
        for key in ((destination_key, label_key), ("", label_key)):
            if key in self.aliases:
                return self.aliases[key]
        if raw in self.canonical_names:
            return NormalizationResult(raw, "matched")
        canonical = self.canonical_by_key.get(label_key)
        if canonical:
            return NormalizationResult(canonical, "matched")
        if not label_key:
            return NormalizationResult("", "aggregate")
        return NormalizationResult("", "unmatched")


NORMALIZER = CountryNormalizer()


def normalize_country(origin_country: str, destination_country: str = "") -> NormalizationResult:
    return NORMALIZER.normalize(origin_country, destination_country)
