#!/usr/bin/python
"""
DSpace bitstream URL processor 
- for DSpace 6 and earlier via OAI-PMH
- for DSpace 7+ via REST API.

DSpace is one of the most widely-used open source repository platforms for institutional repositories, particularly in academic and research institutions.
the most current estimate is over 3,000 DSpace instances worldwide
DSpace is written in Java and is open source software released under the BSD license.
"""

import requests
import sys
import urllib.parse
import xml.etree.ElementTree as ET


def process_bitstream_url_dspace_7(download_url):
    # https://vtechworks.lib.vt.edu/bitstreams/28448382-01d3-49e7-a6cb-234274cf2fff/download
    parsed_url = urllib.parse.urlparse(download_url)
    # Ensure the URL is valid and contains a bitstream ID
    if parsed_url.path and len(parsed_url.path.split('/')) > 1:
        # case 1 uuid such as /bitstreams/5202cfc8-8cac-4c59-bb21-c5538f22f828/download
        parsed=parsed_url.path.split('/')
        # print(parsed)
        if "bitstreams" in parsed:
            #  the id is the segment after 'bitstreams'
            bitstream_id = parsed[parsed.index("bitstreams")+1]
        else:
            raise ValueError("Bitstreams segment not found in URL path")    
    else:
        print("Error: Invalid URL or bitstream ID not found.")
        sys.exit(1)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    # Get metadata about the bitstream using DSpace REST API
    # DSpace 7+ uses /api/core/bitstreams/{uuid}
    metadata_url = f"{base_url}/server/api/core/bitstreams/{bitstream_id}"
    # print(f"Fetching DSpace 7+ metadata from: {metadata_url}")
    metadata_response = requests.get(metadata_url, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)

    if metadata_response.status_code == 200:
        metadata = metadata_response.json()
        # print(metadata)
        bundle_link = metadata.get('_links', {}).get('bundle', {}).get('href')
        if bundle_link:
            # print(f"Bundle link: {bundle_link}")
            # Make the request to download the bundle
            if bundle_link:
                # print(f"Downloading bundle from: {bundle_link}")
                bundle_response = requests.get(bundle_link, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)

                if bundle_response.status_code == 200:
                    # print(bundle_response.json())
                    item_link = bundle_response.json().get('_links', {}).get('item', {}).get('href')
                    item_response = requests.get(item_link, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)

                    if item_response.status_code == 200:
                        return item_response.json()
                    else:
                        print(f"Error downloading item: {item_response.status_code}")
                        print(item_response.text)
                else:
                    print(f"Error downloading bundle: {bundle_response.status_code}")
                    print(bundle_response.text)
        else:
            print("Bundle link not found in metadata")
    else:
        print(f"\nDSpace Metadata not available (Status: {metadata_response.status_code})")
        print(metadata_response.text)

def dspace_metadata_to_json(data):
    """
    Convert DSpace 7+ bitstream metadata JSON to a standardized format.

    input: DSpace 7+ bitstream metadata JSON
{'id': '2ccdcb87-b12d-4a1a-bc89-5c748cac93d1', 'uuid': '2ccdcb87-b12d-4a1a-bc89-5c748cac93d1', 'name': 'Adversarial Risks and Stereotype Mitigation at Scale in Generative Models', 'handle': '10919/124828', 'metadata': {'dc.contributor.author': [{'value': 'Jha, Akshita', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.contributor.committeechair': [{'value': 'Reddy, Chandan K.', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.contributor.committeemember': [{'value': 'Prabhakaran, Vinodkumar', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}, {'value': 'Blodgett, Su Lin', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 1}, {'value': 'Wang, Xuan', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 2}, {'value': 'Huang, Lifu', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 3}], 'dc.contributor.department': [{'value': 'Computer Science and#38; Applications', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.date.accessioned': [{'value': '2025-03-08T09:00:11Z', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.date.available': [{'value': '2025-03-08T09:00:11Z', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.date.issued': [{'value': '2025-03-07', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.description.abstract': [{'value': "Generative models have rapidly evolved to produce coherent text, realistic images, and functional code. Yet these remarkable capabilities also expose critical vulnerabilities -- ranging from subtle adversarial attacks to harmful stereotypes -- that pose both technical and societal challenges. This research investigates these challenges across three modalities (code, text, and vision) before focusing on strategies to mitigate biases specifically in generative language models. First, we reveal how programming language (PL) models rely on a `natural channel' of code, such as human-readable tokens and structure, that adversaries can exploit with minimal perturbations. These attacks expose the fragility of state-of-the-art PL models, highlighting how superficial patterns and hidden assumptions in training data can lead to unanticipated vulnerabilities. Extending this analysis to textual and visual domains, we show how over-reliance on patterns seen in training data manifests as ingrained biases and harmful stereotypes. To enable more inclusive and globally representative model evaluations, we introduce SeeGULL, a large-scale benchmark of thousands of stereotypes spanning diverse cultures and identity groups worldwide. We also develop ViSAGe, a benchmark for identifying visual stereotypes at scale in text-to-image (T2I) models, illustrating the persistence of stereotypes in generated images even when prompted otherwise. Building on these findings, we propose two complementary approaches to mitigate stereotypical outputs in language models. The first is an explicit method that uses fairness constraints for model pruning, ensuring essential bias-mitigating features remain intact. The second is an implicit bias mitigation framework that makes a crucial distinction between comprehension failures and inherently learned stereotypes. This approach uses instruction tuning on general-purpose datasets and mitigates stereotypes implicitly without relying on targeted debiasing techniques. Extensive evaluations on state-of-the-art models demonstrate that our methods substantially reduce harmful stereotypes across multiple identity dimensions, while preserving downstream performance.", 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.description.abstractgeneral': [{'value': "AI systems, especially generative models that create text, images, and code, have advanced rapidly. They can write essays, generate realistic pictures, and assist with programming. However, these impressive capabilities also come with vulnerabilities that pose both technical and societal challenges. Some of these models can be subtly manipulated into making errors, while others unknowingly reinforce harmful stereotypes present in their training data. This research examines these challenges across three types of generative models: those that generate code, text, and images. First, we investigate how generative models that generate code rely on human-readable patterns that attackers can subtly manipulate, revealing hidden weaknesses in even the most advanced models. Extending this analysis to text and image generation, we show how these models often over-rely on patterns from their training data, leading to harmful stereotypes. To systematically study these issues, we introduce two large-scale benchmarks: SeeGULL, a dataset that identifies stereotypes across cultures and identity groups in AI-generated text, and ViSAGe, a dataset that uncovers hidden biases in AI-generated images. Building on these insights, we propose two complementary solutions to reduce biases in generative language models.  The first method explicitly removes biased patterns from compressed AI models by introducing filtering techniques that ensure fairness while keeping the model's accuracy intact. The second takes an implicit approach by improving how generative models interpret instructions, making them less likely to generate biased responses in under-informative scenarios. By improving models' general-purpose understanding, this method helps reduce biases without relying on direct debiasing techniques. Our evaluations show that these strategies significantly reduce harmful stereotypes across multiple identity dimensions, making AI systems more fair and reliable while ensuring they remain effective in real-world applications.", 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.description.degree': [{'value': 'Doctor of Philosophy', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.format.medium': [{'value': 'ETD', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.identifier.other': [{'value': 'vt_gsexam:42534', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.identifier.uri': [{'value': 'https://hdl.handle.net/10919/124828', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.language.iso': [{'value': 'en', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.publisher': [{'value': 'Virginia Tech', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.rights': [{'value': 'In Copyright', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.rights.uri': [{'value': 'http://rightsstatements.org/vocab/InC/1.0/', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.subject': [{'value': 'generative models', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}, {'value': 'adversarial attacks', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 1}, {'value': 'bias mitigation', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 2}, {'value': 'stereotype evaluation', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 3}, {'value': 'llm-human collaboration', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 4}, {'value': 'visual stereotypes', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 5}, {'value': 'instruction-tuning', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 6}, {'value': 'cross-cultural bias', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 7}], 'dc.title': [{'value': 'Adversarial Risks and Stereotype Mitigation at Scale in Generative Models', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'dc.type': [{'value': 'Dissertation', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'thesis.degree.discipline': [{'value': 'Computer Science & Applications', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'thesis.degree.grantor': [{'value': 'Virginia Polytechnic Institute and State University', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'thesis.degree.level': [{'value': 'doctoral', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}], 'thesis.degree.name': [{'value': 'Doctor of Philosophy', 'language': 'en', 'authority': None, 'confidence': -1, 'place': 0}]}, 'inArchive': True, 'discoverable': True, 'withdrawn': False, 'lastModified': '2025-03-08T10:01:49.157+00:00', 'entityType': None, 'type': 'item', '_links': {'accessStatus': {'href': 'https://vtechworks.lib.vt.edu/server/api/core/items/2ccdcb87-b12d-4a1a-bc89-5c748cac93d1/accessStatus'}, 'bundles': {'href': 'https://vtechworks.lib.vt.edu/server/api/core/items/2ccdcb87-b12d-4a1a-bc89-5c748cac93d1/bundles'}, 'identifiers': {'href': 'https://vtechworks.lib.vt.edu/server/api/core/items/2ccdcb87-b12d-4a1a-bc89-5c748cac93d1/identifiers'}, 'mappedCollections': {'href': 'https://vtechworks.lib.vt.edu/server/api/core/items/2ccdcb87-b12d-4a1a-bc89-5c748cac93d1/mappedCollections'}, 'owningCollection': {'href': 'https://vtechworks.lib.vt.edu/server/api/core/items/2ccdcb87-b12d-4a1a-bc89-5c748cac93d1/owningCollection'}, 'relationships': {'href': 'https://vtechworks.lib.vt.edu/server/api/core/items/2ccdcb87-b12d-4a1a-bc89-5c748cac93d1/relationships'}, 'version': {'href': 'https://vtechworks.lib.vt.edu/server/api/core/items/2ccdcb87-b12d-4a1a-bc89-5c748cac93d1/version'}, 'templateItemOf': {'href': 'https://vtechworks.lib.vt.edu/server/api/core/items/2ccdcb87-b12d-4a1a-bc89-5c748cac93d1/templateItemOf'}, 'thumbnail': {'href': 'https://vtechworks.lib.vt.edu/server/api/core/items/2ccdcb87-b12d-4a1a-bc89-5c748cac93d1/thumbnail'}, 'self': {'href': 'https://vtechworks.lib.vt.edu/server/api/core/items/2ccdcb87-b12d-4a1a-bc89-5c748cac93d1'}}}


    output: {'url': 'https://orbilu.uni.lu/bitstream/10993/66145/1/thesis.pdf', 'title': None, 'abstract': None, 'tldr': '', 'authors': '', 'authors_list': [], 'venue_title': None, 'doi': None, 'note': None}
    """
    if data == None: return None

    url = None

    # first strategy: look for dc.identifier.uri
    md = data.get("metadata", {}) if isinstance(data, dict) else {}
    cands = md.get("dc.identifier.uri") or md.get("dc.identifier") or []
    if cands:
        first = cands[0]
        if isinstance(first, dict):
            url = first.get("value")
        elif isinstance(first, str):
            url = first
    if not url:
        # second strategy: look for top-level identifier
        ident = data.get("identifier")
        if isinstance(ident, dict):
            url = ident.get("uri")
        elif isinstance(ident, str):
            url = ident
            
    result = {
        "url": url,
        "title": None,
        "abstract": None,
        "tldr": "",
        "authors": "",
        "authors_list": [],
        "venue_title": None,
        "doi": None,
        "note": None,
    }

    metadata = data.get('metadata', {})

    # Extract title
    titles = metadata.get('dc.title', [])
    if titles:
        result['title'] = titles[0].get('value')

    # Extract abstract
    abstracts = metadata.get('dc.description.abstract', [])
    if abstracts:
        result['abstract'] = abstracts[0].get('value')

    # Extract authors
    authors = metadata.get('dc.contributor.author', [])
    authors_list = [author.get('value') for author in authors if author.get('value')]
    result['authors_list'] = authors_list
    result['authors'] = '; '.join(authors_list)

    # Extract publisher as venue
    publishers = metadata.get('dc.publisher', [])
    if publishers:
        result['venue_title'] = publishers[0].get('value')

    # Check if it's a thesis/dissertation and update venue
    types = metadata.get('dc.type', [])
    degree_names = metadata.get('thesis.degree.name', [])
    if types or degree_names:
        doc_type = types[0].get('value') if types else None
        degree = degree_names[0].get('value') if degree_names else None
        if doc_type or degree:
            type_str = degree or doc_type
            if result['venue_title']:
                result['venue_title'] = f"{result['venue_title']} ({type_str})"
            else:
                result['venue_title'] = type_str

    # Extract DOI
    identifiers = metadata.get('dc.identifier', []) + metadata.get('dc.identifier.uri', [])
    for ident in identifiers:
        val = ident.get('value', '')
        if 'doi' in val.lower():
            if 'doi.org/' in val.lower():
                result['doi'] = val.split('doi.org/', 1)[1]
            else:
                result['doi'] = val.replace('doi:', '').strip()
            break

    return result

def process_bitstream_url_oai_pmh(download_url):
    # DSpace bitstream URL
        
    # url = "https://dspace.univ-guelma.dz/jspui/bitstream/123456789/18272/1/F5_8_BOUCENA_AMINA_1752072283.pdf"
    # url = "https://studenttheses.uu.nl/bitstream/handle/20.500.12932/50579/Programmable%20Money%20-%20Pablo.pdf"
    # url = "https://www.doria.fi/bitstream/handle/10024/193115/ibiyo_motunrayo.pdf"

    def extract_components(url):
        import urllib.parse
        parsed_url = urllib.parse.urlparse(url)
        path_parts = parsed_url.path.split('/')
        if len(path_parts) < 3:
            raise ValueError("URL path is too short to extract identifier")
        bitstream_index = path_parts.index('bitstream')

        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        # if bitstream_index != 1:
        #     base_url += '/'.join(path_parts[1:bitstream_index]) + '/'
        base_url +="oai/request"
        # Find 'bitstream' in the path and get the parts after it
        identifier_parts = path_parts[bitstream_index + 1:]
        if 'handle' in identifier_parts:
            handle_index = identifier_parts.index('handle')
            identifier_parts = identifier_parts[handle_index + 1:]
        identifier = f"oai:{parsed_url.netloc}:{'/'.join(identifier_parts[0:2])}"
        return base_url, identifier
        

    try:
        # example
        # base_url = "https://orbilu.uni.lu/oai/request"
        # # Identifier for the record
        # identifier = "oai:orbilu.uni.lu:10993/66145"
        base_url, identifier = extract_components(download_url)

        # print("Base URL:", base_url)
        # print("Identifier:", identifier)
        params = {
            "verb": "GetRecord",
            "metadataPrefix": "oai_dc",    # Dublin Core format
            "identifier": identifier
        }

        # print(f"Fetching OAI-PMH record from {base_url} with identifier {identifier}")
        try:
            resp = requests.get(base_url, params=params, timeout=4)
            resp.raise_for_status()
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.HTTPError) as e:
            return 
        xml = resp.text
        # print(xml)

        # parse XML
        root = ET.fromstring(xml)
        ns = {"oai": "http://www.openarchives.org/OAI/2.0/",
            "dc": "http://purl.org/dc/elements/1.1/"}

        record = root.find(".//oai:record", ns)
        if record is None:
            return None
            raise Exception("No record found")

        return record
    except Exception as e:
        if "<body>" in resp.text.lower() or "<doctype" in resp.text.lower() or "<meta http-equiv" in resp.text.lower():
            print(f"\nSoft 404 on {base_url} (HTTP {resp.status_code})")
            return None

        print(f"Error processing DSpace OAI-PMH URL: {base_url} (HTTP {resp.status_code}) \\{resp.text}")
        resp.text[:200] if resp.text else ""
        raise e


def oai_xml_to_json(data):
    """
    input: <ns0:record xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:ns0="http://www.openarchives.org/OAI/2.0/" xmlns:ns1="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:ns4="http://www.niso.org/schemas/ali/1.0/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><ns0:header><ns0:identifier>oai:orbilu.uni.lu:10993/66145</ns0:identifier><ns0:datestamp>2025-10-27T13:03:07Z</ns0:datestamp><ns0:setSpec>com_f00</ns0:setSpec><ns0:setSpec>col_f03</ns0:setSpec><ns0:setSpec>class_c05</ns0:setSpec></ns0:header><ns0:metadata><ns1:dc xsi:schemaLocation="http://www.niso.org/schemas/ali/1.0/ http://www.niso.org/schemas/ali/1.0/ali.xsd http://www.openarchives.org/OAI/2.0/oai_dc/ http://www.openarchives.org/OAI/2.0/oai_dc.xsd">
<dc:type xml:lang="en">doctoral thesis</dc:type>
<dc:type>http://purl.org/coar/resource_type/c_db06</dc:type>
<dc:type>info:eu-repo/semantics/doctoralThesis</dc:type>
<dc:rights xml:lang="en">open access</dc:rights>
<dc:rights>http://purl.org/coar/access_right/c_abf2</dc:rights>
<dc:rights>info:eu-repo/semantics/openAccess</dc:rights>
<ns4:free_to_read ns4:start_date="2025-10-27" />
<ns4:license_ref>https://orbilu.uni.lu/page/user-license</ns4:license_ref>
<dc:title xml:lang="en">Understanding, Localizing, and Repairing Flakiness in Web Front-End Testing</dc:title>
<dc:creator xml:id="https://orcid.org/0009-0002-3399-0736">PEI, Yu</dc:creator>
<dc:date>2025-10-27</dc:date>
<dc:identifier>https://orbilu.uni.lu/handle/10993/66145</dc:identifier>
<dc:identifier>info:hdl:10993/66145</dc:identifier>
<dc:identifier>https://orbilu.uni.lu/bitstream/10993/66145/1/thesis.pdf</dc:identifier>
<dc:language>en</dc:language>
<dc:subject xml:lang="en">Engineering, computing &amp; technology</dc:subject>
<dc:subject xml:lang="en">Computer science</dc:subject>
<dc:subject xml:lang="fr">Ingénierie, informatique &amp; technologie</dc:subject>
<dc:subject xml:lang="fr">Sciences informatiques</dc:subject>
<dc:publisher>Unilu - University of Luxembourg</dc:publisher>
</ns1:dc></ns0:metadata></ns0:record>

    output: {'url': 'https://orbilu.uni.lu/bitstream/10993/66145/1/thesis.pdf', 'title': None, 'abstract': None, 'tldr': '', 'authors': '', 'authors_list': [], 'venue_title': None, 'doi': None, 'note': None}

    """

    # Accept either an Element or XML string
    if isinstance(data, ET.Element):
        record = data
    else:
        record = ET.fromstring(data)

    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "dc": "http://purl.org/dc/elements/1.1/"
    }

    # If this is a full OAI response, narrow to record element
    if record.tag.endswith("OAI-PMH"):
        r = record.find(".//oai:record", ns)
        if r is not None:
            record = r

    metadata = record.find(".//oai:metadata", ns)
    if metadata is None:
        return {
            "url": None,
            "title": None,
            "abstract": None,
            "tldr": "",
            "authors": "",
            "authors_list": [],
            "venue_title": None,
            "doi": None,
            "note": None,
        }

    dc_root = metadata.find(".//{http://www.openarchives.org/OAI/2.0/oai_dc/}dc")
    if dc_root is None:
        dc_root = metadata.find("dc:dc", ns)

    def elements(name):
        if dc_root is None:
            return []
        return dc_root.findall(f"dc:{name}", ns)

    # Title (prefer lang=en)
    titles = elements("title")
    title = None
    for t in titles:
        if t.get("{http://www.w3.org/XML/1998/namespace}lang") == "en":
            title = t.text
            break
    if title is None and titles:
        title = titles[0].text

    # Abstract (description)
    descriptions = elements("description")
    abstract = None
    for d in descriptions:
        if d.get("{http://www.w3.org/XML/1998/namespace}lang") in (None, "en"):
            if d.text:
                abstract = d.text
                break

    # Creators
    creators = elements("creator")
    authors_list = [c.text.strip() for c in creators if c.text]
    authors = "; ".join(authors_list)

    # Publisher
    publishers = elements("publisher")
    venue_title = publishers[0].text.strip() if publishers and publishers[0].text else None
    types = elements("type")
    if any((t.text or "").strip() == "info:eu-repo/semantics/doctoralThesis" for t in types):
        venue_title = f"{venue_title} (Doctoral thesis)" if venue_title else "Doctoral thesis"

    # Identifiers: find bitstream URL, DOI
    identifiers = elements("identifier")
    url = None
    doi = None
    for ident in identifiers:
        val = (ident.text or "").strip()
        if "/bitstream/" in val and val.startswith("http"):
            url = val
        if "doi" in val.lower():
            # normalize DOI
            if "doi.org/" in val.lower():
                doi = val.split("doi.org/", 1)[1]
            else:
                doi = val.split("doi:", 1)[-1].strip()

    result = {
        "url": url,
        "title": title,
        "abstract": abstract,
        "tldr": "",
        "authors": authors,
        "authors_list": authors_list,
        "venue_title": venue_title,
        "doi": doi,
        "note": None,
    }
    return result


def main_bitstream(download_url):
    try:
        # DSpace bitstream URL DSpace 7+
        if "/bitstreams/" in download_url:
            data = dspace_metadata_to_json(process_bitstream_url_dspace_7(download_url))
            return data

        # DSpace bitstream URL DSpace 6 and earlier via OAI-PMH
        if "/bitstream/" in download_url:
            # python dspace_bitstreams.py https://orbilu.uni.lu/bitstream/10993/66145/1/thesis.pd
            # DSpace bitstream URL DSpace 6 and earlier via OAI-PMH
            oai_data = process_bitstream_url_oai_pmh(download_url)
            if oai_data is None:
                return None
            data = oai_xml_to_json(oai_data)
            return data
    except Exception as e:
        # first message for debugging, second to raise for visibility
        print(f"main_bitstream: Error processing URL: {download_url}")
        raise e

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: dspace_bitstreams.py <dspace_bitstream_url>")
        sys.exit(1)
    download_url = sys.argv[1] if len(sys.argv) > 1 else None
    data = main_bitstream(download_url)
    print(data)
