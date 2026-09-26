from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import time

import requests

from core.config import Settings
from core.utils import compact_join, normalize_whitespace, read_json, write_json

CROSSREF_ENDPOINT = "https://api.crossref.org/works"
USER_AGENT = "day10-data-observability-lab/0.1 (mailto:student@example.edu)"
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
JATS_TAG_RE = re.compile(r"<[^>]+>")
JATS_ENTITIES = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
    "&#x2010;": "-",
    "&nbsp;": " ",
}


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _strip_jats(text: str) -> str:
    """Remove JATS XML markup that Crossref wraps around abstracts."""
    cleaned = JATS_TAG_RE.sub(" ", text or "")
    for entity, replacement in JATS_ENTITIES.items():
        cleaned = cleaned.replace(entity, replacement)
    return normalize_whitespace(cleaned)


def _format_date_parts(node: dict | None) -> str:
    """Convert a Crossref `date-parts` node into an ISO `YYYY-MM-DD` string."""
    if not node:
        return ""
    parts = (node.get("date-parts") or [[]])[0]
    if not parts:
        # Some records only carry a `date-time`; fall back to its date portion.
        date_time = node.get("date-time", "")
        return date_time[:10] if date_time else ""
    numbers = [int(value) for value in parts if value is not None]
    while len(numbers) < 3:
        numbers.append(1)
    year, month, day = numbers[:3]
    return f"{year:04d}-{month:02d}-{day:02d}"


def _format_authors(raw_authors: list[dict] | None) -> list[str]:
    authors: list[str] = []
    for author in raw_authors or []:
        given = normalize_whitespace(author.get("given", ""))
        family = normalize_whitespace(author.get("family", ""))
        name = compact_join([given, family], sep=" ")
        if not name:
            name = normalize_whitespace(author.get("name", ""))
        if name:
            authors.append(name)
    return authors


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse a Crossref `/works` payload into validated `PaperRecord` objects."""
    items = (payload.get("message") or {}).get("items") or []
    records: list[PaperRecord] = []
    for item in items:
        paper_id = normalize_whitespace(item.get("DOI", ""))
        titles = item.get("title") or []
        title = normalize_whitespace(titles[0]) if titles else ""
        summary = _strip_jats(item.get("abstract", ""))
        if not paper_id or not title or not summary:
            # Records without a stable id, a title or an abstract cannot be
            # embedded or evaluated, so they are dropped at the boundary.
            continue

        categories = [normalize_whitespace(c) for c in (item.get("subject") or []) if normalize_whitespace(c)]
        published = _format_date_parts(item.get("published")) or _format_date_parts(item.get("issued"))
        updated = _format_date_parts(item.get("created")) or published
        url = normalize_whitespace(item.get("URL", ""))
        links = item.get("link") or []
        pdf_url = normalize_whitespace(links[0].get("URL", "")) if links else url

        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=_format_authors(item.get("author")),
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=published,
                updated=updated,
                abs_url=url,
                pdf_url=pdf_url,
                comment=f"Crossref record {paper_id}",
            )
        )
    return records


def _request_with_retry(params: dict, max_attempts: int = 4) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(
                CROSSREF_ENDPOINT,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            if response.status_code in RETRY_STATUS_CODES:
                raise requests.HTTPError(f"Crossref returned retryable status {response.status_code}")
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # network errors, JSON errors, retryable statuses
            last_error = exc
            if attempt < max_attempts:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"Crossref request failed after {max_attempts} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch records from Crossref, persist raw artifacts, with offline fallback."""
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "select": "DOI,title,abstract,author,subject,published,created,URL,link",
    }
    try:
        payload = _request_with_retry(params)
    except Exception as exc:
        print(f"[ingestion] Live Crossref fetch failed ({exc}); falling back to local snapshot.")
        if settings.paths.raw_api_response.exists():
            payload = read_json(settings.paths.raw_api_response)
        elif settings.paths.raw_records_json.exists():
            return load_raw_records(settings.paths.raw_records_json)
        else:
            raise RuntimeError("No network and no local raw snapshot available.") from exc

    write_json(settings.paths.raw_api_response, payload)
    records = parse_crossref_payload(payload)
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load a raw records JSON snapshot and map each row to a `PaperRecord`."""
    payload = read_json(path)
    if isinstance(payload, dict):
        # The stored artifact may be either a Crossref response or a records list.
        return parse_crossref_payload(payload)
    records: list[PaperRecord] = []
    for row in payload:
        records.append(
            PaperRecord(
                paper_id=row["paper_id"],
                title=row["title"],
                summary=row["summary"],
                authors=list(row.get("authors") or []),
                categories=list(row.get("categories") or []),
                primary_category=row.get("primary_category", ""),
                published=row.get("published", ""),
                updated=row.get("updated", "") or row.get("published", ""),
                abs_url=row.get("abs_url", ""),
                pdf_url=row.get("pdf_url", ""),
                comment=row.get("comment", ""),
            )
        )
    return records
