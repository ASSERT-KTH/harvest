#!/usr/bin/env python3
#
# Analyzes paper notifications (Google Scholar, Semanticscholar, planetse) sent over email
#
# send notifications over email
#
# To make stats of reasons, as easy as jq .reason cache/harvest/*.json | freqlines
#
#
# Author: Martin Monperrus

from __future__ import print_function
from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools
from lxml import etree
import urllib
from html.parser import HTMLParser
import base64
import re
from collections import Counter
import os
import hashlib
from datetime import datetime, timedelta
import requests
import time
import json
import config
import sys
from urllib.parse import urlparse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import random
import glob

from harvest_lib import *
from semanticscholar_lib import *
import dspace_bitstreams

import gakomail as sendemail



try:
    # ollama pull jeffh/intfloat-multilingual-e5-large-instruct:f16
    # kate /home/martin/workspace/reviewer-recommendation-system/embed.py
    sys.path.append("/home/martin/workspace/reviewer-recommendation-system/")
    import embed as rrs
    rrs.ensure_embedding_up()
except:
    pass




RUN_TIMESTAMP = datetime.now().astimezone().isoformat()

# If modifying these scopes, delete the file token.json.
# scodes read and write email
SCOPES = 'https://www.googleapis.com/auth/gmail.modify'

# the Scholar notification emails are localized
author_rx = re.compile("^(.*) [-–] (new articles|nya artiklar)$")
citing_rx = re.compile("^(.*) [-–] (new citations|nya citat|de nouvelles citations|neue Zitationen)")# – nya citat
related_rx = re.compile("^(.*) [-–] new related research$")
search_rx = re.compile("^(.*) [-–] (new results|nya sökresultat)$")

def type_alert(subject):
    subject = subject.replace('"','')
    am = author_rx.match(subject)
    if am:
        return ("author_alert", am.group(1))
    cm = citing_rx.match(subject)
    if cm:
        return ("citing_alert", cm.group(1))
    rm = related_rx.match(subject)
    if rm:
        return ("related_alert", rm.group(1))
    sm = search_rx.match(subject)
    if sm:
        return ("search_alert", sm.group(1))
    if "Alert is inactive" in subject:
        return ("inactive", "")
    if "New citations to my articles" in subject:
        return ("citing_me", "")
    if "Recommended articles" in subject:
        return ("scholar_recommendation", "")
    
CLASSIFICATION_DATA = {
 'uncategorized': [],
 'Program Repair': ['repair',
                    'bug', # matcheds debug
                    'fix',
                    'patch',
                    'overfitting'
                    ],
 'Vulnerability': [ # vivi
                    ' go ',
                    'golang',
                    'vulnerabil' 
                    ],
 'Chains': [ 'supply chain',
            'protection',
            'integrity',
            'guard',
            'package',
            'librar',
            'dependenc',
            'compatib',
            'break',
            'sbom',
            'bill',
            'substitut',
            'transparency', # transparency log, binary transparency
            ' ci ',
            'ci/cd',
            'continuous integration',
            'continuous deployment',
            'workflow',
            'pipeline',
            'github action',
            'build',
            'air-gap',
            'compromise',
            'sigstore'],
 'Smart contracts': ['blockchain',
                     'transaction',
                     'smart contract',
                     'smart-contract',
                     'bitcoin',
                     'ethereum',
                     'solidity',
                     'web3',
                     'evm',
                     'dapp',
                     'exploit generation',
                     'flash loan',
                     'stablecoin',
                     'framework for smart',
                     'nft',
                     'audit',
                     'fungible',
                     'wallet',
                     'governance',
                     'defi',
                     'zocrates',
                     'zk',
                     'zero-knowledge',
                     'solana',
                     'attackdb',
                     'decentralized autonomous organization'
                     'empirical review of automated analysis tools',
                     'enter the hydra',
                     'gigahorse',
                     ],
 'LLM on code': [
                 'learn',
                 'llm',
                 'neural',
                 'predict',
                 'generative',
                 'transformer',
                 'prompt',
                 'embedding',
                 'representation',
                 'fine-tun',
                 'summar',
                 'incoder',
                 'codet5',
                 'code llama',
                 'codellama',
                 'code-llama',
                 'octopack',
                 'learning performance-improving',
                 'neural code',
                 'model of code',
                 'models of code',
                 'models for code',
                 'trained on code',
                 'AI code',
                 'models of source code',
                 'python-state-changes', # dataset
                 'translat',
                 'language model', 
                 'pre-training', 
                 'toolformer',
                 'jigsaw',
                 'langchain',
                 'talm'],
 'Testing': ['test', 'oracle', 'metamorphic', 'mutant'],
 'Reliability': ['fault','robustness', 'multi-variant', 'divers', 'chaos', 'n-version', 'antifrag', 'heal','observability'], 
 'Fake': ['fake', 'decoy', 'honeypot']
 }


categories = {}
for i,j in CLASSIFICATION_DATA.items():
    categories["readinglist - "+i] = {"labelId":"","papers":[]}

class Paper:
    def __init__(self, url, title):
        self.url = url
        self.reader_url = ""
        self.desc = title
        self.reason = []
        self.abstract = None
        self.note = None
        self.category = None
        self.categories = []
        self.origin = None

    def note_subject(self, subject):
        type_a = type_alert(subject)
        if type_a:
            self.reason.append(type_a[0]+":"+type_a[1])

    def dump(self):
        print(str(self))

    def print_reason(self):
        return ", ".join(self.array_reason())
    def array_reason(self):
        return self.reason
    
    def __str__2(self):
        r=""
        r+="title: " + self.desc+"\n"
        r+="url: " + self.url+"\n"
        r+=", ".join(self.print_reason())
        return r

    def __str__(self):
        r=""
        r+=self.desc+"\n"
        r+=self.url+"\n"
        #r+=", ".join(self.print_reason())
        return r
    def as_dict(self):
        return {
            "timestamp":RUN_TIMESTAMP,
            "detection_date":self.detection_date,
            "title":self.desc,
            "category":self.category,
            "tldr":self.tldr,
            "authors":self.authors,
            "reason":self.print_reason(),
            "venue_title":self.venue_title,
            "url":self.url,
            "abstract":self.abstract,
            }
    def as_json(self):
        return json.dumps(self.as_dict())
    def get_authors(self):
        return self.authors if self.authors else ""


class ScholarParserLXML:
    def __init__(self):
        self.papers= dict()
        self.pending_subject = None
    def set_subject(self, subject):
        self.pending_subject = subject.decode("utf-8")
    def feed(self, data_txt):
        data = etree.HTML(data_txt)
        for i in data.xpath('.//a[@class="gse_alrt_title"]'):
            scholar_url = i.attrib['href']
            parsed = urllib.parse.urlparse(scholar_url)
            qdict = urllib.parse.parse_qs(parsed.query)
            if 'url' in qdict:
                scholar_url = str(qdict['url'][0])
            title = " ".join(i.xpath(".//text()"))
            #title = i.text
            #print(url, title)
            paper = Paper(scholar_url, title)
            if self.pending_subject is not None:
                paper.note_subject(self.pending_subject)
            self.papers[scholar_url] = paper

def extract_my_articles(data_txt):
    papers = dict()
    data = etree.HTML(data_txt)
    for i in data.xpath('.//a[@class="gse_alrt_title"]'):
            scholar_url = i.attrib['href']
            parsed = urllib.parse.urlparse(scholar_url)
            qdict = urllib.parse.parse_qs(parsed.query)
            if 'url' in qdict:
                scholar_url = str(qdict['url'][0])
            title = " ".join(i.xpath(".//text()"))
            #title = i.text
            #print(url, title)
            paper = Paper(scholar_url, title)
            paper.subject = "to my articles"
            paper.reason.append("citing: "+i.xpath('../following-sibling::table')[0].xpath(".//span/text()")[0])
            papers[scholar_url] = paper
    return papers
    
class ScholarScraper():
    def __init__(self):
        self.papers = dict()
        self.pending_subject = None
    def set_subject(self, subject):
        if subject!=None:
            self.pending_subject = subject
            return
        raise Exception()
    def feed(self, message):
        data = base64.urlsafe_b64decode(str(message["payload"]["body"]["data"])).decode("utf-8")
        self.msg_date = datetime.fromtimestamp(int(message['internalDate'])/1000)
        # my own articles
        new_papers = []
        if "to your articles" in self.pending_subject.decode("utf-8"):
            new_papers = extract_my_articles(data)
        else:
            #scraper = ScholarParser()
            scraper = ScholarParserLXML()
            scraper.set_subject(self.pending_subject)
            scraper.feed(data)
            new_papers = scraper.papers

        #print(len(scraper.papers))
        if len(new_papers)==0:
            print(data)
            raise Exception("no papers found")
        n=0
        for paper in new_papers.values():
            n+=self.save_paper(paper)
        self.papers.update(new_papers)

    def dump(self):

        for url, paper in self.papers.items():
            paper.dump()

    def save_paper(self, paper):
                # this should work
        create_harvest_email_paper(paper, self.service, origin="scholar",detection_date=self.msg_date)        
        return 1
    
    def dump_by_reason(self):

        reasons = Counter()
        unknown_reasons = Counter()
        for url, paper in self.papers.items():
            #self.save_paper(paper)
            # base64.urlsafe_b64encode(

            reasons.update(paper.print_reason())
            unknown_reasons.update(paper.print_reason())
    
            
        #for cat, papers in categories.items():
            #print ('\n## '+cat)
            #for paper in papers:
                #print("--")
                #print(str(paper))
        #print(unknown_reasons)
        print()


def already_seen_url(url, prefix):
    """
    example: urlseen, thepath = already_seen_url("https://doi.org/10.1145/3597503.3623337", "/home/martin/workspace/scholar-harvest/cache/XXXXXXX/")
    """
    assert prefix.endswith("/")
    thepath = prefix+hashlib.sha256(url.encode("utf-8")).hexdigest()+".json"
    return os.path.exists(thepath), thepath
READING_NOTES=""
def already_seen(paper):
    fname= path_on_disk(paper)
    if paper.desc.lower() in READING_NOTES: return True
    return os.path.exists(fname)

def record_paper_as_seen(paper, **kwargs):
    """
        we've already seen this paper, we create a file on disk accordingly
    """
    raise Exception("deprecated")
    fname= path_on_disk(paper)
    with open(fname,"w") as f: 
        data = paper.as_dict()
        data.update(kwargs)
        f.write(json.dumps(data))



def get_zotero_translator_service_url(url):
    """
    returns the zotero translator service output for the given url
    """
    fname = path_on_disk_internal_v2(url, "/home/martin/workspace/scholar-harvest/cache/get_zotero_translator_service/")
    if os.path.exists(fname):
        with open(fname, "r") as f:
            try:
                # print(fname)
                return json.load(f)
            except Exception as e:
                os.remove(fname)
                return None
    resp = requests.post("https://t0guvf0w17.execute-api.us-east-1.amazonaws.com/Prod/web", data = url, headers ={"Content-Type": "text/plain"})
    ## argh, Zotero sometimes return a list, sometimes a dictionary, that's really bad
    # print(resp.status_code, resp.text)

    # this is really a horrible API
    if resp.status_code == 400 or resp.status_code == 500 or '"message"'  in resp.text or "No items returned from any translator" in resp.text:
        result = []
    else:
        try:
            data = resp.json()
        except Exception as e:
            print("error loading json",resp.text)
            raise e

        result = data # happy path

        # the API of Zotero is not consistent, sometimes it returns a list, sometimes a dict
        # probably because the individual translators are not regularized
        if not isinstance(data, list):
            result = [data]

        # force firstName lastName for all authors
        for i in range(len(result)):
            if "creators" in result[i]:
                for o in range(len(result[i]["creators"])):
                    if "name" in result[i]["creators"][o]:
                        result[i]["creators"][o]["lastName"] = result[i]["creators"][o]["name"]
                        result[i]["creators"][o]["firstName"] = ""
                    if "firstName" not in result[i]["creators"][o]:
                        raise Exception("no firstName in creator")
                    if "lastName" not in result[i]["creators"][o]:
                        raise Exception("no lastName in creator")

        # print(data)


    # save and return
    with open(fname, "w") as f:
        json.dump(result, f)
    return result

def transform_zotero_to_output(zotero_input):
    """
    Transform Zotero JSON input to the desired output format.
    
    Args:
        zotero_input (list): A list containing a single Zotero item dictionary
    
    Returns:
        dict: Transformed output in the desired format
    """
    # Extract the first (and only) item from the input list
    item = zotero_input[0]
    
    # Extract authors
    authors = []
    for creator in item.get('creators', []):
        if creator.get('creatorType') == 'author':
            first_name = creator.get('firstName', '')
            last_name = creator.get('lastName', '')
            if first_name and last_name:
                # For the first author, use initial for first name
                if not authors:
                    authors.append(f"{first_name[0]}. {last_name}")
                else:
                    authors.append(f"{first_name} {last_name}")
    
    # Join authors with commas
    authors_str = ", ".join(authors)
    
    # Create a TLDR from the abstract
    abstract = item.get('abstractNote', '')
    tldr = abstract + "\n\n"  # In this example, we're just using the abstract as the TLDR
    
    # Construct the output dictionary
    url = item.get('url', '')
    if 'archiveID' in item and len(item.get('archiveID', '').split(':'))>=2:
        arxiv_id=item.get('archiveID', '').split(':')[1]
        url = f"https://arxiv.org/abs/{arxiv_id}"
    output = {
        'url': url,
        'title': item.get('title', ''),
        'semanticscholarid': '0092ce9c83a4c033fa69a6225f8a542566915006',  # This seems to be a fixed value in the example
        'abstract': f"  {abstract}" if abstract else '',
        'tldr': tldr,
        'authors': authors_str,
        'venue_title': item.get('publicationTitle', ''),
        'doi': None,  # None in the example
    }
    
    return output



def get_cdsl_data(csdlid):
    """ get the data based on computer.org 
    can be used as follows
        
    import harvest
    harvest.get_cdsl_doi("20lm4WmcwrS")

    remember that DOI redirects to IEEE Xplore
    """
    csdlurl = 'https://www.computer.org/csdl/api/v1/graphql'
    headers = {
        'Content-Type': 'application/json',
    }
    data = {
        "variables": {
            "articleId": csdlid
        },
        "query": """
        query ($articleId: String!) {
        issue: periodicalIssueByArticleId(articleId: $articleId) {
            id
            title
            year
            issueNum
            idPrefix
            pubType
            volume
            year
            label
            downloadables {
            hasCover
            __typename
            }
            __typename
        }
        article: articleById(articleId: $articleId) {
            id
            doi
            abstract
            abstracts {
            abstractType
            content
            __typename
            }
            normalizedAbstract
            title
            normalizedTitle
            fno
            hasPdf
            idPrefix
            keywords
            authors {
            givenName
            surname
            fullName
            affiliation
            __typename
            }
            replicability {
            isEnabled
            codeDownloadUrl
            codeRepositoryUrl
            __typename
            }
            showBuyMe
            showRecommendedArticles
            isOpenAccess
            issueNum
            pubDate
            pubType
            pages
            year
            issn
            isbn
            notes
            notesType
            __typename
        }
        recommendedArticles: recommendedArticlesById(articleId: $articleId) {
            id
            title
            doi
            abstractUrl
            parentPublication {
            id
            title
            __typename
            }
            __typename
        }
        adjacentArticles: adjacentArticles(articleId: $articleId) {
            previous {
            fno
            articleId
            __typename
            }
            next {
            fno
            articleId
            __typename
            }
            __typename
        }
        webExtras: webExtrasByArticleId(articleId: $articleId) {
            id
            name
            location
            extension
            size
            __typename
        }
        articleVideos: videosByArticleId(articleId: $articleId) {
            id
            videoExt
            videoType {
            featured
            recommended
            sponsored
            __typename
            }
            article {
            id
            fno
            issueNum
            pubType
            volume
            year
            idPrefix
            doi
            title
            __typename
            }
            channel {
            id
            title
            status
            featured
            defaultVideoId
            category {
                id
                title
                type
                __typename
            }
            __typename
            }
            year
            title
            description
            keywords {
            id
            title
            status
            __typename
            }
            speakers {
            firstName
            lastName
            affiliation
            __typename
            }
            created
            updated
            imageThumbnailUrl
            runningTime
            aspectRatio
            metrics {
            views
            likes
            __typename
            }
            notShowInVideoLib
            __typename
        }
        }
        """
    }
    response = requests.post(csdlurl, headers=headers, json=data).json()
    # jq .data.article.doi /tmp/foo
    if "article" in response["data"] and response["data"]["article"] and "doi" in response["data"]["article"]:
        return response["data"]["article"]
    return {"error":"unknown_cdsl"}
def get_cdsl_doi(csdlid):
    return get_cdsl_data(csdlid)["doi"]


def create_harvest_email_paper(paper, service, **kwargs):
    """
    python -c "import harvest; harvest.create_harvest_email_paper(harvest.Paper('https://doi.org/10.1145/3597503.3623337','title foo'), None)"

    # Example usage with arXiv:
    python -c "import harvest; harvest.create_harvest_email_paper(harvest.Paper('https://arxiv.org/abs/2304.12015','Deep Learning for Code'), None)"

    """


    origin_url = paper.url
    if "https://scholar.google" in paper.url:
        # the paper will appear formally later
        return False
    assert paper.url.startswith("http")

    origin = ""
    if "origin" in kwargs: origin = kwargs["origin"]
    detection_date = "unknown_detection_date"
    if "detection_date" in kwargs: detection_date = kwargs["detection_date"]
    if already_seen(paper):
        return False
    
    paper_data = collect_paper_data_from_url_with_cache(paper.url)
    
    # logging cases where no metadata is available
    if not paper_data or paper_data["title"] == None or paper_data["title"] == "":
        parsed_url = urlparse(paper.url)
        domain = parsed_url.netloc
        log_entry = {"domain": domain, "url": paper.url}
        log_file_path = "cache/domains-no-api.support.jsonl"
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        with open(log_file_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        print("no API metadata available for "+paper.url)
        # we return so we don't mark as seen
        # and we'll see it again later
        return False

    try:
        # getting the embedding  from semanticscholar_lib
        semanticscholar = get_embedding_and_push_to_db(paper_data["title"])
        paper_data["tldr"] = ""

        # knn in embedding space (from semantic scholar)
        if semanticscholar and semanticscholar["embedding"] and semanticscholar["embedding"]["vector"]:
            paper_data["note"]  = "related in embedding space:\n- "+"\n- ".join([x["title"] for x in rrs.search_in_pinecone_semanticscholar(paper_data["title"], semanticscholar["embedding"]["vector"], 5)])
            try: paper_data["tldr"] = semanticscholar["tldr"]["text"]
            except: pass
            # print("got an embedding for "+paper_data["url"])
    except Exception as e:
        raise e
        print("error getting embedding for "+paper.url, e)


    # what we obtained from the endpoint
    transfer_data_from_dict_to_paper(paper, paper_data)
        
    paper.origin = origin
    
    paper.categories = [x[1] for x in compute_category_embedding(paper)]

    # backward compatibility

    paper.category = paper.categories[0] 

    # now handle by collect_paper_data_from_url_with_cache above
    # record_paper_as_seen(paper)

    ### now, send notifications via appropriate channel
    # notify if high reputation only   
    if is_high_reputation(paper.url):
        notify_email(paper, service)
    else: 
        print("no reputation for "+origin_url+" not sending notification")   


    return True

def is_high_reputation(url):
    """
    check if the paper is from a high reputation source, before sending a notification
    discards mdpi, researchgate.net (no API)
    """
    if not url: return False
    if "nature.com" in url: return True
    if "doi.org" in url: return True
    if "arxiv.org" in url: return True
    if "semanticscholar.org" in url: return True
    if "dblp.org" in url: return True
    if "computer.org" in url: return True
    if "ieeexplore.ieee.org" in url: return True
    if "dl.acm.org" in url: return True

    # main publishers
    if "link.springer.com" in url: return True
    if "onlinelibrary.wiley.com" in url: return True # metadata via zotero, via crossref
    if "sciencedirect.com" in url: return True
    if "elsevier.com" in url: return True
    if "sagepub.com" in url: return True
    
    if "diva-portal.org" in url: return True
    if "hal.science" in url: return True
    if "ojs.aaai.org" in url: return True
    if "bitstream" in url: return True # dspace, probably from a university repository
    if "handle.net" in url: return True
    if "openreview.net" in url: return True
    if "google.com" in url: return True # for patents.google.com mostly
    return False


def collect_paper_data_from_doi(doi):
    assert len(doi)>0
    return collect_paper_data_from_url(get_doi_target(doi))

def collect_paper_data_from_url_with_cache(url):
    urlseen, thepath = already_seen_url(url,"/home/martin/workspace/scholar-harvest/cache/harvest/")
    if urlseen:
        with open(thepath, "r") as f:
            data = json.load(f)
            if not data or "title" not in data or not data["title"] or len(data["title"])==0:
                print("error, no title for ", url)
                os.remove(thepath)
                return collect_paper_data_from_url_with_cache(url)
            if "url" in data:
                return data
            else:
                # remove the file, it is not consistent
                print("inconsistent data in cache, removing", thepath)
                os.remove(thepath)
    data = collect_paper_data_from_url(url)
    if not data:
        try:
            with open("cache/collect_paper_data_from_url_error.log", "a") as f:
                f.write(url+"\n")
            domain = urlparse(url).netloc or url
            return None
        except Exception:
            domain = url
            log_path = "cache/domains-no-api.support.jsonl"
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a") as f:
                f.write(json.dumps({"url": url, "domain": domain}) + "\n")
            return None
    if "doi" in data and data["doi"]:
        data["doi"] = data["doi"].lower().replace("https://doi.org/","").replace("http://doi.org/","")
    if data:
        if not (data["title"] and len(data["title"])>0):
            if os.path.isfile(thepath):
                os.remove(thepath)
            return None
        if data["title"] and len(data["title"])>0:
            print("\033[92m✔\033[0mgood, writing cache for ", url)
            
            with open(thepath, "w") as f:
                f.write(json.dumps(data))

            # double linking
            _,titlepath = already_seen_url(data["title"],"/home/martin/workspace/scholar-harvest/cache/harvest/")
            # print("linking", thepath, "to", titlepath)  
            if not os.path.exists(titlepath):
                os.link(thepath, titlepath)
    return data

def get_paper_data_semanticscholar(title):
    id = get_semantic_scholar_id_from_title(title)
    id = id["paperId"]
    paper_data = collect_paper_data_from_url_with_cache("https://www.semanticscholar.org/paper/"+id)
    return paper_data


def info_from_crossref(doi):

    """
    Transform CROSSREF JSON data to the specified FORMAT structure.
    
    Args:
        crossref_data (dict): The CROSSREF JSON data
    
    Returns:
        dict: The transformed data in the FORMAT structure
    """

    try:
        response = requests.get(f"https://api.crossref.org/works/{doi}")
        if response.status_code != 200:
            # print("Error fetching data from CrossRef for DOI: " + doi)
            return None
        crossref_data = response.json()
    except:
        raise Exception("Error fetching data from CrossRef for DOI: " + doi)
    # print(json.dumps(crossref_data, indent=2))
    message = crossref_data.get("message", {})
    
    # Extract basic information
    title = message.get("title", [""])[0] if message.get("title") else ""
    doi = message.get("DOI", "")
    url = f"https://doi.org/{doi}" if doi else ""
    # if resource/primary/URL use it
    try:
        url = message["resource"]["primary"]["URL"]
    except:
        pass
    
    # Extract authors
    authors = []
    for author in message.get("author", []):
        given = author.get("given", "")
        family = author.get("family", "")
        full_name = f"{given} {family}".strip()
        if full_name:
            authors.append(full_name)
    
    # Extract venue information
    venue_title = ""
    if message.get("container-title"):
        venue_title = message.get("container-title", [""])[0]

# "journal-issue": {
    #   "issue": "FSE",
    # Extract issue information
    if message.get("journal-issue"):
        if message["journal-issue"].get("issue"):
            issue = message["journal-issue"]["issue"]
            if issue and venue_title:
                venue_title += f" ({issue})"
        
    elif message.get("event", {}).get("name"):
        venue_title = message.get("event", {}).get("name", "")
    
    # Create a note with publication date and publisher information
    published_date = ""
    if message.get("published"):
        date_parts = message.get("published", {}).get("date-parts", [[]])[0]
        if date_parts:
            published_date = "-".join(str(part) for part in date_parts)
    
    publisher = message.get("publisher", "")

    note = ""
    
    year = message.get("published", {}).get("date-parts", [[]])[0][0] if message.get("published") else ""
    # Create the formatted output
    formatted_output = {
        "url": url,
        "title": title,
        "semanticscholarid": "",  # Not available in CROSSREF data
        "abstract": "",  # Not available in CROSSREF data
        "tldr": "",  # Not available in CROSSREF data
        "authors": ", ".join(authors),
        "venue_title": venue_title,
        "doi": doi,
        "year": year,
        "note": note
    }
    
    return formatted_output

def collect_paper_data_from_arxiv(url):
    try:
        # init
        semanticscholarid=""
        tldr=""
        authors=""
        author_list = []
        venue_title = "arXiv"
        doi=None
        abstract = None
        title = None
        note = None
        year = None

        # data
        ## https://www.monperrus.net/martin/arxiv-json.py?id=2304.12015
        semanticscholarid="url:"+url.replace("/html/","/pdf/")
        components = [x for x in url.split("/") if len(x)>0]
        arxiv_id = components[-1].split("?")[0]
        # https://www.monperrus.net/martin/arxiv-json.py?id=2409.18952v1
        theurl = "https://www.monperrus.net/martin/arxiv-json.py?id="+arxiv_id

        arxiv_metadata = requests.get(theurl).json()
        abstract = (arxiv_metadata.get("summary") or "").replace("\n"," ")
        # support both "author" and "authors" keys and different shapes
        authors_data = arxiv_metadata.get("author") or []
        # normalize to list of names
        normalized = []
        if isinstance(authors_data, dict):
            # unlikely, but handle single dict
            authors_data = [authors_data]
        for x in authors_data:
            if isinstance(x, dict):
                name = x.get("name") or x.get("fullname") or x.get("given") or x.get("family") or ""
                normalized.append(name.strip())
            else:
                normalized.append(str(x).strip())
        author_list = [n for n in normalized if n]
        authors = ", ".join(author_list)
        venue_title = arxiv_metadata.get("journal_ref") if arxiv_metadata.get("journal_ref") and len(arxiv_metadata.get("journal_ref")) > 0 else "arXiv"
        title = arxiv_metadata.get("title")

        # extract year if available
        if arxiv_metadata.get("published"):
            m = re.search(r'(\d{4})', arxiv_metadata.get("published"))
            if m:
                year = int(m.group(1))
        elif arxiv_metadata.get("published_parsed"):
            try:
                year = int(arxiv_metadata.get("published_parsed")[0])
            except Exception:
                pass
        elif arxiv_metadata.get("created"):
            m = re.search(r'(\d{4})', arxiv_metadata.get("created"))
            if m:
                year = int(m.group(1))

        # we only point to the paper
        url = url.replace("/abs/","/pdf/")
        
        return {
            "url": url,
            "semanticscholarid": semanticscholarid,
            "tldr": tldr,
            "authors": authors,
            "author_list": author_list,
            "venue_title": venue_title,
            "doi": doi,
            "abstract": abstract,
            "title": title,
            "note": note,
            "year": year
        }
    except Exception as e:
        print("error fetching arxiv metadata for "+url, e)
        return None

def collect_paper_data_from_diva(url):
    # exaple url = https://www.diva-portal.org/smash/get/diva2:1981288/FULLTEXT01.pdf
    # urn: 
    # https://www.monperrus.net/martin/diva-urn-json.py?urn=
    # init
    semanticscholarid=""
    tldr=""
    authors=""
    venue_title = None
    doi=None
    abstract = None
    title = None
    note = None

    # Extract diva id from URL
    diva_id = None
    if 'record.jsf?pid=' in url:
        diva_id = url.split('record.jsf?pid=')[-1]
    else:
        parts = url.split('/')
        for part in parts:
            if 'diva2:' in part:
                diva_id = part
                break
    
    if not diva_id:
        return {
            "url": url, "title": None, "semanticscholarid": "", "abstract": None,
            "tldr": "", "authors": "", "venue_title": None, "doi": None, "note": None
        }

    # Call the DiVA API
    api_url = f"https://www.monperrus.net/martin/diva-urn-json.py?urn={diva_id}"
    print(api_url)
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        diva_data = response.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"Error fetching or parsing DiVA data for {diva_id}: {e}")
        return {
            "url": url, "title": None, "semanticscholarid": "", "abstract": None,
            "tldr": "", "authors": "", "venue_title": None, "doi": None, "note": None
        }

    if not diva_data or 'error' in diva_data:
        print(api_url)
        return None
    # print(diva_data)
    # Transform the data
    mods = diva_data.get('mods', [{}])
    # argh, the API is not consistent
    if isinstance(mods, list):
        mods = mods[0]
    
    # Title
    title = "failure to parse title"
    try:
        title = mods.get('titleInfo', {}).get(O).get('title')
    except: pass

    # Authors
    author_list = []
    # print(mods)
    for person in mods.get('name', []):
        if person.get('role', {}).get('roleTerm') == 'aut':
            name_parts = person.get('namePart', [])
            if len(name_parts) >= 2:
                author_list.append(f"{name_parts[1]} {name_parts[0]}") # Given Family
                venue_title = "Thesis at "+str(person.get('affiliation',"")[0])
    authors = ", ".join(author_list)

    # Abstract
    abstract_html = None
    try:
        abstract_html = mods.get('abstract')[0]
    except: pass


    # DOI
    for identifier in mods.get('identifier', []):
        if isinstance(identifier, str) and '.' in identifier and '/' in identifier:
            # Simple heuristic to find a DOI-like string
            doi = identifier
            break

    # Venue
    for k in mods.get('relatedItem', []):
        item = mods.get('relatedItem', [])[k]
        if 'title' in item:
            venue_title = item['title']
            break # Take the first one

    return {
        "url": url,
        "semanticscholarid": semanticscholarid,
        "tldr": tldr,
        "authors": authors,
        "venue_title": venue_title,
        "doi": doi,
        "abstract": abstract_html,
        "title": title,
        "note": note
    }

def collect_paper_data_from_hal(url):
    """
    python -c "import harvest; print(harvest.collect_paper_data_from_hal('https://inria.hal.science/tel-05433201/file/thesis.pdf'))"
    
    """
    # example https://hal.science/hal-01956501/document
    # Extract HAL ID from URL
    hal_id = url.split("/")[3]

    # Construct JSON API URL
    json_url = f"https://hal.science/{hal_id}/json"

    try:
        response = requests.get(json_url, timeout=10)
        """ example
      "response": {
            "numFound": 1,
            "start": 0,
            "maxScore": 5.9154453,
            "numFoundExact": true,
            "docs": [
                  {
                        "docid": "4204968",
                        "label_s": "Martin Monperrus. The Living Review on Automated Program Repair. [Technical Report] hal-01956501, HAL Archives Ouvertes. 2018. &#x27E8;hal-01956501v6&#x27E9;",
                        "citationRef_s": "[Technical Report] hal-01956501, HAL Archives Ouvertes. 2018",
                        "citationFull_s": "Martin Monperrus. The Living Review on Automated Program Repair. [Technical Report] hal-01956501, HAL Archives Ouvertes. 2018. <a target=\"_blank\" href=\"https://hal.science/hal-01956501v6\">&#x27E8;hal-01956501v6&#x27E9;</a>",
                        "label_bibtex": "@techreport{monperrus:hal-01956501,\n  TITLE = {{The Living Review on Automated Program Repair}},\n  AUTHOR = {Monperrus, Martin},\n  URL = {https://hal.science/hal-01956501},\n  TYPE = {Technical Report},\n  NUMBER = {hal-01956501},\n  INSTITUTION = {{HAL Archives Ouvertes}},\n  YEAR = {2018},\n  PDF = {https://hal.science/hal-01956501v6/file/repair-living-review.pdf},\n  HAL_ID = {hal-01956501},\n  HAL_VERSION = {v6},\n}\n",
                        "label_endnote": "%0 Report\n%T The Living Review on Automated Program Repair\n%+ KTH Royal Institute of Technology [Stockholm] (KTH)\n%A Monperrus, Martin\n%N hal-01956501\n%I HAL Archives Ouvertes\n%8 2018\n%D 2018\n%Z Computer Science [cs]/Software Engineering [cs.SE]Reports\n%X Concept This paper is a living review on automatic program repair 1. Compared to a traditional survey, a living review evolves over time. I use a concise bullet-list style meant to be easily accessible by the greatest number of readers, in particular students and practitioners. Within a section, all papers are ordered in a reverse chronological order, so as to easily get the research timeline. The references are sorted chronologically and years are explicitly stated inline to easily grasp the most recent references. Inclusion criteria The inclusion criteria are that the considered papers 1) must be about automatic repair with some kind of patch generation (runtime repair without patch generation is excluded 2); 2) must contain a reasonable amount of material (at least 4 double-column pages); 3) are stored on an durable site (notable publisher, arXiv, Zenodo). There is no restriction about whether the paper has been formally peer-reviewed or not. Originality Compared to formal surveys [132, 125], this living review contains very recent references and continues to evolve. It uses a bullet-list concise style that is not typical academic writing. Notification To get notified with new versions, click here. Feedback Do not hesitate to report a mistake, a confusing statement or a missing paper,\n%G English\n%2 https://hal.science/hal-01956501v6/document\n%2 https://hal.science/hal-01956501v6/file/repair-living-review.pdf\n%L hal-01956501\n%U https://hal.science/hal-01956501\n%~ LARA\n",
                        "label_coins": "<span class=\"Z3988\" title=\"ctx_ver=Z39.88-2004&amp;rft_val_fmt=info%3Aofi%2Ffmt%3Akev%3Amtx%3Adc&amp;rft.type=report&amp;rft.identifier=https%3A%2F%2Fhal.science%2Fhal-01956501&amp;rft.identifier=hal-01956501&amp;rft.title=The%20Living%20Review%20on%20Automated%20Program%20Repair&amp;rft.creator=Monperrus%2C%20Martin&amp;rft.language=en&amp;rft.date=2018\"></span>",
                        "openAccess_bool": true,
                        "domainAllCode_s": [
                              "info.info-se"
                        ],
                        "level0_domain_s": [
                              "info"
                        ],
                        "domain_s": [
                              "0.info",
                              "1.info.info-se"
                        ],
                        "level1_domain_s": [
                              "info.info-se"
                        ],
                        "fr_domainAllCodeLabel_fs": [
                              "info.info-se_FacetSep_Informatique [cs]/Génie logiciel [cs.SE]"
                        ],
                        "en_domainAllCodeLabel_fs": [
                              "info.info-se_FacetSep_Computer Science [cs]/Software Engineering [cs.SE]"
                        ],
                        "es_domainAllCodeLabel_fs": [
                              "info.info-se_FacetSep_Computer Science [cs]/Software Engineering [cs.SE]"
                        ],
                        "eu_domainAllCodeLabel_fs": [
                              "info.info-se_FacetSep_domain_info/domain_info.info-se"
                        ],
                        "primaryDomain_s": "info.info-se",
                        "en_title_s": [
                              "The Living Review on Automated Program Repair"
                        ],
                        "title_s": [
                              "The Living Review on Automated Program Repair"
                        ],
                        "abstract_s": [
                              "Concept This paper is a living review on automatic program repair 1. Compared to a traditional survey, a living review evolves over time. I use a concise bullet-list style meant to be easily accessible by the greatest number of readers, in particular students and practitioners. Within a section, all papers are ordered in a reverse chronological order, so as to easily get the research timeline. The references are sorted chronologically and years are explicitly stated inline to easily grasp the most recent references. Inclusion criteria The inclusion criteria are that the considered papers 1) must be about automatic repair with some kind of patch generation (runtime repair without patch generation is excluded 2); 2) must contain a reasonable amount of material (at least 4 double-column pages); 3) are stored on an durable site (notable publisher, arXiv, Zenodo). There is no restriction about whether the paper has been formally peer-reviewed or not. Originality Compared to formal surveys [132, 125], this living review contains very recent references and continues to evolve. It uses a bullet-list concise style that is not typical academic writing. Notification To get notified with new versions, click here. Feedback Do not hesitate to report a mistake, a confusing statement or a missing paper,"
                        ],
                        "en_abstract_s": [
                              "Concept This paper is a living review on automatic program repair 1. Compared to a traditional survey, a living review evolves over time. I use a concise bullet-list style meant to be easily accessible by the greatest number of readers, in particular students and practitioners. Within a section, all papers are ordered in a reverse chronological order, so as to easily get the research timeline. The references are sorted chronologically and years are explicitly stated inline to easily grasp the most recent references. Inclusion criteria The inclusion criteria are that the considered papers 1) must be about automatic repair with some kind of patch generation (runtime repair without patch generation is excluded 2); 2) must contain a reasonable amount of material (at least 4 double-column pages); 3) are stored on an durable site (notable publisher, arXiv, Zenodo). There is no restriction about whether the paper has been formally peer-reviewed or not. Originality Compared to formal surveys [132, 125], this living review contains very recent references and continues to evolve. It uses a bullet-list concise style that is not typical academic writing. Notification To get notified with new versions, click here. Feedback Do not hesitate to report a mistake, a confusing statement or a missing paper,"
                        ],
                        "authIdFormPerson_s": [
                              "23400-537"
                        ],
                        "authIdForm_i": [
                              23400
                        ],
                        "authIdPerson_i": [
                              537
                        ],
                        "authLastName_s": [
                              "Monperrus"
                        ],
                        "authFirstName_s": [
                              "Martin"
                        ],
                        "authFullName_s": [
                              "Martin Monperrus"
                        ],
                        "authLastNameFirstName_s": [
                              "Monperrus Martin"
                        ],
                        "authIdLastNameFirstName_fs": [
                              "537_FacetSep_Monperrus Martin"
                        ],
                        "authFullNameIdFormPerson_fs": [
                              "Martin Monperrus_FacetSep_23400-537"
                        ],
                        "authAlphaLastNameFirstNameId_fs": [
                              "M_AlphaSep_Monperrus Martin_FacetSep_537"
                        ],
                        "authIdFullName_fs": [
                              "537_FacetSep_Martin Monperrus"
                        ],
                        "authFullNameId_fs": [
                              "Martin Monperrus_FacetSep_537"
                        ],
                        "authQuality_s": [
                              "aut"
                        ],
                        "authOrganismId_i": [
                              92973
                        ],
                        "authStructId_i": [
                              92973
                        ],
                        "authOrganism_s": [
                              "Université de Lille, Sciences et Technologies"
                        ],
                        "authEmailDomain_s": [
                              "csc.kth.se"
                        ],
                        "authIdHal_i": [
                              537
                        ],
                        "authIdHal_s": [
                              "martin-monperrus"
                        ],
                        "authORCIDIdExt_s": [
                              "0000-0003-3505-3383"
                        ],
                        "authIDHALIdExt_s": [
                              "martin-monperrus"
                        ],
                        "authIdRefIdExt_s": [
                              "129846759"
                        ],
                        "authFullNameFormIDPersonIDIDHal_fs": [
                              "Martin Monperrus_FacetSep_23400-537_FacetSep_martin-monperrus"
                        ],
                        "authFullNamePersonIDIDHal_fs": [
                              "Martin Monperrus_FacetSep_537_FacetSep_martin-monperrus"
                        ],
                        "authIdHalFullName_fs": [
                              "martin-monperrus_FacetSep_Martin Monperrus"
                        ],
                        "authFullNameIdHal_fs": [
                              "Martin Monperrus_FacetSep_martin-monperrus"
                        ],
                        "authAlphaLastNameFirstNameIdHal_fs": [
                              "M_AlphaSep_Monperrus Martin_FacetSep_martin-monperrus"
                        ],
                        "authLastNameFirstNameIdHalPersonid_fs": [
                              "Monperrus Martin_FacetSep_martin-monperrus_FacetSep_537"
                        ],
                        "authIdHasPrimaryStructure_fs": [
                              "23400-537_FacetSep_Martin Monperrus_JoinSep_366312_FacetSep_KTH Royal Institute of Technology [Stockholm]"
                        ],
                        "structPrimaryHasAuthId_fs": [
                              "366312_FacetSep_KTH Royal Institute of Technology [Stockholm]_JoinSep_23400-537_FacetSep_Martin Monperrus"
                        ],
                        "structPrimaryHasAuthIdHal_fs": [
                              "366312_FacetSep_KTH Royal Institute of Technology [Stockholm]_JoinSep_martin-monperrus_FacetSep_Monperrus Martin"
                        ],
                        "structPrimaryHasAlphaAuthId_fs": [
                              "M_AlphaSep_366312_FacetSep_KTH Royal Institute of Technology [Stockholm]_JoinSep_23400-537_FacetSep_Monperrus Martin"
                        ],
                        "structPrimaryHasAlphaAuthIdHal_fs": [
                              "M_AlphaSep_366312_FacetSep_KTH Royal Institute of Technology [Stockholm]_JoinSep_martin-monperrus_FacetSep_Monperrus Martin"
                        ],
                        "structPrimaryHasAlphaAuthIdHalPersonid_fs": [
                              "M_AlphaSep_366312_FacetSep_KTH Royal Institute of Technology [Stockholm]_JoinSep_martin-monperrus_FacetSep_537_FacetSep_Monperrus Martin"
                        ],
                        "authIdHasStructure_fs": [
                              "23400-537_FacetSep_Martin Monperrus_JoinSep_366312_FacetSep_KTH Royal Institute of Technology [Stockholm]"
                        ],
                        "structHasAuthId_fs": [
                              "366312_FacetSep_KTH Royal Institute of Technology [Stockholm]_JoinSep_23400-537_FacetSep_Martin Monperrus"
                        ],
                        "structHasAuthIdHal_fs": [
                              "366312_FacetSep_KTH Royal Institute of Technology [Stockholm]_JoinSep_martin-monperrus_FacetSep_Monperrus Martin"
                        ],
                        "structHasAuthIdHalPersonid_s": [
                              "366312_FacetSep_KTH Royal Institute of Technology [Stockholm]_JoinSep_martin-monperrus_FacetSep_537_FacetSep_Monperrus Martin"
                        ],
                        "structHasAlphaAuthId_fs": [
                              "M_AlphaSep_366312_FacetSep_KTH Royal Institute of Technology [Stockholm]_JoinSep_23400-537_FacetSep_Monperrus Martin"
                        ],
                        "structHasAlphaAuthIdHal_fs": [
                              "M_AlphaSep_366312_FacetSep_KTH Royal Institute of Technology [Stockholm]_JoinSep_martin-monperrus_FacetSep_Monperrus Martin"
                        ],
                        "structHasAlphaAuthIdHalPersonid_fs": [
                              "M_AlphaSep_366312_FacetSep_KTH Royal Institute of Technology [Stockholm]_JoinSep_martin-monperrus_FacetSep_537_FacetSep_Monperrus Martin"
                        ],
                        "instStructId_i": [
                              366312
                        ],
                        "instStructIdName_fs": [
                              "366312_FacetSep_KTH Royal Institute of Technology [Stockholm]"
                        ],
                        "instStructNameId_fs": [
                              "K_AlphaSep_KTH Royal Institute of Technology [Stockholm]_FacetSep_366312"
                        ],
                        "instStructName_fs": [
                              "K_AlphaSep_KTH Royal Institute of Technology [Stockholm]"
                        ],
                        "instStructAcronym_s": [
                              "KTH"
                        ],
                        "instStructName_s": [
                              "KTH Royal Institute of Technology [Stockholm]"
                        ],
                        "instStructAddress_s": [
                              "SE-100 44, Stockholm, Sweden"
                        ],
                        "instStructCountry_s": [
                              "se"
                        ],
                        "instStructType_s": [
                              "institution"
                        ],
                        "instStructValid_s": [
                              "VALID"
                        ],
                        "instStructRorIdExt_s": [
                              "https://ror.org/026vcq606"
                        ],
                        "instStructRorIdExtUrl_s": [
                              "https://ror.org/https://ror.org/026vcq606"
                        ],
                        "structId_i": [
                              366312
                        ],
                        "structIdName_fs": [
                              "366312_FacetSep_KTH Royal Institute of Technology [Stockholm]"
                        ],
                        "structNameId_fs": [
                              "K_AlphaSep_KTH Royal Institute of Technology [Stockholm]_FacetSep_366312"
                        ],
                        "structName_fs": [
                              "K_AlphaSep_KTH Royal Institute of Technology [Stockholm]"
                        ],
                        "structAcronym_s": [
                              "KTH"
                        ],
                        "structName_s": [
                              "KTH Royal Institute of Technology [Stockholm]"
                        ],
                        "structAddress_s": [
                              "SE-100 44, Stockholm, Sweden"
                        ],
                        "structCountry_s": [
                              "se"
                        ],
                        "structType_s": [
                              "institution"
                        ],
                        "structValid_s": [
                              "VALID"
                        ],
                        "structRorIdExt_s": [
                              "https://ror.org/026vcq606"
                        ],
                        "structRorIdExtUrl_s": [
                              "https://ror.org/https://ror.org/026vcq606"
                        ],
                        "contributorId_i": 159508,
                        "contributorFullName_s": "Martin Monperrus",
                        "contributorIdFullName_fs": "159508_FacetSep_Martin Monperrus",
                        "contributorFullNameId_fs": "Martin Monperrus_FacetSep_159508",
                        "language_s": [
                              "en"
                        ],
                        "halId_s": "hal-01956501",
                        "uri_s": "https://hal.science/hal-01956501v6",
                        "version_i": 6,
                        "status_i": 11,
                        "instance_s": "hal",
                        "sid_i": 1,
                        "submitType_s": "file",
                        "docType_s": "REPORT",
                        "docSubType_s": "TECHREPORT",
                        "oldDocType_s": "REPORT",
                        "thumbId_i": 9278270,
                        "selfArchiving_bool": true,
                        "authorityInstitution_s": [
                              "HAL Archives Ouvertes"
                        ],
                        "number_s": [
                              "hal-01956501"
                        ],
                        "reportType_s": "4",
                        "inPress_bool": false,
                        "modifiedDate_tdate": "2023-09-14T03:36:44Z",
                        "modifiedDate_s": "2023-09-14 03:36:44",
                        "modifiedDateY_i": 2023,
                        "modifiedDateM_i": 9,
                        "modifiedDateD_i": 14,
                        "submittedDate_tdate": "2023-09-12T14:40:27Z",
                        "submittedDate_s": "2023-09-12 14:40:27",
                        "submittedDateY_i": 2023,
                        "submittedDateM_i": 9,
                        "submittedDateD_i": 12,
                        "releasedDate_tdate": "2023-09-13T10:56:36Z",
                        "releasedDate_s": "2023-09-13 10:56:36",
                        "releasedDateY_i": 2023,
                        "releasedDateM_i": 9,
                        "releasedDateD_i": 13,
                        "producedDate_tdate": "2018-01-01T00:00:00Z",
                        "producedDate_s": "2018",
                        "producedDateY_i": 2018,
                        "publicationDate_tdate": "2018-01-01T00:00:00Z",
                        "publicationDate_s": "2018",
                        "publicationDateY_i": 2018,
                        "owners_i": [
                              159508
                        ],
                        "collId_i": [
                              4731
                        ],
                        "collName_s": [
                              "LARA"
                        ],
                        "collCode_s": [
                              "LARA"
                        ],
                        "collCategory_s": [
                              "THEME"
                        ],
                        "collIdName_fs": [
                              "4731_FacetSep_LARA"
                        ],
                        "collNameId_fs": [
                              "LARA_FacetSep_4731"
                        ],
                        "collCodeName_fs": [
                              "LARA_FacetSep_LARA"
                        ],
                        "collCategoryCodeName_fs": [
                              "THEME_JoinSep_LARA_FacetSep_LARA"
                        ],
                        "collNameCode_fs": [
                              "LARA_FacetSep_LARA"
                        ],
                        "fileMain_s": "https://hal.science/hal-01956501/document",
                        "files_s": [
                              "https://hal.science/hal-01956501/file/repair-living-review.pdf"
                        ],
                        "fileType_s": [
                              "file"
                        ],
        """
        if response.status_code == 200:
            hal_data = response.json()
            # Extract data from HAL response
            docs = hal_data.get("response", {}).get("docs", [])
            if not docs:
                return None

            doc = docs[0]

            # Extract title
            title = None
            if "title_s" in doc:
                title = doc["title_s"][0] if isinstance(doc["title_s"], list) else doc["title_s"]

            # Extract authors
            authors = ""
            if "authFullName_s" in doc:
                author_list = doc["authFullName_s"]
                if isinstance(author_list, list):
                    authors = ", ".join(author_list)
                else:
                    authors = author_list

            # Extract abstract
            abstract = None
            if "abstract_s" in doc:
                abstract = doc["abstract_s"][0] if isinstance(doc["abstract_s"], list) else doc["abstract_s"]

            # Extract DOI
            doi = None
            if "doiId_s" in doc:
                doi = doc["doiId_s"]

            # Extract venue/publication info
            venue_title = None
            if "journalTitle_s" in doc:
                venue_title = doc["journalTitle_s"]
            elif "bookTitle_s" in doc:
                venue_title = doc["bookTitle_s"]
            elif "conferenceTitle_s" in doc:
                venue_title = doc["conferenceTitle_s"]

            # Extract year for note
            year = doc.get("producedDateY_i", "")
            note = f"Published: {year}" if year else ""

            return {
                "url": url,
                "semanticscholarid": None,
                "tldr": None,
                "authors": authors,
                "venue_title": venue_title,
                "doi": doi,
                "abstract": abstract,
                "title": title,
                "note": note
            }
    except Exception as e:
        print(f"Error fetching HAL metadata for {hal_id}: {e}")
        return None



def collect_paper_data_from_url(url):
    """
    python -c "import harvest; print(harvest.collect_paper_data_from_url('https://doi.org/10.1145/3368089.3409733'))"

    """
    title = None
    authors=""
    author_list=None
    semanticscholarid=""
    tldr=""
    venue_title = None
    doi=None
    abstract = None
    note = None
    if "doi.org/" in url:
        doi = url.replace("https://dx.doi.org/","").replace("https://doi.org/","").replace("http://doi.org/","")
        try:
            return collect_paper_data_from_doi(doi)
        except Exception as e:
            print("doi error",doi)
    if "hal.science/" in url:
        # fould be hal.science or inria.hal.science or theses.hal.science    
        return collect_paper_data_from_hal(url)

    # added Nov 2025
    if "/bitstream/" in url or "/bitstreams/" in url:
        dspace= dspace_bitstreams.main_bitstream(url)
        if dspace:
            return dspace

    if "arxiv.org/" in url:    
        ## https://www.monperrus.net/martin/arxiv-json.py?id=2304.12015
        return collect_paper_data_from_arxiv(url)

    if "diva-portal.org/" in url:    
        ## https://www.monperrus.net/martin/arxiv-json.py?id=2304.12015
        return collect_paper_data_from_diva(url)
    
    if "dblp.org/" in url:
        return collect_paper_data_from_dblp(url)


    if "dl.acm.org" in url:
        components = [x for x in url.split("/") if len(x)>0]
        doi = components[-2]+"/"+components[-1]
        crossref_data = info_from_crossref(doi)
        if crossref_data: return crossref_data
        # no api for acm
        # see https://stackoverflow.com/questions/33380715/acm-digital-library-access-with-r-no-api-so-how-possible
        # alternative 1: go through crossref
        # alternative 2: there is the bibtex export which actually returns json
        req = requests.post('https://dl.acm.org/action/exportCiteProcCitation', data={
            'dois': doi,
            'format': 'bibTex',
            'targetFile': 'custom-bibtex',
        })
        if '<!DOCTYPE html>' not in req.text:
            r = req.json()
            if "container-title" in r["items"][0][doi]:
                venue_title = r["items"][0][doi]["container-title"]
            elif "container-title-short" in r["items"][0][doi]:
                venue_title = r["items"][0][doi]["container-title-short"]
            else:
                print("TODO dl.acm.org"+str(r["items"][0][doi].keys()))
            title = r["items"][0][doi]["title"]
            try:
                authors = ", ".join([x["given"]+" "+x["family"] for x in r["items"][0][doi]["author"]])
            except: pass
        # print("acm.org TODO implement call to https://dl.acm.org/action/exportCiteProcCitation")

    if "link.springer.com" in url:
        # example url-analysis.py http://link.springer.com/10.1007/s11219-025-09709-4
        components = [x for x in url.split("/") if len(x)>0]
        doi = components[-2]+"/"+components[-1]
        # https://dev.springernature.com/
        # https://dev.springernature.com/docs/api-endpoints/metadata-api/
        # GET https://api.springernature.com/meta/v2/json?api_key=YOUR_API_KEY&q=doi:YOUR_DOI
        springer_url = f"https://api.springernature.com/meta/v2/json?api_key={config.springernature_key}&q=doi:{doi}"
        springer_data = requests.get(springer_url).json()
        if "records" in springer_data and len(springer_data["records"])>0:
            # print(url)
            paper_data = springer_data["records"][0]
            venue_title=paper_data["publicationName"]
            abstract=paper_data["abstract"]
            title=paper_data["title"]
            author_list = [x["creator"] for x in paper_data["creators"]]
            authors = " | ".join(author_list)
        else: print("no records found in Springer "+url)

        # print(springer_data)
        
    if "computer.org" in url:
        csdlid = [x for x in url.split("/") if len(x)>0][-1]
        cdsl_data = get_cdsl_data(csdlid)
        if "error" in cdsl_data:
            return None
        doi = cdsl_data["doi"]
        abstract = cdsl_data["abstract"]
        title = cdsl_data["title"]
        author_list = [x["fullName"] for x in cdsl_data["authors"]]
        authors = " | ".join(author_list)
        # print(cdsl_data)
        # at KTH we need to pass through IEEE Xplore and the DOI resolves to that
        url = "https://doi.org/"+doi

    if 'sciencedirect.com' in url:
        # https://dev.elsevier.com/documentation/ScienceDirectSearchAPI.wadl#d1e166
        # GET https://dev.elsevier.com/documentation/ScienceDirectSearchAPI.wadl#d1e166
        # apikey key registered in https://dev.elsevier.com/apikey/manage but not required for the core content
        # query param
        # probably with title or id 
        # example https://www.sciencedirect.com/science/article/pii/S016764232400100X
        # https://api.elsevier.com/content/search/sciencedirect?query=all(Articulation+Disorders)
        # curl -H "x-els-apikey: xxxxxx" -H "content-type: application/json" -H "Accept: application/json" "https://api.elsevier.com/content/search/sciencedirect?query=all(Articulation+Disorders)"
        # curl -H "Accept: application/json" -H "x-els-apikey: xxxxxx" "https://api.elsevier.com/content/article/doi/10.1016/j.prosdent.2024.08.001" 
        # ["coredata"]["prism:publicationName"]
        # curl -H "Accept: application/json" -H "x-els-apikey: xxxxxx" "https://api.elsevier.com/content/article/pii/S0950584924002593" 
        pattern = r'/pii/([A-Z0-9]+)'

        match = re.search(pattern, url)
        if match:
            pii = match.group(1)
            api_url = 'https://api.elsevier.com/content/article/pii/'+ pii + "?httpAccept=application/json"
            elsevier_data = requests.get(api_url, headers = {"x-els-apikey":config.sciencedirect_key}).json()
            # print("elsevier_data",pii,json.dumps(elsevier_data, indent=2))
            if "full-text-retrieval-response" in elsevier_data:
                venue_title = elsevier_data["full-text-retrieval-response"]["coredata"]["prism:publicationName"]
                doi = elsevier_data["full-text-retrieval-response"]["coredata"]["prism:doi"]
                title = elsevier_data["full-text-retrieval-response"]["coredata"]["dc:title"]
                abstract = elsevier_data["full-text-retrieval-response"]["coredata"]["dc:description"]
                url = url.replace('?dgcid=rss_sd_all','')
                author_list = []
                for x in elsevier_data["full-text-retrieval-response"]["coredata"]["dc:creator"]:
                    author_list.append(x["$"])
                authors = ", ".join(author_list)
                # print(authors)
            # print(elsevier_data)
            # note the abstract is not available in the free version of the API
            # author = " and ".join([x["$"] for x in elsevier_data["full-text-retrieval-response"]["coredata"]["dc:creator"]])
            # example curl -H "Accept: application/json" -H "x-els-apikey: xxxxxx" "https://api.elsevier.com/content/article/pii/S0950584924002593" 
            # print('curl -H "Accept: application/json" -H "x-els-apikey: xxxxxx" "https://api.elsevier.com/content/article/pii/'+pii)
            # now get on kth network via SSH, Socks or HTTP proxy
        
        # must be done from the kth network, so through SSH or proxy, unclear whether it's actually the case
        # print("implement doi retrieval for sciencedirect")
        pass

    if "ieeexplore.ieee.org" in url:
        # special case
        url = url.replace("/figures#figures","")

        # rate limit see https://developer.ieee.org/API_Terms_of_Use2
        # not documented in response headers
        # rate limit on https://developer.ieee.org/apps/myapis
        #  10 Calls per second / 200 Calls per day
        # we can also get tldr for ieee papers
        if "abs_all.jsp" in url:
            # parse url
            components = urllib.parse.urlparse(url)
            qdict = urllib.parse.parse_qs(components.query)
            ieeeid = qdict["arnumber"][0]
            # print(qdict)
        else:
            ieeeid = [x for x in url.split("/") if len(x)>0][-1].replace(".pdf","")
        # curl "https://ieeexploreapi.ieee.org/api/v1/search/articles?apiKey=XXXXXX&article_number=10833642"

        req_url = "https://ieeexploreapi.ieee.org/api/v1/search/articles?article_number="+ieeeid+"&apiKey="+config.ieeexplore_key
        resp = requests.get(req_url)
        if resp.status_code != 418: # i'm a teapot, WTF?
            # print(resp.text)
            try:
                ieeedata = resp.json()
            except Exception as e:
                raise Exception("ieee error",resp.status_code,resp.text, resp.headers)
                
            if "error" not in ieeedata and "articles" in ieeedata:
                if "doi" in ieeedata["articles"][0]:
                    doi = ieeedata["articles"][0]["doi"]
                venue_title = ieeedata["articles"][0]["publication_title"]
                abstract = ieeedata["articles"][0]["abstract"] if "abstract" in  ieeedata["articles"][0] else ""
                # print ([x for x in ieeedata["articles"][0]["authors"]["authors"]])
                # args the ["authors"]["authors"], bad data model
                authors = ", ".join([x["full_name"] for x in ieeedata["articles"][0]["authors"]["authors"]])
                title = ieeedata["articles"][0]["title"]                
                # semanticscholarid="doi:"+doi
            else: print("no data in ieee "+json.dumps(ieeedata, indent=2))

    if "semanticscholar.org/" in url:
        return collect_paper_data_from_semanticscholar(url)

    if "mdpi.com/" in url:
        return collect_paper_data_from_mdpi(url)

    if "openreview.net/" in url:
        return collect_paper_data_from_openreview(url)

    if title == None:
        # default from Zotero Translation Server
        zotero_data = get_zotero_translator_service_url(url)
        if zotero_data != None and len(zotero_data)>0:
            return transform_zotero_to_output(zotero_data)
            
    return {
        "url":url,
        "title":title,
        "semanticscholarid":semanticscholarid,
        "abstract":abstract,
        "tldr": tldr,
        "authors": authors,
        "author_list": author_list,
        "venue_title" : venue_title,
        "doi" : doi,
        "note" : note
    }

def collect_paper_data_from_mdpi(url):
    """
    Extract paper metadata from MDPI URLs.
    
    Args:
        url (str): URL of the MDPI paper
    
    Returns:
        dict: Paper metadata including title, authors, abstract, etc.
    """
    title = None
    authors = ""
    semanticscholarid = ""
    tldr = ""
    venue_title = None
    doi = None
    abstract = None
    note = None
    
    # Extract DOI from URL if possible
    # MDPI URLs are typically like https://www.mdpi.com/2076-3417/10/4/1342
    # or https://www.mdpi.com/journal/sensors/2000000
    # First try to get data via DOI if we can extract it
    path_parts = [p for p in url.split('/') if p]
    if len(path_parts) >= 3 and path_parts[-2].isdigit() and path_parts[-1].isdigit():
        identifier = "/".join(path_parts[2:])
        oai_url = f"http://oai.mdpi.com/oai/oai2.php?verb=GetRecord&metadataPrefix=oai_dc&identifier=oai:mdpi.com:/{identifier}/"
        try:
            response = requests.get(oai_url, timeout=10)
            if response.status_code == 200:
                # Parse XML response
                xml_root = etree.fromstring(response.content)
                
                # Extract metadata
                dc_namespace = {'dc': 'http://purl.org/dc/elements/1.1/',
                               'oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/',
                               'oai': 'http://www.openarchives.org/OAI/2.0/'}
                
                # Extract metadata elements
                metadata = xml_root.find('.//oai:record/oai:metadata/oai_dc:dc', dc_namespace)
                if metadata is not None:
                    title = metadata.find('dc:title', dc_namespace)
                    title = title.text if title is not None else None
                    
                    abstract = metadata.find('dc:description', dc_namespace)
                    abstract = abstract.text if abstract is not None else None
                    
                    # Get all authors
                    author_elements = metadata.findall('dc:creator', dc_namespace)
                    authors = ", ".join([author.text for author in author_elements]) if author_elements else ""
                    
                    # Get DOI
                    identifiers = metadata.findall('dc:identifier', dc_namespace)
                    for identifier in identifiers:
                        if identifier.text and "doi" in identifier.text:
                            doi = identifier.text.replace('doi:', '').replace('https://dx.doi.org/', '')
                            break
                    
                    # Get publication info
                    source = metadata.find('dc:source', dc_namespace)
                    if source is not None and source.text:
                        venue_title = source.text
                        
                    # Some MDPI journals include the journal name in a specific format
                    if not venue_title:
                        publisher = metadata.find('dc:publisher', dc_namespace)
                        if publisher is not None and publisher.text and 'MDPI' in publisher.text:
                            venue_title = publisher.text
        except Exception as e:
            print(f"Error extracting MDPI metadata: {e}")


    return {
        "url": url,
        "title": title,
        "semanticscholarid": semanticscholarid,
        "abstract": abstract,
        "tldr": tldr,
        "authors": authors,
        "venue_title": venue_title,
        "doi": doi,
        "note": note
    }
    
def collect_paper_data_from_dblp(url):
    try:
        # https://dblp.org/rec/conf/icst/AlshammariAHB24.xml
        # example https://www.monperrus.net/martin/dblp-json.py?id=conf/icst/AlshammariAHB24
        components = [x for x in url.split("/") if len(x)>0]
        dblp_id = "/".join(components[-3:])
        dblp_id = dblp_id.replace(".html","").replace(".xml","")
        # print("dblp_id",dblp_id)
        # added Jan 2025
        dblp_url = "https://www.monperrus.net/martin/dblp-json.py?id="+dblp_id
        # print(dblp_url)
        
        dblp_resp = requests.get(dblp_url)
        # print(dblp_url, dblp_resp.status_code, dblp_resp.text) # debug
        dblp_metadata = dblp_resp.json()
        venue_title = dblp_metadata["venue_title"]
        authors = ", ".join(dblp_metadata["author"])
        # print(dblp_metadata)
        # DOI Chain from dblp
        if "ee" in dblp_metadata and len(dblp_metadata["ee"])>0:
            if "doi" in dblp_metadata["ee"][0]:
                # print(dblp_metadata["ee"])
                doi = dblp_metadata["ee"][0].replace("https://doi.org/","").replace("https://dx.doi.org/","")
                return collect_paper_data_from_doi(doi)
        # if "doi.org" in dblp_metadata["ee"]:
        #     url = get_doi_target(dblp_metadata["ee"])
        # print("TODO implement DOI and chain for DBLP")
    except Exception as e:
        print("collect_paper_data_from_dblp",dblp_url, dblp_resp.status_code, dblp_resp.text) # debug
        print("Error in collect_paper_data_from_dblp", e)
    return None

def collect_paper_data_from_openreview(url):
    """
    Extract metadata from an OpenReview URL using the OpenReview public API.
    Returns a dict with keys similar to other collectors:
    {url, title, semanticscholarid, abstract, tldr, authors, venue_title, doi, note, year}

    Example:

    python -c "import harvest; print(harvest.collect_paper_data_from_openreview('https://openreview.net/pdf?id=BCS7HHInC2'))"
    """
    # extract id from query or path
    parsed = urlparse(url)
    q = urllib.parse.parse_qs(parsed.query)
    forum_id = q.get('id', [None])[0]
    if not forum_id:
        parts = [p for p in parsed.path.split('/') if p]
        # common patterns: /forum?id=..., /pdf?id=..., /pdf/ID, /forum/ID
        for i, p in enumerate(parts):
            if p in ('forum', 'pdf', 'notes') and i + 1 < len(parts):
                forum_id = parts[i + 1]
                break
        if not forum_id and parts:
            # fallback: last path segment may be the id
            forum_id = parts[-1]

    if not forum_id:
        return None

    api_url = f"https://api2.openreview.net/notes?forum={forum_id}&limit=1"
    resp = requests.get(api_url, timeout=10)
    if resp.status_code != 200:
        raise Exception(f"OpenReview API error {resp.status_code} for forum {forum_id}")
    data = resp.json()

    # API can return 'notes' or 'rows'
    notes = data.get('notes') or data.get('rows') or []
    if not notes:
        return None
    note = notes[0]

    content = note.get('content', {}) if isinstance(note, dict) else {}
    title = content.get('title').get("value") or note.get('title').get("value") or ""
    abstract = content.get('abstract') or content.get('summary') or ""
    # authors often a list
    authors_list = []
    if content.get('authors'):
        authors_list = content.get('authors').get('value') or content.get('authorids') or []
    else:
        authors_list.append("Anonymous OpenReview")

    venue_title = content.get('venue').get('value') if content.get('venue') else None
    doi = content.get('doi') or content.get('paper_doi') or None

    # try to extract year from 'date_submitted' or note 'tcdate' or 'created'
    year = None
    # try to extract year from various possible fields
    year = None
    try:
        candidates = []
        candidates.append(note.get('tcdate'))
        candidates.append(note.get('mdate'))

        for c in candidates:
            if not c:
                continue
            # numeric timestamp (ms or s)
            if isinstance(c, (int, float)) or (isinstance(c, str) and c.isdigit()):
                try:
                    ts = int(c)
                    # if looks like milliseconds, convert
                    if ts > 1e12:
                        year = datetime.fromtimestamp(ts / 1000).year
                    else:
                        year = datetime.fromtimestamp(ts).year
                    break
                except Exception:
                    pass
            # ISO-like string
            if isinstance(c, str):
                s = c.strip()
                # try ISO parse
                try:
                    s_iso = s.replace('Z', '+00:00') if s.endswith('Z') else s
                    year = datetime.fromisoformat(s_iso).year
                    break
                except Exception:
                    # fallback: regex search for 4-digit year
                    m = re.search(r'([12]\d{3})', s)
                    if m:
                        year = int(m.group(1))
                        break
    except Exception:
        year = None


    # build a short note
    note_txt = f"openreview_forum:{forum_id}"
    if note.get('id'):
        note_txt += f" id:{note.get('id')}"

    return {
        "url": url,
        "title": title,
        "semanticscholarid": "",
        "abstract": abstract,
        "tldr": "",
        "author_list": authors_list,
        "authors": " | ".join([a.strip() for a in authors_list]),
        "venue_title": venue_title,
        "doi": doi,
        "year": year
    }

def collect_paper_data_from_semanticscholar(url):
    """
    Example URL: https://www.semanticscholar.org/paper/00023588eb75959bfbd6ab6b1c266cf007f400d1
    
    """
    title = None
    semanticscholarid = url.split("?")[0].split("/")[-1]
    semanticscholar = get_paper_info_from_semantic_scholar_id(semanticscholarid)
    # semanticscholar = requests.get("https://api.semanticscholar.org/graph/v1/paper/"+semanticscholarid+"?fields=title,venue,tldr,authors,externalIds,embedding,embedding.specter_v2", headers = {"x-api-key": config.semanticscholar_key}).json()        
    tldr=semanticscholar["tldr"]["text"]+"\n\n" if "tldr" in semanticscholar and semanticscholar["tldr"] and semanticscholar["tldr"]["text"]  else ""
    authors = ""
    if semanticscholar!=None and "authors" in semanticscholar:           
        authors = ", ".join([x["name"] for x in semanticscholar["authors"]])
    if semanticscholar!=None and "title" in semanticscholar:           
        title = semanticscholar["title"]

    doi = None
    if "externalIds" in semanticscholar:
        if "DOI" in semanticscholar["externalIds"]:
            doi = semanticscholar["externalIds"]["DOI"]

    return {
        "url": url,
        "title": title,
        "semanticscholarid": semanticscholarid,
        "abstract": "",  # not available in the SemanticScholar API
        "tldr": tldr,
        "authors": authors,
        "venue_title" : semanticscholar.get("venue",""), 
        "doi" : doi,  
        "note" : ""  
    }


def old_code_for_tldr():        
    # if we have semanticscholarid,  we ask semanticscholarid for tldr and embedding
    if semanticscholarid!="" and ( \
        "arxiv.org" in url or "semanticscholar.org" in url or doi!=None)  \
    :
        if semanticscholarid == "" and doi:
            semanticscholarid="doi:"+doi
        #print(semanticscholarid)
        semanticscholar = requests.get("https://api.semanticscholar.org/graph/v1/paper/"+semanticscholarid+"?fields=title,tldr,authors,embedding,embedding.specter_v2", headers = {"x-api-key": config.semanticscholar_key}).json()
        #print(semanticscholar)
        if semanticscholar!=None and "paperId" in semanticscholar:
            # replacing "url:https://arxiv.org/pdf/2409.18317" by real paper if for the reader URL below
            semanticscholarid = semanticscholar["paperId"]
        if semanticscholar!=None and "tldr" in semanticscholar and semanticscholar["tldr"] != None and semanticscholar["tldr"]["text"]:
            tldr=semanticscholar["tldr"]["text"]+"\n\n"
        if semanticscholar!=None and "authors" in semanticscholar:           
            authors = ", ".join([x["name"] for x in semanticscholar["authors"]])
            
        # knn in embedding space
        if semanticscholar!=None and "embedding" in semanticscholar and semanticscholar["embedding"] and "vector" in semanticscholar["embedding"]:           
            note = "related in embedding space:\n- "+"\n- ".join([x["title"] for x in rrs.search_in_pinecone_semanticscholar(title, semanticscholar["embedding"]["vector"], 6) if x["title"] != title])
        #             # test of closest papers
        # closest = rrs.search_in_pinecone_str(paper.desc)
        # if len(closest) > 0:
        #     email += "\n\nclosest papers:\n"+rrs.search_in_pinecone_str(paper.desc)

        # if "url:" not in semanticscholarid and "doi:" not in semanticscholarid :
            # we like the semanticscholar reader
            # paper.reader_url = "https://www.semanticscholar.org/reader/"+semanticscholarid
        time.sleep(1)
    
    if doi and venue_title == None:
        # we ask crossref for info
        #  jq '.message."container-title"[0]' foo.json 
        crossref_data = "uknowncrossref"
        try:
            crossref_data = requests.get("https://api.crossref.org/works/"+doi).json()
            venue_title = crossref_data["message"]["container-title"][0]+''
            # authors = ", ".join([x["given"]+" "+x["family"] for x in crossref_data["message"]["author"]])
        except: pass
    


def notify_email(paper, service):
    """
    Send an email notification about a new paper using the Gmail API.
    """
    path = path_on_disk_internal_v2(paper.desc, "/home/martin/workspace/scholar-harvest/cache/already_notified/")
    if os.path.exists(path):
        return    

    # create an email body with the paper
    encoded_title = "=?utf-8?B?" + base64.b64encode(paper.desc.encode("utf-8")).decode("ascii") + "?="
    
    # must end with \n\n
    header = "From: <harvest@monperrus.net>\nTo: <martin.monperrus@gmail.com>\nSubject: "+encoded_title+"\n\n"

    # body, see     def __str__(self):        r+=self.desc+"\n"        r+=self.url+"\n"
    email = str(paper)
    
    if paper.venue_title and paper.venue_title != "":
        email += ""+paper.venue_title+"\n"
    
    if paper.tldr and paper.tldr != "":
        email += "\ntldr: "+paper.tldr
    
    if paper.abstract and paper.abstract != "":
        email += "\nabstract: "+paper.abstract+"\n"

    if paper.authors != "":
        email += "\nauthors:"+str(paper.authors)+"\n"

    if paper.reader_url and paper.reader_url != "":
        email += paper.reader_url+"\n"

    email += "\n\ncategories: "+", ".join(paper.categories)+"\n"
    email += "\nreason: "+paper.print_reason()+"\n"
    
    if paper.origin and paper.origin != "":
        email += "origin: "+paper.origin+"\n"
        
    if paper.note and paper.note != "":
        email += paper.note+"\n"

    # create a new email
    # Label_4447645605958895953 is label for harvest.py
    # Create HTML email content
    email_html_body = f"""<html>
<body>
<p><strong>{paper.desc}</strong><br/>
<a href="{paper.url}">{paper.url}</a></p>
{f"<p><strong>Venue:</strong> {paper.venue_title}</p>" if paper.venue_title else ""}
{f"<p><strong>TLDR:</strong> {paper.tldr}</p>" if paper.tldr else ""}
{f"<p><strong>Abstract:</strong> {paper.abstract}</p>" if paper.abstract else ""}
{f"<p><strong>Authors:</strong> {paper.get_authors()}</p>"}
<p><strong>Category:</strong> {", ".join(paper.categories)}</p>
<p><strong>Reason:</strong> {paper.print_reason()}</p>
{f"<pre>{paper.note}</pre>" if paper.note else ""}
{f"<!--<p><strong>Origin:</strong> {paper.origin}</p>-->" if paper.origin else ""}
</body>
</html>"""
    
    # Create multipart message with both text and HTML
    
    msg = MIMEMultipart('alternative')
    msg['From'] = 'harvest@monperrus.net'
    msg['To'] = 'martin.monperrus@gmail.com'
    msg['Subject'] = paper.desc
    
    # Add text version
    # text_part = MIMEText(email, 'plain', 'utf-8')
    # msg.attach(text_part)
    
    # Add HTML version
    html_part = MIMEText(email_html_body, 'html', 'utf-8')
    msg.attach(html_part)
    
    # add one single labelId tag to reduce reviewing time
    category_label_ids = []
    label = get_labelId(random.choice(paper.categories))
    if not label.startswith("https://"):
        category_label_ids.append(label)

    # 1. historical notification via gmail api
    if service != None and str(type(service)) == "<class 'googleapiclient.discovery.Resource'>":
        return push_email_via_gmail(service, msg, category_label_ids)
    
    # 2. new notification via direct SMTP email
    notify_followers(paper, email_html_body)

    # 3. test email to myself
    send_email(paper.desc, email_html_body,"martin.monperrus@laposte.net")

def push_email_via_gmail(service, msg, category_label_ids):
    """
    Push an email message to Gmail with the specified labels.
    
    Args:
        service: Gmail API service object
        msg: MIMEMultipart message object
        category_label_ids: List of label IDs to apply to the message
    
    Returns:
        tuple: (recorded message object, rfc822msgid or None)
    """
    recorded = service.users().messages().insert(userId='me', body={
        'raw': base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8"), 
        "labelIds":['UNREAD', "Label_4447645605958895953"] + category_label_ids
    }).execute()

    try:
        recorded = service.users().messages().get(userId='me', id=recorded["id"], format='metadata', metadataHeaders=['Message-Id']).execute()
        rfc822msgid = recorded["payload"]["headers"][0]['value']
    except Exception as e:
        print("error when getting message id, should probably sleep but this would become too slow", e)
        rfc822msgid = None

def notify_followers(paper, email_html_body):
    # test of sending emails, it works
    # if "webassembly" in paper.desc.lower(): # old sending emails vie gmail
    #     # send email to some collaborators
    #     res = service.users().messages().send(userId='me', body={
    #         'raw': base64.urlsafe_b64encode((header + email).replace('<martin.monperrus@gmail.com>','<monperrus@kth.se>,<xppcoder@gmail.com>,<benoit.baudry@umontreal.ca>').encode("utf-8")).decode("utf-8")
    #         }).execute()
    if paper.category.lower() == "LLM on code".lower():        
        # send_email("[harvest] new paper about "+paper.category, email_html_body,"markus.borg@codescene.com,postmaster@monperrus.net")
        pass
        
    if paper.category.lower() == "Testing".lower():
        # send_email("[harvest] new paper about "+paper.category, email_html_body,"deepika.tiwari@systemverification.com,benoit.baudry@umontreal.ca,postmaster@monperrus.net")
        pass


def send_email(encoded_title, email, recipients):
    # print("TODO implement daily summary email for Markus and Deepika")
    return
    print("sending",recipients,encoded_title)
    # send the email
    args = sendemail.EmailArgs()
    args.sender_email = "harvest@monperrus.net"
    args.sender_password = sendemail.login_keyring.get_password('login2', args.sender_email)
    args.receiver_email = ""
    # comma separated list, ** BCC ** 
    args.bcc = recipients
    args.subject = encoded_title
    # args.message = invitation.serialize() # ics version
    # print(dir(invitation))
    args.message = email
    # args.smtp_server = server # should be default
    # arg.to = ""  
    args.list = encoded_title
    sendemail.send_email(args)
    
def get_labelId(category):
    """
        get the Gmail labelId for a given category
    """

    if category=="planetse": return "Label_816000980291680327"
    if "readinglist - "+category not in categories:
        return "Label_4447645605958895953"
    label= categories["readinglist - "+category]["labelId"]
    if label == None or label == "":
        setup_categories()
        return get_labelId(category)
    return label 

def compute_category_embedding_test():
    """
    For the 20 most recent papers in cache/harvest, compute the category based on embedding similarity
    python -c "import harvest; harvest.compute_category_embedding_test()"
    """
    paths = sorted(glob.glob("cache/harvest/*"), key=os.path.getmtime, reverse=True)[:50]
    for path in paths:
        with open(path, "r") as f:
            paper_data = json.load(f)
            paper = Paper(paper_data["url"], paper_data["title"])
            categories = compute_category_embedding(paper)
            if len(categories) > 0:
                print(paper.desc)
                print("categories:", categories)
                print()

def compute_category_embedding(paper):
    """
    Compute the category based on the 5 nearest neighbors in embedding space

    python -c "import harvest; p=harvest.Paper('url','Testing machine learning based systems: a systematic mapping'); print(harvest.compute_category_embedding(p))"
    """
    # Get embedding for the paper
    embedding_result = get_embedding_and_push_to_db(paper.desc)
    if not embedding_result or not embedding_result.get("embedding") or not embedding_result["embedding"].get("vector"):
        return [("embedding_similarity", "uncategorized (no embedding)")]
    
    vector = embedding_result["embedding"]["vector"]
    
    # Search for similar papers in pinecone
    similar_papers = rrs.search_in_pinecone_semanticscholar(paper.desc, vector, 5)
        
    # Collect categories from similar papers
    category_counts = Counter()
    for similar in similar_papers:
        # Try to find the similar paper in our cache
        title = similar.get("title", "")
        # Create a temporary paper object for the similar paper
        similar_paper = Paper(None, title)
        categories = compute_category_based_past_classification(similar_paper)
        for _, category in categories:
            if category != "uncategorized":
                category_counts[category] += 1
    
    # Return the most common category if we found any
    if category_counts:
        most_common = category_counts.most_common(1)[0]
        return [(f"embedding_similarity_{most_common[1]}_neighbors", most_common[0])]
    
    return [("embedding_similarity", "uncategorized")]
        
_topic_mapping_cache = None

def compute_category_based_past_classification(paper):
    """
        in cache/link_to_topic_mapping.json title=>category
        {
    "online loans for software": "related_work_on_property-based_testing_for_program_repair__papers_tools.md",

        check whether the paper is in the mapping else return uncategorized    
    """
    global _topic_mapping_cache
    
    if _topic_mapping_cache is None:
        mapping_path = "cache/link_to_topic_mapping.json"
        if os.path.exists(mapping_path):
            with open(mapping_path, "r") as f:
                _topic_mapping_cache = json.load(f)
        else:
            _topic_mapping_cache = {}
    
    title_lower = normalize_title(paper.desc.lower())
    
    # Check for exact match
    if title_lower in _topic_mapping_cache:
        return [("compute_category_based_past_classification", _topic_mapping_cache[title_lower])]
        
    return [("compute_category_based_past_classification", "uncategorized")]

def compute_category_keywords_paper(paper):
    """
      classify the paper based on keywords
      categorize according to function classify_internal
    """

    title = paper.desc.lower()
    reason_txt = paper.print_reason()

    l1 = classify_internal_list(title)    
    classes = set()
    results = []
    for pattern, classification in l1:
        if classification != "uncategorized" and classification not in classes:
            results.append((pattern, classification))
            classes.add(classification)
            
    if len(results) == 0:
        l2 = classify_internal_list(reason_txt)    
        for pattern, classification in l2:
    
            if classification != "uncategorized" and classification not in classes:
                results.append((pattern, classification))
                classes.add(classification)
                

    if len(results) == 0:
        # ensure one
        results.append(("unknownpattern","uncategorized"))

    return results


def classify_internal(reason_txt):
    # backward compatible
    return classify_internal_list(reason_txt)[0]

def classify_internal_list(reason_txt):
    reason_txt = reason_txt.lower()
    results = []
     
    for THEME,j in CLASSIFICATION_DATA.items():
      for pattern in j:
        if pattern.lower() in reason_txt.lower(): 
            results.append((pattern,THEME))
    
    if len(results) == 0:
        # ensure one
        results.append(("unknownpattern","uncategorized"))

    return results


def increment_integer_in_file(file_path):
    file_path = file_path.replace("/","-")
    file_path = "./cache/increment_integer_in_file/"+file_path
    try:
        # Read the integer from the file
        with open(file_path, 'r') as file:
            integer = int(file.read())
    except FileNotFoundError:
        # If the file does not exist, start with integer value of 0
        integer = 0

    # Increment the integer
    integer += 1

    # Write the incremented integer back to the file
    with open(file_path, 'w') as file:
        file.write(str(integer))

    return integer





class ScholarParser(HTMLParser):
    """
        parses a Google Scholar email alert in HTML """
    def __init__(self):
        HTMLParser.__init__(self)
        self.papers = dict()
        self.pending_subject = None
        self.pending_url = None

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if tag == 'a' and attr_dict.get('class', None) == 'gse_alrt_title':
            scholar_url = attr_dict.get('href', '')
            parsed = urllib.parse.urlparse(scholar_url)
            qdict = urllib.parse.parse_qs(parsed.query)
            if 'url' in qdict:
                self.pending_url = str(qdict['url'][0])

    def handle_endtag(self, tag):
        if self.pending_url is not None:
            self.pending_url = None

    def handle_data(self, data):
        #if "my articles" in self.pending_subject:
        if self.pending_url is not None:
            if self.pending_url not in self.papers:
                paper_title = data
                self.papers[self.pending_url] = Paper(self.pending_url, paper_title)
            paper = self.papers[self.pending_url]
            if self.pending_subject is not None:
                paper.note_subject(self.pending_subject)

    def set_subject(self, subject):
        self.pending_subject = subject.decode("utf-8")


class ScholarScraperOrig(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.papers = dict()
        self.pending_subject = None
        self.pending_url = None

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if tag == 'a' and attr_dict.get('class', None) == 'gse_alrt_title':
            scholar_url = attr_dict.get('href', '')
            parsed = urllib.parse.urlparse(scholar_url)
            qdict = urllib.parse.parse_qs(parsed.query)
            if 'url' in qdict:
                self.pending_url = str(qdict['url'][0])

    def handle_endtag(self, tag):
        if self.pending_url is not None:
            self.pending_url = None

    def handle_data(self, data):
        #if "my articles" in self.pending_subject:
        print(data)
        if self.pending_url is not None:
            if self.pending_url not in self.papers:
                self.papers[self.pending_url] = Paper(self.pending_url, data)
            paper = self.papers[self.pending_url]
            if self.pending_subject is not None:
                paper.note_subject(self.pending_subject)

    def set_subject(self, subject):
        self.pending_subject = subject.decode("utf-8")



def setup_categories():
    scraper = ScholarScraper()
    scraper.service = build('gmail', 'v1', http=get_creds().authorize(Http()))

    # get all labels in the account
    
    labels = scraper.service.users().labels().list(userId='me').execute()
    for label in labels['labels']:
        #print(label)
        if label['name'] in categories:
            categories[label['name']]["labelId"] = label['id']
            #print("found "+label['id'] +" "+label['name'])
        #print(label['id'] +" "+label['name'])
    for category, l in categories.items():
        if l['labelId']=="":
            print("creating label "+category)
            label = scraper.service.users().labels().create(userId='me', body={
                "name": category,
                "messageListVisibility": "show",
                "labelListVisibility": "labelShowIfUnread",
                "type": "user"
            }).execute()            
            categories[label['name']]["labelId"] = label['id']

def main():
    global READING_NOTES
    READING_NOTES=open("/home/martin/workspace/related-work-github/ASSERT-KTH-related-work/allall.md").read().lower()
    setup_categories()
    classify_scholarnotifications()
    classify_planetse()
    classify_semanticscholar()

def get_creds():
    store = file.Storage(os.path.dirname(__file__)+'/token.json')
    creds = store.get()
    if not creds or creds.invalid:
        """
        The **`credentials.json`** file for the Gmail API is not something you can just "write" by hand — it must be downloaded directly from your Google Cloud project after you configure OAuth credentials.

Now using the one from project "assert-experiments"
        
1. **Go to Google Cloud Console**
   [https://console.cloud.google.com/](https://console.cloud.google.com/)

2. **Create a new project (or select an existing one)**

   * Click the project dropdown → **New Project**.
   * Give it a name (e.g., *Gmail API Project*).

3. **Enable the Gmail API**

   * Go to **APIs & Services → Library**.
   * Search for **Gmail API**.
   * Click **Enable**.

4. **Create OAuth 2.0 credentials**

   * Navigate to **APIs & Services → Credentials**.
   * Click **Create Credentials → OAuth client ID**.
   * Configure the **OAuth consent screen** if prompted (add scopes, user info).
   * Choose **Application type**:

     * *Desktop app* (for scripts or testing)
     * *Web application* (if building a web app)
   * Click **Create**.

5. **Download the `credentials.json` file**

   * Once created, click the **Download JSON** button.
   * Rename it to `credentials.json` and place it in your project folder.


        
        
        """
        # get token for gmail read and write
        path= os.path.dirname(__file__)+'/credentials.json'
        # path = "/home/martin/harvest-credentials.json"
        flow = client.flow_from_clientsecrets(path, SCOPES)
        creds = tools.run_flow(flow, store)
        store.put(creds)
    return creds

def classify_scholarnotifications():
    scraper = ScholarScraper()
    scraper.service = build('gmail', 'v1', http=get_creds().authorize(Http()))


    query = 'from:scholaralerts-noreply@google.com is:unread '+cutoff_date_gmail()
    maxRes = 10000
    response = scraper.service.users().messages().list(userId='me', q=query, maxResults=maxRes).execute()

    messages = []
    if 'messages' in response:
      messages.extend(response['messages'])

    while 'nextPageToken' in response:
      page_token = response['nextPageToken']
      response = scraper.service.users().messages().list(userId='me', q=query,
                                         pageToken=page_token).execute()
      messages.extend(response['messages'])

    print('Scanning %d Google Scholar notifications' % len(messages))
    for m in messages:
        msg = scraper.service.users().messages().get(userId='me', id=m['id']).execute()
        payload = msg['payload']
        subj = [h['value'] for h in payload['headers'] if h['name']=='Subject'][0]
        subj = subj.encode('utf-8')
        if subj ==None: print(payload['headers']) 
        if 'data' not in payload['body']: continue
        v = payload['body']['data']
        scraper.set_subject(subj)
        scraper.feed(msg)
        
        # mark the message as read
        scraper.service.users().messages().modify(userId='me', id=m['id'], body={'removeLabelIds': ['UNREAD']}).execute()


    scraper.dump_by_reason()


def cutoff_date_gmail():
    # older than 2 weeks, to let my students share it
    return 'before:'+(datetime.now() - timedelta(weeks=2)).strftime("%Y/%m/%d")

def classify_planetse():

    service = build('gmail', 'v1', http=get_creds().authorize(Http()))

    # was after:'+(datetime.now() - timedelta(weeks=2)).strftime("%Y/%m/%d"), replaced by is:unread
    query = 'is:unread label:planetse '+cutoff_date_gmail()
    maxRes = 10000
    #print(get_labelId('planetse'))
    #response = service.users().messages().list(userId='me', labelIds=[get_labelId('planetse')], maxResults=maxRes).execute()
    response = service.users().messages().list(userId='me', q=query, maxResults=maxRes).execute()

    messages = []
    if 'messages' in response:
      messages.extend(response['messages'])

    while 'nextPageToken' in response:
      page_token = response['nextPageToken']
      response = service.users().messages().list(userId='me', q=query,
                                         pageToken=page_token).execute()
      messages.extend(response['messages'])

    print('Scanning %d planetse notifications' % len(messages))
    for m in messages:
        msg = service.users().messages().get(userId='me', id=m['id']).execute()

        msg_date = datetime.fromtimestamp(int(msg['internalDate'])/1000)

        #print(msg['labelIds'])
        payload = msg['payload']
        subj = [h['value'] for h in payload['headers'] if h['name']=='Subject'][0]
        # X-RSS-URL is added by r2e, nice
        url = [h['value'] for h in payload['headers'] if h['name']=='X-RSS-URL'][0]
        
        # get the embedding
        get_embedding(subj)

        # avoid duplicate
        paper = Paper(url, subj)
        #if already_seen(paper): continue
        
        pattern, classification = classify_internal(paper.desc.lower())
        paper.reason.append("title match "+pattern)
        if classification != "uncategorized":
            
            # in theory we can do that
            create_harvest_email_paper(paper, service, origin="planetse", detection_date=msg_date)

            # we delete the classified message
            service.users().messages().trash(userId='me', id=m['id']).execute()

            #print(subj, classification)
            #         self.service.users().messages().modify(userId='me', id=message['id'], body={'removeLabelIds': ['UNREAD']}).execute()
            # move to a folder
            #r= service.users().messages().modify(
                #userId='me',
                #id=m['id'],
                #body={'addLabelIds': [get_labelId(classification)],'removeLabelIds': [get_labelId('planetse')] }
            #).execute()
            #A list IDs of labels to remove from this message. You can remove up to 100 labels with each update.
            #print(r, get_labelId('planetse'))
        else: 
            # we may delete the messages
            #service.users().messages().trash(userId='me', id=m['id']).execute()
            pass


def classify_semanticscholar():
    service = build('gmail', 'v1', http=get_creds().authorize(Http()))


    query = 'from:do-not-reply@semanticscholar.org is:unread '+cutoff_date_gmail()
    maxRes = 10000
    response = service.users().messages().list(userId='me', q=query, maxResults=maxRes).execute()

    messages = []
    if 'messages' in response:
      messages.extend(response['messages'])

    while 'nextPageToken' in response:
      page_token = response['nextPageToken']
      response = service.users().messages().list(userId='me', q=query,
                                         pageToken=page_token).execute()
      messages.extend(response['messages'])

    print('Scanning %d Semanticscholar notifications' % len(messages))
    for m in messages:
        msg = service.users().messages().get(userId='me', id=m['id']).execute()
        msg_date = datetime.fromtimestamp(int(msg['internalDate'])/1000)
        for payload in msg['payload']["parts"]:
            payload = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
            
            doc = etree.HTML(payload)
            for i in doc.xpath(".//a[contains(@class,'paper-link')]"):
                link = i.attrib["href"]
                # removing ?utm_source=alert_email
                # if "?" in link: link = link.split("?")[0]
                link = link.replace("utm_source=alert_email","")
                if link.endswith("?"): link = link[:-1]
                
                paper = Paper(link, i.text.strip())
                paper.reason.append("semanticscholar recommendation")
                if create_harvest_email_paper(paper, service, origin="semanticscholar", detection_date=msg_date):
                    #print("semanticscholar:", i.text)
                    pass
        # we put it in the trash
        service.users().messages().trash(userId='me', id=m['id']).execute()

def esc(s):
    if not s:
        return ""
    return s.replace("{", r"\{").replace("}", r"\}").replace("\n", " ").strip()

def to_bibtex(paper_data_dict):

    title = paper_data_dict.get("title", "") or ""
    if paper_data_dict.get("author_list"):
        authors = " and ".join(paper_data_dict.get("author_list"))
    else:
        authors = paper_data_dict.get("authors", "") or ""
    venue = paper_data_dict.get("venue_title", "") or ""
    doi = paper_data_dict.get("doi", "") or ""
    year = str(paper_data_dict.get("year", "") or "")
    url = paper_data_dict.get("url", "") or ""
    abstract = paper_data_dict.get("abstract", "") or ""
    note = paper_data_dict.get("note", "") or ""
    ssid = paper_data_dict.get("semanticscholarid", "") or ""

    # key generation
    if doi:
        key = re.sub(r'[^0-9A-Za-z_-]+', '_', doi)
    else:
        first_author = "anon"
        if authors:
            first_author = authors.split(",")[0].split()[-1]
        title_snip = re.sub(r'[^0-9A-Za-z]+', '', title[:30])
        key = f"{first_author}{year or ''}{title_snip or 'X'}"

    # authors -> BibTeX author list (best-effort)
    if " and " in authors:
        bib_authors = authors
    elif "," in authors:
        parts = [p.strip() for p in authors.split(",") if p.strip()]
        # if "Last, First" style detected leave as is, else join with ' and '
        if all(len(p.split()) >= 2 for p in parts):
            bib_authors = " and ".join(parts)
        else:
            bib_authors = authors
    else:
        bib_authors = authors

    fields = []
    if bib_authors:
        fields.append(f"  author = {{{esc(bib_authors)}}}")
    if title:
        fields.append(f"  title = {{{esc(title)}}}")
    if venue:
        fields.append(f"  journal = {{{esc(venue)}}}")
    if year:
        fields.append(f"  year = {{{esc(year)}}}")
    if doi:
        fields.append(f"  doi = {{{esc(doi)}}}")
    if url:
        fields.append(f"  url = {{{esc(url)}}}")
    if abstract:
        fields.append(f"  abstract = {{{esc(abstract)}}}")
    # if arXiv url, add number field with arXiv id
    arxiv_id = None
    if url and "arxiv.org" in url:
        m = re.search(r'([0-9]{4}\.[0-9]{4,5}(v\d+)?)|([a-z\-]+/\d{7})', url)
        if m:
            arxiv_id = m.group(0)
        else:
            # fallback: take last path segment and strip .pdf and query
            try:
                last = url.split('/')[-1]
                last = last.split('?')[0]
                last = last.replace('.pdf', '')
                if last:
                    arxiv_id = last
            except:
                arxiv_id = None
    if arxiv_id:
        fields.append(f"  number = {{   arXiv:{esc(arxiv_id)}}}")
    bibtype = "techreport"
    if venue or doi:
        bibtype = "article"
    body = ",\n".join(fields)
    return f"@{bibtype}{{{key},\n{body}\n}}\n"

def compute_stats_missing_metadata():
    """
Analyze "cache/domains-no-api.support.jsonl" to output the top 10 missing domains to be supported

python -c "import harvest; harvest.compute_stats_missing_metadata()"
    """
    counter = Counter()
    with open("cache/domains-no-api.support.jsonl", "r") as f:
        for line in f:
            data = json.loads(line)
            domain = data.get("domain", "unknown")
            counter[domain] += 1
    print("Top 10 missing domains to be supported:")
    for domain, count in counter.most_common(10):
        print(f"{domain}: {count}")

def transfer_data_from_dict_to_paper(paper, paper_data):
    paper.url = paper_data["url"] if "url" in paper_data and len(paper_data["url"]) > 0 else paper.url
    # OOPS for historical reasons paper.desc is title
    paper.desc = paper_data["title"] if "title" in paper_data and len(paper_data["title"]) > 0 else paper.desc
    if "author_list" in paper_data and paper_data["author_list"]:
        paper.authors = " | ".join(paper_data["author_list"]) if "author_list" in paper_data and paper_data["author_list"] else ""
        paper.author_list = paper_data["author_list"]
    else:
        paper.authors = paper_data.get("authors", "")
    paper.abstract = paper_data.get("abstract", "")
    paper.venue_title = paper_data.get("venue_title", "")
    paper.year = paper_data.get("year", "unknown year")
    paper.tldr = paper_data.get("tldr", "")
    paper.note = paper_data.get("note", "")
    paper.detection_date = datetime.now().isoformat()

def collect_and_send_email(url):
    """
    Collect paper data from the given URL and send an email notification if it's a high-reputation source and not already seen.

    python -c "import harvest; harvest.collect_and_send_email('https://arxiv.org/abs/2406.12345')"
    """
    
    # Collect paper data with caching
    paper_data = collect_paper_data_from_url_with_cache(url)
    if not paper_data or not paper_data.get("title"):
        print(f"No data collected for URL: {url}")
        return False
    
    # Create a Paper object
    paper = Paper(url, paper_data["title"])
    transfer_data_from_dict_to_paper(paper, paper_data)
    
    # Classify the paper
    paper.categories = [x[1] for x in compute_category_keywords_paper(paper)]
    paper.category = paper.categories[0] if paper.categories else "uncategorized"
    
    # Set up Gmail service
    service = build('gmail', 'v1', http=get_creds().authorize(Http()))
    
    # Check if high reputation and send notification
    notify_email(paper, service)
    

if __name__ == '__main__':
    main()
