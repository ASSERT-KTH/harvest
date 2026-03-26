#!/usr/bin/env python3
"""Convert an ASTA (asta.allen.ai) share URL to a Markdown document.

Usage:
    python asta-to-markdown.py <asta-share-url> [output.md]

Example:
    python asta-to-markdown.py https://asta.allen.ai/chat/626a589a-aff6-42c5-97e4-7f6b721747b9
"""

import json
import re
import sys
import time
import urllib.request
import urllib.parse
import urllib.error


ASTA_API = "https://asta.allen.ai/api/chat/thread/{tid}"
S2_BATCH_API = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_FIELDS = "title,year,venue,externalIds,abstract,url"
BATCH_SIZE = 50  # S2 batch limit


def extract_thread_id(url: str) -> str:
    """Extract UUID from an ASTA share URL."""
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", url)
    if not m:
        raise ValueError(f"No UUID found in URL: {url}")
    return m.group(0)


def fetch_json(url: str, data: bytes = None, headers: dict = None) -> dict | list:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_asta_thread(tid: str) -> dict:
    url = ASTA_API.format(tid=tid)
    return fetch_json(url)


def extract_papers(thread: dict) -> list[dict]:
    """Return list of {corpusId, paperTitle, paperYear} dicts from all widgets."""
    papers = []
    widgets = thread.get("thread", {}).get("ui_state", {}).get("widgets_in_view", [])
    seen = set()
    for widget in widgets:
        if widget.get("type") != "PAPER_FINDER":
            continue
        for p in widget.get("papers", []):
            cid = p.get("corpusId")
            if cid and cid not in seen:
                seen.add(cid)
                papers.append(p)
    return papers


def enrich_with_s2(papers: list[dict]) -> list[dict]:
    """Add venue, abstract, url, arxiv_id to each paper via Semantic Scholar batch API."""
    ids = [f"CorpusId:{p['corpusId']}" for p in papers]
    enriched = {}

    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i:i + BATCH_SIZE]
        payload = json.dumps({"ids": batch}).encode()
        for attempt in range(3):
            try:
                results = fetch_json(
                    f"{S2_BATCH_API}?fields={S2_FIELDS}",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    time.sleep(5 * (attempt + 1))
                else:
                    raise
        for r in results:
            if r is None:
                continue
            cid = (r.get("externalIds") or {}).get("CorpusId")
            if cid:
                enriched[cid] = r
        if i + BATCH_SIZE < len(ids):
            time.sleep(1)  # be polite

    for p in papers:
        r = enriched.get(p["corpusId"], {})
        arxiv = (r.get("externalIds") or {}).get("ArXiv")
        p["venue"] = r.get("venue") or ""
        p["abstract"] = r.get("abstract") or ""
        p["s2_url"] = r.get("url") or ""
        p["url"] = f"https://arxiv.org/abs/{arxiv}" if arxiv else p.get("s2_url", "")

    return papers


def extract_query(thread: dict) -> str:
    """Return the user's search query (first human message)."""
    messages = thread.get("thread", {}).get("messages", [])
    asta_user_id = None
    # Find non-asta sender
    users = thread.get("thread", {}).get("users", [])
    for u in users:
        if u.get("display_name", "").lower() != "asta":
            asta_user_id = u.get("uuid")
            break
    for msg in messages:
        sender = msg.get("sender", {})
        if sender.get("uuid") == asta_user_id or sender.get("display_name", "").lower() != "asta":
            return msg.get("stripped_text", "").strip()
    return ""


def to_markdown(query: str, papers: list[dict], asta_url: str) -> str:
    lines = []
    lines.append(f"# ASTA Paper Search: {query}")
    lines.append("")
    lines.append(f"Source: {asta_url}")
    lines.append(f"Total papers: {len(papers)}")
    lines.append("")

    for i, p in enumerate(papers, 1):
        title = p.get("paperTitle") or p.get("title") or "(untitled)"
        year = p.get("paperYear") or ""
        venue = p.get("venue") or ""
        url = p.get("url") or p.get("s2_url") or ""
        abstract = p.get("abstract") or ""

        header = f"## {i}. {title}"
        if year:
            header += f" ({year})"
        lines.append(header)
        lines.append("")

        meta = []
        if venue:
            meta.append(f"**Venue:** {venue}")
        if url:
            meta.append(f"**URL:** {url}")
        if meta:
            lines.append("  ".join(meta))
            lines.append("")

        if abstract:
            lines.append(abstract)
            lines.append("")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    asta_url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    tid = extract_thread_id(asta_url)
    thread = fetch_asta_thread(tid)

    query = extract_query(thread)
    papers = extract_papers(thread)
    papers = enrich_with_s2(papers)
    md = to_markdown(query, papers, asta_url)

    if output_file:
        with open(output_file, "w") as f:
            f.write(md)
        print(f"Written to {output_file}", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
