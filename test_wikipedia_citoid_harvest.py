import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("wikipedia-citoid-harvest.py")
SPEC = importlib.util.spec_from_file_location("wikipedia_citoid_harvest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

PATH_SCRIPT = shutil.which("wikipedia-citoid.py")

PUBLISHER_CASES = [
    ("nature", "10.1038/171737a0"),
    ("elsevier", "10.1016/j.infsof.2024.107654"),
    ("mdpi", "10.3390/smartcities8040118"),
    ("ieee", "10.1109/5.771073"),
    ("wiley", "10.1002/smj.4250140909"),
    ("springer", "10.1007/BF00127314"),
]


def parse_citation_fields(text):
    fields = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "=" not in stripped:
            continue
        name, value = stripped[1:].split("=", 1)
        fields[name.strip()] = value.strip()
    return fields


def extract_author_fields(fields):
    authors = []
    index = 1
    while True:
        last_name = fields.get(f"last{index}")
        first_name = fields.get(f"first{index}")
        full_name = fields.get(f"author{index}")
        if last_name is None and first_name is None and full_name is None:
            break
        if full_name is not None:
            authors.append(("author", full_name))
        else:
            authors.append(("author", first_name, last_name))
        index += 1
    return authors


def run_script(command, doi):
    completed = subprocess.run(
        command + [doi],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return completed.stdout


def test_format_citoid_as_mediawiki_journal():
    record = {
        "itemType": "journalArticle",
        "creators": [
            {
                "firstName": "J. D.",
                "lastName": "Watson",
                "creatorType": "author",
            },
            {
                "firstName": "F. H. C.",
                "lastName": "Crick",
                "creatorType": "author",
            },
        ],
        "publicationTitle": "Nature",
        "volume": "171",
        "issue": "4356",
        "language": "en",
        "ISSN": "0028-0836, 1476-4687",
        "date": "1953-04-25",
        "pages": "737–738",
        "DOI": "10.1038/171737a0",
        "url": "https://www.nature.com/articles/171737a0",
        "title": "Molecular Structure of Nucleic Acids: A Structure for Deoxyribose Nucleic Acid",
        "accessDate": "2026-04-21",
    }

    rendered = MODULE.format_citoid_as_mediawiki(
        record,
        quote="Example quote from the landing page.",
    )

    assert rendered == "\n".join(
        [
            "{{cite journal",
            " |last1= Watson",
            " |first1= J. D.",
            " |last2= Crick",
            " |first2= F. H. C.",
            " |title= Molecular Structure of Nucleic Acids: A Structure for Deoxyribose Nucleic Acid",
            " |journal= Nature",
            " |date= 1953-04",
            " |volume= 171",
            " |issue= 4356",
            " |pages= 737–738",
            " |url= https://www.nature.com/articles/171737a0",
            " |access-date= 2026-04-21",
            " |language= en",
            " |quote= Example quote from the landing page.",
            " |doi= 10.1038/171737a0",
            " |issn= 1476-4687",
            "}}",
        ]
    )


def test_pick_issn_prefers_last_value():
    assert MODULE.pick_issn(["0028-0836", "1476-4687"]) == "1476-4687"
    assert MODULE.pick_issn("0028-0836, 1476-4687") == "1476-4687"


def test_normalize_date_strips_day_precision():
    assert MODULE.normalize_date("1953-04-25") == "1953-04"
    assert MODULE.normalize_date("1953-04") == "1953-04"


@pytest.mark.skipif(PATH_SCRIPT is None, reason="wikipedia-citoid.py not found in PATH")
@pytest.mark.parametrize(("publisher", "doi"), PUBLISHER_CASES)
def test_back_to_back_citoid_publishers_match(publisher, doi):
    path_output = run_script([PATH_SCRIPT], doi)
    local_output = run_script([sys.executable, str(MODULE_PATH)], doi)

    path_fields = parse_citation_fields(path_output)
    local_fields = parse_citation_fields(local_output)

    assert extract_author_fields(local_fields) == extract_author_fields(path_fields), (
        f"{publisher} author mismatch\nPATH:\n{path_output}\nLOCAL:\n{local_output}"
    )
    assert local_fields.get("title") == path_fields.get("title"), (
        f"{publisher} title mismatch\nPATH:\n{path_output}\nLOCAL:\n{local_output}"
    )
    assert local_fields.get("journal") == path_fields.get("journal"), (
        f"{publisher} journal mismatch\nPATH:\n{path_output}\nLOCAL:\n{local_output}"
    )
    assert local_fields.get("doi") == path_fields.get("doi"), (
        f"{publisher} doi mismatch\nPATH:\n{path_output}\nLOCAL:\n{local_output}"
    )
