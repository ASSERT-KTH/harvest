#!/usr/bin/python

from harvest_lib import *
from harvest import *
import json
import sys
sys.path.append("/home/martin/workspace/reviewer-recommendation-system/")
import embed as rrs
import semanticscholar_lib
import get_embedding_semanticscholar
import datetime
import math

title = "A Literature Study of Embeddings on Source Code"
title = sys.argv[1]

paper_id = semanticscholar_lib.get_semantic_scholar_id_from_title(title)


# also push to pine cone
get_embedding_semanticscholar.download_and_save(title)


path = path_on_disk_internal_v2(title,prefix="cache/embedding.specter_v2/")
if not os.path.exists(path):
    print("embedding not yet computed at semanticscholar, try again later")
    sys.exit(1)

paper_data = json.load(open(path))

if not paper_data or "vector" not in paper_data["embedding"]:
    print("embedding not yet computed at semanticscholar, try again later")
    missing_entry = {
        "date": datetime.datetime.now().isoformat(),
        "title": title
    }
    with open("cache/embedding_missing.json", "a") as f:
        f.write(json.dumps(missing_entry) + "\n")
    sys.exit(1)

# print(embedding)
vector = paper_data["embedding"]["vector"]


def _extract_vec(x):
    if isinstance(x, dict):
        if "vector" in x:
            return x["vector"]
        if "embedding" in x:
            emb = x["embedding"]
            if isinstance(emb, dict) and "vector" in emb:
                return emb["vector"]
            if isinstance(emb, (list, tuple)):
                return list(emb)
    return x



angles_deg = []
results = []
skipped = []

for cited in semanticscholar_lib.get_cited_papers(paper_id["paperId"]):
    cited_id = cited["citedPaper"]["paperId"]
    try:
        citedPaper = collect_paper_data_from_url_with_cache("https://www.semanticscholar.org/paper/" + cited_id)
    except Exception as e:
        continue
    title2 = citedPaper.get("title", cited_id)
    embedding = get_embedding_and_push_to_db(title2)

    v1 = _extract_vec(embedding)
    v2 = vector  # original paper vector from above

    if not v1 or not v2 or len(v1) != len(v2):
        skipped.append(title2)
        continue

    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        skipped.append(title2)
        continue

    cos = dot / (n1 * n2)
    cos = max(-1.0, min(1.0, cos))
    angle_deg = math.degrees(math.acos(cos))
    angles_deg.append(angle_deg)
    results.append((angle_deg, cos, title2))

# print cited papers by decreasing angle
if results:
    results.sort(key=lambda x: x[0], reverse=True)
    for angle_deg, cos, title2 in results:
        print(title2)
        print(f"cosine={cos:.6f}, angle_deg={angle_deg:.3f}")
        print()
else:
    print("no cited papers with comparable embeddings")

# median angle
if angles_deg:
    angles_deg.sort()
    mid = len(angles_deg) // 2
    if len(angles_deg) % 2:
        median_angle = angles_deg[mid]
    else:
        median_angle = 0.5 * (angles_deg[mid - 1] + angles_deg[mid])
    print(f"median_angle_deg={median_angle:.3f}")
else:
    print("median_angle_deg=n/a")


print("====================  KNN")
titles = []
for x in rrs.search_in_pinecone_semanticscholar(title, vector):
    id = x["id"]
    i = x["title"]
    score = x["score"] if x["score"]<=1 else 1
    print(i,x["score"],type(x["score"]))
    titles.append(i + " (" + f"{math.degrees(math.acos(score)):.2f}" + "°)")
    try:
        try:
            # this works only if already gotten
            paper_data = get_cached_paper_data(i)
        except:
            paper_data = None

        if not paper_data:
            paper_data = collect_paper_data_from_url_with_cache("https://www.semanticscholar.org/paper/"+id.replace("semanticscholar:",""))

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
    # todo
    #print(paper_data) get recommendation from https://api.semanticscholar.org/api-do
# print(paper_id)
print('related in embedding space')
for i in titles:
    print(i)
