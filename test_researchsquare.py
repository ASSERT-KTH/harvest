from harvest import collect_paper_data_from_researchsquare


def test_collect_paper_data_from_researchsquare_pdf_url():
    url = "https://www.researchsquare.com/article/rs-7745381/latest.pdf"
    data = collect_paper_data_from_researchsquare(url)
    assert data is not None
    assert data["title"]
    assert data["authors"]
    print("title:", data["title"])
    print("authors:", data["authors"])
    print("year:", data.get("year"))


def test_collect_paper_data_from_researchsquare_article_url():
    url = "https://www.researchsquare.com/article/rs-7745381"
    data = collect_paper_data_from_researchsquare(url)
    assert data is not None
    assert data["title"]


if __name__ == "__main__":
    test_collect_paper_data_from_researchsquare_pdf_url()
    test_collect_paper_data_from_researchsquare_article_url()
    print("all tests passed")
