import hashlib
import requests
import json

def normalize_title(papertitle):
    # the single quote in a title is a caveat ’/'
    # the comma in a title is a caveat
    # special space  
    return papertitle.lower().strip().rstrip(".").replace(","," ").replace("   "," ").replace("  "," ").replace("’","'").replace("{","").replace("}","").replace(' ',' ')
def path_on_disk_internal_v2(papertitle, prefix="/home/martin/workspace/scholar-harvest/cache/harvest/"):
    # assert prefix.endswith("/")
    """ returns the local file name corresponding to a paper LOWER CASE BETTER THAN V1"""
    # remove trailing space and trailing dots from paper.desc
    papertitle = normalize_title(papertitle)
    return prefix+hashlib.sha256(papertitle.encode("utf-8")).hexdigest()+".json"
def DEPRECATED_path_on_disk_internal_v1(papertitle, prefix):
    assert prefix.endswith("/")
    """ DEPRECATED SEE V2 """
    # remove trailing space and trailing dots from paper.desc
    papertitle = papertitle.strip().rstrip(".").replace("   "," ").replace("  "," ")
    return prefix+hashlib.sha256(papertitle.encode("utf-8")).hexdigest()+".json"
def path_on_disk(paper):
    return path_on_disk_internal_v2(paper.desc, "/home/martin/workspace/scholar-harvest/cache/harvest/")
def path_on_disk_internal(papertitle, prefix = "/home/martin/workspace/scholar-harvest/cache/harvest/"):
    return path_on_disk_internal_v2(papertitle, prefix)


def get_doi_target(doi):
    # https://doi.org/api/handles/10.1145/3597503.3623337
    url = f"https://doi.org/api/handles/{doi}"
    data = requests.get(url).json()
    if data["responseCode"] == 1:
        for i in data["values"]:
            if i["type"] == "URL":
                return i["data"]["value"]
    raise Exception("doi not found")

def get_cached_paper_data(title):
    path = path_on_disk_internal_v2(title,prefix="/home/martin/workspace/scholar-harvest/cache/harvest/")
    return json.load(open(path))