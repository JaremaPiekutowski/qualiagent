"""Stub language model for deterministic graph tests."""

import re


class StubLanguageModelClient:
    """Returns canned plan, coverage, write, and web-search responses."""

    def __init__(
        self,
        subqueries: list[str] | None = None,
        reformulated_subqueries: list[str] | None = None,
        coverage_verdict: str = "sufficient",
        coverage_verdicts: list[str] | None = None,
        coverage_reasoning: str = "Several respondents speak to the question.",
        missing_dimensions: list[str] | None = None,
        draft_quote: str | None = None,
        draft_marker: str | None = None,
        invalid_first_write: bool = False,
        web_results: list[dict[str, object]] | None = None,
    ) -> None:
        """Create a stub client.

        Args:
            subqueries: Fixed plan subqueries.
            reformulated_subqueries: Subqueries returned by reformulate.
            coverage_verdict: Default coverage verdict when no sequence is set.
            coverage_verdicts: Optional sequence of coverage verdicts (consumed in order).
            coverage_reasoning: Fixed coverage reasoning.
            missing_dimensions: Dimensions returned with thin coverage.
            draft_quote: Literal quote used in the write stub.
            draft_marker: Marker paired with ``draft_quote``.
            invalid_first_write: If true, first write uses a fake quote that fails verify.
            web_results: Fixed web search results.
        """
        self.subqueries = subqueries or [
            "co mówią wprost o zmianie",
            "jakie metafory pojawiają się przy zmianie",
            "kiedy temat wychodzi sam",
            "kto mówi inaczej niż większość",
        ]
        self.reformulated_subqueries = reformulated_subqueries or [
            "co było trudne przy wdrożeniu zmiany",
            "jakiego wsparcia brakowało",
            "kiedy zmiana pojawia się w rozmowie sama",
            "kto ocenia zmianę pozytywnie",
        ]
        self.coverage_verdicts = list(coverage_verdicts) if coverage_verdicts is not None else None
        self.coverage_verdict = coverage_verdict
        self.coverage_reasoning = coverage_reasoning
        self.missing_dimensions = missing_dimensions or ["głosy odmienne"]
        self.draft_quote = draft_quote
        self.draft_marker = draft_marker
        self.invalid_first_write = invalid_first_write
        self.write_calls = 0
        self.reformulate_calls = 0
        self.web_results = web_results or [
            {
                "title": "Change management overview",
                "url": "https://example.com/change",
                "snippet": "Public guidance on organizational change.",
            }
        ]

    def complete_json(self, system: str, user: str) -> dict[str, object]:
        """Return plan, reformulate, or coverage JSON based on the system prompt.

        Args:
            system: System prompt text.
            user: User prompt text.

        Returns:
            Parsed JSON object.
        """
        del user
        lowered = system.lower()
        if "reformulate" in lowered:
            self.reformulate_calls += 1
            return {"subqueries": list(self.reformulated_subqueries)}
        if "subqueries" in lowered or "plan node" in lowered:
            return {"subqueries": list(self.subqueries)}
        verdict = self.coverage_verdict
        if self.coverage_verdicts is not None:
            if self.coverage_verdicts:
                verdict = self.coverage_verdicts.pop(0)
            else:
                verdict = "sufficient"
        return {
            "verdict": verdict,
            "reasoning": self.coverage_reasoning,
            "missing_dimensions": list(self.missing_dimensions),
        }

    def complete_text(self, system: str, user: str) -> str:
        """Return a draft that cites a literal quote when material exists.

        Args:
            system: System prompt text.
            user: User prompt text containing material blocks.

        Returns:
            Draft section text.
        """
        del system
        self.write_calls += 1
        try:
            quote, marker = self._resolve_quote_and_marker(user)
        except ValueError:
            web_section = ""
            if "https://" in user or "example.com" in user:
                web_section = "\n\nKontekst zewnętrzny\nPublic sources discuss organizational change in general terms."
            return f"Brak materiału badawczego w źródłach badania.{web_section}"

        if self.invalid_first_write and self.write_calls == 1:
            return f'Tekst z błędnym cytatem: "TO NIE JEST CYTAT Z CHUNKA" {marker}'

        return (
            "Respondenci opisują zmianę jako odgórną. "
            f'Jeden z nich mówi: "{quote}" {marker} '
            "Głosy różnią się co do oceny wsparcia."
        )

    def search_web(self, query: str) -> list[dict[str, object]]:
        """Return canned web search results.

        Args:
            query: Search query.

        Returns:
            Fixed web result dictionaries.
        """
        del query
        return [dict(item) for item in self.web_results]

    def _resolve_quote_and_marker(self, user_prompt: str) -> tuple[str, str]:
        """Pick a quote/marker from config or the first material block.

        Args:
            user_prompt: Write-node user prompt.

        Returns:
            Quote substring and matching marker.

        Raises:
            ValueError: If the prompt has no material blocks and no fixed quote.
        """
        if self.draft_quote is not None and self.draft_marker is not None:
            return self.draft_quote, self.draft_marker
        return self.first_quote_and_marker(user_prompt)

    def first_quote_and_marker(self, user_prompt: str) -> tuple[str, str]:
        """Pick the first material block from the write prompt.

        Args:
            user_prompt: Write-node user prompt.

        Returns:
            Quote substring and matching marker.

        Raises:
            ValueError: If the prompt has no material blocks.
        """
        pattern = re.compile(
            r"\[(?P<code>S\d+):c(?P<position>\d+)\]\s+respondent=[^\n]+\n(?P<body>.+?)(?:\n\n|$)",
            re.DOTALL,
        )
        match = pattern.search(user_prompt)
        if match is None:
            raise ValueError("Write prompt contained no material blocks")
        body = " ".join(match.group("body").split())
        quote = body[: min(48, len(body))].strip()
        marker = f"[{match.group('code')}:c{match.group('position')}]"
        return quote, marker
