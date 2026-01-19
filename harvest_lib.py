import hashlib
import requests
import json
import re

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

def unredirect(url):
    if "www.google.com/url" in url:
        # extract url query parameter like &url=
        url_pattern = r"[&?]url=([^&]+)"
        match = re.search(url_pattern, url)
        if match:
            extracted_url = match.group(1)
            if extracted_url:
                return extracted_url
    # handle outlook https://can01.safelinks.protection.outlook.com/?url=https%3A%2F%2Fscholar.google.com%2Fscholar_url%3Furl%3Dhttps%3A%2F%2Fhammer.purdue.edu%2Farticles%2Fthesis%2FA_Quantitative_Comparison_of_Pre-Trained_Model_Registries_to_Traditional_Software_Package_Registries%2F25686447%2F1%2Ffiles%2F46096152.pdf%26hl%3Den%26sa%3DX%26d%3D3778915615121808096%26ei%3DWbs9Zvz3KO2q6rQPwMehqAs%26scisig%3DAFWwaebHos93BVLfDSF-cqYVV5JP%26oi%3Dscholaralrt%26html%3D%26pos%3D0%26folt%3Dkw&data=05%7C02%7Cbenoit.baudry%40umontreal.ca%7Cf7c7f9aadefe4c7f381e08dc70b88009%7Cd27eefec2a474be7981e0f8977fa31d8%7C1%7C0%7C638509185050969324%7CUnknown%7CTWFpbGZsb3d8eyJWIjoiMC4wLjAwMDAiLCJQIjoiV2luMzIiLCJBTiI6Ik1haWwiLCJXVCI6Mn0%3D%7C0%7C%7C%7C&sdata=75S2RaKdONqqniD93HCYrSlAKT0N3Lsreeg87SZZZSY%3D&reserved=0
    if "safelinks.protection.outlook.com" in url:
        url_pattern = r"url=([^&]+)"
        match = re.search(url_pattern, url)
        if match:
            extracted_url = match.group(1)
            if extracted_url:
                return unredirect(extracted_url)
            
    return url
