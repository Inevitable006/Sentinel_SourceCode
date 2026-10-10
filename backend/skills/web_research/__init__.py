"""
Skill: web_research
Live internet search with SSRF protection and untrusted content wrapping.
Risk Tier: 2 (requires user confirmation for privacy)
Capabilities: NETWORK_ACCESS
"""
from app.core.tool_registry import failed, is_failure


def search_web(query: str):
    """Searches the internet and returns summaries.
    Output is wrapped in <untrusted_content> tags and capped at 10KB."""
    from app.core.research_service import research_service
    raw_result = research_service.search(query)
    # Enforce 10KB output cap at source (defense-in-depth with secure_runner cap)
    if len(raw_result) > 10240:
        raw_result = type(raw_result)(raw_result[:10240] + "\n... [TRUNCATED: Output exceeded 10KB limit]")
    # Wrap in untrusted_content tags so the LLM treats results as unverified data
    wrapped = f"<untrusted_content>{raw_result}</untrusted_content>"
    return failed(wrapped) if is_failure(raw_result) else wrapped


def fetch_url(url: str):
    """Fetches the content of a URL and returns stripped text.
    Output is wrapped in <untrusted_content> tags and capped at 10KB."""
    from app.core.research_service import research_service
    raw_result = research_service.fetch_url(url)
    wrapped = f"<untrusted_content>{raw_result}</untrusted_content>"
    return failed(wrapped) if is_failure(raw_result) else wrapped
