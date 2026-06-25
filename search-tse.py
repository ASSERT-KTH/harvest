#!/usr/bin/env python3
"""search-tse.py — Search for papers in IEEE Transactions on Software Engineering.

Delegates to https://api.monperrus.com/search-tse.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

ENDPOINT = "https://api.monperrus.com/search-tse"
DEFAULT_MAX = 100


def _format_author(a: dict) -> str:
    parts = [a["name"]]
    links = [u for u in (a.get("orcid"), a.get("dblp")) if u]
    if links:
        parts.append(f"({' | '.join(links)})")
    return " ".join(parts)


def output_human(doc: dict) -> None:
    papers = doc.get("papers", [])
    statuses = doc.get("api_status", [])
    print()
    print("=" * 72)
    print("  IEEE Transactions on Software Engineering — Search Results")
    print(f"  Unique papers found: {doc.get('total_unique', len(papers))}")
    print("=" * 72)
    print("\n── API status ──")
    for s in statuses:
        if s.get("error"):
            print(f"  ✗  {s['source']:<20s}  {s['error']}")
        else:
            print(f"  ✓  {s['source']:<20s}  {s['count']} paper(s)")
    if not papers:
        print("\nNo papers matched.")
        return
    print(f"\n── Papers ({len(papers)}) ──")
    for i, p in enumerate(papers, 1):
        print(f"\n{i:3d}. {p['title']}")
        authors = p.get("authors") or []
        for a in authors[:6]:
            print(f"     {_format_author(a)}")
        if len(authors) > 6:
            print("      …")
        parts = [str(p["year"])] if p.get("year") else []
        if p.get("venue"):
            parts.append(p["venue"])
        if p.get("source"):
            parts.append(f"[{p['source']}]")
        if parts:
            print(f"     {'  |  '.join(parts)}")
        if p.get("doi"):
            print(f"     DOI: {p['doi']}")
        if p.get("url"):
            print(f"     URL: {p['url']}")
        if p.get("abstract"):
            text = p["abstract"][:200].replace("\n", " ")
            suffix = "…" if len(p["abstract"]) > 200 else ""
            print(f"     Abstract: {text}{suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search for papers in IEEE Transactions on Software Engineering.",
    )
    parser.add_argument("query", nargs="?", default="software engineering")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX)
    args = parser.parse_args()

    qs = urllib.parse.urlencode({"q": args.query, "max": args.max})
    with urllib.request.urlopen(f"{ENDPOINT}?{qs}") as resp:
        doc = json.load(resp)

    if args.json:
        json.dump(doc, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        output_human(doc)


if __name__ == "__main__":
    main()
