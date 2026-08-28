"""Helpers for analysis run API responses and HITL previews."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qualiagent.graph.state import AgentState
from qualiagent.models import AnalysisRun, Section
from qualiagent.schemas import (
    AnalysisApprovalPreview,
    AnalysisRunDetail,
    RetrievedChunk,
    RetrievedChunkSummary,
)


def preview_from_state(state: AgentState | dict[str, Any]) -> AnalysisApprovalPreview:
    """Build a HITL preview from graph state.

    Args:
        state: Current agent state.

    Returns:
        Preview shown before write.
    """
    questions = list(state["research_questions"])
    index = int(state["current_question_idx"])
    question = questions[index] if 0 <= index < len(questions) else ""
    retrieved_summaries: dict[str, list[RetrievedChunkSummary]] = {}
    retrieved = state.get("retrieved", {})
    for subquery, chunks in retrieved.items():
        summaries: list[RetrievedChunkSummary] = []
        for chunk in chunks:
            model = chunk if isinstance(chunk, RetrievedChunk) else RetrievedChunk.model_validate(chunk)
            summaries.append(
                RetrievedChunkSummary(
                    chunk_id=model.chunk_id,
                    source_code=model.source_code,
                    respondent_label=model.respondent_label,
                    position=model.position,
                    text_preview=model.text[:240],
                    score=model.score,
                )
            )
        retrieved_summaries[str(subquery)] = summaries
    return AnalysisApprovalPreview(
        research_question=question,
        subqueries=list(state.get("subqueries", [])),
        coverage=state.get("coverage"),
        coverage_note=str(state.get("coverage_note", "")),
        respondents_covered=int(state.get("respondents_covered", 0)),
        respondents_total=int(state.get("respondents_total", 0)),
        missing_dimensions=list(state.get("missing_dimensions", [])),
        retrieved=retrieved_summaries,
    )


def section_count_for_run(session: Session, analysis_run_id: UUID) -> int:
    """Count persisted sections for an analysis run.

    Args:
        session: Database session.
        analysis_run_id: Analysis run id.

    Returns:
        Section count.
    """
    return int(
        session.execute(
            select(func.count()).select_from(Section).where(Section.analysis_run_id == analysis_run_id)
        ).scalar_one()
    )


def analysis_run_detail(
    session: Session,
    analysis_run: AnalysisRun,
    state: AgentState | dict[str, Any] | None = None,
) -> AnalysisRunDetail:
    """Serialize an analysis run for the API.

    Args:
        session: Database session.
        analysis_run: ORM run row.
        state: Optional graph state for HITL preview / report path.

    Returns:
        API detail payload.
    """
    preview = None
    report_path = None
    if state is not None:
        if analysis_run.status == "awaiting_approval":
            preview = preview_from_state(state)
        report_path = str(state.get("report_path") or "") or None
    return AnalysisRunDetail(
        id=analysis_run.id,
        study_id=analysis_run.study_id,
        thread_id=analysis_run.thread_id,
        status=analysis_run.status,  # type: ignore[arg-type]
        created_at=analysis_run.created_at,
        finished_at=analysis_run.finished_at,
        error=analysis_run.error,
        section_count=section_count_for_run(session, analysis_run.id),
        report_path=report_path,
        approval_preview=preview,
    )
