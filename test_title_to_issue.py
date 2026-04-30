import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("title-to-issue.py")
SPEC = importlib.util.spec_from_file_location("title_to_issue_script", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


SAMPLE_ISSUES = [
    {
        "number": 83,
        "title": "related work on code editing with LLMs",
        "url": "https://github.com/ASSERT-KTH/related-work/issues/83",
    },
    {
        "number": 60,
        "title": "related work on LLM-based Code Generation",
        "url": "https://github.com/ASSERT-KTH/related-work/issues/60",
    },
    {
        "number": 20,
        "title": "related work on property-based testing for program repair  (papers, tools)",
        "url": "https://github.com/ASSERT-KTH/related-work/issues/20",
    },
    {
        "number": 15,
        "title": "related work on smart contract exploit generation / proof of concept / PoCo",
        "url": "https://github.com/ASSERT-KTH/related-work/issues/15",
    },
    {
        "number": 49,
        "title": "related work on LLM and smart contracts (incl. generation)",
        "url": "https://github.com/ASSERT-KTH/related-work/issues/49",
    },
]


def test_llm_code_editing_title_maps_to_code_editing_issue():
    matches = MODULE.match_title_to_issues(
        "EditBench: Evaluating Large Language Models for Code Editing",
        SAMPLE_ISSUES,
    )

    assert matches[0].number == 83
    assert matches[0].keywords == ("code", "code_editing", "edit", "llm")
    assert len(matches) <= 2


def test_program_repair_property_based_testing_maps_to_issue_20():
    matches = MODULE.match_title_to_issues(
        "Property-Based Testing for Neural Program Repair",
        SAMPLE_ISSUES,
    )

    assert matches[0].number == 20
    assert "program_repair" in matches[0].keywords
    assert "property_based_testing" in matches[0].keywords


def test_smart_contract_poc_title_prefers_exploit_generation_issue():
    matches = MODULE.match_title_to_issues(
        "Large Language Models for Smart Contract Proof-of-Concept Generation",
        SAMPLE_ISSUES,
    )

    assert matches[0].number == 15
    assert len(matches) <= 2
    assert all(match.number in {15, 49, 60, 83, 20} for match in matches)
