#!/usr/bin/env python3
#
# Analyzes paper notifications (Google Scholar, Semanticscholar, planetse) sent over email
#
# send notifications over email
#
# TODO: add support for searching in the main search engines
# TODO: document the past matches on a web page
# 
# To make stats of reasons, as easy as jq .reason cache/*.json | freqlines
# grep -l "Evaluating large language models trained on code" cache/*.json | xargs rm 
#
#  new search by scholar: curl -X GET "https://api.semanticscholar.org/graph/v1/snippet/search?query=program+repair+by+removing+the+mandatory+presence&limit=10" -H "x-api-key: "
# return the section and snippet, quite useful

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
from harvest_lib import *


# ollama pull jeffh/intfloat-multilingual-e5-large-instruct:f16
# kate /home/martin/workspace/reviewer-recommendation-system/embed.py
sys.path.append("/home/martin/workspace/reviewer-recommendation-system/")
import embed as rrs

sys.path.append("/home/martin/bin/")
import sendemail


rrs.ensure_embedding_up()


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
                    'fix',
                    'patch',
                    'bug',
                    'debug', # already in "bug" but that's clear
                    'overfitting'
                    ],
 'Vulnerability': [
                    ' go ',
                    'golang',
                    'vulnerabil' # vivi
                    ],
 'Chains': [ 'supply chain',
            'protection',
            'integrity',
            'guard',
            'package',
            'librar',
            'dependenc',
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
            'compatib',
            'sigstore'],
 'Smart contracts': ['blockchain',
                     'transaction',
                     'smart contract',
                     'smart-contract',
                     'bitcoin',
                     'ethereum',
                     'solidity',
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
                 'llm',
                 'neural',
                 'predict',
                 'learn',
                 'generative',
                 'transformer',
                 'prompt',
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
                 'translation'],
 'Code analysis': [ 'spoon',
                    'dataset',
                    'benchmark',
                    'merge',
                    'differencing', 'compil', 'analysis', 'fuzz', 'transform'],
 'Testing': ['test', 'oracle', 'metamorphic', 'mutant'],
 'LLM general': ['language model', 
                 'pre-training', 
                 'toolformer',
                 'jigsaw',
                 'langchain',
                 'talm'],
 'Reliability': ['fault','robustness', 'multi-variant', 'divers', 'chaos', 'n-version', 'antifrag', 'heal','observability'], 
 'Fake': ['fake', 'decoy', 'honeypot'],
 'Curiosity': ['password'],
 'WebAssembly': ['webassembly','wasm'],
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

def DEPRECATED_path_on_disk_internal_v1(papertitle, prefix):
    assert prefix.endswith("/")
    """ DEPRECATED SEE V2 """
    # remove trailing space and trailing dots from paper.desc
    papertitle = papertitle.strip().rstrip(".").replace("   "," ").replace("  "," ")
    return prefix+hashlib.sha256(papertitle.encode("utf-8")).hexdigest()+".json"
def path_on_disk(paper):
    return path_on_disk_internal(paper.desc)
def path_on_disk_internal(papertitle, prefix = "/home/martin/workspace/scholar-harvest/cache/harvest/"):
    return path_on_disk_internal_v2(papertitle, prefix)

def already_seen_url(url, prefix):
    """
    example: urlseen, thepath = already_seen_url("https://doi.org/10.1145/3597503.3623337", "/home/martin/workspace/scholar-harvest/cache/XXXXXXX/")
    """
    assert prefix.endswith("/")
    thepath = prefix+hashlib.sha256(url.encode("utf-8")).hexdigest()+".json"
    return os.path.exists(thepath), thepath
READING_NOTES=open("/home/martin/workspace/related-work-github/ASSERT-KTH-related-work/allall.md").read().lower()
def already_seen(paper):
    fname= path_on_disk(paper)
    if paper.desc.lower() in READING_NOTES: return True
    return os.path.exists(fname)

def record_paper_as_seen(paper, **kwargs):
    """
        we've already seen this paper, we create a file on disk accordingly
    """
    fname= path_on_disk(paper)
    with open(fname,"w") as f: 
        data = paper.as_dict()
        data.update(kwargs)
        f.write(json.dumps(data))


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
    assert paper.url.startswith("http")
    if not is_high_reputation(paper.url):
        print("no reputation for "+paper.url)
        return False

    origin = ""
    if "origin" in kwargs: origin = kwargs["origin"]
    detection_date = "unknown_detection_date"
    if "detection_date" in kwargs: detection_date = kwargs["detection_date"]
    
    if already_seen(paper):
        return
    
    paper_data = collect_paper_data_from_url(paper.url)
    
    # what we obtained from the endpoint
    paper.venue_title = paper_data["venue_title"]
    paper.url = paper_data["url"] # for some paper we replace with a better url (eg computer.org)
    paper.tldr = paper_data["tldr"]
    paper.authors = paper_data["authors"]
    paper.abstract = paper_data["abstract"]
    paper.note = paper_data["note"]
        
    paper.origin = origin
    
    category = compute_category_keywords(paper)
    paper.category = category 

    paper.detection_date = detection_date.isoformat()

    # notify if high reputation only   
    if is_high_reputation(paper.url):
        notify_email(paper, service)
    else: 
        print("no reputation for "+paper.url)   

    record_paper_as_seen(paper)

    return True

def is_high_reputation(url):
    """
    check if the paper is from a high reputation source, before sending a notification
    discards mdpi, researchgate.net
    """
    if "nature.com" in url: return True
    if "doi.org" in url: return True
    if "arxiv.org" in url: return True
    if "semanticscholar.org" in url: return True
    if "dblp.org" in url: return True
    if "computer.org" in url: return True
    if "ieeexplore.ieee.org" in url: return True
    if "dl.acm.org" in url: return True
    if "link.springer.com" in url: return True
    if "onlinelibrary.wiley.com" in url: return True
    if "sciencedirect.com" in url: return True
    if "linkinghub.elsevier.com" in url: return True
    if "diva-portal.org" in url: return True
    if "hal.science" in url: return True
    if "ojs.aaai.org" in url: return True
    return False

def get_doi_target(doi):
    # https://doi.org/api/handles/10.1145/3597503.3623337
    url = f"https://doi.org/api/handles/{doi}"
    data = requests.get(url).json()
    if data["responseCode"] == 1:
        for i in data["values"]:
            if i["type"] == "URL":
                return i["data"]["value"]
    raise Exception("doi not found")

def collect_paper_data_from_doi(doi):
    assert len(doi)>0
    return collect_paper_data_from_url(get_doi_target(doi))

def collect_paper_data_from_url_with_cache(url):
    urlseen, thepath = already_seen_url(url,"/home/martin/workspace/scholar-harvest/cache/collect_paper_data_from_url_with_cache/")
    if urlseen:
        with open(thepath, "r") as f:
            data = json.load(f)
            if "url" in data:
                return data
    data = collect_paper_data_from_url(url)
    with open(thepath, "w") as f:
        f.write(json.dumps(data))
    return data

def info_from_crossref(doi):

    """
    Transform CROSSREF JSON data to the specified FORMAT structure.
    
    Args:
        crossref_data (dict): The CROSSREF JSON data
    
    Returns:
        dict: The transformed data in the FORMAT structure
    """

    crossref_data = requests.get(f"https://api.crossref.org/works/{doi}").json()
    message = crossref_data.get("message", {})
    
    # Extract basic information
    title = message.get("title", [""])[0] if message.get("title") else ""
    doi = message.get("DOI", "")
    url = f"https://doi.org/{doi}" if doi else ""
    
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
    elif message.get("event", {}).get("name"):
        venue_title = message.get("event", {}).get("name", "")
    
    # Create a note with publication date and publisher information
    published_date = ""
    if message.get("published"):
        date_parts = message.get("published", {}).get("date-parts", [[]])[0]
        if date_parts:
            published_date = "-".join(str(part) for part in date_parts)
    
    publisher = message.get("publisher", "")
    note = f"Published: {published_date}, Publisher: {publisher}" if published_date or publisher else ""
    
    # Create the formatted output
    formatted_output = {
        "url": url,
        "title": title,
        "semanticscholarid": "",  # Not available in CROSSREF data
        "abstract": "",  # Not available in CROSSREF data
        "tldr": "",  # Not available in CROSSREF data
        "authors": authors,
        "venue_title": venue_title,
        "doi": doi,
        "note": note
    }
    
    return formatted_output

def collect_paper_data_from_url(url):
    """
    from harvest import *
    print(collect_paper_data_from_url("https://www.sciencedirect.com/science/article/pii/S0950584924002593"))
    >>> collect_paper_data_from_url("https://www.sciencedirect.com/science/article/pii/S0950584924002593")
    {'url': 'https://www.sciencedirect.com/science/article/pii/S0950584924002593', 'semanticscholarid': '', 'tldr': '', 'authors': '', 'venue_title': 'Information and Software Technology', 'doi': '10.1016/j.infsof.2024.107654'}
        
    >>> collect_paper_data_from_url("dl.acm.org/doi/abs/10.1145/3708474")
    {'url': 'dl.acm.org/doi/abs/10.1145/3708474', 'semanticscholarid': '', 'tldr': '', 'authors': 'Yinan Chen, Yuan Huang, Xiangping Chen, Zibin Zheng', 'venue_title': 'ACM Trans. Softw. Eng. Methodol.', 'doi': '10.1145/3708474'}
    """
    # addition of tldr
    semanticscholarid=""
    tldr=""
    authors=""
    venue_title = None
    doi=None
    abstract = None
    title = None
    note = None
    if "/doi.org/" in url:
        doi = url.replace("https://doi.org/","").replace("http://doi.org/","")
        try:
            return collect_paper_data_from_doi(doi)
        except Exception as e:
            print("doi error",doi)
        
    if "arxiv.org" in url:    
        ## https://www.monperrus.net/martin/arxiv-json.py?id=2304.12015
        semanticscholarid="url:"+url.replace("/html/","/pdf/")
        components = [x for x in url.split("/") if len(x)>0]
        arxiv_id = components[-1].split("?")[0]
        # https://www.monperrus.net/martin/arxiv-json.py?id=2409.18952v1
        theurl = "https://www.monperrus.net/martin/arxiv-json.py?id="+arxiv_id
        # print(theurl)
        arxiv_metadata = requests.get(theurl).json()
        abstract = arxiv_metadata["summary"].replace("\n"," ")
        authors = ", ".join([x["name"] for x in arxiv_metadata["author"]])
        venue_title = arxiv_metadata["journal_ref"]
        title = arxiv_metadata["title"]
    if "semanticscholar.org" in url:
        semanticscholarid=url.split("/")[-1]
    if "dblp.org" in url:
        components = [x for x in url.split("/") if len(x)>0]
        dblp_id = "/".join(components[-3:])
        # added Jan 2025
        dblp_url = "https://www.monperrus.net/martin/dblp-json.py?id="+dblp_id
        # print(dblp_url)
        dblp_metadata = requests.get(dblp_url).json()
        venue_title = dblp_metadata["venue_title"]
        authors = ", ".join(dblp_metadata["author"])
        # DOI Chain from dblp
        if "ee" in dblp_metatata:
            return collect_paper_data_from_doi(dblp_metadata["ee"])
        # if "doi.org" in dblp_metadata["ee"]:
        #     url = get_doi_target(dblp_metadata["ee"])
        # print("TODO implement DOI and chain for DBLP")
    if "dl.acm.org" in url:
        components = [x for x in url.split("/") if len(x)>0]
        doi = components[-2]+"/"+components[-1]
        return info_from_crossref(doi)
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
        if len(springer_data["records"])>0:
            # print(url)
            paper_data = springer_data["records"][0]
            venue_title=paper_data["publicationName"]
            abstract=paper_data["abstract"]
            title=paper_data["title"]
            authors = " - ".join([x["creator"] for x in paper_data["creators"]])

        # print(springer_data)
        
    if "computer.org" in url:
        # we can also get tldr for ieee papers
        csdlid = [x for x in url.split("/") if len(x)>0][-1]
        cdsl_data = get_cdsl_data(csdlid)
        doi = cdsl_data["doi"]
        abstract = cdsl_data["abstract"]
        title = cdsl_data["title"]
        authors = ", ".join([x["fullName"] for x in cdsl_data["authors"]])
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
            if "full-text-retrieval-response" in elsevier_data:
                venue_title = elsevier_data["full-text-retrieval-response"]["coredata"]["prism:publicationName"]
                doi = elsevier_data["full-text-retrieval-response"]["coredata"]["prism:doi"]
                title = elsevier_data["full-text-retrieval-response"]["coredata"]["dc:title"]
                abstract = elsevier_data["full-text-retrieval-response"]["coredata"]["dc:description"]
                url = url.replace('?dgcid=rss_sd_all','')
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
        # we can also get tldr for ieee papers
        if "abs_all.jsp" in url:
            # parse url
            components = urllib.parse.urlparse(url)
            qdict = urllib.parse.parse_qs(components.query)
            ieeeid = qdict["arnumber"][0]
            # print(qdict)
        else:
            ieeeid = [x for x in url.split("/") if len(x)>0][-1]
        # curl "https://ieeexploreapi.ieee.org/api/v1/search/articles?apiKey=XXXXXX&article_number=10833642"
        resp = requests.get("https://ieeexploreapi.ieee.org/api/v1/search/articles?article_number="+ieeeid+"&apiKey="+config.ieeexplore_key)
        if resp.status_code != 418: # i'm a teapot, WTF?
            print(resp.text)
            try:
                ieeedata = resp.json()
            except Exception as e:
                raise Exception("ieee error",resp.status_code,resp.text)
                
            if "error" not in ieeedata and "articles" in ieeedata:
                if "doi" in ieeedata["articles"][0]:
                    doi = ieeedata["articles"][0]["doi"]
                venue_title = ieeedata["articles"][0]["publication_title"]
                abstract = ieeedata["articles"][0]["abstract"]
                # print ([x for x in ieeedata["articles"][0]["authors"]["authors"]])
                # args the ["authors"]["authors"], bad data model
                authors = ", ".join([x["full_name"] for x in ieeedata["articles"][0]["authors"]["authors"]])
                title = ieeedata["articles"][0]["title"]                
                # semanticscholarid="doi:"+doi
            else: print("no data in ieee "+json.dumps(ieeedata, indent=2))
            
        
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
            
        if semanticscholar!=None and "embedding" in semanticscholar and semanticscholar["embedding"] and "vector" in semanticscholar["embedding"]:           
            note = "related:\n- "+"\n- ".join(rrs.search_in_pinecone_semanticscholar(title, semanticscholar["embedding"]["vector"], 5))
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
    
    return {
        "url":url,
        "title":title,
        "semanticscholarid":semanticscholarid,
        "abstract":abstract,
        "tldr": tldr,
        "authors": authors,
        "venue_title" : venue_title,
        "doi" : doi,
        "note" : note
    }

def notify_email(paper, service):
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

    email += "\n\ncategory: "+paper.category
    email += "\nreason: "+paper.print_reason()+"\n"
    
    if paper.origin and paper.origin != "":
        email += "origin: "+paper.origin+"\n"
        
    if paper.note and paper.note != "":
        email += paper.note+"\n"

    # create a new email
    # Label_4447645605958895953 is label for harvest.py
    recorded = service.users().messages().insert(userId='me', body={
        'raw': 
            base64.urlsafe_b64encode((header + email).encode("utf-8")).decode("utf-8"), "labelIds":['UNREAD', "Label_4447645605958895953", categories["readinglist - "+paper.category]["labelId"]]}).execute()
    recorded = service.users().messages().get(userId='me', id=recorded["id"], format='metadata', metadataHeaders=['Message-Id']).execute()
    rfc822msgid = recorded["payload"]["headers"][0]['value']
    
    # test of sending emails, it works
    # if "webassembly" in paper.desc.lower(): # old sending emails vie gmail
    #     # send email to some collaborators
    #     res = service.users().messages().send(userId='me', body={
    #         'raw': base64.urlsafe_b64encode((header + email).replace('<martin.monperrus@gmail.com>','<monperrus@kth.se>,<xppcoder@gmail.com>,<benoit.baudry@umontreal.ca>').encode("utf-8")).decode("utf-8")
    #         }).execute()
    if paper.category.lower() == "LLM on code".lower():
        # send the email
        args = sendemail.EmailArgs()
        args.sender_email = "harvest@monperrus.net"
        args.sender_password = sendemail.login_keyring.get_password('login2', args.sender_email)
        args.receiver_email = ""
        # comma separated list, ** BCC ** 
        args.bcc = "markus.borg@codescene.com"
        args.subject = encoded_title
        # args.message = invitation.serialize() # ics version
        # print(dir(invitation))
        args.message = email
        # args.smtp_server = server # should be default
        # arg.to = ""  
        args.list = "harvest - "+paper.category
        sendemail.send_email(args)
        
    # print(res)

    #print("unique_id", unique_id)
    print("emailed", paper.desc, paper.category)

def get_labelId(category):
    if category=="planetse": return "Label_816000980291680327"
    return categories["readinglist - "+category]["labelId"]

# def classify(reason_txt):
#     return classify_internal(reason_txt)[1]

def compute_category_keywords(paper):
    """
      classify the paper based on keywords
      categorize according to function classify_internal
    """

    title = paper.desc.lower()
    reason_txt = paper.print_reason()

    pattern1, classification1 = classify_internal(title)    
    increment_integer_in_file(pattern1)

    if classification1 != "uncategorized": return classification1

    pattern2, classification2 = classify_internal(reason_txt)
    
    if classification2 != "uncategorized": return classification2

    return "uncategorized"

def classify_internal(reason_txt):
    reason_txt = reason_txt.lower()
     
    for THEME,j in CLASSIFICATION_DATA.items():
      for pattern in j:
        if pattern.lower() in reason_txt.lower(): 
            return pattern,THEME
    
    

    return "none", "uncategorized"


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
    setup_categories()
    classify_scholarnotifications()
    classify_planetse()
    classify_semanticscholar()

def get_creds():
    store = file.Storage(os.path.dirname(__file__)+'/token.json')
    creds = store.get()
    if not creds or creds.invalid:
        # get token for gmail read and write
        flow = client.flow_from_clientsecrets(os.path.dirname(__file__)+'/credentials.json', SCOPES)
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



if __name__ == '__main__':
    main()
