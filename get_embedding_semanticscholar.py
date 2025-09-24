#!/usr/bin/python3
# encoding: utf8
"""
Gets the SemanticScholar embedding for paper titles

Usage:
  ./get_embedding_semanticscholar.py "Paper Title"
  ./get_embedding_semanticscholar.py --batch --input titles.txt
  ./get_embedding_semanticscholar.py --all-cached

For batch processing of cached papers:
  jq -r ".title" cache/*json | shuf | xargs -I{} sh -c "./get_embedding_semanticscholar.py '{}' || true"
"""
import feedparser
import re
import cgi
import datetime
import email.utils
import pytz
import requests
from harvest import *
import subprocess
import sys
import argparse
import os
import json
import time
import random
import glob
from semanticscholar_lib import *

def parse_arguments():
    """Parse command-line arguments for the script."""
    parser = argparse.ArgumentParser(
        description='Get embeddings from SemanticScholar API for academic papers.'
    )
    
    # Input source group
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        'title', 
        nargs='?', 
        help='Paper title to get embedding for'
    )
    input_group.add_argument(
        '--batch', 
        action='store_true', 
        help='Process multiple titles from a file'
    )
    input_group.add_argument(
        '--all-cached', 
        action='store_true', 
        help='Process all cached paper titles'
    )
    
    # Additional options
    parser.add_argument(
        '--input', 
        help='Input file with one paper title per line (for --batch mode)'
    )
    parser.add_argument(
        '--output-dir', 
        default='/home/martin/workspace/scholar-harvest/cache/embedding.specter_v2/',
        help='Directory to store embedding data'
    )
    parser.add_argument(
        '--format', 
        choices=['json', 'vector'], 
        default='json',
        help='Output format: full JSON or vector only'
    )
    parser.add_argument(
        '--delay', 
        type=float, 
        default=0.5,
        help='Delay between API requests in seconds'
    )
    parser.add_argument(
        '--verbose', 
        action='store_true', 
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    # Validation
    if args.batch and not args.input:
        parser.error("--batch requires --input file")
    
    return args

def all_title():
    # 
    return subprocess.check_output("jq -r '.title' cache/*json", shell=True).decode("utf-8").split("\n")


def process_batch(input_file, output_dir, delay=1.0, format_type='json', verbose=False):
    """Process a batch of titles from a file."""
    try:
        with open(input_file, 'r') as f:
            titles = [line.strip() for line in f if line.strip()]
            
        results = []
        for title in titles:
            if len(title.split(" "))<2: continue
            result = get_embedding(title, output_dir, verbose, delay)
            if result:
                if format_type == 'vector' and 'embedding' in result:
                    results.append(result['embedding'].get('specter_v2', []))
                else:
                    results.append(result)
            
            
        return results
            
    except Exception as e:
        print(f"Error processing batch: {str(e)}")
        raise e
        # return []

def process_cache(output_dir, delay=1.0, format_type='json', verbose=False):
    """Process a batch of titles from a file."""
    for x in glob.glob("cache/harvest/*json"):
        with open(x, 'r') as f:
            data = json.load(f)
            if "title" not in data:
                os.remove(x)
        if "title" in data and data["title"]:
            result = get_embedding(data["title"], output_dir, verbose, delay)
            if result and verbose:
                print(data["title"],result["cached"])
 
def download_and_save(title, output_dir = "/home/martin/workspace/scholar-harvest/cache/embedding.specter_v2/", verbose = False):
        result = get_embedding(title, output_dir, verbose)
        path = path_on_disk_internal_v2(title,prefix="cache/embedding.specter_v2/")
        with open(path,"w") as f: json.dump(result,f)
        return result

def main():
    args = parse_arguments()
    
    # Process based on input mode
    if args.all_cached:
        process_cache(args.output_dir, args.delay, args.format, args.verbose)
        # titles = all_title()
        # random.shuffle(titles)
        # for title in titles:
        #     if title.strip():
        #         result = get_embedding(title, args.output_dir, args.verbose)
        #         # Respect rate limits
        #         time.sleep(args.delay)
                
    elif args.batch:
        results = process_batch(args.input, args.output_dir, args.delay, args.format, args.verbose)
        # Results are already saved to files in output_dir
        if args.verbose:
            print(f"Processed {len(results)} titles")
            
    else:
        # Single title mode
        result = download_and_save(args.title, args.output_dir, args.verbose)
        print(result)
        # if result:
        #     if args.format == 'vector' and 'embedding' in result:
        #         print(json.dumps(result['embedding'].get('specter_v2', [])))
        #     else:
        #         print(json.dumps(result))

if __name__ == "__main__":
    main()

