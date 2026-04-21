#!/usr/bin/env python3

import sys
import urllib.parse

import requests
from lxml import html


USER_AGENT = "scholar-harvest/0.1.0 (wikipedia-citoid-harvest.py)"
CITOID_ENDPOINT = "https://en.wikipedia.org/api/rest_v1/data/citation/zotero/{identifier}"

ITEM_TYPE_TO_TEMPLATE = {
    "journalArticle": "cite journal",
    "newspaperArticle": "cite news",
    "magazineArticle": "cite magazine",
    "webpage": "cite web",
    "blogPost": "cite web",
    "forumPost": "cite web",
    "book": "cite book",
    "bookSection": "cite book",
    "conferencePaper": "cite conference",
    "report": "cite report",
    "thesis": "cite thesis",
}

PUBLICATION_FIELD_BY_TYPE = {
    "journalArticle": "journal",
    "newspaperArticle": "newspaper",
    "magazineArticle": "magazine",
    "webpage": "website",
    "blogPost": "website",
    "forumPost": "website",
    "conferencePaper": "conference",
}


def fetch_citoid_record(identifier):
    encoded_identifier = urllib.parse.quote(identifier.strip(), safe="")
    response = requests.get(
        CITOID_ENDPOINT.format(identifier=encoded_identifier),
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    records = response.json()
    if not records:
        raise ValueError(f"No Citoid metadata found for {identifier}")
    return records[0]


def fetch_quote(url):
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    tree = html.fromstring(response.content)

    for xpath in (
        '//meta[@property="og:description"]/@content',
        '//meta[@name="citation_abstract"]/@content',
        '//meta[@name="description"]/@content',
    ):
        values = tree.xpath(xpath)
        if values:
            return " ".join(values[0].split())

    return None


def pick_issn(value):
    if isinstance(value, list):
        issns = [item.strip() for item in value if item and item.strip()]
    elif isinstance(value, str):
        issns = [item.strip() for item in value.split(",") if item.strip()]
    else:
        issns = []
    return issns[-1] if issns else None


def normalize_date(value):
    if not isinstance(value, str):
        return value
    parts = value.split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        return "-".join(parts[:2])
    return value


def add_field(lines, name, value):
    if value is None:
        return
    if isinstance(value, str):
        value = value.strip()
    if value == "":
        return
    lines.append(f" |{name}= {value}")


def author_fields(record):
    lines = []
    author_index = 0
    for creator in record.get("creators", []):
        if creator.get("creatorType") != "author":
            continue
        author_index += 1
        if creator.get("lastName") or creator.get("firstName"):
            add_field(lines, f"last{author_index}", creator.get("lastName"))
            add_field(lines, f"first{author_index}", creator.get("firstName"))
        else:
            add_field(lines, f"author{author_index}", creator.get("name"))
    return lines


def format_citoid_as_mediawiki(record, quote=None):
    item_type = record.get("itemType", "")
    template_name = ITEM_TYPE_TO_TEMPLATE.get(item_type, "citation")
    lines = [f"{{{{{template_name}"]
    lines.extend(author_fields(record))

    add_field(lines, "title", record.get("title"))

    publication_field = PUBLICATION_FIELD_BY_TYPE.get(item_type)
    if publication_field:
        add_field(lines, publication_field, record.get("publicationTitle"))
    elif item_type == "book":
        add_field(lines, "publisher", record.get("publisher"))
    else:
        add_field(lines, "work", record.get("publicationTitle"))

    add_field(lines, "date", normalize_date(record.get("date")))
    add_field(lines, "volume", record.get("volume"))
    add_field(lines, "issue", record.get("issue"))
    add_field(lines, "pages", record.get("pages"))
    add_field(lines, "url", record.get("url"))
    add_field(lines, "access-date", record.get("accessDate"))
    add_field(lines, "language", record.get("language"))
    add_field(lines, "quote", quote or record.get("abstractNote"))
    add_field(lines, "doi", record.get("DOI"))
    add_field(lines, "isbn", record.get("ISBN"))
    add_field(lines, "issn", pick_issn(record.get("ISSN")))
    lines.append("}}")
    return "\n".join(lines)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: wikipedia-citoid-harvest.py <doi-or-url>")

    identifier = sys.argv[1]
    record = fetch_citoid_record(identifier)

    quote = None
    if record.get("url"):
        quote = fetch_quote(record["url"])

    print(format_citoid_as_mediawiki(record, quote=quote))


if __name__ == "__main__":
    main()
