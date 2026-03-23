#!/usr/bin/python
"""
Find the 10 papers in cache/toread that are closest in embedding space
to the papers discussed in ../related-work-github/ml-on-code.md

Usage: python notify-ml-on-code.py
"""

import sys
import re
import glob
import json
import numpy as np

sys.path.append("/home/martin/workspace/reviewer-recommendation-system/")
import embed as rrs

from harvest import *
from semanticscholar_lib import get_embedding_and_push_to_db

ML_ON_CODE_MD = "/home/martin/workspace/related-work-github/ml-on-code.md"
TOREAD_DIR = "/home/martin/workspace/scholar-harvest/cache/toread/"
TOP_K = 10


def extract_urls_from_md(path):
    """Extract all URLs from the markdown file."""
    with open(path, "r") as f:
        content = f.read()
    # Extract URLs from markdown links [text](url) and bare URLs
    urls = re.findall(r'\]\((https?://[^)]+)\)', content)
    urls += re.findall(r'(?<!\])\(?(https?://[^\s)\]]+)', content)
    return list(dict.fromkeys(urls))  # deduplicate preserving order


def extract_titles_from_md(path):
    """Extract titles by fetching paper data for each URL in the markdown file."""
    urls = extract_urls_from_md(path)
    print(f"Found {len(urls)} URLs in ml-on-code.md", file=sys.stderr)
    titles = []
    for url in urls:
        try:
            data = collect_paper_data_from_url_with_cache(url)
            if data and data.get("title"):
                titles.append(data["title"])
        except Exception as e:
            print(f"  [skip] {url}: {e}", file=sys.stderr)
    return titles


def avg_embedding(titles):
    """Return the average embedding vector for a list of titles."""
    vectors = []
    for title in titles:
        result = get_embedding_and_push_to_db(title)
        if result and result.get("embedding") and result["embedding"].get("vector"):
            vectors.append(result["embedding"]["vector"])
        else:
            print(f"  [skip] no embedding for: {title}", file=sys.stderr)
    if not vectors:
        return None
    return np.mean(vectors, axis=0).tolist()


def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def main():
    # Step 1: extract titles from ml-on-code.md
    titles = extract_titles_from_md(ML_ON_CODE_MD)
    print(f"Resolved {len(titles)} titles from URLs in ml-on-code.md", file=sys.stderr)

    # Step 2: compute average embedding
    print("Computing average embedding...", file=sys.stderr)
    ref_vector = avg_embedding(titles)
    if ref_vector is None:
        print("Error: could not compute reference embedding", file=sys.stderr)
        sys.exit(1)

    # Step 3: score each paper in toread
    toread_files = glob.glob(TOREAD_DIR + "*")
    print(f"Scoring {len(toread_files)} papers in toread...", file=sys.stderr)

    scored = []
    for filepath in toread_files:
        try:
            with open(filepath) as f:
                paper_data = json.load(f)
            title = paper_data.get("title", "")
            url = paper_data.get("url", "")
            if not title:
                continue
            result = get_embedding_and_push_to_db(title)
            if not result or not result.get("embedding") or not result["embedding"].get("vector"):
                continue
            score = cosine_similarity(ref_vector, result["embedding"]["vector"])
            scored.append((score, title, url))
        except Exception as e:
            print(f"Error processing {filepath}: {e}", file=sys.stderr)

    # Step 4: print top 10
    scored.sort(reverse=True)
    print(f"\nTop {TOP_K} papers closest to ml-on-code.md:")
    for score, title, url in scored[:TOP_K]:
        print(f"* {title} {url}")


if __name__ == "__main__":
    main()
