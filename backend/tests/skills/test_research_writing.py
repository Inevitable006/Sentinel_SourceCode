"""Research/writing pack exercised through registered tools and owner approval."""
import json

import pytest

from app.core.secure_runner import secure_runner


@pytest.fixture(autouse=True)
def registered():
    from app.core.skill_router import skill_router
    if "research_writing" not in skill_router._skills:
        from app.core.skill_loader import register_all_skills
        register_all_skills()


def approve(tool, args):
    first = secure_runner.execute(tool, args, "writing", force_confirmation=True)
    assert first["status"] == "needs_confirmation", first
    return secure_runner.execute(tool, args, "writing", token=first["token"])


@pytest.mark.parametrize("format,section", [("report", "Conflicting evidence"),
                                           ("article", "Counterpoint"), ("email", "Subject")])
def test_brief_is_a_scaffold_not_invented_research(format, section):
    result = approve("skill_prepare_writing_brief", {
        "topic": "Urban gardens", "audience": "beginners", "purpose": "explain options", "format": format,
    })
    assert result["status"] == "success"
    assert section in result["data"] and "beginners" in result["data"]
    assert "evidence has not been collected" in result["data"]
    assert "[TODO:" in result["data"] and "Email output remains a draft" in result["data"]


def test_review_reports_actionable_reference_problems():
    result = approve("skill_review_writing", {"text": (
        "A claim [1]. Another [2]. TODO revise now [3].\n"
        "[1]: Field notes, page 2\n[1]: Different notes\n[3]:\n[4]: Unused notes"
    ), "word_limit": 4})
    assert result["status"] == "success"
    review = json.loads(result["data"])
    assert review["word_count_excluding_reference_definitions"] == 6
    assert review["words_over_limit"] == 2
    assert review["possible_placeholders"] == {"TODO": 1}
    for key, number in (("missing_definitions", 2), ("duplicate_definitions", 1),
                        ("empty_definitions", 3), ("unused_definitions", 4)):
        assert review["citations"][key] == {"count": 1, "first_20": [number]}


def test_consistent_references_do_not_claim_factual_verification():
    result = approve("skill_review_writing", {
        "text": "An unsupported claim [1]. Repeated [1].\n[1]: This source may not exist", "word_limit": 5,
    })
    review = json.loads(result["data"])
    assert review["word_count_excluding_reference_definitions"] == 4
    assert review["words_over_limit"] == 0
    assert review["citations"]["missing_definitions"]["count"] == 0
    assert review["citations"]["cited_source_count"] == 1
    assert "not verified" in review["notes"][0]


def test_no_citations_and_placeholder_counts():
    review = json.loads(approve("skill_review_writing", {"text": "TODO todo TBD FIXME"})["data"])
    assert review["possible_placeholders"] == {"TODO": 2, "TBD": 1, "FIXME": 1}
    assert review["word_limit"] is None
    assert any("No numbered citations" in note for note in review["notes"])


def test_many_missing_references_have_bounded_complete_counts():
    text = " ".join(f"[{n}]" for n in range(1, 2001))
    result = approve("skill_review_writing", {"text": text})
    review = json.loads(result["data"])
    assert review["citations"]["missing_definitions"] == {"count": 2000, "first_20": list(range(1, 21))}
    assert len(result["data"]) < 4000


@pytest.mark.parametrize("args", [{"text": ""}, {"text": "x" * 60001},
                                  {"text": "Draft", "word_limit": -1},
                                  {"text": "Draft", "word_limit": True}],
                         ids=["empty", "oversized", "negative-limit", "boolean-limit"])
def test_invalid_drafts_fail_honestly(args):
    assert approve("skill_review_writing", args)["status"] == "error"


@pytest.mark.parametrize("args", [{"topic": " "}, {"topic": "x" * 501},
                                  {"topic": "Gardens", "format": "unknown"}],
                         ids=["empty", "oversized", "unknown-format"])
def test_invalid_briefs_fail_honestly(args):
    assert approve("skill_prepare_writing_brief", args)["status"] == "error"


def test_disabled_pack_blocks_both_tools(monkeypatch):
    from app import workspace_routes
    monkeypatch.setattr(workspace_routes, "skill_enabled", lambda name: name != "research_writing")
    for tool, args in (("skill_review_writing", {"text": "Draft"}),
                       ("skill_prepare_writing_brief", {"topic": "Gardens"})):
        result = secure_runner.execute(tool, args, "writing", force_confirmation=True)
        assert result["status"] == "error"
        assert "turned off" in result["message"].lower()
