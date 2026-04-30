from types import SimpleNamespace

import dl_monperrus_paper
import notify_10_papers_monperrus


def test_format_related_work_recommendation_formats_matches(monkeypatch):
    sample_issues = [{"number": 83, "title": "related work on code editing with LLMs", "url": "https://github.com/ASSERT-KTH/related-work/issues/83"}]
    sample_matches = [
        SimpleNamespace(
            number=83,
            title="related work on code editing with LLMs",
            url="https://github.com/ASSERT-KTH/related-work/issues/83",
        )
    ]

    matcher = SimpleNamespace(
        REPO_URL="https://github.com/ASSERT-KTH/related-work",
        match_title_to_issues=lambda title, issues, limit=2: sample_matches,
    )

    monkeypatch.setattr(dl_monperrus_paper, "get_title_to_issue_module", lambda: matcher)
    monkeypatch.setattr(dl_monperrus_paper, "get_related_work_issues", lambda: sample_issues)

    recommendation = dl_monperrus_paper.format_related_work_recommendation(
        "EditBench: Evaluating Large Language Models for Code Editing"
    )

    assert recommendation == "\n".join(
        [
            "Recommended related-work issue:",
            "- #83 related work on code editing with LLMs",
            "  https://github.com/ASSERT-KTH/related-work/issues/83",
        ]
    )


def test_format_closest_related_work_issue_formats_match(monkeypatch):
    sample_issues = [{"number": 83, "title": "related work on code editing with LLMs", "url": "https://github.com/ASSERT-KTH/related-work/issues/83"}]
    sample_matches = [
        SimpleNamespace(
            number=83,
            title="related work on code editing with LLMs",
            url="https://github.com/ASSERT-KTH/related-work/issues/83",
        )
    ]

    matcher = SimpleNamespace(
        REPO_URL="https://github.com/ASSERT-KTH/related-work",
        match_title_to_issues=lambda title, issues, limit=1: sample_matches,
    )

    monkeypatch.setattr(dl_monperrus_paper, "get_title_to_issue_module", lambda: matcher)
    monkeypatch.setattr(dl_monperrus_paper, "get_related_work_issues", lambda: sample_issues)

    issue_line = dl_monperrus_paper.format_closest_related_work_issue(
        "EditBench: Evaluating Large Language Models for Code Editing"
    )

    assert issue_line == "\n".join(
        [
            "Closest related-work issue: #83 related work on code editing with LLMs",
            "https://github.com/ASSERT-KTH/related-work/issues/83",
        ]
    )


def test_format_ranked_paper_preview_includes_closest_issue(monkeypatch):
    monkeypatch.setattr(
        dl_monperrus_paper,
        "format_closest_related_work_issue",
        lambda title: "Closest related-work issue: #83 related work on code editing with LLMs\nhttps://github.com/ASSERT-KTH/related-work/issues/83",
    )

    preview = dl_monperrus_paper.format_ranked_paper_preview(
        {
            "angle": 12.34,
            "most_similar_to": "RepairBench",
            "data": {
                "title": "EditBench: Evaluating Large Language Models for Code Editing",
                "venue_title": "ICSE",
                "url": "https://example.org/paper",
                "authors": "A. Researcher",
                "tldr": "A benchmark for code editing.",
            },
        },
        1,
    )

    assert "TLDR: A benchmark for code editing." in preview
    assert "Closest related-work issue: #83 related work on code editing with LLMs" in preview
    assert "https://github.com/ASSERT-KTH/related-work/issues/83" in preview
    assert "\nVenue: ICSE" in preview
    assert "\nURL: https://example.org/paper" in preview
    assert "\nAuthors: A. Researcher..." in preview
    assert preview.index("Authors: A. Researcher...") < preview.index("TLDR: A benchmark for code editing.")
    assert preview.index("TLDR: A benchmark for code editing.") < preview.index("Most similar to: RepairBench")


def test_notify_most_related_papers_adds_recommendation_to_note(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        dl_monperrus_paper,
        "list_most_related_papers_to_monperrus_research",
        lambda preview_limit=10: [
            {
                "data": {
                    "title": "EditBench: Evaluating Large Language Models for Code Editing",
                    "url": "https://example.org/paper",
                    "venue_title": "ICSE",
                    "authors": "A. Researcher",
                    "tldr": "A benchmark for code editing.",
                },
                "angle": 12.34,
                "most_similar_to": "RepairBench",
                "filepath": "/tmp/does-not-exist.json",
            }
        ],
    )
    monkeypatch.setattr(
        dl_monperrus_paper,
        "format_related_work_recommendation",
        lambda title: "Recommended related-work issue:\n- #83 related work on code editing with LLMs",
    )
    monkeypatch.setattr(dl_monperrus_paper, "build", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        dl_monperrus_paper,
        "get_creds",
        lambda: SimpleNamespace(authorize=lambda http: None),
    )
    monkeypatch.setattr(dl_monperrus_paper, "Http", lambda: None)

    def fake_notify_email(paper, service):
        captured["note"] = paper.note
        captured["title"] = paper.desc

    monkeypatch.setattr(dl_monperrus_paper, "notify_email", fake_notify_email)

    dl_monperrus_paper.notify_most_related_papers_to_monperrus_research(1)

    assert captured["title"] == "EditBench: Evaluating Large Language Models for Code Editing"
    assert captured["note"].startswith("Recommended related-work issue:")


def test_notify_most_related_papers_does_not_print_send_progress(monkeypatch, capsys):
    monkeypatch.setattr(
        dl_monperrus_paper,
        "list_most_related_papers_to_monperrus_research",
        lambda preview_limit=10: [
            {
                "data": {
                    "title": "EditBench: Evaluating Large Language Models for Code Editing",
                    "url": "https://example.org/paper",
                    "venue_title": "ICSE",
                    "authors": "A. Researcher",
                    "tldr": "A benchmark for code editing.",
                },
                "angle": 12.34,
                "most_similar_to": "RepairBench",
                "filepath": "/tmp/does-not-exist.json",
            }
        ],
    )
    monkeypatch.setattr(
        dl_monperrus_paper,
        "format_related_work_recommendation",
        lambda title: "Recommended related-work issue:\n- #83 related work on code editing with LLMs",
    )
    monkeypatch.setattr(dl_monperrus_paper, "build", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        dl_monperrus_paper,
        "get_creds",
        lambda: SimpleNamespace(authorize=lambda http: None),
    )
    monkeypatch.setattr(dl_monperrus_paper, "Http", lambda: None)
    monkeypatch.setattr(dl_monperrus_paper, "notify_email", lambda paper, service: None)

    dl_monperrus_paper.notify_most_related_papers_to_monperrus_research(1)

    output = capsys.readouterr().out
    assert "Sending email notifications" not in output
    assert "Notifying:" not in output
    assert "Completed sending" not in output


def test_notify_most_related_papers_passes_requested_preview_limit(monkeypatch):
    captured = {}

    def fake_list_most_related_papers_to_monperrus_research(preview_limit=10):
        captured["preview_limit"] = preview_limit
        return []

    monkeypatch.setattr(
        dl_monperrus_paper,
        "list_most_related_papers_to_monperrus_research",
        fake_list_most_related_papers_to_monperrus_research,
    )

    dl_monperrus_paper.notify_most_related_papers_to_monperrus_research(1)

    assert captured["preview_limit"] == 1


def test_notify_wrapper_defaults_to_ten(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        notify_10_papers_monperrus,
        "notify_most_related_papers_to_monperrus_research",
        lambda number: captured.setdefault("number", number),
    )

    notify_10_papers_monperrus.main([])

    assert captured["number"] == 10


def test_notify_wrapper_accepts_number_override(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        notify_10_papers_monperrus,
        "notify_most_related_papers_to_monperrus_research",
        lambda number: captured.setdefault("number", number),
    )

    notify_10_papers_monperrus.main(["--number", "3"])

    assert captured["number"] == 3
