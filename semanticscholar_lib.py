#!/usr/bin/python

import sys
import requests
import os
import json
import config
import time
from harvest_lib import *
# from harvest import *

def get_semantic_scholar_tldr_embedding(semanticscholarid):
    
    semanticscholar = requests.get("https://api.semanticscholar.org/graph/v1/paper/"+semanticscholarid+"?fields=title,tldr,authors,embedding,embedding.specter_v2", headers = {"x-api-key": config.semanticscholar_key}).json()
    #print(semanticscholar)
    if semanticscholar!=None and "paperId" in semanticscholar:
        # replacing "url:https://arxiv.org/pdf/2409.18317" by real paper if for the reader URL below
        semanticscholarid = semanticscholar["paperId"]

    # tldr
    if semanticscholar!=None and "tldr" in semanticscholar and semanticscholar["tldr"] != None and semanticscholar["tldr"]["text"]:
        tldr=semanticscholar["tldr"]["text"]+"\n\n"

    # embedding
    if semanticscholar!=None and "embedding" in semanticscholar and semanticscholar["embedding"] and "vector" in semanticscholar["embedding"]:     
        embedding = semanticscholar["embedding"]["vector"]
        #note = "related:\n- "+"\n- ".join(rrs.search_in_pinecone_semanticscholar(title, semanticscholar["embedding"]["vector"], 5))

    return {
        "semanticscholarid": semanticscholarid,
        "tldr": tldr if "tldr" in locals() else None,
        "embedding": embedding if "embedding" in locals() else None,
    }
    
def get_embedding(title, output_dir='/home/martin/workspace/scholar-harvest/cache/embedding.specter_v2/', verbose=False, delay=1.0):
    """
    Get embedding for a paper title from SemanticScholar API
    
    Args:
        title (str): Paper title to search for
        output_dir (str): Directory to store embedding data
        verbose (bool): Whether to print verbose output
        
    Returns:
        dict: Full response from SemanticScholar API or None if not found
    """
    if not title or title.strip() == '':
        if verbose:
            print("Error: Empty title")
        return None
        
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Check if we already have this embedding
    target_path = path_on_disk_internal(title, output_dir)
    if os.path.exists(target_path):
        if verbose:
            print(f"Loading cached embedding for: {title}")
        data = json.load(open(target_path))
        data["cached"] = True
        return data

    # Check if this title is in the 404 cache
    not_found_dir = "cache/404/"
    # print(not_found_dir)
    not_found_path = path_on_disk_internal(title, not_found_dir)
    if os.path.exists(not_found_path):
        # Check if the file is not older than 3 weeks
        file_time = os.path.getmtime(not_found_path)
        current_time = time.time()
        three_weeks_in_seconds = 21 * 24 * 60 * 60
        
        if current_time - file_time < three_weeks_in_seconds:
            if verbose:
                print(f"Skipping previously not found title: {title}")
            return None
        elif verbose:
            print(f"404 cache for '{title}' is older than 3 weeks, trying again")
    if verbose:
        print(f"Fetching embedding for: {title}")
        
    # Paper title search
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search/match?query=" + title
        semanticscholar = requests.get(url, headers={"x-api-key": config.semanticscholar_key})
        resp = semanticscholar.json()
        
        if "data" not in resp or not resp["data"]:
            if verbose:
                print(f"No matching paper found for title: {title}")
                print(f"API response: {semanticscholar.text}")
            
            # Create 404 directory if it doesn't exist            
            # Write to 404 cache to avoid future lookups
            not_found_path = path_on_disk_internal(title, not_found_dir)
            with open(not_found_path, "w") as f:
                f.write(json.dumps({
                    "title": title,
                    "response": semanticscholar.text
                }, indent=2))
            return None
            
        semanticscholarid = resp["data"][0]["paperId"]
        
        # Get embeddings
        url = f"https://api.semanticscholar.org/graph/v1/paper/{semanticscholarid}?fields=title,tldr,citationCount,embedding,embedding.specter_v2"
        resp = requests.get(url, headers={"x-api-key": config.semanticscholar_key})
        semanticscholarfull = resp.json()
        # Respect rate limits
        print("grace delay for semanticscholar")
        time.sleep(delay)
        
        # Add the URL for reference
        semanticscholarfull["url"] = url
        
        # Save result
        with open(target_path, "w") as f:
            f.write(json.dumps(semanticscholarfull, indent=2))
            
        semanticscholarfull["cached"] = False
        return semanticscholarfull
        
    except Exception as e:
        if verbose:
            print(f"Error fetching embedding: {str(e)}")
        raise e
        return None



def get_semantic_scholar_id_from_title(title):
    """
    Get the Semantic Scholar paper ID from the title.
    
    {'data': [{'paperId': '38f382ed157cd187d28e14c3eac36e3bed34071e', 'title': 'RepairBench: Leaderboard of Frontier Models for Program Repair', 'matchScore': 237.96303}]}
    """
    fname = path_on_disk_internal_v2(title, "/home/martin/workspace/scholar-harvest/cache/get_semantic_scholar_id_from_title/")
    if os.path.exists(fname):
        with open(fname, "r") as f:
            return json.load(f)
    url = "https://api.semanticscholar.org/graph/v1/paper/search/match?query=" + title
    semanticscholar = requests.get(url, headers={"x-api-key": config.semanticscholar_key})
    orig_data = semanticscholar.json()
    if "data" in orig_data:
        # simplifying the happy path
        data = orig_data["data"][0]
    with open(fname, "w") as f:
        json.dump(data, f)
    return data

def get_paper_info_from_semantic_scholar_id(semanticscholarid):
    fname = f"/home/martin/workspace/scholar-harvest/cache/get_paper_info_from_semantic_scholar_id/{semanticscholarid}"
    if os.path.exists(fname):
        with open(fname, "r") as f:
            return json.load(f)
    # "Details about a paper "
    # documentation https://api.semanticscholar.org/api-docs/#tag/Paper-Data/operation/get_graph_get_paper
    #  If the fields parameter is omitted, only the paperId and title will be returned.
    
    # url: points to a semantic scholar url kinds of boring
    # externalIds: contain arxiv, doi, etc
    # authors
    # fieldsOfStudy cool
    # tldr

    url = "https://api.semanticscholar.org/graph/v1/paper/"+semanticscholarid+"?fields=title,authors,year,externalIds,fieldsOfStudy,tldr"
    semanticscholar = requests.get(url, headers={"x-api-key": config.semanticscholar_key})
    data = semanticscholar.json()
    with open(fname, "w") as f:
        json.dump(data, f)
    return data


class SemanticScholarNotFound(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
def get_url_from_title(title):
    result = get_semantic_scholar_id_from_title(title)
    if "data" not in result:
        raise SemanticScholarNotFound("No data found for title: " + title)
    if normalize_title(result["data"][0]["title"]) == normalize_title(title):
        # print("Title matches: " + result["data"][0]["title"])
        data = get_paper_info_from_semantic_scholar_id(result["data"][0]["paperId"])
        # print(data)
        if "externalIds" in data:
            if "DOI" in data["externalIds"]:
                # print("DOI: " + data["externalIds"]["DOI"])
                try:
                    return get_doi_target(data["externalIds"]["DOI"])
                except Exception as e:
                    return "https://doi.org/" + data["externalIds"]["DOI"]
            elif "ArXiv" in data["externalIds"]:
                return "https://arxiv.org/abs/" + data["externalIds"]["ArXiv"]
            return f"https://www.semanticscholar.org/paper/"+result["data"][0]["paperId"]
            raise Exception("No DOI or ArXiv found for title: " + str(data["externalIds"]))
        # some cases with no DOI
        else: return f"https://www.semanticscholar.org/paper/"+result["data"][0]["paperId"]
    raise SemanticScholarNotFound("Title not found: " + title)        

def get_data_from_title(title):
    real_url = get_url_from_title(title)
    result = collect_paper_data_from_url_with_cache(real_url)
    return result

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python get_semantic_scholar.py <title>")
        sys.exit(1)
    title = sys.argv[1]
    result = get_data_from_title(title)
    print(result)
