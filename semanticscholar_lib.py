#!/usr/bin/python

import sys
import requests
import os
import json
import config
import time
from harvest_lib import *
import embed
# from harvest import *

SEMANTICSCHOLAR_DELAY=1.0

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

def get_embedding_and_push_to_db(title, output_dir='/home/martin/workspace/scholar-harvest/cache/embedding.specter_v2/', verbose=False, delay=1.0):
    result = get_embedding(title, output_dir, verbose, delay)
    # print(result)
    if result and "embedding" in result and result["embedding"] and "vector" in result["embedding"]:
        embed.push_single_entry_to_pinecone("se-semanticscholar", result)
    return result

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
        if not data or not "embedding" in data or not data["embedding"] or "vector" not in data["embedding"]:
            os.remove(target_path)
            return get_embedding(title, output_dir, verbose, delay)
        if data and data["embedding"]:
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
                    "url": url,
                    "title": title,
                    "response": semanticscholar.text
                }, indent=2))
            return None
            
        semanticscholarid = resp["data"][0]["paperId"]
        
        # Get embeddings
        url = f"https://api.semanticscholar.org/graph/v1/paper/{semanticscholarid}?fields=title,tldr,citationCount,embedding,embedding.specter_v2"
        resp = requests.get(url, headers={"x-api-key": config.semanticscholar_key})
        semanticscholarfull = resp.json()

        if "embedding" not in semanticscholarfull or not semanticscholarfull["embedding"] or "vector" not in semanticscholarfull["embedding"]:
            not_found_path = path_on_disk_internal(title, not_found_dir)
            with open(not_found_path, "w") as f:
                f.write(json.dumps({
                    "url": url,
                    "title": title,
                    "response": resp.text
                }, indent=2))

        # Respect rate limits
        print("grace delay for semanticscholar embedding call for ", title, file=sys.stderr)
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
            try:
                data = json.load(f)
                return data
            except:
                os.remove(fname)
                return get_semantic_scholar_id_from_title(title)
        
    # the service does not like column so removing them
    #  
    title = title.replace(":","")

    url = "https://api.semanticscholar.org/graph/v1/paper/search/match?query=" + title

    semanticscholar = requests.get(url, headers={"x-api-key": config.semanticscholar_key})
    time.sleep(SEMANTICSCHOLAR_DELAY)
    # print(semanticscholar.text)
    semanticscholar.raise_for_status()
    orig_data = semanticscholar.json()
    if "data" in orig_data:
        # simplifying the happy path
        data = orig_data["data"][0]
    else: raise Exception("not found in SemanticScholar")
    with open(fname, "w") as f:
        json.dump(data, f)
    return data

def get_paper_info_from_semantic_scholar_id(semanticscholarid):
    """
    Low level function used by collect_paper_data_from_semanticscholar
    
    """
    fname = f"/home/martin/workspace/scholar-harvest/cache/get_paper_info_from_semantic_scholar_id/{semanticscholarid}"
    if os.path.exists(fname):
        with open(fname, "r") as f:
            data = json.load(f)
            return data
    # "Details about a paper "
    # documentation https://api.semanticscholar.org/api-docs/#tag/Paper-Data/operation/get_graph_get_paper
    #  If the fields parameter is omitted, only the paperId and title will be returned.
    
    # url: points to a semantic scholar url kinds of boring
    # externalIds: contain arxiv, doi, etc
    # authors
    # fieldsOfStudy cool
    # tldr

    url = "https://api.semanticscholar.org/graph/v1/paper/"+semanticscholarid+"?fields=title,authors,year,venue,externalIds,fieldsOfStudy,tldr"
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
    # print(result)
    if "paperId" not in result:
        raise SemanticScholarNotFound("No data found for title: " + title)
    if normalize_title(result["title"]) == normalize_title(title):
        # print("Title matches: " + result["data"][0]["title"])
        data = get_paper_info_from_semantic_scholar_id(result["paperId"])
        if "externalIds" in data:
            if "DOI" in data["externalIds"]:
                # print("DOI: " + data["externalIds"]["DOI"])
                try:
                    return get_doi_target(data["externalIds"]["DOI"])
                except Exception as e:
                    raise e
                    return "https://doi.org/" + data["externalIds"]["DOI"]
            elif "ArXiv" in data["externalIds"]:
                return "https://arxiv.org/abs/" + data["externalIds"]["ArXiv"]
            return f"https://www.semanticscholar.org/paper/"+result["data"][0]["paperId"]
            raise Exception("No DOI or ArXiv found for title: " + str(data["externalIds"]))
        # some cases with no DOI
        else: return f"https://www.semanticscholar.org/paper/"+result["data"][0]["paperId"]
    raise SemanticScholarNotFound("Title does not match: " + title +" "+normalize_title(result["title"]) +" "+ normalize_title(title))        

def get_data_from_title(title):
    real_url = get_url_from_title(title)
    result = collect_paper_data_from_url_with_cache(real_url)
    return result

def get_recommended_papers(paper_id, cache_dir="/home/martin/workspace/scholar-harvest/cache/recommendations/", verbose=False):
    """
    Get recommended papers for a given paper ID from Semantic Scholar API
    
    Args:
        paper_id (str): The Semantic Scholar paper ID
        cache_dir (str): Directory to store cached recommendations
        verbose (bool): Whether to print verbose output
        
    Returns:
        dict: API response containing recommended papers with title, url, and authors
              or None if not found
    """
    if not paper_id or paper_id.strip() == '':
        raise Exception("Error: Empty paper ID")
        return None
        
    # Ensure cache directory exists
    os.makedirs(cache_dir, exist_ok=True)
    
    # Check if we already have cached recommendations
    cache_file = os.path.join(cache_dir, f"{paper_id}.json")
    if os.path.exists(cache_file):
        if verbose:
            print(f"Loading cached recommendations for paper ID: {paper_id}")
        with open(cache_file, "r") as f:
            data = json.load(f)
            data["cached"] = True
            return data
    
    if verbose:
        print(f"Fetching recommendations for paper ID: {paper_id}")
        
    url = f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{paper_id}"
    response = requests.get(url, headers={"x-api-key": config.semanticscholar_key})
    
    if response.status_code == 404:
        if verbose:
            print(f"No recommendations found for paper ID: {paper_id}")
        return None
        
    response.raise_for_status()  # Raise an exception for bad status codes
    data = response.json()
    
    # Add metadata
    data["paper_id"] = paper_id
    data["cached"] = False
    data["fetched_at"] = time.time()
    
    # Save to cache
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)
        
    if verbose:
        print(f"Found {len(data.get('recommendedPapers', []))} recommendations")
        
    # Respect rate limits
    time.sleep(SEMANTICSCHOLAR_DELAY)
    
    return data


def get_cited_papers(paper_id, cache_dir="/home/martin/workspace/scholar-harvest/cache/cited_papers/", verbose=False):
    """
    Get papers cited by a given paper ID from Semantic Scholar API
    
    Args:
        paper_id (str): The Semantic Scholar paper ID
        cache_dir (str): Directory to store cached cited papers data
        verbose (bool): Whether to print verbose output
        
    Returns:
        dict: API response containing cited papers with offset, citingPaperInfo, and data array
              or None if not found
    """
    if not paper_id or paper_id.strip() == '':
        raise Exception("Error: Empty paper ID")
        return None
        
    # Ensure cache directory exists
    os.makedirs(cache_dir, exist_ok=True)
    
    # Check if we already have cached cited papers
    cache_file = os.path.join(cache_dir, f"{paper_id}.json")
    if os.path.exists(cache_file):
        if verbose:
            print(f"Loading cached cited papers for paper ID: {paper_id}")
        with open(cache_file, "r") as f:
            data = json.load(f)
            # data["cached"] = True
            return data
    
    if verbose:
        print(f"Fetching cited papers for paper ID: {paper_id}")
        
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/references"
    response = requests.get(url, headers={"x-api-key": config.semanticscholar_key})
    
    if response.status_code == 404:
        if verbose:
            print(f"No cited papers found for paper ID: {paper_id}")
        return None
        
    response.raise_for_status()  # Raise an exception for bad status codes
    data = response.json()
    
    data = data["data"]
    data = [d for d in data if "citedPaper" in d and "paperId" in d["citedPaper"] and d["citedPaper"]["paperId"]]

    # Save to cache
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)
        
    if verbose:
        cited_count = len(data.get('data', []))
        print(f"Found {cited_count} cited papers")
        
    # Respect rate limits
    time.sleep(SEMANTICSCHOLAR_DELAY)

    return data


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python get_semantic_scholar.py <title>")
        sys.exit(1)
    title = sys.argv[1]
    result = get_data_from_title(title)
    print(result)
