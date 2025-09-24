#!/usr/bin/python

from harvest_lib import *
from harvest import *
import json
import sys
sys.path.append("/home/martin/workspace/reviewer-recommendation-system/")
import embed as rrs
import get_embedding_semanticscholar

title = "A Literature Study of Embeddings on Source Code"
title = sys.argv[1]

get_embedding_semanticscholar.download_and_save(title)

path = path_on_disk_internal_v2(title,prefix="cache/embedding.specter_v2/")
embedding = json.load(open(path))

if not embedding or "vector" not in embedding["embedding"]:
    print("embedding not yet computed at semanticscholar, try again later")
    sys.exit(1)

vector = embedding["vector"]

for id,i in rrs.search_in_pinecone_semanticscholar(title, vector):

    print(i)
    try:
        try:
            paper_data = get_paper_data(i)
        except:
            paper_data = None

        if not paper_data:
            paper_data = collect_paper_data_from_url_with_cache("https://www.semanticscholar.org/paper/"+id)

        # print(paper_data)
        print(paper_data["venue_title"])
        print(paper_data["url"])
        if "tldr" in paper_data and paper_data["tldr"]:
            print("tldr: "+paper_data["tldr"])
    except Exception as e:
        raise e
        pass
        # print(f"Error processing URL: {url}\n   ")
    print()
    # todo get recommendation from https://api.semanticscholar.org/api-docs/recommendations#tag/Paper-Recommendations/operation/post_papers
