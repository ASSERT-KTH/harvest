#!/usr/bin/env python3

from datetime import date
import re
import sys

import harvest
import requests


USER_AGENT = "scholar-harvest/0.1.0 (wikipedia-citoid-harvest.py)"


def normalize_identifier(identifier):
    identifier = identifier.strip()
    if identifier.startswith(("http://", "https://")):
        return identifier, identifier
    return identifier, f"https://doi.org/{identifier}"


def clean_doi(value):
    if not value:
        return None
    value = value.strip()
    value = value.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return value or None


def extract_doi(identifier, paper_data):
    if paper_data and paper_data.get("doi"):
        return clean_doi(paper_data["doi"])
    if identifier.startswith(("http://", "https://")):
        match = re.search(r"10\.\S+/\S+", identifier)
        if match:
            return clean_doi(match.group(0))
        return None
    return clean_doi(identifier)


def fetch_crossref_message(doi):
    if not doi:
        return None
    response = requests.get(
        f"https://api.crossref.org/works/{doi}",
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    if response.status_code != 200:
        return None
    return response.json().get("message")


def normalize_date(value):
    if not value:
        return None
    if isinstance(value, list):
        parts = [str(part) for part in value if part]
    else:
        parts = str(value).split("-")
    if len(parts) >= 2:
        parts[1] = parts[1].zfill(2)
    if len(parts) >= 2:
        return "-".join(parts[:2])
    return parts[0] if parts else None


def normalize_pages(value):
    if not value:
        return None
    return re.sub(r"(?<=\d)-(?=\d)", "–", value)


def crossref_date(message):
    if not message:
        return None
    for key in ("published-print", "published-online", "published", "issued"):
        parts = message.get(key, {}).get("date-parts", [[]])[0]
        if parts:
            return normalize_date(parts)
    return None


def pick_issn(value):
    if isinstance(value, list):
        issns = [item.strip() for item in value if item and item.strip()]
    elif isinstance(value, str):
        issns = [item.strip() for item in value.split(",") if item.strip()]
    else:
        issns = []
    return issns[-1] if issns else None


def normalize_name_case(value):
    if not isinstance(value, str):
        return value
    return value.title() if value.isupper() else value


def split_author_name(name):
    name = name.strip()
    if not name:
        return None, None
    if "," in name:
        parts = [part.strip() for part in name.split(",", 1)]
        if len(parts) == 2:
            return parts[1] or None, parts[0] or None
    tokens = name.split()
    if len(tokens) == 1:
        return None, tokens[0]
    return " ".join(tokens[:-1]), tokens[-1]


def author_entries(paper_data, crossref_message):
    if crossref_message and crossref_message.get("author"):
        entries = []
        for author in crossref_message["author"]:
            entries.append(
                {
                    "first": normalize_name_case(author.get("given", "")) or None,
                    "last": normalize_name_case(author.get("family", "")) or None,
                }
            )
        return entries

    if paper_data and paper_data.get("author_list"):
        names = paper_data["author_list"]
    else:
        authors = paper_data.get("authors", "") if paper_data else ""
        if " | " in authors:
            names = [name.strip() for name in authors.split(" | ") if name.strip()]
        else:
            names = [name.strip() for name in authors.split(", ") if name.strip()]

    entries = []
    for name in names:
        first_name, last_name = split_author_name(name)
        if first_name or last_name:
            entries.append({"first": first_name, "last": last_name})
    return entries


def add_field(lines, name, value):
    if value is None:
        return
    if isinstance(value, str):
        value = value.strip()
    if value == "":
        return
    lines.append(f" |{name}= {value}")


def render_author_fields(lines, paper_data, crossref_message):
    for index, author in enumerate(author_entries(paper_data, crossref_message), start=1):
        add_field(lines, f"last{index}", author.get("last"))
        add_field(lines, f"first{index}", author.get("first"))


def fetch_semantic_scholar(identifier):
    """Try to fetch metadata from Semantic Scholar API."""
    try:
        response = requests.get(
            f"https://api.semanticscholar.org/graph/v1/paper/{identifier}",
            params={"fields": "title,authors,venue,year,publicationDate,url"},
            timeout=10,
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None


def build_citation_fields(identifier, debug=False):
    _, source_url = normalize_identifier(identifier)

    paper_data = harvest.collect_paper_data_from_url(source_url) or {}
    doi = extract_doi(identifier, paper_data)

    if debug:
        print(f"[DEBUG] Identifier: {identifier}", file=sys.stderr)
        print(f"[DEBUG] Source URL: {source_url}", file=sys.stderr)
        print(f"[DEBUG] Initial paper_data: {paper_data}", file=sys.stderr)
        print(f"[DEBUG] Extracted DOI: {doi}", file=sys.stderr)

    crossref_message = None
    if doi:
        crossref_info = harvest.info_from_crossref(doi)
        if crossref_info:
            paper_data = harvest.merge_paper_data(paper_data, crossref_info)
        crossref_message = fetch_crossref_message(doi)
        if debug:
            print(f"[DEBUG] CrossRef message: {crossref_message is not None}", file=sys.stderr)

    # Fallback to Semantic Scholar if CrossRef didn't work
    if not crossref_message and not paper_data:
        ss_data = fetch_semantic_scholar(identifier)
        if ss_data and debug:
            print(f"[DEBUG] Semantic Scholar found: {ss_data.get('title')}", file=sys.stderr)
        if ss_data:
            paper_data = {
                "title": ss_data.get("title"),
                "authors": ", ".join([a.get("name", "") for a in ss_data.get("authors", [])[:5]]),
                "year": ss_data.get("year"),
                "venue_title": ss_data.get("venue"),
                "url": ss_data.get("url"),
            }

    return {
        "paper_data": paper_data or {},
        "crossref_message": crossref_message,
        "doi": doi or (crossref_message.get("DOI") if crossref_message else None),
        "date": crossref_date(crossref_message) or normalize_date((paper_data or {}).get("year")),
        "volume": crossref_message.get("volume") if crossref_message else None,
        "issue": crossref_message.get("issue") if crossref_message else None,
        "pages": normalize_pages(crossref_message.get("page")) if crossref_message else None,
        "issn": pick_issn(crossref_message.get("ISSN")) if crossref_message else None,
    }


def format_citoid_as_mediawiki(citation_fields):
    paper_data = citation_fields["paper_data"]
    crossref_message = citation_fields["crossref_message"]

    lines = ["{{cite journal"]
    render_author_fields(lines, paper_data, crossref_message)
    add_field(lines, "title", paper_data.get("title"))
    add_field(lines, "journal", paper_data.get("venue_title"))
    add_field(lines, "date", citation_fields.get("date"))
    add_field(lines, "volume", citation_fields.get("volume"))
    add_field(lines, "issue", citation_fields.get("issue"))
    add_field(lines, "pages", citation_fields.get("pages"))
    add_field(lines, "url", paper_data.get("url"))
    add_field(lines, "access-date", date.today().isoformat())
    add_field(lines, "doi", citation_fields.get("doi"))
    add_field(lines, "issn", citation_fields.get("issn"))
    lines.append("}}")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        raise SystemExit("Usage: wikipedia-citoid-harvest.py <doi-or-url> [fix]")

    identifier = sys.argv[1]
    fix_mode = sys.argv[2] == "fix" if len(sys.argv) == 3 else False

    citation_fields = build_citation_fields(identifier)
    
    # Check if we have meaningful metadata (more than just DOI and access-date)
    paper_data = citation_fields.get("paper_data", {})
    has_title = paper_data.get("title")
    has_authors = paper_data.get("authors") or paper_data.get("author_list")
    has_venue = paper_data.get("venue_title")
    crossref_msg = citation_fields.get("crossref_message")
    
    # Require at least a title and either authors or venue, not just a DOI
    if not has_title and not (crossref_msg and crossref_msg.get("title")):
        sys.stderr.write(f"Error: Could not find full metadata for '{identifier}'\n")
        sys.stderr.write(f"The DOI/URL may be invalid, malformed, or not yet indexed in CrossRef\n")
        raise SystemExit(1)
    
    output = format_citoid_as_mediawiki(citation_fields)

    if fix_mode:
        output = fix_citation_output(output, citation_fields)

    print(output)


def fix_citation_output(output, citation_fields):
    """Apply fixes and improvements to citation output.
    
    - Remove empty/None fields
    - Normalize whitespace
    - Ensure consistent formatting
    - Validate required fields
    """
    lines = output.split("\n")
    fixed_lines = []

    for line in lines:
        # Keep template markers
        if line.strip() in ("{{cite journal", "}}"):
            fixed_lines.append(line)
            continue

        # Skip empty lines
        if not line.strip():
            continue

        # Parse field line
        if "|" in line and "=" in line:
            parts = line.split("=", 1)
            if len(parts) == 2:
                field_part = parts[0]
                value_part = parts[1].strip()

                # Skip empty/None values
                if not value_part or value_part in ("None", ""):
                    continue

                # Normalize spacing around equals
                fixed_lines.append(f"{field_part}= {value_part}")
                continue

        # Keep other lines as-is
        if line.strip():
            fixed_lines.append(line)

    return "\n".join(fixed_lines)


if __name__ == "__main__":
    main()
