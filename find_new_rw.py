#!/usr/bin/python
"""
Find new related work (missing references) based on a list of papers in a GitHub issue.

This script analyzes the papers listed in a given GitHub issue URL to discover potentially
missed related work. It employs two primary methods for discovery:
1. Citation Graph Analysis: Identifies papers that frequently cite the papers listed in the issue.
2. Embedding Space Similarity: Uses vector embeddings to find papers that are semantically
   similar to those listed in the issue.

The script filters out papers that are already mentioned in the issue content to suggest
only new, relevant additions.

Usage:
    python find_new_rw.py <issue_url>

Example:
    python find_new_rw.py https://github.com/ASSERT-KTH/related-work/issues/67

This is a successor to and new implementation of previous tools like bibassist.py
and missingreferences.py.
"""

import json
import harvest_lib
import harvest
import semanticscholar_lib
import sys
import re
import embed
import issues_to_readme
import traceback
import collections
import os
import overleaf_lib


def extract_urls(content):

    # Regex pattern to match URLs
    url_pattern = r'https?://[^\s\)\]\>"\'<,]+'

    # Find all URLs
    urls = re.findall(url_pattern, content)

    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        url = harvest_lib.unredirect(url)
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    return unique_urls


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python find_new_rw.py <issue_url|md_file|folder>")
        print(
            "Example: python find_new_rw.py https://github.com/ASSERT-KTH/related-work/issues/92"
        )
        print("Example: python find_new_rw.py related_work.md")
        sys.exit(1)

    if sys.argv[1].startswith("https://github.com"):
        # bit dirty to harvest_lib.normalize_title for the whole text
        content = harvest_lib.normalize_title(
            issues_to_readme.single_issue_to_markdown_with_cache(sys.argv[1])
        )

        print(content[:200])
        urls = extract_urls(content)
        source_text = "this issue"
    elif os.path.isfile(sys.argv[1]) and sys.argv[1].endswith(".md"):
        source_text = "this document"

        with open(sys.argv[1], "r") as f:
            content = harvest_lib.normalize_title(f.read())
        urls = extract_urls(content)
    elif os.path.isdir(sys.argv[1]):
        source_text = "this paper"

        data = overleaf_lib.extract_citations_url_from_paper_folder(sys.argv[1])
        for k, v in dict(data).items():
            data[harvest_lib.normalize_title(k)] = v
        content = json.dumps(data, indent=2)
        urls = list(data.values())
        # print(content[:200])
    else:
        print("No README.md found in the folder.")
        sys.exit(1)
    # print(urls)

    incorrect_titles = []
    all_citations = []  # (title, url) for every resolved input paper

    paperIds = set()

    for url in urls:
        paperId = None
        try:
            data = harvest.collect_paper_data_from_url_with_cache(url)
            if data and "doi" in data and data["doi"] and len(data["doi"]) > 0:
                paperId = semanticscholar_lib.get_semantic_scholar_id_from_url(
                    data["doi"], prefix="DOI:"
                )
            elif "arxiv.org" in url:
                paperId = semanticscholar_lib.get_semantic_scholar_id_from_url(
                    url, prefix="URL:"
                )
            elif (
                data
                and "semanticscholarid" in data
                and len(data["semanticscholarid"]) > 0
                and "arxiv.org" not in url
            ):
                paperId = data["semanticscholarid"]
            elif data and "title" in data and len(data["title"]) > 0:
                ssdata = semanticscholar_lib.get_semantic_scholar_id_from_title(
                    data["title"]
                )
                if ssdata:
                    paperId = ssdata["paperId"]
        except Exception as e:
            print(f"error processing {url}: {e}")
            traceback.print_exc()
            continue

        if paperId:
            paperIds.add(paperId)

        if data and "title" in data:
            all_citations.append((data["title"], url))

        url2 = f"https://www.semanticscholar.org/paper/{paperId}"
        # print(url2)
        citing_data = harvest.collect_paper_data_from_url_with_cache(url2)
        if citing_data:
            if harvest_lib.normalize_title(citing_data["title"]) not in content:
                incorrect_titles.append((url, citing_data))
    for url, citing_data in incorrect_titles:
        print("INCORRECT TITLE", url, citing_data["title"])

    print(f"## All citations in {source_text}:")
    i = 1
    for title, url in all_citations:
        print(f"{title}")
        print(url)
        print()
        i += 1

    # now checking for very close papers in embedding space
    # Collect embeddings for all papers mentioned in the issue
    paper_embeddings = {}
    citations = collections.Counter()
    title_to_paperId_cg = {}
    for paperId in paperIds:
        paper_data = semanticscholar_lib.get_embedding_from_paper_id(paperId)

        paper_embeddings[paperId] = paper_data
        if (
            paper_data
            and "embedding" in paper_data
            and "title" in paper_data
            and paper_data["embedding"]
            and "vector" in paper_data["embedding"]
        ):
            print(f"Found embedding for {paper_data['title']} {paperId}")
            # print(paper_data["embedding"]["vector"])
        else:
            print(f"No embedding found for {paperId}")

        for x in semanticscholar_lib.get_citing_papers(paperId):
            citer = semanticscholar_lib.get_paper_info_from_semantic_scholar_id(x)
            if "title" not in citer:
                continue
            if citer["title"].lower() in content.lower():
                continue
            citations[citer["title"]] += 1
            if citer["title"] not in title_to_paperId_cg:
                title_to_paperId_cg[citer["title"]] = citer.get("paperId", x)
    print(f"\n## Missing papers from {source_text} (by citation graph):")
    for title, count in citations.most_common(10):
        print(f"{title} : {count} citations")
        paperId = title_to_paperId_cg.get(title, "")
        if paperId:
            print(f"https://www.semanticscholar.org/paper/{paperId}")

    print(f"\n## Missing papers from {source_text} (by closeness in embedding space):")
    embedding_suggestions = collections.Counter()
    title_to_paperId_emb = {}
    for paperId, paper_data in paper_embeddings.items():
        if (
            paper_data
            and "embedding" in paper_data
            and paper_data["embedding"]
            and "vector" in paper_data["embedding"]
        ):
            vector = paper_data["embedding"]["vector"]
            try:
                results = embed.search_in_pinecone_semanticscholar(
                    paper_data.get("title", "query"), vector, top_k=10
                )
                for res in results:
                    title = res["title"]
                    # filter out if title is already in the issue content
                    if title.lower() in content.lower():
                        continue
                    embedding_suggestions[title] += 1
                    if title not in title_to_paperId_emb:
                        title_to_paperId_emb[title] = res["id"]
            except Exception as e:
                print(f"Error searching embedding space for {paperId}: {e}")

    for title, count in embedding_suggestions.most_common(10):
        print(f"{title} : {count}")
        paperId = title_to_paperId_emb.get(title, "")
        if paperId:
            print(f"https://www.semanticscholar.org/paper/{paperId}")
