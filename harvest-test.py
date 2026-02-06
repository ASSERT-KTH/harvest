#!/usr/bin/env python3
# test for harvest

from harvest import *
import pytest
import sys


# test collect_paper_data_from_url
def test_collect_paper_data_from_url():
    url = "https://arxiv.org/abs/2301.00001"
    paper_data = collect_paper_data_from_url(url)
    # {'url': 'https://arxiv.org/abs/2301.00001', 'title': 'NFTrig', 'semanticscholarid': '0092ce9c83a4c033fa69a6225f8a542566915006', 'abstract': '  NFTrig is a web-based application created for use as an educational tool to teach trigonometry and block chain technology. Creation of the application includes front and back end development as well as integration with other outside sources including MetaMask and OpenSea. The primary development languages include HTML, CSS (Bootstrap 5), and JavaScript as well as Solidity for smart contract creation. The application itself is hosted on Moralis utilizing their Web3 API. This technical report describes how the application was created, what the application requires, and smart contract design with security considerations in mind. The NFTrig application has underwent significant testing and validation prior to and after deployment. Future suggestions and recommendations for further development, maintenance, and use in other fields for education are also described.', 'tldr': 'How the NFTrig application was created, what the application requires, and smart contract design with security considerations in mind are described, and future suggestions and recommendations for further development, maintenance, and use in other fields for education are described.\n\n', 'authors': 'J. Thompson, Ryan Benac, Kidus Olana, Talha Hassan, Andrew Sward, Tauheed Khan Mohd', 'venue_title': '', 'doi': None, 'note': 'related:\n- Enhancing Non-Fungible Tokens for the Evolution of Blockchain Technology\n- Major vulnerabilities in Ethereum smart contracts: Investigation and statistical analysis\n- Flow-Based Programming, 2nd Edition: A New Approach to Application Development\n- Java Cookbook\n- Smart contracts: security patterns in the ethereum ecosystem and solidity'}

    # Assert that paper_data is a dictionary with the expected keys
    assert isinstance(paper_data, dict)
    
    # Assert specific values
    assert paper_data['url'] == url.replace("/abs/", "/pdf/")
    assert paper_data['title'] == 'NFTrig'
    assert 'NFTrig is a web-based application' in paper_data['abstract']
    assert paper_data['authors'] == 'Thompson, Jordan, Benac, Ryan, Olana, Kidus, Hassan, Talha, Sward, Andrew, Mohd, Tauheed Khan'

# get_zotero_translator_service_url(url)
def test_get_zotero_translator_service_url():
    url = "https://arxiv.org/abs/2301.00001"
    paper_data = get_zotero_translator_service_url(url)
    # [{'key': 'BM7BVF3M', 'version': 0, 'itemType': 'preprint', 'creators': [{'firstName': 'Jordan', 'lastName': 'Thompson', 'creatorType': 'author'}, {'firstName': 'Ryan', 'lastName': 'Benac', 'creatorType': 'author'}, {'firstName': 'Kidus', 'lastName': 'Olana', 'creatorType': 'author'}, {'firstName': 'Talha', 'lastName': 'Hassan', 'creatorType': 'author'}, {'firstName': 'Andrew', 'lastName': 'Sward', 'creatorType': 'author'}, {'firstName': 'Tauheed Khan', 'lastName': 'Mohd', 'creatorType': 'author'}], 'tags': [{'tag': 'Computer Science - Human-Computer Interaction', 'type': 1}], 'title': 'NFTrig', 'date': '2022-12-21', 'abstractNote': 'NFTrig is a web-based application created for use as an educational tool to teach trigonometry and block chain technology. Creation of the application includes front and back end development as well as integration with other outside sources including MetaMask and OpenSea. The primary development languages include HTML, CSS (Bootstrap 5), and JavaScript as well as Solidity for smart contract creation. The application itself is hosted on Moralis utilizing their Web3 API. This technical report describes how the application was created, what the application requires, and smart contract design with security considerations in mind. The NFTrig application has underwent significant testing and validation prior to and after deployment. Future suggestions and recommendations for further development, maintenance, and use in other fields for education are also described.', 'url': 'http://arxiv.org/abs/2301.00001', 'extra': 'arXiv:2301.00001', 'repository': 'arXiv', 'archiveID': 'arXiv:2301.00001', 'DOI': '10.48550/arXiv.2301.00001', 'libraryCatalog': 'arXiv.org', 'accessDate': '2025-05-27T11:37:18Z'}]

    # Assert that paper_data is not None and has expected structure
    assert paper_data is not None
    assert isinstance(paper_data, (dict, list))


    after_transfo = transform_zotero_to_output(paper_data)
    assert after_transfo['url'] == url
    assert after_transfo['title'] == 'NFTrig'
    assert 'NFTrig is a web-based application' in after_transfo['abstract']
    assert after_transfo['authors'] == 'J. Thompson, Ryan Benac, Kidus Olana, Talha Hassan, Andrew Sward, Tauheed Khan Mohd'


def test_collect_paper_data_from_url_arxiv():
    """Test collect_paper_data_from_url with arXiv URL"""
    url = "https://arxiv.org/abs/2301.00001"
    paper_data = collect_paper_data_from_url(url)
    
    # Assert that paper_data is a dictionary with the expected keys
    assert isinstance(paper_data, dict)
    assert paper_data['url'] == url.replace("/abs/", "/pdf/")
    assert paper_data['title'] == 'NFTrig'
    assert 'NFTrig is a web-based application' in paper_data['abstract']
    assert paper_data['authors'] == 'Thompson, Jordan, Benac, Ryan, Olana, Kidus, Hassan, Talha, Sward, Andrew, Mohd, Tauheed Khan'


def test_collect_paper_data_from_url_sciencedirect():
    """Test collect_paper_data_from_url with ScienceDirect URL"""
    url = "https://www.sciencedirect.com/science/article/pii/S0950584924002593"
    paper_data = collect_paper_data_from_url(url)
    
    # Assert basic structure
    assert isinstance(paper_data, dict)
    assert paper_data['url'] == url
    assert paper_data['venue_title'] == 'Information and Software Technology'
    assert paper_data['doi'] == '10.1016/j.infsof.2024.107654'
    assert paper_data['semanticscholarid'] == ''
    assert paper_data['tldr'] == ''
    expected_authors = 'Qian, Zhongsheng, Yu, Qingyuan, Zhu, Hui, Liu, Jinping, Fu, Tingfeng'
    actual_authors = paper_data['authors']
    assert actual_authors == expected_authors, f"Expected authors '{expected_authors}', but got '{actual_authors}'"


def test_collect_paper_data_from_url_acm():
    """Test collect_paper_data_from_url with ACM URL"""
    url = "https://dl.acm.org/doi/abs/10.1145/3708474"
    paper_data = collect_paper_data_from_url(url)
    # print(paper_data)
    
    # Assert basic structure
    assert isinstance(paper_data, dict)
    assert paper_data['url'] == "https://dl.acm.org/doi/10.1145/3708474"
    assert paper_data['authors'] == 'Yinan Chen, Yuan Huang, Xiangping Chen, Zibin Zheng'
    assert paper_data['venue_title'] == 'ACM Transactions on Software Engineering and Methodology (3)'
    assert paper_data['doi'] == '10.1145/3708474'
    assert paper_data['semanticscholarid'] == ''
    assert paper_data['tldr'] == ''


def test_get_zotero_translator_service_url():
    """Test get_zotero_translator_service_url function"""
    url = "https://arxiv.org/abs/2301.00001"
    paper_data = get_zotero_translator_service_url(url)
    
    # Assert that paper_data is not None and has expected structure
    assert paper_data is not None
    assert isinstance(paper_data, (dict, list))

    after_transfo = transform_zotero_to_output(paper_data)
    assert after_transfo['url'] == url
    assert after_transfo['title'] == 'NFTrig'
    assert 'NFTrig is a web-based application' in after_transfo['abstract']
    assert after_transfo['authors'] == 'J. Thompson, Ryan Benac, Kidus Olana, Talha Hassan, Andrew Sward, Tauheed Khan Mohd'

def test_collect_paper_data_from_doi():
    """Test collect_paper_data_from_url with ACM DOI URL"""
    url = "https://doi.org/10.1145/3597503.3623337"
    paper_data = collect_paper_data_from_url(url)
    
    # Assert basic structure
    assert isinstance(paper_data, dict)
    # assert paper_data['url'] == url
    assert paper_data['title'] == 'ITER: Iterative Neural Repair for Multi-Location Patches'
    assert paper_data['authors'] == 'He Ye, Martin Monperrus'
    assert paper_data['venue_title'] == "ICSE '24: IEEE/ACM 46th International Conference on Software Engineering"
    assert paper_data['doi'] == '10.1145/3597503.3623337'
    assert paper_data['year'] == 2024
    assert paper_data['semanticscholarid'] == ''
    assert paper_data['abstract'] == ''
    assert paper_data['tldr'] == ''

def test_collect_paper_data_from_ieee():
    """Test collect_paper_data_from_url with IEEE URL"""
    url = "https://ieeexplore.ieee.org/document/10638563/"
    paper_data = collect_paper_data_from_url(url)
    # Assert that paper_data is a dictionary with the expected keys
    assert isinstance(paper_data, dict)
    assert paper_data['url'] == 'https://ieeexplore.ieee.org/document/10638563/'
    assert paper_data['title'] == '230,439 Test Failures Later: An Empirical Evaluation of Flaky Failure Classifiers'
    assert paper_data['semanticscholarid'] == ''
    assert "Flaky tests are tests that can non-deterministically pass or fail" in paper_data['abstract']
    assert paper_data['tldr'] == ''
    assert paper_data['authors'] == 'Abdulrahman Alshammari, Paul Ammann, Michael Hilton, Jonathan Bell'
    assert paper_data['venue_title'] == '2024 IEEE Conference on Software Testing, Verification and Validation (ICST)'
    assert paper_data['doi'] == '10.1109/ICST60714.2024.00031'
    assert paper_data['note'] is None


def test_collect_paper_data_from_dblp():
    """Test collect_paper_data_from_url with DBLP URL"""
    url = "https://dblp.org/rec/conf/icst/AlshammariAHB24"
    paper_data = collect_paper_data_from_url(url)
    
    # Assert that paper_data is a dictionary with the expected keys
    assert isinstance(paper_data, dict)
    assert paper_data['url'] == 'https://ieeexplore.ieee.org/document/10638563/'
    assert paper_data['title'] == '230,439 Test Failures Later: An Empirical Evaluation of Flaky Failure Classifiers'
    assert paper_data['semanticscholarid'] == ''
    assert "Flaky tests are tests that can non-deterministically pass or fail" in paper_data['abstract']
    assert paper_data['tldr'] == ''
    assert paper_data['authors'] == 'Abdulrahman Alshammari, Paul Ammann, Michael Hilton, Jonathan Bell'
    assert paper_data['venue_title'] == '2024 IEEE Conference on Software Testing, Verification and Validation (ICST)'
    assert paper_data['doi'] == '10.1109/ICST60714.2024.00031'
    assert paper_data['note'] is None

def test_collect_paper_data_from_semanticscholar():
    url = "https://www.semanticscholar.org/paper/FERRARI%3A-FailurE-RepRoduction-through-automatic-and-Pontillo-Vandercammen/3ddf90c3a970ea14a7532bf9cc63682fd31d1d47"
    paper_data = collect_paper_data_from_url(url)
    
    # Assert that paper_data is a dictionary with the expected keys
    assert isinstance(paper_data, dict)
    # {'url': 'https://www.semanticscholar.org/paper/FERRARI%3A-FailurE-RepRoduction-through-automatic-and-Pontillo-Vandercammen/3ddf90c3a970ea14a7532bf9cc63682fd31d1d47', 'title': 'FERRARI: FailurE RepRoduction through automatic test cAse generation and stack tRace analysIs', 'semanticscholarid': '3ddf90c3a970ea14a7532bf9cc63682fd31d1d47', 'abstract': '', 'tldr': 'FERRARI is an extension of RESTler that automates the mapping of stack traces to generate targeted test cases for failure reproduction, and introduces a novel similarity scoring mechanism to quantify how closely the behavior of generated test cases matches the conditions of the initial failure, enabling efficient reproduction and diagnosis.\n\n', 'authors': 'Valeria Pontillo, Maarten Vandercammen, Sarah Verbelen, Coen De Roover', 'venue_title': '', 'doi': None, 'note': ''}

    assert paper_data['url'] == 'https://www.semanticscholar.org/paper/FERRARI%3A-FailurE-RepRoduction-through-automatic-and-Pontillo-Vandercammen/3ddf90c3a970ea14a7532bf9cc63682fd31d1d47'
    assert paper_data['title'] == 'FERRARI: FailurE RepRoduction through automatic test cAse generation and stack tRace analysIs'
    assert paper_data['semanticscholarid'] == '3ddf90c3a970ea14a7532bf9cc63682fd31d1d47'

    assert paper_data['authors'] == 'Valeria Pontillo, Maarten Vandercammen, Sarah Verbelen, Coen De Roover'

    
def test_collect_paper_data_from_mdpi():
    """
     pytest harvest-test.py -k 'test_collect_paper_data_from_mdpi'
    """
    pass
    paper_data = collect_paper_data_from_url("https://www.mdpi.com/2624-6511/8/4/118")
    # {'url': 'https://www.mdpi.com/2624-6511/8/4/118', 'title': 'Generative AI-Driven Smart Contract Optimization for Secure and Scalable Smart City Services', 'semanticscholarid': '', 'abstract': 'Smart cities use advanced infrastructure and technology to improve the quality of life for their citizens. Collaborative services in smart cities are making the smart city ecosystem more reliable. These services are required to enhance the operation of interoperable systems, such as smart transportation services that share their data with smart safety services to execute emergency response, surveillance, and criminal prevention measures. However, an important issue in this ecosystem is data security, which involves the protection of sensitive data exchange during the interoperability of heterogeneous smart services. Researchers have addressed these issues through blockchain integration and the implementation of smart contracts, where collaborative applications can enhance both the efficiency and security of the smart city ecosystem. Despite these facts, complexity is an issue in smart contracts since complex coding associated with their deployment might influence the performance and scalability of collaborative applications in interconnected systems. These challenges underscore the need to optimize smart contract code to ensure efficient and scalable solutions in the smart city ecosystem. In this article, we propose a new framework that integrates generative AI with blockchain in order to eliminate the limitations of smart contracts. We make use of models such as GPT-2, GPT-3, and GPT4, which natively can write and optimize code in an efficient manner and support multiple programming languages, including Python 3.12.x and Solidity. To validate our proposed framework, we integrate these models with already existing frameworks for collaborative smart services to optimize smart contract code, reducing resource-intensive processes while maintaining security and efficiency. Our findings demonstrate that GPT-4-based optimized smart contracts outperform other optimized and non-optimized approaches. This integration reduces smart contract execution overhead, enhances security, and improves scalability, paving the way for a more robust and efficient smart contract ecosystem in smart city applications.', 'tldr': '', 'authors': 'Sameer Misbah, Muhammad Farrukh Shahid, Shahbaz Siddiqui, Tariq Jamil S. Khanzada, Rehab Bahaaddin Ashari, Zahid Ullah, Mona Jamjoom', 'venue_title': 'Smart Cities', 'doi': '10.3390/smartcities8040118', 'note': None}
    
    # Assert that paper_data is a dictionary with the expected keys
    assert isinstance(paper_data, dict)
    assert paper_data['title'] == 'Generative AI-Driven Smart Contract Optimization for Secure and Scalable Smart City Services'
    assert 'Smart cities use advanced infrastructure' in paper_data['abstract']
    assert paper_data['authors'] == 'Sameer Misbah, Muhammad Farrukh Shahid, Shahbaz Siddiqui, Tariq Jamil S. Khanzada, Rehab Bahaaddin Ashari, Zahid Ullah, Mona Jamjoom'
    assert paper_data['venue_title'] == 'Smart Cities'
    assert paper_data['doi'] == '10.3390/smartcities8040118'



def test_collect_paper_data_from_aclanthology():
    """Test collect_paper_data_from_url with ACL Anthology URL"""
    url = "https://aclanthology.org/2020.acl-main.1/"
    paper_data = collect_paper_data_from_url(url)
    
    # Assert basic structure
    assert isinstance(paper_data, dict)
    assert paper_data['url'] == "https://aclanthology.org/2020.acl-main.1/"
    assert paper_data['title'] == 'Learning to Understand Child-directed and Adult-directed Speech'
    assert paper_data['authors'] == 'Lieke Gelderloos, Grzegorz Chrupała, Afra Alishahi'
    assert paper_data['author_list'] == ['Lieke Gelderloos', 'Grzegorz Chrupała', 'Afra Alishahi']
    assert paper_data['venue_title'] == 'Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics'
    assert paper_data['doi'] == '10.18653/v1/2020.acl-main.1'
    assert paper_data['year'] == 2020
    assert "Speech directed to children differs from adult-directed speech" in paper_data['abstract']

def main():
    test_collect_paper_data_from_aclanthology()
    test_collect_paper_data_from_ieee()
    test_collect_paper_data_from_semanticscholar()
    test_collect_paper_data_from_dblp()
    test_collect_paper_data_from_url_arxiv()
    test_collect_paper_data_from_url_sciencedirect()
    test_collect_paper_data_from_url_acm()
    test_get_zotero_translator_service_url()
    test_collect_paper_data_from_url()
    test_get_zotero_translator_service_url()
    test_collect_paper_data_from_doi()

    print("All tests passed!")

if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
