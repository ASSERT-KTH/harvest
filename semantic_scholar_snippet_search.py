#!/usr/bin/python

from semanticscholar_lib import snippet_search_bibtex
import sys
import argparse

parser = argparse.ArgumentParser(
    description="Search for academic papers on Semantic Scholar and return results in BibTeX format.",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Input:
  QUERY   A free-text search query (e.g. a keyword, phrase, or sentence).
          The query is matched against paper titles, abstracts, and snippets.

Output:
  YAML list where each entry has the following fields:
    title     - Paper title
    abstract  - Full abstract of the paper
    snippet   - The text snippet that matched the query
    bibtex    - BibTeX citation entry for the paper

Example:
  semantic_scholar_snippet_search "automated program repair"
""",
)
parser.add_argument("query", help="Search query string")
args = parser.parse_args()

snippets = snippet_search_bibtex(args.query)
print(snippets)
