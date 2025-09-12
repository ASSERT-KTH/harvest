#!/usr/bin/python

from harvest_lib import *
import json
import sys
sys.path.append("/home/martin/workspace/reviewer-recommendation-system/")
import embed as rrs
import get_embedding_semanticscholar

title = "A Literature Study of Embeddings on Source Code"
title = sys.argv[1]

get_embedding_semanticscholar.download_and_save(title)

path = path_on_disk_internal_v2(title,prefix="cache/embedding.specter_v2/")
vector = json.load(open(path))["embedding"]["vector"]

for id,i in rrs.search_in_pinecone_semanticscholar(title, vector):

    print(id,i)
    # todo get recommendation from https://api.semanticscholar.org/api-docs/recommendations#tag/Paper-Recommendations/operation/post_papers
