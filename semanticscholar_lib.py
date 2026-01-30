#!/usr/bin/python

import sys
import requests
import os
import json
import config
import time
from harvest_lib import *
import yaml
from datetime import datetime
import hashlib

try:
    import embed
except: pass

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

    if result and "cached" in result and result["cached"] == True:
        return result
    
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
        if "authors" not in data or not isinstance(data["authors"], str):
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
        
        semanticscholarfull = get_embedding_from_paper_id(semanticscholarid,delay)
        
        # Respect rate limits
        # print("grace delay for semanticscholar embedding call for ", title, file=sys.stderr)
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

def get_embedding_from_paper_id(semanticscholarid, delay=SEMANTICSCHOLAR_DELAY):
    """
    Get embedding and other details for a paper from its Semantic Scholar ID.
    Includes caching support.
    """
    cache_dir = "/home/martin/workspace/scholar-harvest/cache/get_embedding_from_paper_id/"

    assert not semanticscholarid.startswith("http")
    os.makedirs(cache_dir, exist_ok=True)
    fname = os.path.join(cache_dir, f"{semanticscholarid}.json")

    not_found_dir = "cache/404/"
    os.makedirs(not_found_dir, exist_ok=True)
    # Note: 'title' is not available in this function; assuming it's passed or derived if needed
    # For now, using semanticscholarid as a placeholder for title in path
    not_found_path = os.path.join(not_found_dir, f"{semanticscholarid}.json")

    if os.path.exists(not_found_path):
        if (time.time() - os.path.getmtime(not_found_path) > 21 * 24 * 60 * 60):
            os.remove(not_found_path)
            return get_embedding_from_paper_id(semanticscholarid, delay)
        with open(not_found_path, "r") as f:
            return json.load(f)
        
    
    
    # Get embeddings
    url = f"https://api.semanticscholar.org/graph/v1/paper/{semanticscholarid}?fields=authors,title,tldr,citationCount,embedding,embedding.specter_v2"
    resp = requests.get(url, headers={"x-api-key": config.semanticscholar_key})
    semanticscholarfull = resp.json()

    if 'authors' in semanticscholarfull and isinstance(semanticscholarfull['authors'], list):
        semanticscholarfull["authors_list"] = semanticscholarfull["authors"]
        semanticscholarfull["authors"] = ", ".join([a["name"] for a in semanticscholarfull["authors"]]) if "authors" in semanticscholarfull else ""
    # raise Exception(semanticscholarfull)
    if "embedding" not in semanticscholarfull or not semanticscholarfull["embedding"] or "vector" not in semanticscholarfull["embedding"]:
        data = {
                "url": url,
                "semanticscholarid": semanticscholarid,
                "response": resp.text,
                "embedding": None
            }
        with open(not_found_path, "w") as f:
            f.write(json.dumps(data, indent=2))
        return data
    
    semanticscholarfull["url"] = url

    # Save to cache
    with open(fname, "w") as f:
        json.dump(semanticscholarfull, f, indent=2)
    
    return semanticscholarfull


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
    title = title.replace(":","").replace("'","").replace('’','')

    url = "https://api.semanticscholar.org/graph/v1/paper/search/match?query=" + title

    semanticscholar = requests.get(url, headers={"x-api-key": config.semanticscholar_key})
    time.sleep(SEMANTICSCHOLAR_DELAY)
    # print(semanticscholar.text)
    if semanticscholar.status_code != 200:
        return None
    orig_data = semanticscholar.json()
    if "data" in orig_data:
        # simplifying the happy path
        data = orig_data["data"][0]
    else: raise Exception("not found in SemanticScholar")
    with open(fname, "w") as f:
        json.dump(data, f)
    return data

def hash_string(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def get_semantic_scholar_id_from_url(url, prefix = "URL:"):
    """
    Get the Semantic Scholar paper ID from a URL by calling 
    https://api.semanticscholar.org/graph/v1/paper/URL:<url>
    
    Example:
    python -c "from semanticscholar_lib import get_semantic_scholar_id_from_url; print(get_semantic_scholar_id_from_url('https://arxiv.org/abs/2409.18317'))"

    with doi
    python -c "from semanticscholar_lib import get_semantic_scholar_id_from_url; print(get_semantic_scholar_id_from_url('https://doi.org/10.1145/3366423.3380143'))"
    """
    os.makedirs("cache/get_semantic_scholar_id_from_url/", exist_ok=True)
    fname = f"cache/get_semantic_scholar_id_from_url/{hash_string(url)}"
    if os.path.exists(fname):
        with open(fname, "r") as f:
            data = json.load(f)
            return data["paperId"]
    semanticscholar = requests.get(f"https://api.semanticscholar.org/graph/v1/paper/{prefix}"+url, headers={"x-api-key": config.semanticscholar_key})
    time.sleep(SEMANTICSCHOLAR_DELAY)
    # semanticscholar.raise_for_status()
    if semanticscholar.status_code != 200:
        # raise Exception(f"Error fetching Semantic Scholar ID for URL {url}: {semanticscholar.status_code} {semanticscholar.text}")
        return None
    data = semanticscholar.json()
    with open(fname, "w") as f:
        json.dump(data, f)
    return data["paperId"]

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

def get_citing_papers(paper_id, verbose=False):
    """
    Get papers that cite a given paper ID from Semantic Scholar API
    
    Example: 
    python -c "from semanticscholar_lib import get_citing_papers; print(get_citing_papers('doi:10.1145/3366423.3380143'))"

    python -c "from semanticscholar_lib import get_citing_papers; print(get_citing_papers('arxiv:2411.18401'))"

        Args:
        paper_id (str): The Semantic Scholar paper ID or external ID (e.g., DOI, ArXiv) with prefix
        verbose (bool): Whether to print verbose output
        
    Returns:
        list: List of citing papers or None if not found
    """
    cache_dir = "/home/martin/workspace/scholar-harvest/cache/citing_papers/"
    
    if not paper_id or paper_id.strip() == '':
        raise Exception("Error: Empty paper ID")
        return None
        
    # Ensure cache directory exists
    os.makedirs(cache_dir, exist_ok=True)
    
    # Check if we already have cached citing papers
    # Replace special characters in paper_id to create a safe filename
    safe_paper_id = paper_id.replace("/", "_").replace(":", "_").replace("\\", "_")
    cache_file = os.path.join(cache_dir, f"{safe_paper_id}.json")

    if os.path.exists(cache_file):
        # Check if cache is older than 3 weeks
        file_time = os.path.getmtime(cache_file)
        current_time = time.time()
        three_weeks_in_seconds = 21 * 24 * 60 * 60        
        if current_time - file_time > three_weeks_in_seconds:
            os.remove(cache_file)

    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            data = json.load(f)
            return data

    
    
    if verbose:
        print(f"Fetching citing papers from SemanticScholar API for paper ID: {paper_id}")
        
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations"
    response = requests.get(url, headers={"x-api-key": config.semanticscholar_key})
    
    if response.status_code == 404:
        if verbose:
            print(f"No citing papers found for paper ID: {paper_id}")
        return None
        
    response.raise_for_status()  # Raise an exception for bad status codes
    data = response.json()
    
    # print(paper_id,data)
    if 'data' not in data or not data['data']:
        return []
    
    data = data["data"]
    data = [d["citingPaper"]["paperId"] for d in data if "citingPaper" in d and "paperId" in d["citingPaper"] and d["citingPaper"]["paperId"]]

    # Save to cache
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)
        
    if verbose:
        print(f"Found {len(data)} citing papers")
        
    # Respect rate limits
    time.sleep(SEMANTICSCHOLAR_DELAY)

    return data

def get_cited_papers(paper_id, cache_dir="/home/martin/workspace/scholar-harvest/cache/cited_papers/", verbose=True):
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
    print(paper_id,data)
    if 'data' not in data or not data['data']:
        return []
        
    data = data["data"]
    data = [d["citedPaper"]["paperId"] for d in data if "citedPaper" in d and "paperId" in d["citedPaper"] and d["citedPaper"]["paperId"]]

    # Save to cache
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)
        
    if verbose:
        cited_count = len(data)
        print(f"Found {cited_count} cited papers")
        
    # Respect rate limits
    time.sleep(SEMANTICSCHOLAR_DELAY)

    return data

def latex_sanitize_file(path):
    """
    Sanitize a file for LaTeX by escaping all special characters.

    python -c "from semanticscholar_lib import latex_sanitize_file; latex_sanitize_file('test.txt')"
    """
    with open(path, "r") as f:
        content = f.read()
    sanitized_content = latex_sanitize(content)
    with open(path, "w") as f:
        f.write(sanitized_content)

def latex_sanitize(string):
    """
    Sanitize a string for LaTeX by escaping all special characters.
    https://claude.ai/chat/0ec82764-0548-4922-9f01-835ebf460276
    Args:
        string: The input string to sanitize
    
    Returns:
        A string with LaTeX special characters properly escaped
    """
    if not isinstance(string, str):
        return string
    
    # Dictionary mapping special characters to their LaTeX escaped versions
    replacements = {
        '\\': r'\textbackslash{}',
        # '{': r'\{',
        # '}': r'\}',
        '$': r'\$',
        '&': r'\&',
        '%': r'\%',
        '#': r'\#',
        '_': r'\_',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }

    # Common accents and diacritics that need special handling in LaTeX
    accent_replacements = {
        'á': r"\'a", 'à': r'\`a', 'â': r'\^a', 'ä': r'\"a', 'ã': r'\~a', 'å': r'\aa',
        'é': r"\'e", 'è': r'\`e', 'ê': r'\^e', 'ë': r'\"e',
        'í': r"\'i", 'ì': r'\`i', 'î': r'\^i', 'ï': r'\"i',
        'ó': r"\'o", 'ò': r'\`o', 'ô': r'\^o', 'ö': r'\"o', 'õ': r'\~o', 'ø': r'\o',
        'ú': r"\'u", 'ù': r'\`u', 'û': r'\^u', 'ü': r'\"u',
        'ý': r"\'y", 'ÿ': r'\"y',
        'ñ': r'\~n',
        'ç': r'\c{c}',
        'Á': r"\'A", 'À': r'\`A', 'Â': r'\^A', 'Ä': r'\"A', 'Ã': r'\~A', 'Å': r'\AA',
        'É': r"\'E", 'È': r'\`E', 'Ê': r'\^E', 'Ë': r'\"E',
        'Í': r"\'I", 'Ì': r'\`I', 'Î': r'\^I', 'Ï': r'\"I',
        'Ó': r"\'O", 'Ò': r'\`O', 'Ô': r'\^O', 'Ö': r'\"O', 'Õ': r'\~O', 'Ø': r'\O',
        'Ú': r"\'U", 'Ù': r'\`U', 'Û': r'\^U', 'Ü': r'\"U',
        'Ý': r"\'Y", 'Ÿ': r'\"Y',
        'Ñ': r'\~N',
        'Ç': r'\c{C}',
    }
    
    # Handle backslash first to avoid double-escaping
    result = string.replace('\\', replacements['\\'])
    
    # Replace other special characters
    for char, replacement in replacements.items():
        if char != '\\':  # Already handled
            result = result.replace(char, replacement)
    
    # Replace accented characters
    for char, replacement in accent_replacements.items():
        result = result.replace(char, replacement)
    
    return result

def snippet_search(query, limit=100):
    """
    Search for paper snippets based on a query string using Semantic Scholar API
    
    Args:
        query (str): The search query
        limit (int): Maximum number of results to return (default 100)
        
    Returns:
        dict: API response containing snippet search results

    Usage:
    python -c "from semanticscholar_lib import snippet_search; print(snippet_search('Ai fo science'))"
    """
    url = "https://api.semanticscholar.org/graph/v1/snippet/search"
    params = {
        "query": query,
        "limit": limit
    }
    headers = {
        "x-api-key": config.semanticscholar_key
    }
    
    response = requests.get(url, params=params, headers=headers)
    # {'data': [{'score': 0.5355408350010007, 'paper': {'corpusId': '279403245', 'title': 'Solving tricky quantum optics problems with assistance from (artificial) intelligence', 'authors': ['Manas Pandey', 'Bharath Hebbe Madhusudhana', 'Saikat Ghosh', 'Dmitry Budker'], 'openAccessInfo': {'license': None, 'status': None, 'disclaimer': 'Notice: This snippet is extracted from the open access paper or abstract available at https://arxiv.org/abs/2506.12770, which is subject to the license by the author or copyright owner provided with this content. Please go to the source to verify the license and copyright information for your use.'}}, 'snippet': {'text': 'The rapid emergence of artificial intelligence (AI) is changing the way science is done. As with many new tools (calculators, e-mail, internet, etc.), we usually begin by applying these tools to solve common tasks better than it is possible with existing tools (e.g., performing arithmetical operations with a calculator rather than a slide rule). However, the real power of new tools lies in enabling completely new uses such as collaborative paper writing with colleagues anywhere in the world, enabled by the Internet. We are convinced that the use of AI in science will bring a plethora of new uses and capabilities, some of which are already apparent today. An example is that AI is "democratizing" science by enabling any reasonably qualified scientist to perform sophisticated modeling using highly specialized algorithms, without the need to master software packages. AI takes the role of an expert colleague who can understand the "professor" formulating the question and is also able to run the dedicated software, thus eliminating the "middleman". \n\nHere, we describe how we test AI abilities and new ways of "interacting with the tool" with three problems in quantum optics: i. A straightforward question; however, known to trick even mature physicists in the field. \n\nii. A subtle problem with important applications that, while known for some years, is still a subject of current research. \n\niii. A problem of current research with an unsettled solution. \n\nBased on experience with these problems, we make observations regarding the possible utility of modern AI in the scientific process. In essence, every scientist now has access to sophisticated tools previously accessible only to specialists. This brings forward the importance of ideas rather than techniques. Of course, the speed with which ideas can be elaborated, tested in detail, and perhaps executed is higher. What used to take months and years can now be done in minutes. \n\nWe also remark on the striking similarity of the AI behavior to that of students. We need to explain here what exactly we mean by "AI". We test our problems on various stateof-the-art general-purpose models, accessible for public use (e.g., Gemini 2.5 Pro). When using different models, the details of the dialog are different; however, the overall results are broadly consistent across AI platforms.', 'snippetKind': 'body', 'section': 'Introduction', 'snippetOffset': {'start': 15, 'end': 2368}, 'annotations': {'refMentions': [{'start': 112, 'end': 149, 'matchedPaperCorpusId': None}], 'sentences': [{'start': 0, 'end': 88}, {'start': 89, 'end': 347}, {'start': 348, 'end': 521}, {'start': 522, 'end': 662}, {'start': 663, 'end': 875}, {'start': 876, 'end': 1058}, {'start': 1061, 'end': 1189}, {'start': 1190, 'end': 1278}, {'start': 1281, 'end': 1284}, {'start': 1285, 'end': 1403}, {'start': 1406, 'end': 1410}, {'start': 1411, 'end': 1468}, {'start': 1471, 'end': 1603}, {'start': 1604, 'end': 1712}, {'start': 1713, 'end': 1780}, {'start': 1781, 'end': 1887}, {'start': 1888, 'end': 1950}, {'start': 1953, 'end': 2034}, {'start': 2035, 'end': 2088}, {'start': 2089, 'end': 2210}, {'start': 2211, 'end': 2353}]}}}], 'retrievalVersion': 'pa1-v1'}
    response.raise_for_status()
    
    # Respect rate limits
    time.sleep(SEMANTICSCHOLAR_DELAY)
    
    return response.json()

def paperId_to_bibtex(paperId):
    """
    python -c "from semanticscholar_lib import paperId_to_bibtex; print(paperId_to_bibtex('38f382ed157cd187d28e14c3eac36e3bed34071e'))"
    """
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paperId}?fields=citationStyles,abstract"
    response = requests.get(url, headers={"x-api-key": config.semanticscholar_key})
    # {"paperId": "38f382ed157cd187d28e14c3eac36e3bed34071e", "citationStyles": {"bibtex": "@Article{Silva2024RepairBenchLO,\n author = {Andr\u00e9 Silva and Monperrus Martin},\n booktitle = {2025 IEEE/ACM International Workshop on Large Language Models for Code (LLM4Code)},\n journal = {2025 IEEE/ACM International Workshop on Large Language Models for Code (LLM4Code)},\n pages = {9-16},\n title = {RepairBench: Leaderboard of Frontier Models for Program Repair},\n year = {2024}\n}\n"}}
    response.raise_for_status()
    time.sleep(SEMANTICSCHOLAR_DELAY)
    return response.json()

def snippet_search_bibtex(query):
    """
    paper_search.py <query>

    Search for papers using a query string and return snippets with BibTeX citations.
    This function performs a snippet search with a limit of 5 results and retrieves
    the corresponding BibTeX entries for each paper found.
    Args:
        query (str): The search query string to find relevant papers.
    Returns:
        str: A YAML-formatted string containing a list of dictionaries, where each
            dictionary has the following keys:
            - 'title' (str): The title of the paper
            - 'snippet' (str): A text snippet from the paper relevant to the query
            - 'bibtex' (str): The BibTeX citation entry for the paper
            - 'abstract' (str): The abstract of the paper
    Example:
        - bibtex: '@article{...'
          snippet: 'This paper discusses...'
          title: 'Artificial Intelligence for Scientific Discovery'
          abstract: 'In this work, we explore...'
        ...
    Note:
        This function depends on snippet_search() and paperId_to_bibtex() functions.
        The search is limited to 5 results by default.

        
    python -c "from semanticscholar_lib import snippet_search_bibtex; snippets = snippet_search_bibtex('Ai for science'); print(snippets)"


    """
    snippets = snippet_search(query, limit=5)
    result = []
    for snippet in snippets["data"]:
        paper = paperId_to_bibtex("CorpusId:"+snippet["paper"]["corpusId"])
        entry = {
            "title": snippet["paper"]["title"],
            "abstract": paper.get("abstract", ""),
            "snippet": snippet["snippet"]["text"],
            "bibtex": latex_sanitize(paper["citationStyles"]["bibtex"])
        }
        result.append(entry)

    data = yaml.dump(result, default_flow_style=False, allow_unicode=True, encoding="utf-8", sort_keys=False)

    # Save query and data to cache
    cache_dir = os.path.expanduser("~/.cache/paper_search")
    os.makedirs(cache_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cache_file = os.path.join(cache_dir, f"{timestamp}.yaml")
    with open(cache_file, "wb") as f:
        f.write(data)

    return data

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python get_semantic_scholar.py <title>")
        sys.exit(1)
    title = sys.argv[1]
    result = get_data_from_title(title)
    print(result)
