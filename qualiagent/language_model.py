"""Injectable language-model clients used by graph nodes."""

import json
import logging
import re
from typing import Protocol, cast

import anthropic

from qualiagent.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LanguageModelClient(Protocol):
    """Interface for text, JSON, and web-search completions."""

    def complete_json(self, system: str, user: str) -> dict[str, object]:
        """Return a JSON object from the model.

        Args:
            system: System prompt.
            user: User prompt.

        Returns:
            Parsed JSON object.
        """
        ...

    def complete_text(self, system: str, user: str) -> str:
        """Return plain text from the model.

        Args:
            system: System prompt.
            user: User prompt.

        Returns:
            Model text response.
        """
        ...

    def search_web(self, query: str) -> list[dict[str, object]]:
        """Search the public web and return structured snippets.

        Args:
            query: Search query.

        Returns:
            Result dicts with title, url, and snippet.
        """
        ...


def extract_json_object(text: str) -> dict[str, object]:
    """Parse a JSON object from model output, tolerating markdown fences.

    Args:
        text: Raw model response.

    Returns:
        Parsed JSON object.

    Raises:
        ValueError: If no JSON object can be parsed.
    """
    stripped = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else stripped
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model response did not contain a JSON object") from None
        parsed = json.loads(candidate[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Model JSON response must be an object")
    return cast(dict[str, object], parsed)


def web_results_from_anthropic_message(content: list[object]) -> list[dict[str, object]]:
    """Extract title/url/snippet dicts from an Anthropic message content list.

    Args:
        content: ``response.content`` blocks from the Anthropic SDK.

    Returns:
        Deduplicated web result dictionaries.
    """
    results: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for block in content:
        block_type = getattr(block, "type", None)
        if block_type == "web_search_tool_result":
            for item in getattr(block, "content", []) or []:
                if getattr(item, "type", None) != "web_search_result":
                    continue
                url = str(getattr(item, "url", "") or "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                results.append(
                    {
                        "title": str(getattr(item, "title", "") or ""),
                        "url": url,
                        "snippet": str(getattr(item, "page_age", "") or ""),
                    }
                )
        if block_type == "text":
            for citation in getattr(block, "citations", None) or []:
                if getattr(citation, "type", None) != "web_search_result_location":
                    continue
                url = str(getattr(citation, "url", "") or "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                results.append(
                    {
                        "title": str(getattr(citation, "title", "") or ""),
                        "url": url,
                        "snippet": str(getattr(citation, "cited_text", "") or ""),
                    }
                )
    return results


class AnthropicLanguageModelClient:
    """Claude client used for plan, coverage, write, and web search."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Create an Anthropic client.

        Args:
            settings: Optional settings override; defaults to env settings.
        """
        self.settings = settings or get_settings()
        if not self.settings.anthropic_api_key:
            raise ValueError("anthropic_api_key is required for AnthropicLanguageModelClient")
        self.client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)

    def complete_json(self, system: str, user: str) -> dict[str, object]:
        """Ask Claude for a JSON object and parse it.

        Args:
            system: System prompt.
            user: User prompt.

        Returns:
            Parsed JSON object.
        """
        text = self.complete_text(system, user)
        return extract_json_object(text)

    def complete_text(self, system: str, user: str) -> str:
        """Ask Claude for a plain-text completion.

        Args:
            system: System prompt.
            user: User prompt.

        Returns:
            Model text response.
        """
        logger.info("Anthropic completion model=%s", self.settings.anthropic_model)
        response = self.client.messages.create(
            model=self.settings.anthropic_model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts: list[str] = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "".join(parts)

    def search_web(self, query: str) -> list[dict[str, object]]:
        """Run Anthropic server-side web search and collect result snippets.

        Args:
            query: Search query.

        Returns:
            Result dicts with title, url, and snippet.
        """
        logger.info("Anthropic web search model=%s", self.settings.anthropic_model)
        response = self.client.messages.create(
            model=self.settings.anthropic_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": query}],
            tools=[
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": self.settings.web_search_max_uses,
                }
            ],
        )
        results = web_results_from_anthropic_message(list(response.content))
        if results:
            return results
        text_parts: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(str(getattr(block, "text", "")))
        summary = " ".join(text_parts).strip()
        if not summary:
            return []
        return [{"title": "Web search summary", "url": "", "snippet": summary}]
