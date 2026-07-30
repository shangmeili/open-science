#!/usr/bin/env python3
"""Queue and retrieve legally available open full text for a local library."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import mimetypes
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from reference_library import (
    ContractError,
    atomic_write,
    canonical_json,
    load_library,
    path_inside_workspace,
)


SCHEMA_VERSION = "ai4heor-full-text-queue/v1"
SOURCE_ARCHIVE_SCHEMA_VERSION = "ai4heor-source-file-archive/v1"
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
USER_AGENT = "AI4HEOR/1.0 open-access-full-text"
EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPE_PMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
UNPAYWALL_API = "https://api.unpaywall.org/v2/{doi}"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def library_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_source_archive(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SOURCE_ARCHIVE_SCHEMA_VERSION, "items": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError(f"source-file archive is unreadable: {error}") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "items"}
        or payload["schema_version"] != SOURCE_ARCHIVE_SCHEMA_VERSION
        or not isinstance(payload["items"], list)
    ):
        raise ContractError("source-file archive fields are invalid")
    return payload


def queue_record(record: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "record_id": record["id"],
        "title": record["title"],
        "status": "queued",
        "attempts": [],
        "full_text": None,
    }
    for field in ("DOI", "PMID", "PMCID"):
        if record.get(field):
            item[field] = record[field]
    return item


def load_queue(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError(f"full-text queue is unreadable: {error}") from error
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "library", "items"}:
        raise ContractError("full-text queue fields are invalid")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ContractError(f"unsupported full-text queue schema: {payload['schema_version']}")
    library = payload["library"]
    if not isinstance(library, dict) or set(library) != {"path", "sha256"}:
        raise ContractError("full-text queue library binding is invalid")
    if not isinstance(payload["items"], list):
        raise ContractError("full-text queue items must be an array")
    seen: set[str] = set()
    for item in payload["items"]:
        if not isinstance(item, dict) or not {"record_id", "title", "status", "attempts", "full_text"}.issubset(item):
            raise ContractError("full-text queue item is invalid")
        if item["record_id"] in seen:
            raise ContractError(f"duplicate full-text queue record: {item['record_id']}")
        seen.add(item["record_id"])
        if item["status"] not in {"queued", "running", "downloaded", "unavailable", "needs_input", "failed"}:
            raise ContractError(f"invalid full-text status: {item['status']}")
        if not isinstance(item["attempts"], list):
            raise ContractError("full-text attempts must be an array")
    return payload


def prepare_queue(
    workspace: Path,
    library_path: Path,
    queue_path: Path,
    record_ids: list[str] | None = None,
) -> dict[str, Any]:
    library = load_library(library_path)
    current_hash = library_sha256(library_path)
    selected = set(record_ids or [record["id"] for record in library["records"]])
    records = {record["id"]: record for record in library["records"]}
    missing = sorted(selected - set(records))
    if missing:
        raise ContractError("unknown library record IDs: " + ", ".join(missing))
    if queue_path.exists():
        payload = load_queue(queue_path)
        if payload["library"]["sha256"] != current_hash:
            raise ContractError("library has changed; prepare a new full-text queue")
    else:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "library": {
                "path": library_path.relative_to(workspace).as_posix(),
                "sha256": current_hash,
            },
            "items": [],
        }
    existing = {item["record_id"] for item in payload["items"]}
    additions = [queue_record(records[record_id]) for record_id in sorted(selected - existing)]
    payload["items"].extend(additions)
    payload["items"].sort(key=lambda item: item["record_id"])
    output = canonical_json(payload)
    if not queue_path.exists() or queue_path.read_bytes() != output:
        atomic_write(queue_path, output)
    return {
        "action": "prepare",
        "queue_path": queue_path.relative_to(workspace).as_posix(),
        "library_sha256": current_hash,
        "added": len(additions),
        "queued": sum(item["status"] == "queued" for item in payload["items"]),
        "total": len(payload["items"]),
    }


def validate_remote_url(url: str, resolver: Callable[..., list[Any]] = socket.getaddrinfo) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ContractError("full-text URL must be an ordinary absolute http(s) URL")
    try:
        addresses = resolver(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as error:
        raise ContractError(f"cannot resolve full-text host: {parsed.hostname}") from error
    if not addresses:
        raise ContractError(f"cannot resolve full-text host: {parsed.hostname}")
    for address in addresses:
        host = address[4][0]
        try:
            public = ipaddress.ip_address(host).is_global
        except ValueError as error:
            raise ContractError(f"invalid resolved address for full-text host: {host}") from error
        if not public:
            raise ContractError("full-text downloads must use the public network, not a private or local address")
    return url


class SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        validate_remote_url(urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_bytes(url: str) -> tuple[bytes, str, str]:
    validate_remote_url(url)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/xml, application/pdf;q=0.9, */*;q=0.1"})
    try:
        with build_opener(SafeRedirectHandler()).open(request, timeout=30) as response:
            final_url = validate_remote_url(response.geturl())
            content_type = response.headers.get_content_type()
            raw = response.read(MAX_DOWNLOAD_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise ContractError(f"network retrieval failed: {error}") from error
    if len(raw) > MAX_DOWNLOAD_BYTES:
        raise ContractError(f"full text exceeds {MAX_DOWNLOAD_BYTES} bytes")
    return raw, final_url, content_type


def archive_public_pdf(
    workspace: Path,
    archive_path: Path,
    *,
    url: str,
    title: str,
    publisher: str | None = None,
    license_name: str | None = None,
    binary_fetch: Callable[[str], tuple[bytes, str, str]] | None = None,
    now: Callable[[], str] = utc_now,
    url_validator: Callable[[str], str] = validate_remote_url,
) -> dict[str, Any]:
    """Archive one public PDF actually used by the research task."""
    if not title.strip():
        raise ContractError("source-file title is required")
    url_validator(url)
    fetcher = binary_fetch or fetch_bytes
    raw, final_url, content_type = fetcher(url)
    url_validator(final_url)
    if not raw.startswith(b"%PDF-"):
        raise ContractError("public source URL did not return a PDF")
    content_hash = hashlib.sha256(raw).hexdigest()
    source_id = hashlib.sha256(f"{url}\n{content_hash}".encode("utf-8")).hexdigest()[:24]
    file_path = path_inside_workspace(
        workspace,
        f"references/source-files/{content_hash[:24]}.pdf",
        must_exist=False,
    )
    if file_path.exists() and file_path.read_bytes() != raw:
        raise ContractError(
            f"refusing to overwrite different source file: {file_path.relative_to(workspace)}"
        )
    if not file_path.exists():
        atomic_write(file_path, raw)

    payload = load_source_archive(archive_path)
    existing = next((item for item in payload["items"] if item.get("id") == source_id), None)
    already_archived = existing is not None
    if existing is None:
        item = {
            "id": source_id,
            "status": "downloaded",
            "title": title.strip(),
            "source_url": url,
            "final_url": final_url,
            "publisher": publisher.strip() if publisher and publisher.strip() else None,
            "license": license_name.strip() if license_name and license_name.strip() else None,
            "rights_basis": "public_direct_download",
            "media_type": "application/pdf",
            "reported_media_type": content_type,
            "retrieved_at": now(),
            "path": file_path.relative_to(workspace).as_posix(),
            "sha256": content_hash,
        }
        payload["items"].append(item)
        payload["items"].sort(key=lambda value: value["id"])
        atomic_write(archive_path, canonical_json(payload))
        existing = item
    return {
        "action": "archive-url",
        "status": "downloaded",
        "archive_path": archive_path.relative_to(workspace).as_posix(),
        "path": existing["path"],
        "sha256": existing["sha256"],
        "source_url": existing["source_url"],
        "retrieved_at": existing["retrieved_at"],
        "already_archived": already_archived,
    }


def fetch_json(url: str) -> dict[str, Any]:
    raw, _final_url, _content_type = fetch_bytes(url)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError("metadata service returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise ContractError("metadata service returned a non-object JSON response")
    return payload


def europe_pmc_location(item: dict[str, Any], json_fetch: Callable[[str], dict[str, Any]]) -> dict[str, Any] | None:
    if item.get("PMCID"):
        return {"pmcid": item["PMCID"], "license": None}
    if item.get("PMID"):
        query = f'EXT_ID:{item["PMID"]} AND SRC:MED'
    elif item.get("DOI"):
        query = f'DOI:"{item["DOI"]}"'
    else:
        return None
    payload = json_fetch(EUROPE_PMC_SEARCH + "?" + urlencode({"query": query, "format": "json", "pageSize": 5}))
    results = payload.get("resultList", {}).get("result", [])
    if not isinstance(results, list):
        raise ContractError("Europe PMC returned an invalid result list")
    for result in results:
        if not isinstance(result, dict) or not result.get("pmcid"):
            continue
        doi_matches = item.get("DOI") and str(result.get("doi", "")).lower() == item["DOI"].lower()
        pmid_matches = item.get("PMID") and str(result.get("pmid", "")) == item["PMID"]
        if (doi_matches or pmid_matches) and result.get("isOpenAccess") == "Y":
            return {"pmcid": result["pmcid"], "license": result.get("license")}
    return None


def write_full_text(
    workspace: Path,
    item: dict[str, Any],
    raw: bytes,
    suffix: str,
    metadata: dict[str, Any],
    retrieved_at: str,
) -> dict[str, Any]:
    name = hashlib.sha256(item["record_id"].encode("utf-8")).hexdigest()[:24] + suffix
    path = workspace / "references" / "full-text" / name
    if path.exists() and path.read_bytes() != raw:
        raise ContractError(f"refusing to overwrite different full text: {path.relative_to(workspace)}")
    if not path.exists():
        atomic_write(path, raw)
    result = {
        "path": path.relative_to(workspace).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "media_type": "application/pdf" if suffix == ".pdf" else "application/xml",
        "retrieved_at": retrieved_at,
        **metadata,
    }
    return result


def run_one(
    workspace: Path,
    item: dict[str, Any],
    unpaywall_email: str | None,
    json_fetch: Callable[[str], dict[str, Any]],
    binary_fetch: Callable[[str], tuple[bytes, str, str]],
    now: Callable[[], str],
    url_validator: Callable[[str], str],
) -> None:
    item.pop("reason", None)
    item["status"] = "running"
    location = europe_pmc_location(item, json_fetch)
    if location:
        url = EUROPE_PMC_FULLTEXT.format(pmcid=quote(str(location["pmcid"]), safe=""))
        url_validator(url)
        raw, final_url, _content_type = binary_fetch(url)
        if not (raw.lstrip().startswith(b"<?xml") or raw.lstrip().startswith(b"<article")):
            raise ContractError("Europe PMC full text is not article XML")
        item["attempts"].append({"provider": "europe-pmc", "status": "downloaded"})
        item["full_text"] = write_full_text(
            workspace,
            item,
            raw,
            ".xml",
            {
                "provider": "europe-pmc",
                "source_url": final_url,
                "landing_url": f"https://europepmc.org/article/PMC/{location['pmcid']}",
                "license": location.get("license"),
                "version": "publishedVersion",
            },
            now(),
        )
        item["status"] = "downloaded"
        return
    item["attempts"].append({"provider": "europe-pmc", "status": "unavailable"})

    if not item.get("DOI"):
        item.update(status="unavailable", reason="no_open_full_text_found")
        return
    if not unpaywall_email:
        item.update(status="needs_input", reason="unpaywall_email_required")
        return
    url = UNPAYWALL_API.format(doi=quote(item["DOI"], safe="")) + "?" + urlencode({"email": unpaywall_email})
    payload = json_fetch(url)
    best = payload.get("best_oa_location")
    pdf_url = best.get("url_for_pdf") if isinstance(best, dict) else None
    if not isinstance(pdf_url, str) or not pdf_url:
        item["attempts"].append({"provider": "unpaywall", "status": "unavailable"})
        item.update(status="unavailable", reason="no_open_full_text_found")
        return
    url_validator(pdf_url)
    raw, final_url, _content_type = binary_fetch(pdf_url)
    if not raw.startswith(b"%PDF-"):
        raise ContractError("Unpaywall location did not return a PDF")
    item["attempts"].append({"provider": "unpaywall", "status": "downloaded"})
    item["full_text"] = write_full_text(
        workspace,
        item,
        raw,
        ".pdf",
        {
            "provider": "unpaywall",
            "source_url": final_url,
            "landing_url": best.get("url"),
            "license": best.get("license"),
            "version": best.get("version"),
            "host_type": best.get("host_type"),
        },
        now(),
    )
    item["status"] = "downloaded"


def run_queue(
    workspace: Path,
    library_path: Path,
    queue_path: Path,
    *,
    unpaywall_email: str | None,
    limit: int | None = None,
    json_fetch: Callable[[str], dict[str, Any]] = fetch_json,
    binary_fetch: Callable[[str], tuple[bytes, str, str]] = fetch_bytes,
    now: Callable[[], str] = utc_now,
    url_validator: Callable[[str], str] = validate_remote_url,
) -> dict[str, Any]:
    load_library(library_path)
    payload = load_queue(queue_path)
    if payload["library"]["sha256"] != library_sha256(library_path):
        raise ContractError("library has changed; prepare a new full-text queue")
    processed = 0
    for item in payload["items"]:
        if item["status"] not in {"queued", "needs_input", "failed"}:
            continue
        if limit is not None and processed >= limit:
            break
        processed += 1
        try:
            run_one(workspace, item, unpaywall_email, json_fetch, binary_fetch, now, url_validator)
        except ContractError as error:
            item.update(status="failed", reason=str(error))
        atomic_write(queue_path, canonical_json(payload))
    counts = {status: sum(item["status"] == status for item in payload["items"]) for status in ("queued", "downloaded", "unavailable", "needs_input", "failed")}
    return {"action": "run", "queue_path": queue_path.relative_to(workspace).as_posix(), "processed": processed, **counts}


def status_report(workspace: Path, queue_path: Path) -> dict[str, Any]:
    payload = load_queue(queue_path)
    counts = {status: sum(item["status"] == status for item in payload["items"]) for status in ("queued", "running", "downloaded", "unavailable", "needs_input", "failed")}
    return {"action": "status", "queue_path": queue_path.relative_to(workspace).as_posix(), "total": len(payload["items"]), **counts}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="add library records to the open-full-text queue")
    prepare.add_argument("--library", default="references/library.json")
    prepare.add_argument("--queue", default="references/full-text-queue.json")
    prepare.add_argument("--record-id", action="append", default=[])
    prepare.add_argument("--all", action="store_true")
    run = subparsers.add_parser("run", help="run queued open-access retrievals in order")
    run.add_argument("--library", default="references/library.json")
    run.add_argument("--queue", default="references/full-text-queue.json")
    run.add_argument("--unpaywall-email")
    run.add_argument("--limit", type=int)
    status = subparsers.add_parser("status", help="show queue status without network access")
    status.add_argument("--queue", default="references/full-text-queue.json")
    archive = subparsers.add_parser(
        "archive-url",
        help="archive one lawfully downloadable public PDF used by the task",
    )
    archive.add_argument("--url", required=True)
    archive.add_argument("--title", required=True)
    archive.add_argument("--publisher")
    archive.add_argument("--license")
    archive.add_argument("--archive", default="references/source-files.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        workspace = Path(args.workspace).resolve(strict=True)
        if not workspace.is_dir():
            raise ContractError("workspace must be a directory")
        if args.command == "archive-url":
            archive_path = path_inside_workspace(workspace, args.archive, must_exist=False)
            report = archive_public_pdf(
                workspace,
                archive_path,
                url=args.url,
                title=args.title,
                publisher=args.publisher,
                license_name=args.license,
            )
        else:
            queue_path = path_inside_workspace(
                workspace,
                args.queue,
                must_exist=args.command != "prepare",
            )
        if args.command == "prepare":
            library_path = path_inside_workspace(workspace, args.library, must_exist=True)
            if not args.all and not args.record_id:
                raise ContractError("prepare requires --all or at least one --record-id")
            report = prepare_queue(workspace, library_path, queue_path, None if args.all else args.record_id)
        elif args.command == "run":
            library_path = path_inside_workspace(workspace, args.library, must_exist=True)
            report = run_queue(workspace, library_path, queue_path, unpaywall_email=args.unpaywall_email, limit=args.limit)
        elif args.command == "status":
            report = status_report(workspace, queue_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ContractError, OSError) as error:
        print(f"open-full-text: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
