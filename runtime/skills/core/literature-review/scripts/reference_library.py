#!/usr/bin/env python3
"""Deterministic, local-only RIS/BibTeX/CSL-JSON reference library tool."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


SCHEMA_VERSION = "ai4heor-reference-library/v1"
MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 10_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
PMID_RE = re.compile(r"^[0-9]{1,12}$")
SAFE_BIB_KEY_RE = re.compile(r"^[A-Za-z0-9_:.+-]+$")

CSL_TYPES = {
    "article", "article-journal", "article-magazine", "article-newspaper",
    "book", "chapter", "dataset", "document", "entry", "event", "figure",
    "graphic", "interview", "legal_case", "legislation", "manuscript", "map",
    "motion_picture", "pamphlet", "paper-conference", "patent", "post",
    "post-weblog", "regulation", "report", "review", "software", "speech",
    "standard", "thesis", "webpage",
}
SCALAR_FIELDS = (
    "citation-key", "title", "container-title", "container-title-short",
    "abstract", "volume", "issue", "page", "publisher", "publisher-place",
    "DOI", "PMID", "PMCID", "ISBN", "ISSN", "URL", "language", "keyword",
    "note", "genre",
)
NAME_FIELDS = ("author", "editor")
CSL_INPUT_FIELDS = {"id", "type", "issued", *SCALAR_FIELDS, *NAME_FIELDS}
INTERNAL_FIELDS = {"source_bindings", "conflicts"}

RIS_TYPE_TO_CSL = {
    "JOUR": "article-journal", "MGZN": "article-magazine",
    "NEWS": "article-newspaper", "BOOK": "book", "CHAP": "chapter",
    "CONF": "paper-conference", "CPAPER": "paper-conference",
    "THES": "thesis", "RPRT": "report", "DATA": "dataset",
    "ELEC": "webpage", "WEB": "webpage", "GEN": "document",
    "UNPB": "manuscript",
}
CSL_TO_RIS_TYPE = {
    "article-journal": "JOUR", "article-magazine": "MGZN",
    "article-newspaper": "NEWS", "book": "BOOK", "chapter": "CHAP",
    "paper-conference": "CPAPER", "thesis": "THES", "report": "RPRT",
    "dataset": "DATA", "webpage": "ELEC", "manuscript": "UNPB",
}
BIB_TYPE_TO_CSL = {
    "article": "article-journal", "book": "book",
    "inproceedings": "paper-conference", "conference": "paper-conference",
    "incollection": "chapter", "techreport": "report",
    "phdthesis": "thesis", "mastersthesis": "thesis",
    "unpublished": "manuscript", "misc": "document",
}
CSL_TO_BIB_TYPE = {
    "article-journal": "article", "book": "book", "chapter": "incollection",
    "paper-conference": "inproceedings", "report": "techreport",
    "thesis": "phdthesis", "manuscript": "unpublished",
}


class ContractError(ValueError):
    """A user-visible contract failure."""


@dataclass(frozen=True)
class ParsedRecord:
    record: dict[str, Any]
    source_key: str
    warnings: tuple[str, ...] = ()


def normalized_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be a string")
    text = " ".join(unicodedata.normalize("NFKC", value).split())
    if not text:
        raise ContractError(f"{field} must not be empty")
    if "\x00" in text:
        raise ContractError(f"{field} must not contain NUL")
    return text


def normalize_doi(value: str) -> str:
    doi = normalized_text(value, "DOI")
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = doi.rstrip(".,;)").lower()
    if not DOI_RE.fullmatch(doi):
        raise ContractError(f"invalid DOI: {value}")
    return doi


def normalize_pmid(value: str) -> str:
    pmid = re.sub(r"^pmid:\s*", "", normalized_text(value, "PMID"), flags=re.IGNORECASE)
    if not PMID_RE.fullmatch(pmid):
        raise ContractError(f"invalid PMID: {value}")
    return pmid


def normalize_url(value: str) -> str:
    url = normalized_text(value, "URL")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ContractError(f"URL must be an absolute http(s) URL: {value}")
    return url


def normalize_name(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ContractError(f"{field} names must be objects")
    unknown = set(value) - {"family", "given", "literal"}
    if unknown:
        raise ContractError(f"unsupported {field} name fields: {', '.join(sorted(unknown))}")
    if "literal" in value:
        if set(value) != {"literal"}:
            raise ContractError(f"{field} literal names cannot mix with family or given")
        return {"literal": normalized_text(value["literal"], f"{field}.literal")}
    if "family" not in value:
        raise ContractError(f"{field} personal names require family")
    result = {"family": normalized_text(value["family"], f"{field}.family")}
    if value.get("given"):
        result["given"] = normalized_text(value["given"], f"{field}.given")
    return result


def normalize_date(value: Any) -> dict[str, list[list[int]]]:
    if not isinstance(value, dict) or set(value) != {"date-parts"}:
        raise ContractError("issued must contain only date-parts")
    parts = value["date-parts"]
    if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], list):
        raise ContractError("issued date-parts must contain one date")
    date = parts[0]
    if not 1 <= len(date) <= 3 or any(isinstance(item, bool) or not isinstance(item, int) for item in date):
        raise ContractError("issued date must contain integer year, optional month, optional day")
    year = date[0]
    if not 1000 <= year <= 3000:
        raise ContractError("issued year is outside 1000..3000")
    if len(date) >= 2 and not 1 <= date[1] <= 12:
        raise ContractError("issued month is outside 1..12")
    if len(date) == 3 and not 1 <= date[2] <= 31:
        raise ContractError("issued day is outside 1..31")
    return {"date-parts": [date]}


def parse_date_text(value: str) -> dict[str, list[list[int]]]:
    match = re.search(r"(?<!\d)(1\d{3}|2\d{3})(?:[-/](\d{1,2}))?(?:[-/](\d{1,2}))?", value)
    if not match:
        raise ContractError(f"date does not contain a supported year: {value}")
    date = [int(part) for part in match.groups() if part is not None]
    return normalize_date({"date-parts": [date]})


def issued_year(record: dict[str, Any]) -> str:
    try:
        return str(record["issued"]["date-parts"][0][0])
    except (KeyError, IndexError, TypeError):
        return ""


def comparison_text(value: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKC", value).casefold() if ch.isalnum())


def first_author_key(record: dict[str, Any]) -> str:
    authors = record.get("author", [])
    if not authors:
        return ""
    first = authors[0]
    return comparison_text(first.get("literal") or first.get("family") or "")


def stable_id(record: dict[str, Any]) -> str:
    if record.get("DOI"):
        return f"doi:{record['DOI']}"
    if record.get("PMID"):
        return f"pmid:{record['PMID']}"
    material = "|".join(
        (comparison_text(record["title"]), issued_year(record), first_author_key(record))
    )
    return "ref:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContractError("record must be an object")
    unknown = set(raw) - CSL_INPUT_FIELDS - INTERNAL_FIELDS
    if unknown:
        raise ContractError(f"unsupported record fields: {', '.join(sorted(unknown))}")
    if "type" not in raw or "title" not in raw:
        raise ContractError("record requires type and title")
    record_type = normalized_text(raw["type"], "record type")
    if record_type not in CSL_TYPES:
        raise ContractError(f"unsupported CSL type: {record_type}")
    result: dict[str, Any] = {"type": record_type}
    for field in SCALAR_FIELDS:
        if raw.get(field) in (None, ""):
            continue
        if field == "DOI":
            result[field] = normalize_doi(raw[field])
        elif field == "PMID":
            result[field] = normalize_pmid(raw[field])
        elif field == "URL":
            result[field] = normalize_url(raw[field])
        else:
            result[field] = normalized_text(raw[field], field)
    for field in NAME_FIELDS:
        if field not in raw:
            continue
        if not isinstance(raw[field], list) or not raw[field]:
            raise ContractError(f"{field} must be a non-empty array")
        result[field] = [normalize_name(item, field) for item in raw[field]]
    if "issued" in raw:
        result["issued"] = normalize_date(raw["issued"])
    if "title" not in result:
        raise ContractError("record title must not be empty")
    result["id"] = stable_id(result)
    return ordered_record(result)


def ordered_record(record: dict[str, Any]) -> dict[str, Any]:
    order = (
        "id", "type", "citation-key", "title", "author", "editor", "issued",
        "container-title", "container-title-short", "volume", "issue", "page",
        "publisher", "publisher-place", "DOI", "PMID", "PMCID", "ISBN", "ISSN",
        "URL", "language", "keyword", "abstract", "note", "genre",
        "source_bindings", "conflicts",
    )
    return {key: record[key] for key in order if key in record}


def parse_ris(text: str) -> list[ParsedRecord]:
    records: list[ParsedRecord] = []
    current: dict[str, list[str]] | None = None
    index = 0
    tag_re = re.compile(r"^([A-Z0-9]{2})  - ?(.*)$")
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = tag_re.fullmatch(line)
        if not match:
            raise ContractError(f"RIS line {line_number} is not a supported tagged line")
        tag, value = match.groups()
        if tag == "TY":
            if current is not None:
                raise ContractError(f"RIS line {line_number} starts TY before the prior ER")
            current = {"TY": [normalized_text(value, "RIS TY")]}
            index += 1
        elif tag == "ER":
            if current is None:
                raise ContractError(f"RIS line {line_number} has ER without TY")
            records.append(ris_record(current, index))
            current = None
        else:
            if current is None:
                raise ContractError(f"RIS line {line_number} appears outside TY/ER")
            current.setdefault(tag, []).append(normalized_text(value, f"RIS {tag}"))
    if current is not None:
        raise ContractError("RIS record is missing ER terminator")
    if not records:
        raise ContractError("RIS input contains no records")
    return records


def first_tag(tags: dict[str, list[str]], names: Iterable[str]) -> str | None:
    for name in names:
        values = tags.get(name)
        if values:
            return values[0]
    return None


def parse_person_name(value: str) -> dict[str, str]:
    text = normalized_text(value, "name")
    if text.startswith("{") and text.endswith("}"):
        return {"literal": strip_outer_braces(text)}
    if "," in text:
        family, given = (part.strip() for part in text.split(",", 1))
        result = {"family": normalized_text(family, "name family")}
        if given:
            result["given"] = normalized_text(given, "name given")
        return result
    parts = text.split()
    if len(parts) == 1:
        return {"family": parts[0]}
    return {"family": parts[-1], "given": " ".join(parts[:-1])}


def ris_record(tags: dict[str, list[str]], index: int) -> ParsedRecord:
    ris_type = tags["TY"][0].upper()
    record: dict[str, Any] = {
        "type": RIS_TYPE_TO_CSL.get(ris_type, "document"),
        "title": first_tag(tags, ("TI", "T1", "CT", "BT")),
    }
    if not record["title"]:
        raise ContractError(f"RIS record {index} has no title")
    authors = [parse_person_name(value) for tag in ("AU", "A1", "A2", "A3", "A4") for value in tags.get(tag, [])]
    if authors:
        record["author"] = authors
    editors = [parse_person_name(value) for value in tags.get("ED", [])]
    if editors:
        record["editor"] = editors
    mapping = {
        "container-title": ("T2", "JF", "JO", "J1", "J2"),
        "volume": ("VL",), "issue": ("IS",), "publisher": ("PB",),
        "publisher-place": ("CY",), "DOI": ("DO",), "PMID": ("AN",),
        "URL": ("UR", "L1"), "abstract": ("AB", "N2"), "language": ("LA",),
        "ISSN": ("SN",), "note": ("N1",),
    }
    for field, names in mapping.items():
        value = first_tag(tags, names)
        if value:
            if field == "PMID" and not PMID_RE.fullmatch(re.sub(r"^PMID:\s*", "", value, flags=re.I)):
                continue
            record[field] = value
    date = first_tag(tags, ("PY", "Y1", "DA"))
    if date:
        record["issued"] = parse_date_text(date)
    start, end = first_tag(tags, ("SP",)), first_tag(tags, ("EP",))
    if start:
        record["page"] = f"{start}-{end}" if end else start
    keywords = tags.get("KW", [])
    if keywords:
        record["keyword"] = "; ".join(keywords)
    recognized = {
        "TY", "ER", "AU", "A1", "A2", "A3", "A4", "ED", "TI", "T1", "CT", "BT",
        "T2", "JF", "JO", "J1", "J2", "VL", "IS", "PB", "CY", "DO", "AN", "UR",
        "L1", "AB", "N2", "LA", "SN", "N1", "PY", "Y1", "DA", "SP", "EP", "KW",
    }
    warnings = []
    if ris_type not in RIS_TYPE_TO_CSL:
        warnings.append(f"RIS type {ris_type} mapped to document")
    unknown = sorted(set(tags) - recognized)
    if unknown:
        warnings.append("ignored RIS tags: " + ", ".join(unknown))
    source_key = first_tag(tags, ("AN",)) or str(index)
    return ParsedRecord(normalize_record(record), source_key, tuple(warnings))


def skip_bib_space(text: str, position: int) -> int:
    while position < len(text):
        if text[position].isspace():
            position += 1
        elif text[position] == "%":
            newline = text.find("\n", position)
            position = len(text) if newline < 0 else newline + 1
        else:
            break
    return position


def scan_bib_entries(text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    position = 0
    while (position := skip_bib_space(text, position)) < len(text):
        if text[position] != "@":
            raise ContractError(f"BibTeX contains unsupported text near byte {position}")
        type_match = re.match(r"@([A-Za-z]+)", text[position:])
        if not type_match:
            raise ContractError(f"BibTeX entry type is malformed near byte {position}")
        entry_type = type_match.group(1).lower()
        if entry_type in {"string", "preamble", "comment"}:
            raise ContractError(f"BibTeX @{entry_type} is not supported")
        if entry_type not in BIB_TYPE_TO_CSL:
            raise ContractError(f"unsupported BibTeX entry type: @{entry_type}")
        position += type_match.end()
        position = skip_bib_space(text, position)
        if position >= len(text) or text[position] not in "{(":
            raise ContractError(f"BibTeX @{entry_type} requires a braced or parenthesized body")
        opener = text[position]
        closer = "}" if opener == "{" else ")"
        start = position + 1
        stack = [closer]
        in_quote = False
        escaped = False
        position += 1
        while position < len(text) and stack:
            char = text[position]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_quote = not in_quote
            elif not in_quote and char in "{(":
                stack.append("}" if char == "{" else ")")
            elif not in_quote and char == stack[-1]:
                stack.pop()
            position += 1
        if stack:
            raise ContractError(f"BibTeX @{entry_type} body is not closed")
        entries.append((entry_type, text[start:position - 1]))
    if not entries:
        raise ContractError("BibTeX input contains no entries")
    return entries


def split_top_level(text: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    start = 0
    brace_depth = paren_depth = 0
    in_quote = escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
        elif not in_quote and char == "{":
            brace_depth += 1
        elif not in_quote and char == "}":
            brace_depth -= 1
        elif not in_quote and char == "(":
            paren_depth += 1
        elif not in_quote and char == ")":
            paren_depth -= 1
        elif not in_quote and brace_depth == 0 and paren_depth == 0 and char == delimiter:
            parts.append(text[start:index])
            start = index + 1
        if brace_depth < 0 or paren_depth < 0:
            raise ContractError("BibTeX field has unbalanced delimiters")
    if in_quote or brace_depth or paren_depth:
        raise ContractError("BibTeX field has unbalanced quotes or delimiters")
    parts.append(text[start:])
    return parts


def strip_outer_braces(value: str) -> str:
    text = value.strip()
    while text.startswith("{") and text.endswith("}"):
        depth = 0
        closes_at_end = False
        escaped = False
        for index, char in enumerate(text):
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    closes_at_end = index == len(text) - 1
                    break
        if not closes_at_end:
            break
        text = text[1:-1].strip()
    return text


def parse_bib_value(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ContractError("BibTeX field value must not be empty")
    if len(split_top_level(value, "#")) != 1:
        raise ContractError("BibTeX string concatenation (#) is not supported")
    if value.startswith("{") and value.endswith("}"):
        return normalized_text(value[1:-1], "BibTeX value")
    if value.startswith('"') and value.endswith('"'):
        return normalized_text(value[1:-1], "BibTeX value")
    if re.fullmatch(r"[0-9]+", value):
        return value
    raise ContractError(f"BibTeX macro or unsupported bare value: {value}")


def split_bib_names(value: str) -> list[dict[str, str]]:
    names: list[str] = []
    start = depth = 0
    for match in re.finditer(r"\s+and\s+", value, flags=re.IGNORECASE):
        depth = value[:match.start()].count("{") - value[:match.start()].count("}")
        if depth == 0:
            names.append(value[start:match.start()])
            start = match.end()
    names.append(value[start:])
    return [parse_person_name(name.strip()) for name in names if name.strip()]


def bib_record(entry_type: str, body: str, index: int) -> ParsedRecord:
    pieces = split_top_level(body, ",")
    citation_key = normalized_text(pieces[0], "BibTeX citation key")
    if not SAFE_BIB_KEY_RE.fullmatch(citation_key):
        raise ContractError(f"unsupported BibTeX citation key: {citation_key}")
    fields: dict[str, str] = {}
    for piece in pieces[1:]:
        if not piece.strip():
            continue
        match = re.fullmatch(r"\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(.+?)\s*", piece, flags=re.DOTALL)
        if not match:
            raise ContractError(f"malformed BibTeX field in {citation_key}: {piece.strip()}")
        name = match.group(1).lower()
        if name in fields:
            raise ContractError(f"duplicate BibTeX field {name} in {citation_key}")
        parsed_value = parse_bib_value(match.group(2))
        fields[name] = parsed_value if name in {"author", "editor"} else bib_unescape(strip_outer_braces(parsed_value))
    if "title" not in fields:
        raise ContractError(f"BibTeX entry {citation_key} has no title")
    record: dict[str, Any] = {
        "type": BIB_TYPE_TO_CSL[entry_type],
        "citation-key": citation_key,
        "title": fields["title"],
    }
    if "author" in fields:
        record["author"] = split_bib_names(fields["author"])
    if "editor" in fields:
        record["editor"] = split_bib_names(fields["editor"])
    mapping = {
        "journal": "container-title", "booktitle": "container-title",
        "volume": "volume", "number": "issue", "pages": "page",
        "publisher": "publisher", "address": "publisher-place", "doi": "DOI",
        "pmid": "PMID", "url": "URL", "abstract": "abstract", "language": "language",
        "keywords": "keyword", "note": "note", "isbn": "ISBN", "issn": "ISSN",
        "type": "genre",
    }
    for source, target in mapping.items():
        if source in fields:
            value = fields[source].replace("--", "-") if source == "pages" else fields[source]
            record[target] = value
    if "year" in fields:
        record["issued"] = parse_date_text(fields["year"])
    recognized = {"title", "author", "editor", "year", "month", *mapping}
    unknown = sorted(set(fields) - recognized)
    warnings = ("ignored BibTeX fields: " + ", ".join(unknown),) if unknown else ()
    return ParsedRecord(normalize_record(record), citation_key or str(index), warnings)


def parse_bibtex(text: str) -> list[ParsedRecord]:
    return [bib_record(entry_type, body, index) for index, (entry_type, body) in enumerate(scan_bib_entries(text), 1)]


def parse_csl_json(text: str) -> list[ParsedRecord]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ContractError(f"CSL-JSON is invalid JSON: {error.msg}") from error
    if not isinstance(payload, list) or not payload:
        raise ContractError("CSL-JSON must be a non-empty array")
    records: list[ParsedRecord] = []
    for index, item in enumerate(payload, 1):
        if not isinstance(item, dict):
            raise ContractError(f"CSL-JSON item {index} must be an object")
        if "id" not in item or "type" not in item:
            raise ContractError(f"CSL-JSON item {index} requires id and type")
        source_key = normalized_text(str(item["id"]), "CSL id")
        raw = {key: value for key, value in item.items() if key != "id"}
        records.append(ParsedRecord(normalize_record(raw), source_key))
    return records


def path_inside_workspace(workspace: Path, raw: str, *, must_exist: bool) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    absolute = Path(os.path.abspath(candidate))
    try:
        relative = absolute.relative_to(workspace)
    except ValueError as error:
        raise ContractError(f"path must stay inside the workspace: {raw}") from error
    current = workspace
    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if stat.S_ISLNK(current.lstat().st_mode):
                raise ContractError(f"symbolic links are not allowed: {raw}")
    if must_exist:
        if not absolute.exists():
            raise ContractError(f"file does not exist: {raw}")
        if not absolute.is_file():
            raise ContractError(f"path is not an ordinary file: {raw}")
    return absolute


def read_bounded(path: Path) -> bytes:
    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise ContractError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path.name}")
    raw = path.read_bytes()
    if len(raw) != size:
        raise ContractError(f"input changed while reading: {path.name}")
    return raw


def decode_utf8(raw: bytes, label: str) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ContractError(f"{label} must be UTF-8") from error


def detect_format(path: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    suffix = path.suffix.lower()
    mapping = {".ris": "ris", ".bib": "bibtex", ".json": "csl-json"}
    if suffix not in mapping:
        raise ContractError("cannot detect format; pass --format ris, bibtex, or csl-json")
    return mapping[suffix]


def choose_value(left: Any, right: Any) -> Any:
    candidates = [left, right]
    def score(value: Any) -> tuple[int, str]:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if isinstance(value, dict) and "date-parts" in value:
            detail = len(value["date-parts"][0]) * 1000
        elif isinstance(value, list):
            detail = len(value) * 1000
        else:
            detail = len(str(value))
        return detail, encoded.casefold()
    return max(candidates, key=score)


def add_conflict(record: dict[str, Any], field: str, left: Any, right: Any) -> None:
    encoded = {
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for value in (left, right)
    }
    existing = next((item for item in record.get("conflicts", []) if item["field"] == field), None)
    if existing:
        encoded.update(existing["values"])
    conflicts = [item for item in record.get("conflicts", []) if item["field"] != field]
    conflicts.append({"field": field, "values": sorted(encoded)})
    record["conflicts"] = sorted(conflicts, key=lambda item: item["field"])


def compatible_title_year(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if comparison_text(left["title"]) != comparison_text(right["title"]):
        return False
    if issued_year(left) != issued_year(right):
        return False
    for field in ("DOI", "PMID"):
        if left.get(field) and right.get(field) and left[field] != right[field]:
            return False
    return True


def same_record(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("DOI") and right.get("DOI") and left["DOI"] == right["DOI"]:
        return True
    if left.get("PMID") and right.get("PMID") and left["PMID"] == right["PMID"]:
        return True
    return compatible_title_year(left, right)


def merge_records(left: dict[str, Any], right: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    merged = json.loads(json.dumps(left, ensure_ascii=False))
    changed = False
    for field, value in right.items():
        if field in {"id", "source_bindings", "conflicts"}:
            continue
        if field not in merged:
            merged[field] = value
            changed = True
        elif merged[field] != value:
            chosen = choose_value(merged[field], value)
            add_conflict(merged, field, merged[field], value)
            if merged[field] != chosen:
                merged[field] = chosen
            changed = True
    bindings = {json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")): item for item in merged.get("source_bindings", [])}
    for item in right.get("source_bindings", []):
        bindings[json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))] = item
    sorted_bindings = [bindings[key] for key in sorted(bindings)]
    if sorted_bindings != merged.get("source_bindings", []):
        merged["source_bindings"] = sorted_bindings
        changed = True
    for conflict in right.get("conflicts", []):
        values = [json.loads(value) for value in conflict["values"]]
        if len(values) >= 2:
            add_conflict(merged, conflict["field"], values[0], values[1])
    merged["id"] = stable_id(merged)
    return ordered_record(merged), changed


def validate_binding(binding: Any) -> None:
    if not isinstance(binding, dict):
        raise ContractError("source binding must be an object")
    allowed = {"format", "path", "record_key", "sha256", "warnings"}
    if set(binding) - allowed or not {"format", "path", "record_key", "sha256"}.issubset(binding):
        raise ContractError("source binding fields are invalid")
    if binding["format"] not in {"ris", "bibtex", "csl-json"}:
        raise ContractError("source binding format is invalid")
    path = normalized_text(binding["path"], "source path")
    if Path(path).is_absolute() or ".." in Path(path).parts:
        raise ContractError("source binding path must be project-relative")
    if not SHA256_RE.fullmatch(binding["sha256"]):
        raise ContractError("source binding SHA-256 is invalid")
    normalized_text(binding["record_key"], "source record key")
    if "warnings" in binding:
        if not isinstance(binding["warnings"], list) or any(not isinstance(item, str) or not item for item in binding["warnings"]):
            raise ContractError("source binding warnings must be non-empty strings")


def validate_library(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "records"}:
        raise ContractError("library must contain only schema_version and records")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ContractError(f"unsupported library schema: {payload['schema_version']}")
    records = payload["records"]
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise ContractError(f"library records must be an array capped at {MAX_RECORDS}")
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            raise ContractError(f"library record {index} must be an object")
        if "id" not in record or "type" not in record or "title" not in record:
            raise ContractError(f"library record {index} requires id, record type, and title")
        if set(record) - CSL_INPUT_FIELDS - INTERNAL_FIELDS:
            raise ContractError(f"library record {index} contains unsupported fields")
        normalized = normalize_record({key: value for key, value in record.items() if key not in INTERNAL_FIELDS and key != "id"})
        if record["id"] != normalized["id"]:
            raise ContractError(f"library record {index} id is not canonical")
        if record["id"] in seen:
            raise ContractError(f"duplicate library id: {record['id']}")
        seen.add(record["id"])
        bindings = record.get("source_bindings")
        if not isinstance(bindings, list) or not bindings:
            raise ContractError(f"library record {index} requires source_bindings")
        for binding in bindings:
            validate_binding(binding)
        if bindings != sorted(bindings, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))):
            raise ContractError(f"library record {index} source_bindings are not sorted")
        conflicts = record.get("conflicts", [])
        if not isinstance(conflicts, list):
            raise ContractError(f"library record {index} conflicts must be an array")
        for conflict in conflicts:
            if not isinstance(conflict, dict) or set(conflict) != {"field", "values"}:
                raise ContractError(f"library record {index} conflict is invalid")
            if conflict["field"] in {"id", "source_bindings", "conflicts"}:
                raise ContractError(f"library record {index} conflict field is invalid")
            if not isinstance(conflict["values"], list) or len(conflict["values"]) < 2 or conflict["values"] != sorted(set(conflict["values"])):
                raise ContractError(f"library record {index} conflict values are invalid")
    if records != sorted(records, key=lambda item: item["id"]):
        raise ContractError("library records are not sorted by id")
    return payload


def load_library(path: Path) -> dict[str, Any]:
    raw = read_bounded(path)
    try:
        payload = json.loads(decode_utf8(raw, "library"))
    except json.JSONDecodeError as error:
        raise ContractError(f"library is invalid JSON: {error.msg}") from error
    return validate_library(payload)


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def import_records(workspace: Path, library_path: Path, input_path: Path, format_name: str) -> dict[str, Any]:
    source_raw = read_bounded(input_path)
    source_text = decode_utf8(source_raw, "import")
    parsers = {"ris": parse_ris, "bibtex": parse_bibtex, "csl-json": parse_csl_json}
    parsed = parsers[format_name](source_text)
    if len(parsed) > MAX_RECORDS:
        raise ContractError(f"import exceeds {MAX_RECORDS} records")
    payload = load_library(library_path) if library_path.exists() else {"schema_version": SCHEMA_VERSION, "records": []}
    source_hash = hashlib.sha256(source_raw).hexdigest()
    source_relative = input_path.relative_to(workspace).as_posix()
    records = list(payload["records"])
    added = updated = duplicates = 0
    warnings: list[str] = []
    for item in parsed:
        binding: dict[str, Any] = {
            "format": format_name,
            "path": source_relative,
            "record_key": item.source_key,
            "sha256": source_hash,
        }
        if item.warnings:
            binding["warnings"] = list(item.warnings)
            warnings.extend(f"{item.source_key}: {warning}" for warning in item.warnings)
        incoming = dict(item.record)
        incoming["source_bindings"] = [binding]
        matches = [index for index, existing in enumerate(records) if same_record(existing, incoming)]
        if len(matches) > 1:
            raise ContractError(f"record {item.source_key} matches multiple library records; resolve the library manually")
        if matches:
            index = matches[0]
            merged, changed = merge_records(records[index], incoming)
            if changed:
                records[index] = merged
                updated += 1
            else:
                duplicates += 1
        else:
            records.append(ordered_record(incoming))
            added += 1
    records.sort(key=lambda record: record["id"])
    result = {"schema_version": SCHEMA_VERSION, "records": records}
    validate_library(result)
    output = canonical_json(result)
    if not library_path.exists() or library_path.read_bytes() != output:
        atomic_write(library_path, output)
    return {
        "action": "import",
        "format": format_name,
        "input_path": source_relative,
        "input_sha256": source_hash,
        "library_path": library_path.relative_to(workspace).as_posix(),
        "library_sha256": hashlib.sha256(output).hexdigest(),
        "records_read": len(parsed),
        "records_added": added,
        "records_updated": updated,
        "duplicates_unchanged": duplicates,
        "library_records": len(records),
        "warnings": warnings,
    }


def csl_export_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record[key] for key in ("id", "type", *SCALAR_FIELDS, *NAME_FIELDS, "issued") if key in record}


def format_name_for_exchange(name: dict[str, str]) -> str:
    if "literal" in name:
        return name["literal"]
    return f"{name['family']}, {name['given']}" if name.get("given") else name["family"]


def export_ris(records: list[dict[str, Any]]) -> bytes:
    lines: list[str] = []
    for record in records:
        lines.append(f"TY  - {CSL_TO_RIS_TYPE.get(record['type'], 'GEN')}")
        for author in record.get("author", []):
            lines.append(f"AU  - {format_name_for_exchange(author)}")
        lines.append(f"TI  - {record['title']}")
        mapping = (
            ("container-title", "JO"), ("volume", "VL"), ("issue", "IS"),
            ("publisher", "PB"), ("publisher-place", "CY"), ("DOI", "DO"),
            ("PMID", "AN"), ("URL", "UR"), ("abstract", "AB"),
            ("language", "LA"), ("ISSN", "SN"), ("note", "N1"), ("keyword", "KW"),
        )
        for field, tag in mapping:
            if field in record:
                lines.append(f"{tag}  - {record[field]}")
        if record.get("issued"):
            lines.append("PY  - " + "/".join(str(part) for part in record["issued"]["date-parts"][0]))
        if record.get("page"):
            start, separator, end = record["page"].partition("-")
            lines.append(f"SP  - {start}")
            if separator and end:
                lines.append(f"EP  - {end}")
        lines.append("ER  -")
    return ("\n".join(lines) + "\n").encode("utf-8")


def bib_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def bib_unescape(value: str) -> str:
    return re.sub(r"\\([\\{}])", r"\1", value)


def format_bib_name(name: dict[str, str]) -> str:
    if "literal" in name:
        return "{" + bib_escape(name["literal"]) + "}"
    return bib_escape(format_name_for_exchange(name))


def bib_key(record: dict[str, Any]) -> str:
    candidate = record.get("citation-key", "")
    if candidate and SAFE_BIB_KEY_RE.fullmatch(candidate):
        return candidate
    return re.sub(r"[^A-Za-z0-9_:.+-]", "_", record["id"])


def export_bibtex(records: list[dict[str, Any]]) -> bytes:
    entries: list[str] = []
    for record in records:
        fields: list[tuple[str, str, bool]] = []
        if record.get("author"):
            fields.append(("author", " and ".join(format_bib_name(name) for name in record["author"]), True))
        fields.append(("title", record["title"], False))
        mapping = (
            ("container-title", "journal" if record["type"] == "article-journal" else "booktitle"),
            ("volume", "volume"), ("issue", "number"), ("page", "pages"),
            ("publisher", "publisher"), ("publisher-place", "address"),
            ("DOI", "doi"), ("PMID", "pmid"), ("URL", "url"),
            ("abstract", "abstract"), ("language", "language"), ("ISBN", "isbn"),
            ("ISSN", "issn"), ("keyword", "keywords"), ("note", "note"),
        )
        for source, target in mapping:
            if source in record:
                value = record[source].replace("-", "--") if source == "page" else record[source]
                fields.append((target, value, False))
        if record.get("issued"):
            fields.append(("year", str(record["issued"]["date-parts"][0][0]), False))
        rendered = [f"@{CSL_TO_BIB_TYPE.get(record['type'], 'misc')}{{{bib_key(record)},"]
        for index, (name, value, already_escaped) in enumerate(fields):
            comma = "," if index < len(fields) - 1 else ""
            encoded = value if already_escaped else bib_escape(value)
            rendered.append(f"  {name} = {{{encoded}}}{comma}")
        rendered.append("}")
        entries.append("\n".join(rendered))
    return ("\n\n".join(entries) + "\n").encode("utf-8")


def export_records(workspace: Path, library_path: Path, output_path: Path, format_name: str) -> dict[str, Any]:
    payload = load_library(library_path)
    if format_name == "csl-json":
        output = canonical_json([csl_export_record(record) for record in payload["records"]])
    elif format_name == "ris":
        output = export_ris(payload["records"])
    else:
        output = export_bibtex(payload["records"])
    if output_path.exists():
        if not output_path.is_file():
            raise ContractError("export path is not an ordinary file")
        existing = read_bounded(output_path)
        if existing != output:
            raise ContractError("refusing to overwrite a different existing output")
    else:
        atomic_write(output_path, output)
    return {
        "action": "export",
        "format": format_name,
        "library_path": library_path.relative_to(workspace).as_posix(),
        "library_sha256": hashlib.sha256(library_path.read_bytes()).hexdigest(),
        "output_path": output_path.relative_to(workspace).as_posix(),
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "records_exported": len(payload["records"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".", help="project root; defaults to current directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    importer = subparsers.add_parser("import", help="import one RIS, BibTeX, or CSL-JSON file")
    importer.add_argument("--library", default="references/library.json")
    importer.add_argument("--input", required=True)
    importer.add_argument("--format", choices=("auto", "ris", "bibtex", "csl-json"), default="auto")

    validator = subparsers.add_parser("validate", help="validate the canonical local library")
    validator.add_argument("--library", default="references/library.json")

    exporter = subparsers.add_parser("export", help="export the canonical library")
    exporter.add_argument("--library", default="references/library.json")
    exporter.add_argument("--format", choices=("ris", "bibtex", "csl-json"), required=True)
    exporter.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        workspace = Path(args.workspace).resolve(strict=True)
        if not workspace.is_dir():
            raise ContractError("workspace must be a directory")
        library_path = path_inside_workspace(workspace, args.library, must_exist=args.command != "import" or (workspace / args.library).exists())
        if args.command == "import":
            input_path = path_inside_workspace(workspace, args.input, must_exist=True)
            format_name = detect_format(input_path, args.format)
            report = import_records(workspace, library_path, input_path, format_name)
        elif args.command == "validate":
            payload = load_library(library_path)
            report = {
                "action": "validate",
                "library_path": library_path.relative_to(workspace).as_posix(),
                "library_sha256": hashlib.sha256(library_path.read_bytes()).hexdigest(),
                "records": len(payload["records"]),
                "conflicts": sum(len(record.get("conflicts", [])) for record in payload["records"]),
                "valid": True,
            }
        else:
            output_path = path_inside_workspace(workspace, args.output, must_exist=False)
            report = export_records(workspace, library_path, output_path, args.format)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ContractError, OSError) as error:
        print(f"reference-library: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
