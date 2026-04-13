#!/usr/bin/python
"""
Find the 10 papers in cache/toread that best match the existing LLM-on-code
keyword categories.

Usage: python notify-ml-on-code-fast.py
"""

import glob
import json
import sys

from harvest import CLASSIFICATION_DATA, Paper, transfer_data_from_dict_to_paper

TOREAD_DIR = "/home/martin/workspace/scholar-harvest/cache/toread/"
TOP_K = 10
LLM_CATEGORY_PREFIX = "llm -"
EXTRA_TARGET_CATEGORIES = {"Generative AI", "Machine Learning"}
CODE_MODELS_CATEGORY = "LLM - Code Models"


def get_llm_keyword_map():
    """Return all existing LLM-related keywords grouped by category."""
    keyword_map = {}
    for category, keywords in CLASSIFICATION_DATA.items():
        if category.lower().startswith(LLM_CATEGORY_PREFIX) or category in EXTRA_TARGET_CATEGORIES:
            keyword_map[category] = keywords
    return keyword_map


def unique_in_order(items):
    """Deduplicate while preserving input order."""
    return list(dict.fromkeys(items))


def collect_matches(text, keyword_map):
    """Return matched categories and keywords for a lower-cased text."""
    matched_categories = []
    matched_keywords = []

    for category, keywords in keyword_map.items():
        category_matched = False
        for keyword in keywords:
            if keyword.lower() in text:
                matched_keywords.append(keyword)
                category_matched = True
        if category_matched:
            matched_categories.append(category)

    return unique_in_order(matched_categories), unique_in_order(matched_keywords)


def normalize_text(value):
    """Flatten paper metadata to a plain searchable string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(normalize_text(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(normalize_text(v) for v in value)
    return str(value)


def score_paper(paper, keyword_map):
    """
    Score a paper using keyword matches only.

    Title matches are weighted more heavily than abstract/reason/venue matches.
    """
    title = normalize_text(paper.desc).lower()
    context = " ".join(
        filter(
            None,
            [
                normalize_text(paper.abstract),
                normalize_text(paper.print_reason()),
                normalize_text(paper.venue_title),
                normalize_text(getattr(paper, "note", "")),
            ],
        )
    ).lower()

    title_categories, title_keywords = collect_matches(title, keyword_map)
    context_categories, context_keywords = collect_matches(context, keyword_map)
    _, code_title_keywords = collect_matches(title, {CODE_MODELS_CATEGORY: keyword_map[CODE_MODELS_CATEGORY]})
    _, code_context_keywords = collect_matches(
        context, {CODE_MODELS_CATEGORY: keyword_map[CODE_MODELS_CATEGORY]}
    )

    categories = unique_in_order(title_categories + context_categories)
    keywords = unique_in_order(title_keywords + context_keywords)
    score = len(title_keywords) * 10 + len(context_keywords)
    score += len(code_title_keywords) * 20 + len(code_context_keywords) * 5

    return (
        score,
        categories,
        keywords,
        title_keywords,
        context_keywords,
        code_title_keywords,
        code_context_keywords,
    )


def load_paper(filepath):
    with open(filepath) as f:
        paper_data = json.load(f)

    paper = Paper(paper_data.get("url", ""), paper_data.get("title", ""))
    transfer_data_from_dict_to_paper(paper, paper_data)
    return paper


def main():
    keyword_map = get_llm_keyword_map()
    llm_keyword_count = sum(len(keywords) for keywords in keyword_map.values())
    print(
        f"Loaded {llm_keyword_count} LLM-on-code keywords from {len(keyword_map)} categories",
        file=sys.stderr,
    )

    toread_files = glob.glob(TOREAD_DIR + "*")
    print(f"Scoring {len(toread_files)} papers in toread...", file=sys.stderr)

    scored = []
    for filepath in toread_files:
        try:
            paper = load_paper(filepath)
            if not paper.desc:
                continue

            (
                score,
                categories,
                keywords,
                title_keywords,
                context_keywords,
                code_title_keywords,
                code_context_keywords,
            ) = score_paper(paper, keyword_map)
            if score == 0:
                continue

            scored.append(
                (
                    score,
                    len(code_title_keywords),
                    len(code_context_keywords),
                    len(title_keywords),
                    len(context_keywords),
                    paper.desc,
                    paper.url,
                    categories,
                    keywords,
                )
            )
        except Exception as e:
            print(f"Error processing {filepath}: {e}", file=sys.stderr)

    scored.sort(reverse=True)
    print(f"\nTop {TOP_K} papers by LLM-on-code keyword matches:")
    for score, code_title_hits, code_context_hits, title_hits, context_hits, title, url, categories, keywords in scored[:TOP_K]:
        print(f"* [{score}] {title} {url}")
        print(f"  categories: {', '.join(categories)}")
        print(f"  keywords: {', '.join(keywords)}")
        print(
            "  "
            f"code_title_hits={code_title_hits}, code_context_hits={code_context_hits}, "
            f"title_hits={title_hits}, context_hits={context_hits}"
        )


if __name__ == "__main__":
    main()
