import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("wikipedia-citoid-harvest.py")
SPEC = importlib.util.spec_from_file_location("wikipedia_citoid_harvest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


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
