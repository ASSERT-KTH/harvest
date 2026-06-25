#!/usr/bin/env python3
"""search-tse.py — Search for papers published in IEEE Transactions on Software Engineering.

Queries Semantic Scholar, CrossRef, and IEEE Xplore APIs in parallel,
deduplicates results by DOI (falling back to title), and reports which
sources succeeded or failed.

API keys are read from (in priority order):
  1. Environment variables (IEEE_API_KEY, SEMANTIC_SCHOLAR_API_KEY)
  2. config.py (which reads from the system keyring)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

import httpx

try:
    import config
except ImportError:
    config = None  # type: ignore[assignment]


# ── constants ──────────────────────────────────────────────────────────────

TSE_ISSN_PRINT = "0098-5589"       # IEEE Trans. Software Engineering (print)
TSE_ISSN_ELECTRONIC = "1939-3520"  # IEEE Trans. Software Engineering (electronic)
TSE_VENUE_NAME = "IEEE Transactions on Software Engineering"
TSE_PUBLICATION_TITLE = "Transactions on Software Engineering"  # as used by IEEE Xplore

SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"
CROSSREF_BASE = "https://api.crossref.org"
IEEE_BASE = "https://ieeexploreapi.ieee.org/api/v1/search/articles"

DEFAULT_MAX = 100
REQUEST_TIMEOUT = 30.0
# Semantic Scholar free tier (no API key): ~1 request / 3 sec
# With an API key: much higher limits (set SEMANTIC_SCHOLAR_API_KEY env var)
SEMANTIC_SCHOLAR_DELAY = 1.5      # base seconds between requests
SEMANTIC_SCHOLAR_RETRIES = 1     # additional retries on 429


# ── API key resolution ─────────────────────────────────────────────────────

def _get_api_key(env_var: str, config_attr: str) -> str:
    """Return the API key from environment or config.py fallback."""
    val = os.environ.get(env_var)
    if val:
        return val
    if config is not None:
        return getattr(config, config_attr, "") or ""
    return ""


# ── data model ─────────────────────────────────────────────────────────────

@dataclass
class Paper:
    title: str
    authors: list[str] = tuple()  # type: ignore[assignment]
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    venue: str | None = None
    source: str | None = None
    abstract: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.authors, tuple):
            object.__setattr__(self, "authors", list(self.authors))

    @property
    def dedup_key(self) -> str:
        """Normalised key used for deduplication — DOI when available, else title."""
        if self.doi:
            doi = self.doi.lower().strip().rstrip("/")
            # Strip optional https://doi.org/ prefix for normalisation
            for prefix in ("https://doi.org/", "http://doi.org/"):
                if doi.startswith(prefix):
                    doi = doi[len(prefix):]
                    break
            return doi
        t = (self.title or "").lower().strip()
        return " ".join(t.split())


@dataclass
class APIResult:
    source: str
    papers: list[Paper] = tuple()  # type: ignore[assignment]
    error: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.papers, tuple):
            object.__setattr__(self, "papers", list(self.papers))


# ── API clients ────────────────────────────────────────────────────────────

async def _semantic_scholar_request(
    params: dict[str, Any], client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Make a Semantic Scholar request with retry & back-off on 429.

    The API key must be passed as the ``x-api-key`` header, not as a
    query parameter.
    """
    url = f"{SEMANTIC_SCHOLAR_BASE}/paper/search"
    headers = {}
    api_key = _get_api_key("SEMANTIC_SCHOLAR_API_KEY", "semanticscholar_key")
    if api_key:
        headers["x-api-key"] = api_key

    for attempt in range(SEMANTIC_SCHOLAR_RETRIES + 1):
        await asyncio.sleep(SEMANTIC_SCHOLAR_DELAY)  # rate-limit courtesy
        resp = await client.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 429 and attempt < SEMANTIC_SCHOLAR_RETRIES:
            wait = SEMANTIC_SCHOLAR_DELAY * (2 ** attempt)
            await asyncio.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    return {"data": []}


async def search_semantic_scholar(
    query: str, max_results: int, client: httpx.AsyncClient,
) -> APIResult:
    """Search Semantic Scholar, filtered to TSE venue."""
    papers: list[Paper] = []
    try:
        params: dict[str, Any] = {
            "query": query,
            "venue": TSE_VENUE_NAME,
            "limit": min(max_results, 100),
            "fields": "title,authors,year,url,venue,abstract,externalIds",
        }

        data = await _semantic_scholar_request(params, client)

        for item in data.get("data", []):
            authors_raw = item.get("authors") or []
            authors = [
                a.get("name", "")
                for a in authors_raw
                if a.get("name")
            ]
            # DOI is nested inside externalIds on the search endpoint
            ext_ids = item.get("externalIds") or {}
            doi = ext_ids.get("DOI")
            paper = Paper(
                title=item.get("title", "") or "",
                authors=authors,
                year=item.get("year"),
                doi=doi,
                url=item.get("url"),
                venue=item.get("venue"),
                source="Semantic Scholar",
                abstract=item.get("abstract"),
            )
            papers.append(paper)

        return APIResult("Semantic Scholar", papers)

    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        msg = exc.response.text[:300] if exc.response.text else str(exc)
        if code == 429:
            return APIResult("Semantic Scholar", papers,
                             "Rate-limited (HTTP 429). "
                             "Set SEMANTIC_SCHOLAR_API_KEY for higher limits.")
        return APIResult("Semantic Scholar", papers, f"HTTP {code}: {msg}")
    except Exception as exc:
        return APIResult("Semantic Scholar", papers, str(exc))


async def search_crossref(
    query: str, max_results: int, client: httpx.AsyncClient,
) -> APIResult:
    """Search CrossRef filtered to TSE via ISSN."""
    papers: list[Paper] = []
    try:
        params: dict[str, Any] = {
            "query": query,
            "filter": f"issn:{TSE_ISSN_PRINT},type:journal-article",
            "rows": min(max_results, 100),
            "select": "DOI,title,author,issued,URL,container-title,abstract",
        }
        url = f"{CROSSREF_BASE}/works"

        resp = await client.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("message", {}).get("items", [])
        for item in items:
            doi_str = item.get("DOI")
            doi = f"https://doi.org/{doi_str}" if doi_str else None
            title_list = item.get("title") or []
            title = title_list[0] if title_list else ""

            authors = []
            for author in item.get("author") or []:
                given = (author.get("given") or "").strip()
                family = (author.get("family") or "").strip()
                name = f"{given} {family}".strip()
                if name:
                    authors.append(name)

            issued = item.get("issued", {}).get("date-parts")
            year = issued[0][0] if issued and issued[0] else None

            venue_list = item.get("container-title") or []
            venue = venue_list[0] if venue_list else None
            url = item.get("URL")
            abstract = item.get("abstract")

            paper = Paper(
                title=title,
                authors=authors,
                year=year,
                doi=doi,
                url=url,
                venue=venue,
                source="CrossRef",
                abstract=abstract,
            )
            papers.append(paper)

        return APIResult("CrossRef", papers)

    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        msg = exc.response.text[:300] if exc.response.text else str(exc)
        if code == 429:
            return APIResult("CrossRef", papers,
                             "Rate-limited (HTTP 429).")
        return APIResult("CrossRef", papers, f"HTTP {code}: {msg}")
    except Exception as exc:
        return APIResult("CrossRef", papers, str(exc))


async def search_ieee(
    query: str, max_results: int, client: httpx.AsyncClient,
) -> APIResult:
    """Search IEEE Xplore API for TSE papers (requires API key)."""
    papers: list[Paper] = []
    api_key = _get_api_key("IEEE_API_KEY", "ieeexplore_key")
    if not api_key:
        return APIResult(
            "IEEE Xplore", papers,
            "No API key. Set the IEEE_API_KEY environment variable "
            "(get one at https://developer.ieee.org).",
        )

    try:
        params: dict[str, Any] = {
            "querytext": query,
            "publication_title": TSE_PUBLICATION_TITLE,
            "apikey": api_key,
            "max_records": min(max_results, 200),
            "format": "json",
        }
        resp = await client.get(IEEE_BASE, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        articles = data.get("articles") or []
        for article in articles:
            doi = article.get("doi")
            authors_raw = article.get("authors", {}).get("authors") or []
            authors = [a.get("full_name", "") for a in authors_raw if a.get("full_name")]
            title = article.get("title") or ""
            year_str = article.get("publication_year")
            year = int(year_str) if year_str else None
            url = article.get("html_url") or article.get("pdf_url")
            venue = article.get("publication_title")
            abstract = article.get("abstract")

            paper = Paper(
                title=title,
                authors=authors,
                year=year,
                doi=doi,
                url=url,
                venue=venue,
                source="IEEE Xplore",
                abstract=abstract,
            )
            papers.append(paper)

        return APIResult("IEEE Xplore", papers)

    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        msg = exc.response.text[:300] if exc.response.text else str(exc)
        if code == 401:
            return APIResult("IEEE Xplore", papers, "HTTP 401 – invalid API key.")
        if code == 403:
            return APIResult("IEEE Xplore", papers,
                             "HTTP 403 – account inactive. Activate at https://developer.ieee.org.")
        return APIResult("IEEE Xplore", papers, f"HTTP {code}: {msg}")
    except Exception as exc:
        return APIResult("IEEE Xplore", papers, str(exc))


# ── deduplication ──────────────────────────────────────────────────────────

def deduplicate(papers: list[Paper]) -> list[Paper]:
    """Return papers in order, removing duplicates by dedup_key."""
    seen: set[str] = set()
    out: list[Paper] = []
    for p in papers:
        key = p.dedup_key
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(p)
    return out


# ── output ─────────────────────────────────────────────────────────────────

def output_human(papers: list[Paper], results: list[APIResult]) -> None:
    """Pretty-print results to terminal."""
    print()
    print("=" * 72)
    print("  IEEE Transactions on Software Engineering — Search Results")
    print(f"  Unique papers found: {len(papers)}")
    print("=" * 72)

    print("\n── API status ──")
    for r in results:
        if r.error:
            print(f"  ✗  {r.source:<20s}  {r.error}")
        else:
            print(f"  ✓  {r.source:<20s}  {len(r.papers)} paper(s)")

    if not papers:
        print("\nNo papers matched.")
        return

    print(f"\n── Papers ({len(papers)}) ──")
    for i, p in enumerate(papers, 1):
        print(f"\n{i:3d}. {p.title}")
        if p.authors:
            display = p.authors[:6]
            suffix = " …" if len(p.authors) > 6 else ""
            print(f"     Authors: {', '.join(display)}{suffix}")
        parts = []
        if p.year:
            parts.append(str(p.year))
        if p.venue:
            parts.append(p.venue)
        if p.source:
            parts.append(f"[{p.source}]")
        if parts:
            print(f"     {'  |  '.join(parts)}")
        if p.doi:
            print(f"     DOI: {p.doi}")
        if p.url:
            print(f"     URL: {p.url}")
        if p.abstract:
            text = p.abstract[:200].replace("\n", " ")
            print(f"     Abstract: {text}…" if len(p.abstract) > 200 else f"     Abstract: {text}")


def output_json(papers: list[Paper], results: list[APIResult], query: str) -> None:
    """Write JSON document to stdout."""
    doc: dict[str, Any] = {
        "query": query,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_unique": len(papers),
        "api_status": [
            {"source": r.source, "count": len(r.papers), "error": r.error}
            for r in results
        ],
        "papers": [asdict(p) for p in papers],
    }
    json.dump(doc, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


# ── main ───────────────────────────────────────────────────────────────────

async def _run(query: str, max_results: int, output_json_flag: bool) -> None:
    headers = {
        "User-Agent": "search-tse/1.0 (mailto:example@example.org)",
    }

    async with httpx.AsyncClient(headers=headers) as client:
        coros = [
            search_semantic_scholar(query, max_results, client),
            search_crossref(query, max_results, client),
            search_ieee(query, max_results, client),
        ]
        gathered = await asyncio.gather(*coros, return_exceptions=True)

    results: list[APIResult] = []
    for g in gathered:
        if isinstance(g, Exception):
            results.append(APIResult("unknown", [], str(g)))
        else:
            results.append(g)

    all_papers: list[Paper] = []
    for r in results:
        all_papers.extend(r.papers)

    unique = deduplicate(all_papers)

    if output_json_flag:
        output_json(unique, results, query)
    else:
        output_human(unique, results)

    # Report API coverage to stderr
    failed = [r for r in results if r.error]
    if failed:
        print(
            f"\n⚠  {len(failed)} of 3 API(s) had issues:",
            file=sys.stderr,
        )
        for r in failed:
            print(f"   {r.source}: {r.error}", file=sys.stderr)
    else:
        print("\n✓  All three APIs completed successfully.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search for papers in IEEE Transactions on Software Engineering "
                    "via Semantic Scholar, CrossRef, and IEEE Xplore.",
        epilog="API key priority: environment variable → config.py (system keyring)\n"
               "  IEEE_API_KEY / config.ieeexplore_key       Required for IEEE Xplore\n"
               "  SEMANTIC_SCHOLAR_API_KEY / config.semanticscholar_key  Optional, raises rate limits",
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="software engineering",
        help="Search query (default: %(default)r)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON (default: human-readable table)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=DEFAULT_MAX,
        help=f"Max results per source (default: {DEFAULT_MAX})",
    )
    args = parser.parse_args()

    asyncio.run(_run(args.query, args.max, args.json))


if __name__ == "__main__":
    main()
