"""Conditional routing for the analysis graph."""

from typing import Literal

from qualiagent.graph.state import AgentState

MAX_RETRIEVAL_ATTEMPTS = 2
MAX_VERIFY_ATTEMPTS = 2

CoverageRoute = Literal["write", "reformulate", "web_search"]
VerifyRoute = Literal["write", "next_question"]
NextQuestionRoute = Literal["plan", "assemble"]


def route_after_coverage(state: AgentState) -> CoverageRoute:
    """Choose the next node after coverage scoring.

    Args:
        state: Current graph state.

    Returns:
        Target node name.
    """
    coverage = state.get("coverage")
    if coverage == "thin" and state["retrieval_attempts"] < MAX_RETRIEVAL_ATTEMPTS:
        return "reformulate"
    if coverage == "absent" and state["web_enabled"]:
        return "web_search"
    return "write"


def route_after_verify(state: AgentState) -> VerifyRoute:
    """Choose rewrite versus advance after verification.

    Args:
        state: Current graph state.

    Returns:
        Target node name.
    """
    if state["verification_failures"] and state["verify_attempts"] < MAX_VERIFY_ATTEMPTS:
        return "write"
    return "next_question"


def route_after_next_question(state: AgentState) -> NextQuestionRoute:
    """Continue to the next research question or finish the run.

    Args:
        state: Current graph state after advancing the question index.

    Returns:
        Target node name.
    """
    if state["current_question_idx"] < len(state["research_questions"]):
        return "plan"
    return "assemble"


def verification_is_final(state: AgentState) -> bool:
    """Return whether the current verify result should be persisted.

    Args:
        state: Graph state after a verify attempt.

    Returns:
        True when retries are exhausted or verification succeeded.
    """
    if not state["verification_failures"]:
        return True
    return state["verify_attempts"] >= MAX_VERIFY_ATTEMPTS
