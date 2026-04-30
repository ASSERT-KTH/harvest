import subprocess
import os
from lxml import etree

def test_ssrn_parsing():
    url = "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5877662"
    temp_file = "ssrn_temp.html"
    
    # 1. Fetch content using wget
    # Note: Using the user agent that worked
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    cmd = ["wget", "--user-agent=" + user_agent, "-O", temp_file, url]
    
    print(f"Fetching {url} using wget...")
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"wget failed: {e}")
        return

    if not os.path.exists(temp_file):
        print("File not created")
        return

    # 2. Parse content
    print("Parsing content...")
    with open(temp_file, "r", encoding="utf-8", errors="ignore") as f:
        html_content = f.read()

    # Use lxml HTML parser
    parser = etree.HTMLParser()
    tree = etree.fromstring(html_content, parser)

    # Extract Metadata
    
    # Title
    title = ""
    meta_title = tree.xpath('//meta[@name="citation_title"]/@content')
    if meta_title:
        title = meta_title[0]
    else:
        # Fallback
        h1 = tree.xpath('//h1/text()')
        if h1: title = h1[0].strip()

    # Authors
    authors = []
    meta_authors = tree.xpath('//meta[@name="citation_author"]/@content')
    if meta_authors:
        authors = meta_authors
    else:
        # Fallback
        pass # TODO implement fallback if needed
    
    authors_str = ", ".join(authors)

    # DOI
    doi = ""
    meta_doi = tree.xpath('//meta[@name="citation_doi"]/@content')
    if meta_doi:
        doi = meta_doi[0]

    # Abstract
    abstract = ""
    # meta_desc = tree.xpath('//meta[@name="description"]/@content') # often truncated
    # Try div class="abstract-text"
    abs_div = tree.xpath('//div[@class="abstract-text"]/p')
    if abs_div:
        # Join all p tags in abstract text
        abstract = " ".join([p.xpath('string(.)').strip() for p in abs_div])
    
    if not abstract:
        meta_desc = tree.xpath('//meta[@name="description"]/@content')
        if meta_desc: abstract = meta_desc[0]

    # Date
    year = None
    meta_date = tree.xpath('//meta[@name="citation_publication_date"]/@content')
    if not meta_date:
        meta_date = tree.xpath('//meta[@name="citation_online_date"]/@content')
    
    if meta_date:
        # format 2025/12/06
        try:
            year = int(meta_date[0].split("/")[0])
        except:
            pass

    # Venue
    venue_title = "SSRN"

    print("-" * 20)
    print(f"Title: {title}")
    print(f"Authors: {authors_str}")
    print(f"DOI: {doi}")
    print(f"Year: {year}")
    print(f"Venue: {venue_title}")
    print(f"Abstract: {abstract[:100]}...") # Print first 100 chars
    print("-" * 20)
    
    # Clean up
    if os.path.exists(temp_file):
        os.remove(temp_file)

if __name__ == "__main__":
    test_ssrn_parsing()
