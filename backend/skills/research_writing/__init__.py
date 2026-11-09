"""Local writing briefs and mechanical review; no fetching, saving or fact verification."""
import json
import re
from collections import Counter

from app.core.tool_registry import failed

OUTLINES = {
    "report": ("Question and scope", "Findings with numbered citations", "Conflicting evidence and limitations", "Conclusion and next steps"),
    "article": ("Opening and main point", "Evidence and examples with numbered citations", "Counterpoint and limitations", "Closing takeaway"),
    "email": ("Subject", "Purpose", "Supporting details", "Requested action and timing"),
}
REFERENCE = re.compile(r"^\s*\[([1-9][0-9]{0,5})\]:\s*(.*)$")
CITATION = re.compile(r"\[([1-9][0-9]{0,5})\]")


def prepare_writing_brief(topic: str, audience: str = "general reader",
                          purpose: str = "explain the topic", format: str = "report") -> str:
    values = (topic, audience, purpose)
    if any(not isinstance(v, str) or not v.strip() or len(v) > 500 for v in values):
        return failed("Error: topic, audience and purpose must each contain 1–500 characters.")
    if not isinstance(format, str) or format not in OUTLINES:
        return failed("Error: choose report, article or email.")
    sections = "\n\n".join(f"## {section}\n[TODO: draft this section]" for section in OUTLINES[format])
    return (
        f"# Writing brief\nTopic: {topic.strip()}\nAudience: {audience.strip()}\nPurpose: {purpose.strip()}\n\n"
        "Planning scaffold only; evidence has not been collected.\n\n"
        f"{sections}\n\n## Sources\n"
        "Use [1] next to a supported claim and define it on its own line as:\n"
        "[1]: Source title — URL or local document/page — date consulted\n"
        "Replace this example with actual sources before review.\n\n"
        "Before finalizing: collect evidence with the existing search/document tools; "
        "read each cited passage; distinguish facts from inference; check dates, quotations "
        "and conflicting evidence. Save in Workspace Documents or through approved file actions. "
        "Email output remains a draft."
    )


def review_writing(text: str, word_limit: int = 0) -> str:
    """Check plain text with [n] citations and single-line [n]: source definitions."""
    if not isinstance(text, str) or not text.strip() or len(text) > 60000:
        return failed("Error: provide a draft of 1–60,000 characters; split larger drafts into sections.")
    if isinstance(word_limit, bool) or not isinstance(word_limit, int) or not 0 <= word_limit <= 10000:
        return failed("Error: word_limit must be an integer from 0 (no limit) to 10,000.")
    definitions, empty, body = Counter(), set(), []
    for line in text.splitlines():
        match = REFERENCE.fullmatch(line)
        if match:
            number, source = int(match[1]), match[2].strip()
            definitions[number] += 1
            if not source:
                empty.add(number)
        else:
            body.append(line)
    prose = "\n".join(body)
    used = {int(n) for n in CITATION.findall(prose)}
    words = len(re.findall(r"\b\w+(?:['’-]\w+)*\b", CITATION.sub("", prose)))
    placeholders = Counter(m.group().upper() for m in re.finditer(r"\b(?:TODO|TBD|FIXME)\b", text, re.I))

    def ids(numbers):
        ordered = sorted(numbers)
        return {"count": len(ordered), "first_20": ordered[:20]}

    report = {
        "word_count_excluding_reference_definitions": words,
        "word_limit": word_limit or None,
        "words_over_limit": max(0, words - word_limit) if word_limit else 0,
        "possible_placeholders": dict(placeholders),
        "citations": {
            "missing_definitions": ids(used - definitions.keys()),
            "empty_definitions": ids(empty),
            "duplicate_definitions": ids(n for n, count in definitions.items() if count > 1),
            "unused_definitions": ids(definitions.keys() - used),
            "cited_source_count": len(used),
        },
        "notes": [
            "Mechanical checks only; facts, quotations, source existence and support for claims are not verified.",
            "Format: [1] in text and [1]: source title — URL or document/page on its own line. "
            "Only this numbered style is checked; headings count as words. Lists show at most 20 IDs.",
            "Review each cited passage and distinguish evidence from inference before using the draft.",
        ],
    }
    if not used:
        report["notes"].append("No numbered citations found. Decide whether the draft's claims need sources.")
    return json.dumps(report, ensure_ascii=False, indent=2)
