#!/usr/bin/env python3
#
# Analyzes paper notifications (Google Scholar, Semanticscholar, planetse) sent over email
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


sys.path.append("/home/martin/workspace/reviewer-recommendation-system/")
import embed as rrs

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

categories = {
    "readinglist - Program Repair":{"labelId":"","papers":[]},
    "readinglist - Reliability":{"labelId":"","papers":[]},
    "readinglist - Smart contracts":{"labelId":"","papers":[]},
    "readinglist - LLM general":{"labelId":"","papers":[]},
    "readinglist - LLM on code":{"labelId":"","papers":[]},
    "readinglist - Chains":{"labelId":"","papers":[]},
    "readinglist - Fake":{"labelId":"","papers":[]},
    "readinglist - Diversity":{"labelId":"","papers":[]},
    "readinglist - Testing":{"labelId":"","papers":[]},
    "readinglist - WebAssembly":{"labelId":"","papers":[]},
    "readinglist - colleagues":{"labelId":"","papers":[]},
    "readinglist - uncategorized":{"labelId":"","papers":[]}
    }

class Paper:
    def __init__(self, url, desc):
        self.url = url
        self.reader_url = ""
        self.desc = desc
        self.author = set()
        self.citing = set()
        self.related = set()
        self.search = set()
        self.reason = "noreason"
        self.abstract = None

    def note_subject(self, subject):
        subject = subject.replace('"','')
        self.reason = subject
        am = author_rx.match(subject)
        if am:
            self.author.add(am.group(1))
            return
        cm = citing_rx.match(subject)
        if cm:
            self.citing.add(cm.group(1))
            return
        rm = related_rx.match(subject)
        if rm:
            self.related.add(rm.group(1))
            return
        sm = search_rx.match(subject)
        if sm:
            self.search.add(sm.group(1))
            return

    def dump(self):
        print(str(self))

    def print_reason(self):
        return ", ".join(self.array_reason())
    def array_reason(self):
        result=[]
        if len(self.author) != 0:
            result+= ["author: " + x for x in self.author]
        if len(self.citing) != 0:
            result+= ["citing: " + x for x in self.citing]
        if len(self.related) != 0:
            result+= ["related: " + x for x in self.related]
        if len(self.search) != 0:
            result+= ["search: " + x for x in self.search]
        if len(result)==0: result.append(self.reason)
        return result
    
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
            paper.citing.add(i.xpath('../following-sibling::table')[0].xpath(".//span/text()")[0])
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
        # mark the message as read
        self.service.users().messages().modify(userId='me', id=message['id'], body={'removeLabelIds': ['UNREAD']}).execute()
        #if n>0: raise Exception()

        self.papers.update(new_papers)

    def dump(self):

        for url, paper in self.papers.items():
            paper.dump()

    def save_paper(self, paper):
        
        #if already_seen(paper): return 1

        # no need now that we have already_seen
        #query = 'from:(harvest@monperrus.net) subject:"'+paper.desc+'"'
        #maxRes = 10000
        #response = self.service.users().messages().list(userId='me', q=query, maxResults=maxRes).execute()
        #if response["resultSizeEstimate"]>0: return 0

        # this should work
        create_harvest_email_paper(paper, self.service, origin="scholar",detection_date=self.msg_date)
        
        #category = compute_category(paper)
        
        #if category != "uncategorized":
            #print(paper.desc+" "+str(response["resultSizeEstimate"])+" -> "+category)
        
        ## create an email with the paper
        #encoded_title = "=?utf-8?B?" + base64.b64encode(paper.desc.encode("utf-8")).decode("ascii") + "?="
        #email = "From: <harvest@monperrus.net>\nTo: <martin.monperrus@gmail.com>\nSubject: "+encoded_title+"\n\n" + str(paper)
        ## encode email to base64
        #email = base64.urlsafe_b64encode(email.encode("utf-8")).decode("utf-8")
        ## create a new email
        ## Label_4447645605958895953 is label for harvest.py
        #self.service.users().messages().insert(userId='me', body={
            #'raw': 
                #email, "labelIds":['UNREAD', "Label_4447645605958895953", categories["readinglist - "+category]["labelId"]]}).execute()
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

def path_on_disk_internal(papertitle):
    """ returns the local file name corresponding to a paper """
    # remove trailing space and trailing dots from paper.desc
    papertitle = papertitle.strip().rstrip(".").replace("  "," ")
    return "/home/martin/workspace/scholar-harvest/cache/"+hashlib.sha256(papertitle.encode("utf-8")).hexdigest()+".json"
def path_on_disk(paper):
    return path_on_disk_internal(paper.desc)
def already_seen(paper):
    fname= path_on_disk(paper)
    return os.path.exists(fname)
def record_paper_as_seen(paper, **kwargs):
    fname= path_on_disk(paper)
    # with open(fname,"w") as f: f.write(paper.desc) # we stop the naive version
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
    
    
    paper.origin = origin
    
    category = compute_category(paper)
    paper.category = category 

    paper.detection_date = detection_date.isoformat()
    
    save_paper_and_notify_email(paper, service)
    return True

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
    if "arxiv.org" in url:    
        ## https://www.monperrus.net/martin/arxiv-json.py?id=2304.12015
        semanticscholarid="url:"+url.replace("/html/","/pdf/")
        components = [x for x in url.split("/") if len(x)>0]
        arxiv_id = components[-1]
        # https://www.monperrus.net/martin/arxiv-json.py?id=2409.18952v1
        arxiv_metadata = requests.get("https://www.monperrus.net/martin/arxiv-json.py?id="+arxiv_id).json()
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
        print("TODO implement DOI and chain for DBLP")
    if "dl.acm.org" in url:
        components = [x for x in url.split("/") if len(x)>0]
        doi = components[-2]+"/"+components[-1]
        # no api for acm
        # see https://stackoverflow.com/questions/33380715/acm-digital-library-access-with-r-no-api-so-how-possible
        # alternative 1: go through crossref
        # alternative 2: there is the bibtex export which actually returns json
        r = requests.post('https://dl.acm.org/action/exportCiteProcCitation', data={
            'dois': doi,
            'format': 'bibTex',
            'targetFile': 'custom-bibtex',
        }).json()
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
        ieeeid = [x for x in url.split("/") if len(x)>0][-1]
        # curl "https://ieeexploreapi.ieee.org/api/v1/search/articles?apiKey=XXXXXX&article_number=10833642"
        ieeedata = requests.get("https://ieeexploreapi.ieee.org/api/v1/search/articles?article_number="+ieeeid+"&apiKey="+config.ieeexplore_key).json()
        if "error" not in ieeedata and "articles" in ieeedata and "doi" in ieeedata["articles"][0]:
            doi = ieeedata["articles"][0]["doi"]
            venue_title = ieeedata["articles"][0]["publication_title"]
            abstract = ieeedata["articles"][0]["abstract"]
            # semanticscholarid="doi:"+doi
        else: print("no data in ieee "+json.dumps(ieeedata, indent=2))
        
        
    # ok we can ask semanticscholarid for tldr
    if semanticscholarid!="" and ( \
        "arxiv.org" in url or "semanticscholar.org" in url or doi!=None)  \
    :
        if semanticscholarid == "" and doi:
            semanticscholarid="doi:"+doi
        #print(semanticscholarid)
        semanticscholar = requests.get("https://api.semanticscholar.org/graph/v1/paper/"+semanticscholarid+"?fields=title,tldr,authors", headers = {"x-api-key": config.semanticscholar_key}).json()
        #print(semanticscholar)
        if semanticscholar!=None and "paperId" in semanticscholar:
            # replacing "url:https://arxiv.org/pdf/2409.18317" by real paper if for the reader URL below
            semanticscholarid = semanticscholar["paperId"]
        if semanticscholar!=None and "tldr" in semanticscholar and semanticscholar["tldr"] != None and semanticscholar["tldr"]["text"]:
            tldr=semanticscholar["tldr"]["text"]+"\n\n"
        if semanticscholar!=None and "authors" in semanticscholar:           
            authors = ", ".join([x["name"] for x in semanticscholar["authors"]])
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
        except: pass
    
    return {
        "url":url,
        "title":title,
        "semanticscholarid":semanticscholarid,
        "abstract":abstract,
        "tldr": tldr,
        "authors": authors,
        "venue_title" : venue_title,
        "doi" : doi
    }

def save_paper_and_notify_email(paper, service):
    # create an email body with the paper
    encoded_title = "=?utf-8?B?" + base64.b64encode(paper.desc.encode("utf-8")).decode("ascii") + "?="
    email = "From: <harvest@monperrus.net>\nTo: <martin.monperrus@gmail.com>\nSubject: "+encoded_title+"\n\n" + str(paper)

    if paper.venue_title and paper.venue_title != "":
        email += ""+paper.venue_title+"\n"
    
    if paper.tldr and paper.tldr != "":
        email += "\ntldr: "+paper.tldr
    
    if paper.abstract and paper.abstract != "":
        email += "\nabstract: "+paper.abstract+"\n"

    if paper.authors != "":
        email += "\nauthors:"+paper.authors+"\n"

    if paper.reader_url and paper.reader_url != "":
        email += paper.reader_url+"\n"

    email += "\n\ncategory: "+paper.category
    email += "\nreason: "+paper.print_reason()+"\n"
    
    if paper.origin != "":
        email += "origin: "+paper.origin+"\n"
        
    # test of closest papers
    email += "\n\nclosest papers:\n"+rrs.search_in_pinecone_str(paper.desc)

    # create a new email
    # Label_4447645605958895953 is label for harvest.py
    recorded = service.users().messages().insert(userId='me', body={
        'raw': 
            base64.urlsafe_b64encode(email.encode("utf-8")).decode("utf-8"), "labelIds":['UNREAD', "Label_4447645605958895953", categories["readinglist - "+paper.category]["labelId"]]}).execute()
    recorded = service.users().messages().get(userId='me', id=recorded["id"], format='metadata', metadataHeaders=['Message-Id']).execute()
    rfc822msgid = recorded["payload"]["headers"][0]['value']
    
    # test of sending emails, it works
    # if "webassembly" in paper.desc.lower():
    #     # send email to some collaborators
    #     res = service.users().messages().send(userId='me', body={
    #         'raw': base64.urlsafe_b64encode(email.replace('<martin.monperrus@gmail.com>','<monperrus@kth.se>,<xppcoder@gmail.com>,<benoit.baudry@umontreal.ca>').encode("utf-8")).decode("utf-8")
    #         }).execute()
    
    # print(res)

    #print("unique_id", unique_id)
    print("saving", paper.desc, paper.category)
    record_paper_as_seen(paper, unique_id = rfc822msgid)

def get_labelId(category):
    if category=="planetse": return "Label_816000980291680327"
    return categories["readinglist - "+category]["labelId"]

def classify(reason_txt):
    return classify_internal(reason_txt)[1]

def classify_internal(reason_txt):
    reason_txt = reason_txt.lower()
    
    DATA = {
 'Program Repair': ['repair',
                    'fix',
                    'patch',
                    'bug',
                    'debug',
                    'sequencer',
                    'overfitting',
                    'vulnerability' # vivi
                    ],
'Chains': [ 'supply chain',
            'protection',
            'integrity',
            'package',
            'librar',
            'dependenc',
            'password',
            'breaking',
            'sbom',
            'github action',
            'bill',
            'build',
            ' go ',
            'golang',
            'uncompromise',
            'incompatib'],
 'Smart contracts': ['blokchain',
                     'smart contract',
                     'bitcoin',
                     'ethereum',
                     'dapp',
                     'solidity',
                     'evm',
                     'empirical review of automated analysis tools',
                     'enter the hydra',
                     'gigahorse',
                     'exploit generation',
                     'flash loan',
                     'stablecoin',
                     'framework for smart',
                     'nft',
                     'fungible',
                     'wallet','governance','decentralized autonomous organization'],
 'LLM on code': ['incoder',
                 'codet5',
                 'learning performance-improving',
                 'neural code',
                 'model of code',
                 'trained on code',
                 'models of code',
                 'models for code',
                 'octopack',
                 'llm',
                 'code llama',
                 'codellama',
                 'code-llama',
                 'models of source code',
                 'neural',
                 'unsupervised translation of programming languages'],
 'Testing': ['test', 'metamorphic','oracle'],
 # 'Diversity': [],
 'Fake': ['fake', 'decoy', 'honeypot'],
 'LLM general': ['toolformer',
                 'jigsaw',
                 'langchain',
                 'talm'],
 'Reliability': ['divers', 'chaos', 'n-version', 'antifrag', 'heal'],
 'WebAssembly': ['webassembly', 'wasm']}
 
    for THEME,j in DATA.items():
      for pattern in j:
        if pattern in reason_txt: 
            return pattern,THEME
    
    
    #if     'repair' in reason_txt \
        #or 'bug' in reason_txt \
        #or 'patch' in reason_txt\
        #or 'sequencer' in reason_txt\
        #or 'overfitting' in reason_txt\
        #or 'debug' in reason_txt\
            #:
        #return "Program Repair"
    
    
    
    #if     'bitcoin' in reason_txt \
        #or 'ethereum' in reason_txt\
        #or 'smart contract' in reason_txt \
        #or 'empirical review of automated analysis tools' in reason_txt \
        #or 'evm' in reason_txt \
        #or 'enter the hydra' in reason_txt \
        #or 'gigahorse' in reason_txt \
        #or "dynamic exploit generation" in reason_txt\
        #or 'flash loan' in reason_txt\
        #or "stablecoin" in reason_txt \
        #or 'dapp' in reason_txt\
        #or 'solidity' in reason_txt\
        #or 'framework for smart' in reason_txt\
        #or 'nft' in reason_txt\
        #or 'fungible' in reason_txt\
        #or 'wallet' in reason_txt\
    #:
        #return "Smart contracts"
    
    #if     'incoder' in reason_txt \
        #or 'codet5' in reason_txt \
        #or "learning performance-improving" in reason_txt \
        #or "neural code" in reason_txt \
        #or "model of code" in reason_txt \
        #or "trained on code" in reason_txt \
        #or "models of code" in reason_txt \
        #or "models for code" in reason_txt \
        #or "octopack" in reason_txt \
        #or "models of source code" in reason_txt \
        #or "unsupervised translation of programming languages" in reason_txt:
        #return "LLM on code"
    
    
    #if     'toolformer' in reason_txt \
        #or 'jigsaw' in reason_txt \
        #or 'langchain' in reason_txt \
        #or 'code llama' in reason_txt \
        #or 'codellama' in reason_txt \
        #or 'code-llama' in reason_txt \
        #or 'talm' in reason_txt:
        #return "LLM general"
    
    #if 'supply chain' in reason_txt \
        #or 'uncompromise' in reason_txt\
        #or 'protection' in reason_txt\
        #or 'integrity' in reason_txt\
        #or 'package' in reason_txt\
        #or 'librar' in reason_txt\
        #or 'dependenc' in reason_txt\
        #or 'password' in reason_txt\
        #or 'breaking' in reason_txt\
        #or 'sbom' in reason_txt\
        #or 'github action' in reason_txt\
        #or 'bill' in reason_txt\
        #or 'build' in reason_txt\
        #or ' go ' in reason_txt\
        #or 'golang' in reason_txt\
        #or 'incompatib' in reason_txt\
            #:
        #return "Chains"
    #if     'chaos' in reason_txt \
        #or 'n-version' in reason_txt \
        #or 'antifrag' in reason_txt \
        #or 'heal' in reason_txt \
    #:
        #return "Reliability"
    #if     'fake' in reason_txt \
        #or 'decoy' in reason_txt \
        #or 'honey' in reason_txt \
    #:
        #return "Fake"
    #if 'diversi' in reason_txt \
    #:
        #return "Diversity"
    #if   'test' in reason_txt \
      #or 'metamorphic' in reason_txt \
    #:
        #return "Testing"

    #if   'webassembly' in reason_txt \
      #or 'wasm' in reason_txt \
    #:
        #return "WebAssembly"

    return "none", "uncategorized"


def increment_integer_in_file(file_path):
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


def compute_category(paper, title = False):
    """
      categorize from field reason (eg citing), then from title, according to function classify_internal
    """

    reason_txt = paper.print_reason()
    if title: reason_txt = paper.desc.lower()
    
    pattern, classification = classify_internal(reason_txt)
    increment_integer_in_file(pattern)
    
    if classification != "uncategorized": return classification

    # last chance with the title
    if not title: return compute_category(paper, title = True)

    # must be last
    if reason_txt.startswith("author:"): return "colleagues"

    return "uncategorized"


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
        # X-RSS-URL seems to be added by r2e, nice
        url = [h['value'] for h in payload['headers'] if h['name']=='X-RSS-URL'][0]
        
        # avoid duplicate
        paper = Paper(url, subj)
        #if already_seen(paper): continue
        
        # classification = compute_category(paper)
        pattern, classification = classify_internal(paper.desc.lower())
        paper.reason = "title match "+pattern
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
                if "?" in link: link = link.split("?")[0]
                paper = Paper(link, i.text.strip())
                paper.reason = "semanticscholar recommendation"
                if create_harvest_email_paper(paper, service, origin="semanticscholar", detection_date=msg_date):
                    #print("semanticscholar:", i.text)
                    pass
        service.users().messages().trash(userId='me', id=m['id']).execute()



if __name__ == '__main__':
    main()
