#!/usr/bin/python

import argparse
import sys

from semanticscholar_lib import snippet_search_bibtex


def build_parser():
    prog = sys.argv[0] or "paper_search"
    return argparse.ArgumentParser(
        description="Search for academic papers on Semantic Scholar and return results in BibTeX format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
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
  {prog} "automated program repair"
""",
    )


def main():
    parser = build_parser()
    parser.add_argument("query", help="Search query string")
    args = parser.parse_args()
    print(snippet_search_bibtex(args.query))


if __name__ == "__main__":
    main()
