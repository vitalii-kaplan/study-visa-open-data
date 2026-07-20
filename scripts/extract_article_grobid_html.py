#!/usr/bin/env python3
"""Convert the related-research PDFs to semantic HTML with GROBID.

By default, PDFs are read from ``data/articles/`` and HTML and TEI outputs are
written below that directory. Generated article data are ignored by Git; the
curated ``data/articles/registry.json`` is maintained separately.

Requires a running GROBID service, for example:

    docker run --rm --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = ROOT / "data" / "articles"
DEFAULT_OUTPUT_DIR = DEFAULT_INPUT_DIR / "html"
DEFAULT_TEI_DIR = DEFAULT_OUTPUT_DIR / "grobid_tei"
DEFAULT_MANIFEST = DEFAULT_INPUT_DIR / "grobid_html_manifest.csv"
DEFAULT_REGISTRATION_METADATA_DIR = DEFAULT_INPUT_DIR / "metadata" / "registries"
DEFAULT_METADATA_CORRECTIONS = DEFAULT_INPUT_DIR / "article_metadata_corrections.json"
DEFAULT_GROBID_URL = "http://localhost:8070"
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def repository_path(path: Path) -> str:
    """Return a stable repository-relative path when the file is in this project."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pdf_files",
        nargs="*",
        type=Path,
        metavar="PDF",
        help=(
            "PDF file(s) to process. If omitted, process every PDF directly in "
            "--input-dir."
        ),
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--tei-dir", type=Path, default=DEFAULT_TEI_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--registration-metadata-dir",
        type=Path,
        default=DEFAULT_REGISTRATION_METADATA_DIR,
    )
    parser.add_argument(
        "--metadata-corrections",
        type=Path,
        default=DEFAULT_METADATA_CORRECTIONS,
        help=(
            "Optional JSON file with curated per-article metadata corrections, "
            "keyed by article filename stem."
        ),
    )
    parser.add_argument("--grobid-url", default=DEFAULT_GROBID_URL)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Regenerate TEI and HTML for all PDFs, including existing outputs.",
    )
    parser.add_argument(
        "--reuse-existing-tei",
        action="store_true",
        help="Render HTML from existing TEI files when present instead of calling GROBID.",
    )
    return parser.parse_args()


def select_pdf_files(args: argparse.Namespace) -> list[Path]:
    """Return explicitly requested PDFs, or all PDFs in the input directory."""
    pdf_files = args.pdf_files or sorted(args.input_dir.glob("*.pdf"))
    invalid = [
        path
        for path in pdf_files
        if not path.is_file() or path.suffix.lower() != ".pdf"
    ]
    if invalid:
        invalid_list = ", ".join(path.as_posix() for path in invalid)
        raise SystemExit(f"PDF file(s) not found or not PDFs: {invalid_list}")
    if not pdf_files:
        raise SystemExit(f"No PDF files found in {args.input_dir}")
    return pdf_files


def grobid_is_alive(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/isalive", timeout=5) as response:
            body = response.read().decode("utf-8", errors="replace").strip().lower()
        return response.status == 200 and body == "true"
    except (OSError, urllib.error.URLError):
        return False


def request_grobid_tei(pdf_file: Path, base_url: str) -> bytes:
    boundary = "----codex-grobid-html"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="input"; filename="{pdf_file.name}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8") + pdf_file.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/processFulltextDocument",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join(" ".join(element.itertext()).split())


def article_text(element: ET.Element | None) -> str:
    if element is None:
        return ""

    parts: list[str] = []

    def append(value: str | None) -> None:
        if value:
            parts.append(value)

    def walk(node: ET.Element) -> None:
        target = node.attrib.get("target", "")
        tag = node.tag.rsplit("}", 1)[-1]
        if target.startswith(("http://", "https://")) and tag in {"ref", "ptr"}:
            append(target)
        else:
            append(node.text)
            for child in node:
                walk(child)
                append(child.tail)

    walk(element)
    return " ".join(" ".join(parts).split())


def target_urls(element: ET.Element) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for child in element.iter():
        target = child.attrib.get("target")
        if not target or not target.startswith(("http://", "https://")):
            continue
        if target not in seen:
            seen.add(target)
            urls.append(target)
    return urls


def element_text_with_target_urls(element: ET.Element | None) -> str:
    if element is None:
        return ""
    text = article_text(element)
    urls = target_urls(element)
    if urls:
        existing = re.sub(r"\s+", "", text.lower())
        missing_urls = [
            url
            for url in urls
            if re.sub(r"\s+", "", url.lower()) not in existing
        ]
        if missing_urls:
            text = (text + " " + " ".join(missing_urls)).strip()
    return text


def find_title(root: ET.Element) -> str:
    title = root.find(".//tei:titleStmt/tei:title", TEI_NS)
    if title is not None and element_text(title):
        return element_text(title)
    title = root.find(".//tei:title", TEI_NS)
    return element_text(title) or "Untitled article"


def normalize_orcid(value: str) -> str:
    return re.sub(r"^https?://orcid\.org/", "", value.strip(), flags=re.IGNORECASE)


def extract_affiliation(affiliation: ET.Element) -> dict[str, Any]:
    organizations = [
        {
            "type": organization.attrib.get("type", "organization"),
            "name": element_text(organization),
        }
        for organization in affiliation.findall("tei:orgName", TEI_NS)
        if element_text(organization)
    ]
    address_parts: list[dict[str, str]] = []
    address = affiliation.find("tei:address", TEI_NS)
    if address is not None:
        for part in address:
            value = element_text(part)
            if value:
                address_parts.append(
                    {
                        "type": part.tag.rsplit("}", 1)[-1],
                        "value": value,
                        "key": part.attrib.get("key", ""),
                    }
                )
    return {
        "key": affiliation.attrib.get("key", ""),
        "source": "GROBID TEI",
        "organizations": organizations,
        "address": address_parts,
    }


def registered_affiliations(author: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """Convert registry affiliation strings to the common affiliation structure."""
    raw_affiliations = author.get("affiliation", author.get("affiliations", [])) or []
    affiliations = []
    for item in raw_affiliations:
        name = str(item.get("name", "") if isinstance(item, dict) else item).strip()
        if name:
            affiliations.append(
                {
                    "key": "",
                    "source": source,
                    "organizations": [{"type": "organization", "name": name}],
                    "address": [],
                }
            )
    return affiliations


def extract_authors(root: ET.Element) -> list[dict[str, Any]]:
    """Return structured article authors, excluding authors of cited works."""
    author_elements = root.findall(
        ".//tei:teiHeader/tei:fileDesc/tei:sourceDesc/"
        "tei:biblStruct/tei:analytic/tei:author",
        TEI_NS,
    )
    authors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for author in author_elements:
        person_name = author.find("tei:persName", TEI_NS)
        name = element_text(person_name)
        if not name:
            name = element_text(author.find("tei:orgName", TEI_NS))
        if name and name not in seen:
            seen.add(name)
            identifiers = []
            for identifier in author.findall(".//tei:idno", TEI_NS):
                if identifier.attrib.get("type", "").upper() != "ORCID":
                    continue
                value = normalize_orcid(element_text(identifier))
                if value:
                    identifiers.append(
                        {"type": "ORCID", "value": value, "source": "GROBID TEI"}
                    )
            authors.append(
                {
                    "name": name,
                    "given": element_text(
                        person_name.find("tei:forename", TEI_NS)
                        if person_name is not None
                        else None
                    ),
                    "family": element_text(
                        person_name.find("tei:surname", TEI_NS)
                        if person_name is not None
                        else None
                    ),
                    "corresponding": author.attrib.get("role") == "corresp",
                    "identifiers": identifiers,
                    "emails": [
                        element_text(email)
                        for email in author.findall("tei:email", TEI_NS)
                        if element_text(email)
                    ],
                    "affiliations": [
                        extract_affiliation(affiliation)
                        for affiliation in author.findall("tei:affiliation", TEI_NS)
                    ],
                }
            )
    return authors


def find_authors(root: ET.Element) -> list[str]:
    """Return article author names for callers that only need display text."""
    return [str(author["name"]) for author in extract_authors(root)]


def load_registered_authors(
    stem: str, metadata_dir: Path
) -> tuple[list[dict[str, Any]], str]:
    """Load fallback authors from a saved Crossref or DataCite response."""
    crossref_file = metadata_dir / f"{stem}.json"
    datacite_file = metadata_dir / f"{stem}.datacite.json"
    if crossref_file.is_file():
        payload = json.loads(crossref_file.read_text(encoding="utf-8"))
        authors = []
        for author in payload.get("message", {}).get("author", []):
            name = " ".join(
                part for part in (author.get("given", ""), author.get("family", "")) if part
            )
            if not name:
                name = str(author.get("name", ""))
            if name:
                identifiers = []
                orcid = normalize_orcid(str(author.get("ORCID", "")))
                if orcid:
                    identifiers.append(
                        {"type": "ORCID", "value": orcid, "source": "Crossref"}
                    )
                authors.append(
                    {
                        "name": name,
                        "given": str(author.get("given", "")),
                        "family": str(author.get("family", "")),
                        "corresponding": False,
                        "identifiers": identifiers,
                        "emails": [],
                        "affiliations": registered_affiliations(author, "Crossref"),
                    }
                )
        return authors, "Crossref"
    if datacite_file.is_file():
        payload = json.loads(datacite_file.read_text(encoding="utf-8"))
        creators = payload.get("data", {}).get("attributes", {}).get("creators", [])
        authors = []
        for creator in creators:
            name = " ".join(
                part
                for part in (creator.get("givenName", ""), creator.get("familyName", ""))
                if part
            )
            if not name:
                name = str(creator.get("name", ""))
            if name:
                identifiers = []
                for identifier in creator.get("nameIdentifiers", []):
                    scheme = str(identifier.get("nameIdentifierScheme", ""))
                    if scheme.upper() != "ORCID":
                        continue
                    value = normalize_orcid(str(identifier.get("nameIdentifier", "")))
                    if value:
                        identifiers.append(
                            {"type": "ORCID", "value": value, "source": "DataCite"}
                        )
                authors.append(
                    {
                        "name": name,
                        "given": str(creator.get("givenName", "")),
                        "family": str(creator.get("familyName", "")),
                        "corresponding": False,
                        "identifiers": identifiers,
                        "emails": [],
                        "affiliations": registered_affiliations(creator, "DataCite"),
                    }
                )
        return authors, "DataCite"
    return [], ""


def load_metadata_corrections(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"metadata corrections must be a JSON object: {path}")
    return payload


def author_stub(name: str) -> dict[str, Any]:
    parts = name.split()
    return {
        "name": name,
        "given": " ".join(parts[:-1]) if len(parts) > 1 else name,
        "family": parts[-1] if len(parts) > 1 else "",
        "corresponding": False,
        "identifiers": [],
        "emails": [],
        "affiliations": [],
    }


def author_name_equals(author: dict[str, Any], name: str) -> bool:
    return normalized_name_tokens(str(author.get("name", ""))) == normalized_name_tokens(name)


def unique_structures(items: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result = []
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def affiliation_from_spec(item: dict[str, Any]) -> dict[str, Any]:
    organizations = item.get("organizations", [])
    if organizations and isinstance(organizations[0], str):
        organizations = [
            {"type": "organization", "name": str(name)}
            for name in organizations
            if str(name).strip()
        ]
    address = item.get("address", [])
    if isinstance(address, str):
        address = [{"type": "address", "value": address, "key": ""}] if address else []
    return {
        "key": str(item.get("key", "")),
        "source": str(item.get("source", "Curated article metadata")),
        "organizations": organizations,
        "address": address,
    }


def merged_author_record(
    spec: dict[str, Any],
    extracted_authors: list[dict[str, Any]],
    registered_authors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create one corrected author record, preserving matching metadata."""
    name = str(spec["name"])
    source_names = [str(value) for value in spec.get("source_names", [name])]
    matches: list[dict[str, Any]] = []
    for source_name in source_names:
        source_stub = author_stub(source_name)
        matches.extend(
            author
            for author in extracted_authors
            if author_name_equals(author, source_name)
            or author_names_match(author, source_stub)
        )
    corrected_stub = {
        **author_stub(name),
        "given": str(spec.get("given", "")),
        "family": str(spec.get("family", "")),
    }
    matches.extend(
        author
        for author in registered_authors
        if author_names_match(author, corrected_stub)
    )

    base = json.loads(json.dumps(matches[0] if matches else author_stub(name)))
    base["name"] = name
    if spec.get("given") is not None:
        base["given"] = str(spec.get("given", ""))
    if spec.get("family") is not None:
        base["family"] = str(spec.get("family", ""))
    if "corresponding" in spec:
        base["corresponding"] = bool(spec["corresponding"])
    elif matches:
        base["corresponding"] = any(bool(author.get("corresponding")) for author in matches)

    identifiers = []
    emails = []
    affiliations = []
    for author in matches:
        identifiers.extend(author.get("identifiers", []))
        emails.extend(author.get("emails", []))
        affiliations.extend(author.get("affiliations", []))
    base["identifiers"] = unique_structures(identifiers)
    base["emails"] = sorted({str(email) for email in emails if str(email).strip()})
    base["affiliations"] = unique_structures(affiliations)
    if "affiliations" in spec:
        base["affiliations"] = [
            affiliation_from_spec(item)
            for item in spec.get("affiliations", [])
            if isinstance(item, dict)
        ]
    return base


def apply_author_corrections(
    authors: list[dict[str, Any]],
    registered_authors: list[dict[str, Any]],
    correction: dict[str, Any],
) -> list[dict[str, Any]]:
    author_specs = correction.get("authors", [])
    if not author_specs:
        return authors
    corrected = [
        merged_author_record(spec, authors, registered_authors)
        for spec in author_specs
        if spec.get("name")
    ]
    return corrected


def merge_registered_author_metadata(
    authors: list[dict[str, Any]], registered_authors: list[dict[str, Any]]
) -> None:
    """Supplement TEI authors from registry data using unambiguous surnames."""
    for registered in registered_authors:
        identifiers = registered.get("identifiers", [])
        if not registered.get("family"):
            continue
        matches = [
            author
            for author in authors
            if author_names_match(author, registered)
        ]
        if len(matches) != 1:
            continue
        registered_orcids = {
            identifier.get("value")
            for identifier in identifiers
            if identifier.get("type") == "ORCID" and identifier.get("value")
        }
        if registered_orcids:
            matches[0]["identifiers"] = [
                identifier
                for identifier in matches[0].get("identifiers", [])
                if identifier.get("type") != "ORCID"
                or identifier.get("value") in registered_orcids
            ]
        existing = {
            (identifier.get("type"), identifier.get("value"))
            for identifier in matches[0].get("identifiers", [])
        }
        for identifier in identifiers:
            key = (identifier.get("type"), identifier.get("value"))
            if key not in existing:
                matches[0]["identifiers"].append(identifier)
        if not matches[0].get("affiliations") and registered.get("affiliations"):
            matches[0]["affiliations"] = list(registered["affiliations"])


def resolve_duplicate_orcids(
    authors: list[dict[str, Any]], registered_authors: list[dict[str, Any]]
) -> None:
    """Resolve GROBID-shifted ORCIDs using the official DOI author deposit."""
    occurrences: dict[str, list[dict[str, Any]]] = {}
    for author in authors:
        for identifier in author.get("identifiers", []):
            if identifier.get("type") == "ORCID":
                occurrences.setdefault(str(identifier.get("value")), []).append(author)
    for orcid, owners in occurrences.items():
        if len(owners) < 2:
            continue
        registered_owners = [
            author
            for author in registered_authors
            if any(
                identifier.get("type") == "ORCID"
                and identifier.get("value") == orcid
                for identifier in author.get("identifiers", [])
            )
        ]
        keep: dict[str, Any] | None = None
        if len(registered_owners) == 1:
            matches = [
                author
                for author in owners
                if author_names_match(author, registered_owners[0])
            ]
            if len(matches) == 1:
                keep = matches[0]
        for author in owners:
            if author is keep:
                continue
            author["identifiers"] = [
                identifier
                for identifier in author["identifiers"]
                if identifier.get("type") != "ORCID"
                or identifier.get("value") != orcid
            ]


def normalized_name_tokens(value: str) -> list[str]:
    value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value).casefold()
        if not unicodedata.combining(character)
    )
    return re.findall(r"[^\W_]+", value, flags=re.UNICODE)


def author_names_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_family = normalized_name_tokens(str(left.get("family", "")))
    right_family = normalized_name_tokens(str(right.get("family", "")))
    if not left_family or not right_family or left_family[-1] != right_family[-1]:
        return False
    left_given = normalized_name_tokens(
        str(left.get("given", "") or left.get("name", ""))
    )
    right_given = normalized_name_tokens(
        str(right.get("given", "") or right.get("name", ""))
    )
    if not left_given or not right_given:
        return False
    first_left, first_right = left_given[0], right_given[0]
    return (
        first_left == first_right
        or (len(first_left) == 1 and first_right.startswith(first_left))
        or (len(first_right) == 1 and first_left.startswith(first_right))
        or (
            min(len(first_left), len(first_right)) >= 3
            and (
                first_left.startswith(first_right) or first_right.startswith(first_left)
            )
        )
    )


def extract_keywords(root: ET.Element) -> list[dict[str, str]]:
    keywords: list[dict[str, str]] = []
    seen: set[str] = set()
    for term in root.findall(".//tei:teiHeader//tei:keywords/tei:term", TEI_NS):
        value = element_text(term)
        if value and value not in seen:
            seen.add(value)
            keywords.append({"value": value, "source": "GROBID TEI"})
    return keywords


def extract_funders(root: ET.Element) -> list[dict[str, Any]]:
    funders: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[tuple[str, str], ...], tuple[str, ...]]] = set()
    xml_id = "{http://www.w3.org/XML/1998/namespace}id"
    funding_organizations = {
        organization.attrib.get(xml_id, ""): organization
        for organization in root.findall(".//tei:listOrg[@type='funding']/tei:org", TEI_NS)
        if organization.attrib.get(xml_id)
    }
    for funder in root.findall(".//tei:teiHeader//tei:funder", TEI_NS):
        organizations = [
            {
                "type": organization.attrib.get("type", "organization"),
                "name": element_text(organization),
            }
            for organization in funder.findall("tei:orgName", TEI_NS)
            if element_text(organization)
        ]
        if not organizations and element_text(funder):
            organizations = [{"type": "organization", "name": element_text(funder)}]
        identifiers: list[dict[str, str]] = []
        award_numbers: list[str] = []
        for reference in funder.attrib.get("ref", "").split():
            linked = funding_organizations.get(reference.lstrip("#"))
            if linked is None:
                continue
            for organization in linked.findall("tei:orgName", TEI_NS):
                item = {
                    "type": organization.attrib.get("type", "organization"),
                    "name": element_text(organization),
                }
                if item["name"] and item not in organizations:
                    organizations.append(item)
            for identifier in linked.findall("tei:idno", TEI_NS):
                value = element_text(identifier)
                identifier_type = identifier.attrib.get("type", "identifier")
                if value:
                    identifiers.append({"type": identifier_type, "value": value})
                    if identifier_type == "grant-number":
                        award_numbers.append(value)
        key = (
            funder.attrib.get("ref", ""),
            tuple((item["type"], item["name"]) for item in organizations),
            tuple(award_numbers),
        )
        if organizations and key not in seen:
            seen.add(key)
            funders.append(
                {
                    "ref": key[0],
                    "source": "GROBID TEI",
                    "organizations": organizations,
                    "identifiers": identifiers,
                    "award_numbers": award_numbers,
                }
            )
    return funders


def load_registered_subjects_and_funders(
    stem: str, metadata_dir: Path
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Load keyword and funding metadata from saved DOI registry records."""
    crossref_file = metadata_dir / f"{stem}.json"
    if crossref_file.is_file():
        message = json.loads(crossref_file.read_text(encoding="utf-8")).get("message", {})
        keywords = [
            {"value": str(value), "source": "Crossref"}
            for value in message.get("subject", [])
            if str(value).strip()
        ]
        funders = []
        for funder in message.get("funder", []) or []:
            name = str(funder.get("name", "")).strip()
            identifiers = []
            doi = str(funder.get("DOI", "")).strip()
            if doi:
                identifiers.append({"type": "DOI", "value": doi})
            awards = [str(value) for value in funder.get("award", []) if str(value).strip()]
            if name or identifiers or awards:
                funders.append(
                    {
                        "ref": "",
                        "source": "Crossref",
                        "organizations": (
                            [{"type": "funder", "name": name}] if name else []
                        ),
                        "identifiers": identifiers,
                        "award_numbers": awards,
                    }
                )
        return keywords, funders
    return [], []


def merge_unique_metadata(
    extracted: list[dict[str, Any]], registered: list[dict[str, Any]], field: str
) -> list[dict[str, Any]]:
    """Append registry items whose normalized primary value is not already present."""
    def identity(item: dict[str, Any]) -> str:
        if field == "keywords":
            return re.sub(r"\W", "", str(item.get("value", "")).casefold())
        names = item.get("organizations", [])
        return re.sub(
            r"\W", "", "|".join(str(value.get("name", "")) for value in names).casefold()
        )

    seen = {identity(item) for item in extracted if identity(item)}
    merged = list(extracted)
    for item in registered:
        key = identity(item)
        if key and key not in seen:
            seen.add(key)
            merged.append(item)
    return merged


def render_article_metadata(
    authors: list[dict[str, Any]],
    author_source: str,
    keywords: list[dict[str, str]],
    funders: list[dict[str, Any]],
) -> list[str]:
    """Render the stable, machine-readable k2p article metadata HTML schema."""
    parts = [
        '<section id="article-metadata" class="article-metadata" '
        'data-schema="k2p-article-metadata" data-schema-version="1">',
        "<h2>Article Metadata</h2>",
        f'<section class="metadata-authors" data-field="authors" data-count="{len(authors)}" '
        f'data-source="{html.escape(author_source)}">',
        "<h3>Authors</h3>",
        '<ol class="author-list">',
    ]
    for index, author in enumerate(authors, start=1):
        corresponding = "true" if author.get("corresponding") else "false"
        parts.extend(
            [
                f'<li class="author" data-index="{index}" data-corresponding="{corresponding}">',
                f'<span class="author-name" data-field="name">{html.escape(str(author["name"]))}</span>',
                f'<ul class="author-identifiers" data-field="identifiers" data-count="{len(author["identifiers"])}">',
            ]
        )
        for identifier in author["identifiers"]:
            identifier_type = str(identifier["type"])
            identifier_value = str(identifier["value"])
            identifier_source = str(identifier.get("source", ""))
            parts.append(
                f'<li class="author-identifier" data-type="{html.escape(identifier_type)}" '
                f'data-value="{html.escape(identifier_value)}" '
                f'data-source="{html.escape(identifier_source)}">'
                f'<a href="https://orcid.org/{html.escape(identifier_value)}">'
                f'{html.escape(identifier_value)}</a></li>'
            )
        parts.extend(
            [
                "</ul>",
                f'<ul class="author-emails" data-field="emails" data-count="{len(author["emails"])}">',
            ]
        )
        parts.extend(
            f'<li class="author-email"><a href="mailto:{html.escape(email)}">{html.escape(email)}</a></li>'
            for email in author["emails"]
        )
        parts.extend(
            [
                "</ul>",
                f'<ul class="author-affiliations" data-field="affiliations" data-count="{len(author["affiliations"])}">',
            ]
        )
        for affiliation in author["affiliations"]:
            parts.extend(
                [
                    f'<li class="author-affiliation" data-key="{html.escape(str(affiliation["key"]))}" '
                    f'data-source="{html.escape(str(affiliation.get("source", "")))}">',
                    f'<ul class="affiliation-organizations" data-field="organizations" data-count="{len(affiliation["organizations"])}">',
                ]
            )
            parts.extend(
                f'<li class="organization" data-type="{html.escape(str(organization["type"]))}">'
                f'{html.escape(str(organization["name"]))}</li>'
                for organization in affiliation["organizations"]
            )
            parts.extend(
                [
                    "</ul>",
                    f'<address class="affiliation-address" data-field="address" data-count="{len(affiliation["address"])}">',
                ]
            )
            parts.extend(
                f'<span class="address-part" data-type="{html.escape(str(address_part["type"]))}" '
                f'data-key="{html.escape(str(address_part["key"]))}">'
                f'{html.escape(str(address_part["value"]))}</span>'
                for address_part in affiliation["address"]
            )
            parts.extend(["</address>", "</li>"])
        parts.extend(["</ul>", "</li>"])
    parts.extend(
        [
            "</ol>",
            "</section>",
            f'<section class="metadata-keywords" data-field="keywords" data-count="{len(keywords)}">',
            "<h3>Keywords</h3>",
            '<ul class="keyword-list">',
        ]
    )
    parts.extend(
        f'<li class="keyword" data-source="{html.escape(keyword["source"])}">'
        f'{html.escape(keyword["value"])}</li>'
        for keyword in keywords
    )
    parts.extend(
        [
            "</ul>",
            "</section>",
            f'<section class="metadata-funding" data-field="funders" data-count="{len(funders)}">',
            "<h3>Funding</h3>",
            '<ul class="funder-list">',
        ]
    )
    for funder in funders:
        parts.extend(
            [
                f'<li class="funder" data-ref="{html.escape(str(funder["ref"]))}" '
                f'data-source="{html.escape(str(funder.get("source", "")))}">',
                f'<ul class="funder-organizations" data-field="organizations" data-count="{len(funder["organizations"])}">',
            ]
        )
        parts.extend(
            f'<li class="funder-organization" data-type="{html.escape(str(organization["type"]))}">'
            f'{html.escape(str(organization["name"]))}</li>'
            for organization in funder["organizations"]
        )
        parts.extend(
            [
                "</ul>",
                f'<ul class="funder-identifiers" data-field="identifiers" data-count="{len(funder["identifiers"])}">',
            ]
        )
        parts.extend(
            f'<li class="funder-identifier" data-type="{html.escape(str(identifier["type"]))}" '
            f'data-value="{html.escape(str(identifier["value"]))}">'
            f'{html.escape(str(identifier["value"]))}</li>'
            for identifier in funder["identifiers"]
        )
        parts.extend(
            [
                "</ul>",
                f'<ul class="funding-awards" data-field="award-numbers" data-count="{len(funder["award_numbers"])}">',
            ]
        )
        parts.extend(
            f'<li class="funding-award">{html.escape(str(award))}</li>'
            for award in funder["award_numbers"]
        )
        parts.extend(["</ul>", "</li>"])
    parts.extend(["</ul>", "</section>", "</section>"])
    return parts


def render_paragraph(element: ET.Element) -> str:
    text = element_text_with_target_urls(element)
    if not text:
        return ""
    attrs = []
    xml_id = element.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
    if xml_id:
        attrs.append(f'id="{html.escape(xml_id)}"')
    attr_text = " " + " ".join(attrs) if attrs else ""
    return f"<p{attr_text}>{html.escape(text)}</p>"


def render_text_block(element: ET.Element, class_name: str) -> str:
    text = element_text_with_target_urls(element)
    if not text:
        return ""
    attrs = [f'class="{html.escape(class_name)}"']
    xml_id = element.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
    if xml_id:
        attrs.append(f'id="{html.escape(xml_id)}"')
    return f"<p {' '.join(attrs)}>{html.escape(text)}</p>"


def render_div(div: ET.Element, depth: int = 2) -> list[str]:
    parts: list[str] = []
    heading_level = min(max(depth, 2), 6)
    head = div.find("tei:head", TEI_NS)
    if head is not None and element_text(head):
        parts.append(f"<h{heading_level}>{html.escape(element_text(head))}</h{heading_level}>")
    for child in div:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = render_paragraph(child)
            if paragraph:
                parts.append(paragraph)
        elif tag == "div":
            parts.extend(render_div(child, depth + 1))
        elif tag in {"figure", "figDesc", "note", "table"}:
            block = render_text_block(child, tag)
            if block:
                parts.append(block)
    return parts


def render_bibliography(root: ET.Element) -> list[str]:
    entries = root.findall(".//tei:listBibl/tei:biblStruct", TEI_NS)
    if not entries:
        return []
    parts = ["<section id=\"references\">", "<h2>References</h2>", "<ol>"]
    for entry in entries:
        text = element_text_with_target_urls(entry)
        if text:
            parts.append(f"<li>{html.escape(text)}</li>")
    parts.extend(["</ol>", "</section>"])
    return parts


def render_back_matter(root: ET.Element) -> list[str]:
    back = root.find(".//tei:text/tei:back", TEI_NS)
    if back is None:
        return []
    parts: list[str] = []
    for child in back:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "listBibl":
            continue
        if not parts:
            parts.extend(["<section id=\"back-matter\">", "<h2>Back Matter</h2>"])
        if tag == "div":
            parts.extend(render_div(child))
        elif tag == "p":
            rendered = render_paragraph(child)
            if rendered:
                parts.append(rendered)
        elif tag in {"figure", "figDesc", "note", "table"}:
            block = render_text_block(child, tag)
            if block:
                parts.append(block)
        else:
            block = render_text_block(child, tag)
            if block:
                parts.append(block)
    if parts:
        parts.append("</section>")
    return parts


def tei_to_html(tei_bytes: bytes, metadata: dict[str, Any]) -> tuple[str, dict[str, int | str]]:
    root = ET.fromstring(tei_bytes)
    title = find_title(root)
    author_records = extract_authors(root)
    registered_authors = list(metadata.get("_fallback_authors", []))
    author_source = "GROBID TEI" if author_records else ""
    if author_records:
        merge_registered_author_metadata(author_records, registered_authors)
        resolve_duplicate_orcids(author_records, registered_authors)
    else:
        author_records = registered_authors
        author_source = (
            str(metadata.get("_fallback_author_source", "")) if author_records else ""
        )
    correction = metadata.get("_metadata_correction", {})
    if isinstance(correction, dict) and correction.get("authors"):
        author_records = apply_author_corrections(
            author_records, registered_authors, correction
        )
        author_source = str(correction.get("author_source", "Curated article metadata"))
    authors = [str(author["name"]) for author in author_records]
    registered_keywords = list(metadata.get("_registered_keywords", []))
    registered_funders = list(metadata.get("_registered_funders", []))
    keywords = merge_unique_metadata(
        extract_keywords(root), registered_keywords, "keywords"
    )
    funders = merge_unique_metadata(
        extract_funders(root), registered_funders, "funders"
    )
    abstract_div = root.find(".//tei:profileDesc/tei:abstract", TEI_NS)
    body = root.find(".//tei:text/tei:body", TEI_NS)
    html_metadata = {
        key: value for key, value in metadata.items() if not key.startswith("_")
    }
    orcid_count = sum(
        identifier.get("type") == "ORCID"
        for author in author_records
        for identifier in author["identifiers"]
    )
    affiliation_count = sum(len(author["affiliations"]) for author in author_records)
    award_count = sum(len(funder["award_numbers"]) for funder in funders)
    html_metadata.update(
        {
            "authors": authors,
            "author_source": author_source,
            "orcid_count": orcid_count,
            "affiliation_count": affiliation_count,
            "keyword_count": len(keywords),
            "funder_count": len(funders),
            "funding_award_count": award_count,
            "metadata_schema": "k2p-article-metadata",
            "metadata_schema_version": 1,
        }
    )
    metadata_json = json.dumps(html_metadata, ensure_ascii=False, sort_keys=True)
    parts = [
        "<!doctype html>",
        "<html>",
        "<head>",
        "<meta charset=\"utf-8\">",
        f"<meta name=\"article:source_pdf\" content=\"{html.escape(str(metadata.get('source_pdf', '')))}\">",
        f"<meta name=\"article:tei_file\" content=\"{html.escape(str(metadata.get('tei_file', '')))}\">",
        f"<meta name=\"article:html_file\" content=\"{html.escape(str(metadata.get('html_file', '')))}\">",
        f"<meta name=\"article:text_extractor\" content=\"{html.escape(str(metadata.get('text_extractor', '')))}\">",
        f"<meta name=\"article:text_stage\" content=\"{html.escape(str(metadata.get('text_stage', '')))}\">",
        f"<meta name=\"article:author_source\" content=\"{html.escape(author_source)}\">",
        f"<meta name=\"citation_title\" content=\"{html.escape(title)}\">",
    ]
    parts.extend(
        f'<meta name="citation_author" content="{html.escape(author)}">'
        for author in authors
    )
    parts.extend([
        f"<title>{html.escape(title)}</title>",
        "<script type=\"application/json\" id=\"article-html-metadata\">"
        + html.escape(metadata_json)
        + "</script>",
        "</head>",
        "<body>",
        "<!-- article_html_metadata: " + html.escape(metadata_json) + " -->",
        f"<h1>{html.escape(title)}</h1>",
    ])
    parts.extend(render_article_metadata(author_records, author_source, keywords, funders))
    if abstract_div is not None:
        parts.append("<section id=\"abstract\">")
        parts.append("<h2>Abstract</h2>")
        for paragraph in abstract_div.findall(".//tei:p", TEI_NS):
            rendered = render_paragraph(paragraph)
            if rendered:
                parts.append(rendered)
        parts.append("</section>")
    if body is not None:
        parts.append("<main>")
        for child in body:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "div":
                parts.extend(render_div(child))
            elif tag == "p":
                rendered = render_paragraph(child)
                if rendered:
                    parts.append(rendered)
            elif tag in {"figure", "figDesc", "note", "table"}:
                block = render_text_block(child, tag)
                if block:
                    parts.append(block)
        parts.append("</main>")
    parts.extend(render_back_matter(root))
    parts.extend(render_bibliography(root))
    parts.extend(["</body>", "</html>"])
    html_text = "\n".join(parts) + "\n"
    stats = {
        "title": title,
        "authors": len(authors),
        "author_source": author_source,
        "orcids": orcid_count,
        "affiliations": affiliation_count,
        "keywords": len(keywords),
        "funders": len(funders),
        "funding_awards": award_count,
        "tei_text_chars": len(" ".join(root.itertext())),
        "tei_divs": len(root.findall(".//tei:div", TEI_NS)),
        "tei_paragraphs": len(root.findall(".//tei:p", TEI_NS)),
        "tei_bibliography_entries": len(root.findall(".//tei:listBibl/tei:biblStruct", TEI_NS)),
        "html_bytes": len(html_text.encode("utf-8")),
    }
    return html_text, stats


def main() -> int:
    args = parse_args()
    pdf_files = select_pdf_files(args)
    metadata_corrections = load_metadata_corrections(args.metadata_corrections)

    files_needing_grobid = []
    for pdf_file in pdf_files:
        stem = pdf_file.stem
        html_file = args.output_dir / f"{stem}.html"
        tei_file = args.tei_dir / f"{stem}.tei.xml"
        html_exists = html_file.exists() and html_file.stat().st_size > 0
        reusable_tei = tei_file.exists() and tei_file.stat().st_size > 0
        if (args.all or not html_exists) and not (args.reuse_existing_tei and reusable_tei):
            files_needing_grobid.append(pdf_file)

    if files_needing_grobid and not grobid_is_alive(args.grobid_url):
        raise SystemExit(
            f"GROBID service is not available at {args.grobid_url}; "
            f"it is required for {len(files_needing_grobid)} PDF(s)"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.tei_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    processed = 0
    skipped = 0
    failed = 0
    for pdf_file in pdf_files:
        # Preserve the source filename exactly, changing only the extension.
        stem = pdf_file.stem
        tei_file = args.tei_dir / f"{stem}.tei.xml"
        html_file = args.output_dir / f"{stem}.html"
        if not args.all and html_file.exists() and html_file.stat().st_size > 0:
            rows.append(
                {
                    "pdf_file": repository_path(pdf_file),
                    "tei_file": repository_path(tei_file),
                    "html_file": repository_path(html_file),
                    "status": "existing",
                    "title": "",
                    "authors": "",
                    "author_source": "",
                    "orcids": "",
                    "affiliations": "",
                    "keywords": "",
                    "funders": "",
                    "funding_awards": "",
                    "tei_text_chars": "",
                    "tei_divs": "",
                    "tei_paragraphs": "",
                    "tei_bibliography_entries": "",
                    "html_bytes": str(html_file.stat().st_size),
                    "error": "",
                }
            )
            skipped += 1
            continue

        try:
            metadata = {
                "source_pdf": repository_path(pdf_file),
                "tei_file": repository_path(tei_file),
                "html_file": repository_path(html_file),
                "text_extractor": "GROBID",
                "grobid_url": args.grobid_url,
                "text_stage": "semantic_html_from_tei",
            }
            fallback_authors, fallback_author_source = load_registered_authors(
                stem, args.registration_metadata_dir
            )
            registered_keywords, registered_funders = load_registered_subjects_and_funders(
                stem, args.registration_metadata_dir
            )
            metadata["_fallback_authors"] = fallback_authors
            metadata["_fallback_author_source"] = fallback_author_source
            metadata["_registered_keywords"] = registered_keywords
            metadata["_registered_funders"] = registered_funders
            metadata["_metadata_correction"] = metadata_corrections.get(stem, {})
            reuse_tei = (
                args.reuse_existing_tei
                and tei_file.exists()
                and tei_file.stat().st_size > 0
            )
            if reuse_tei:
                tei_bytes = tei_file.read_bytes()
            else:
                tei_bytes = request_grobid_tei(pdf_file, args.grobid_url)
            html_text, stats = tei_to_html(tei_bytes, metadata)
            if not reuse_tei:
                tei_file.write_bytes(tei_bytes)
            html_file.write_text(html_text, encoding="utf-8")
            rows.append(
                {
                    "pdf_file": repository_path(pdf_file),
                    "tei_file": repository_path(tei_file),
                    "html_file": repository_path(html_file),
                    "status": "ok",
                    "title": str(stats["title"]),
                    "authors": str(stats["authors"]),
                    "author_source": str(stats["author_source"]),
                    "orcids": str(stats["orcids"]),
                    "affiliations": str(stats["affiliations"]),
                    "keywords": str(stats["keywords"]),
                    "funders": str(stats["funders"]),
                    "funding_awards": str(stats["funding_awards"]),
                    "tei_text_chars": str(stats["tei_text_chars"]),
                    "tei_divs": str(stats["tei_divs"]),
                    "tei_paragraphs": str(stats["tei_paragraphs"]),
                    "tei_bibliography_entries": str(stats["tei_bibliography_entries"]),
                    "html_bytes": str(stats["html_bytes"]),
                    "error": "",
                }
            )
            processed += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            rows.append(
                {
                    "pdf_file": repository_path(pdf_file),
                    "tei_file": repository_path(tei_file),
                    "html_file": repository_path(html_file),
                    "status": "failed",
                    "title": "",
                    "authors": "",
                    "author_source": "",
                    "orcids": "",
                    "affiliations": "",
                    "keywords": "",
                    "funders": "",
                    "funding_awards": "",
                    "tei_text_chars": "",
                    "tei_divs": "",
                    "tei_paragraphs": "",
                    "tei_bibliography_entries": "",
                    "html_bytes": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    with args.manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            lineterminator="\n",
            fieldnames=[
                "pdf_file",
                "tei_file",
                "html_file",
                "status",
                "title",
                "authors",
                "author_source",
                "orcids",
                "affiliations",
                "keywords",
                "funders",
                "funding_awards",
                "tei_text_chars",
                "tei_divs",
                "tei_paragraphs",
                "tei_bibliography_entries",
                "html_bytes",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"GROBID HTML extraction processed {processed}, skipped {skipped}, "
        f"failed {failed}, total {len(rows)}; output: {args.output_dir}; "
        f"TEI: {args.tei_dir}; manifest: {args.manifest}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
