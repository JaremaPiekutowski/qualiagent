"""LangGraph state for the analysis main path."""

from typing import TypedDict

from qualiagent.schemas import CoverageVerdict, DraftCitation, DraftSection, RetrievedChunk


class AgentState(TypedDict):
    """State carried through plan → retrieve → coverage → write → verify."""

    study_id: str
    analysis_run_id: str
    research_questions: list[str]
    current_question_idx: int

    subqueries: list[str]
    retrieved: dict[str, list[RetrievedChunk]]
    coverage: CoverageVerdict | None
    coverage_note: str
    missing_dimensions: list[str]
    respondents_covered: int
    respondents_total: int
    retrieval_attempts: int

    web_enabled: bool
    web_results: list[dict[str, object]]

    draft: str
    citations: list[DraftCitation]
    verification_failures: list[str]
    verify_attempts: int

    sections: list[DraftSection]
    report_path: str
