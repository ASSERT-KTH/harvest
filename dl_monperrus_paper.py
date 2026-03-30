#!/usr/bin/python

from harvest import *
import os
from pathlib import Path
import json

import numpy as np
from pathlib import Path
import hashlib
import semanticscholar_lib

def cosine_similarity(v1, v2):
    """Compute cosine similarity between two vectors"""
    v1 = np.array(v1)
    v2 = np.array(v2)
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def get_title_hash(title):
    """Get hash of title for cache lookup"""
    return hashlib.sha256(title.encode('utf-8')).hexdigest()

def process_monperrus_bib():
    """
    python -c "from dl_monperrus_paper import process_monperrus_bib; process_monperrus_bib()"
    """
    bib_path = Path.home() / "monperrus.bib"
    
    with open(bib_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse titles from bib file
    titles = []
    for line in content.split('\n'):
        line = line.strip()
        if line.lower().startswith('title'):
            # Extract title value between braces
            start = line.find('{')
            end = line.rfind('}')
            if start != -1 and end != -1:
                title = line[start+1:end]
                titles.append(title)
    
    # Generate embeddings and push to database
    paperIds = []
    for title in titles:
        try:
            x = get_embedding_and_push_to_db(title)
            if x:
                if "openAccessPdf" not in x:
                    collect_paper_data_from_url_with_cache(x["openAccessPdf"]["url"])
                paperIds.append(x["paperId"])
        except Exception as e:
            print(f"Error processing title '{title}': {e}")

    
    return titles, paperIds

def list_most_related_papers_to_monperrus_research():
    """
    python -c "from dl_monperrus_paper import list_most_related_papers_to_monperrus_research; list_most_related_papers_to_monperrus_research()"

    for all papers in folder cache/toread, compute the cosine distance to all papers in cache/monperrus-semanticscholar_ids.json and output by increasing cosine distance
    """
    
    # Load monperrus paper IDs
    monperrus_ids_file = Path('cache/monperrus-semanticscholar_ids.json')
    if not monperrus_ids_file.exists():
        print("Error: monperrus-semanticscholar_ids.json not found")
        return
    
    with open(monperrus_ids_file, 'r') as f:
        monperrus_ids = json.load(f)
    
    # Load embeddings for monperrus papers
    monperrus_embeddings = {}
    embedding_cache_dir = Path('cache/embedding.specter_v2')
    
    for paper_id in monperrus_ids:
        try:
            data = semanticscholar_lib.get_embedding_from_paper_id(paper_id)
            if data.get('paperId') == paper_id:
                if 'embedding' in data and 'vector' in data['embedding']:
                    vector = data['embedding']['vector']
                    if len(vector) > 0:
                        monperrus_embeddings[paper_id] = {
                            'vector': vector,
                            'title': data.get('title', 'Unknown')
                        }
        except Exception as e:
            raise e
            print(f"Error loading embedding for paper ID {paper_id}: {e}")
    
    print(f"Loaded {len(monperrus_embeddings)} monperrus paper embeddings")
    
    # Load toread papers
    toread_dir = Path('cache/toread')
    toread_papers = []
    
    current_year = 2026
    min_year = current_year - 3

    for paper_file in toread_dir.glob('*.json'):
        try:
            with open(paper_file, 'r') as f:
                paper_data = json.load(f)
                title = paper_data.get('title', '')
                # print(title)
                year = paper_data.get('year')
                if year and int(year) < min_year:
                    continue
                if title:
                    embedding_data = semanticscholar_lib.get_embedding_and_push_to_db(title, verbose=False)
                    # print(embedding_data)
                    if embedding_data and 'embedding' in embedding_data and embedding_data['embedding'] and 'vector' in embedding_data['embedding'] and embedding_data['embedding']['vector']:
                        vector = embedding_data['embedding']['vector']
                        if len(vector) > 0:
                            tldr = paper_data.get('tldr', '')
                            if not tldr and 'tldr' in embedding_data and embedding_data['tldr']:
                                if isinstance(embedding_data['tldr'], dict):
                                    tldr = embedding_data['tldr'].get('text', '')
                                else:
                                    tldr = embedding_data['tldr']

                            toread_papers.append({
                                'title': title,
                                'vector': vector,
                                'url': paper_data.get('url', ''),
                                'venue_title': paper_data.get('venue_title', ''),
                                'authors': paper_data.get('authors', ''),
                                'tldr': tldr,
                                "filepath": str(paper_file)
                            })
        except Exception as e:
            raise e
            continue
    
    print(f"Loaded {len(toread_papers)} toread papers with embeddings")
    
    # Compute similarities
    results = []
    for toread_paper in toread_papers:
        min_distance = float('inf')
        most_similar_monperrus_paper = None
        
        for paper_id, monperrus_data in monperrus_embeddings.items():
            similarity = cosine_similarity(toread_paper['vector'], monperrus_data['vector'])
            distance = 1 - similarity  # Convert similarity to distance
            
            if distance < min_distance:
                min_distance = distance
                most_similar_monperrus_paper = monperrus_data['title']
        
        if most_similar_monperrus_paper:
            results.append({
                'data': toread_paper,
                'filepath': toread_paper['filepath'],
                'min_cosine_distance': min_distance,
                'angle': np.arccos(1 - min_distance) * (180 / np.pi),  # Convert distance to angle in degrees
                'most_similar_to': most_similar_monperrus_paper
            })
    
    # Sort by increasing cosine distance
    results.sort(key=lambda x: x['min_cosine_distance'])
    
    # Output results
    print(f"\n{'='*100}")
    print(f"Papers in toread ranked by similarity to Monperrus research")
    print(f"{'='*100}\n")
    
    for i, result in enumerate(results, 1):  # Show top 10 results
        if i > 10:
            break
        print(f"{i}. [{result['angle']:.4f}] {result['data']['title']}")
        print(f"   Most similar to: {result['most_similar_to']}")
        print(f"   Venue: {result['data']['venue_title']}")
        print(f"   URL: {result['data']['url']}")
        print(f"   Authors: {result['data']['authors'][:100]}...")
        print()
    
    return results

def notify_most_related_papers_to_monperrus_research(N=10):
    """
    python -c "from dl_monperrus_paper import notify_most_related_papers_to_monperrus_research; notify_most_related_papers_to_monperrus_research(1)"
    
    for the most 10 related papers to monperrus research send an email notification
    """
    # Get the ranked list of related papers
    results = list_most_related_papers_to_monperrus_research()
    
    if not results:
        print("No results to notify")
        return
    
    # Take top N most related papers (lowest cosine distance)
    top_papers = results[:N]
    
    print(f"\nSending email notifications for top {len(top_papers)} papers...")
    
    # Get Gmail service credentials
    service = build('gmail', 'v1', http=get_creds().authorize(Http()))


    # Send notification for each paper
    for i, result in enumerate(top_papers, 1):
        try:
            # Create Paper object
            paper = Paper(result['data']['url'], result['data']['title'])
            
            # Add additional metadata
            paper.venue_title = result['data']['venue_title']
            paper.authors = result['data']['authors']
            paper.reason = f"Related to Monperrus research (angle: {result['angle']:.4f}, most similar to: {result['most_similar_to']})"
            paper.tldr = result['data'].get('tldr', '')
            
            # Create and send email
            print(f"{i}. Notifying: {result['data']['title'][:80]}...")
            notify_email(
                paper, 
                service
            )

            # deleting the file to avoid sending multiple notifications for the same paper
            if 'filepath' in result and os.path.exists(result['filepath']):
                os.remove(result['filepath'])
            
        except Exception as e:
            print(f"   Error sending notification for '{result['title'][:50]}...': {e}")
            continue
    
    print(f"\nCompleted sending {len(top_papers)} notifications")


def main():
    titles, paperIds = process_monperrus_bib()
    print(f"Processed {len(titles)} titles from monperrus.bib")
    # Save paperIds to JSON file
    with open('cache/monperrus-semanticscholar_ids.json', 'w') as f:
        json.dump(paperIds, f)

if __name__ == "__main__":
    main()
