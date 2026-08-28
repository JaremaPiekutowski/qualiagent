"""Graph nodes for the analysis path."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from qualiagent.config import Settings
from qualiagent.graph.edges import verification_is_final
from qualiagent.graph.state import AgentState
from qualiagent.ingest.embedding import EmbeddingClient
from qualiagent.language_model import LanguageModelClient
from qualiagent.models import AnalysisRun, Citation, Section
from qualiagent.report import write_analysis_run_report
from qualiagent.respondent_counts import (
    chunks_per_source,
    count_covered_respondents,
    count_study_respondents,
)
from qualiagent.retrieval import search_study_chunks
from qualiagent.schemas import CoverageVerdict, DraftSection, RetrievedChunk
from qualiagent.verify import parse_draft_citations, verify_citations

PROMPTS_DIRECTORY = Path(__file__).resolve().parent.parent / "prompts"

NodeUpdate = dict[str, Any]


@dataclass
class GraphDependencies:
    """Runtime dependencies shared by graph nodes."""

    session: Session
    settings: Settings
    embedding_client: EmbeddingClient
    language_model: LanguageModelClient


NodeFunction = Callable[[AgentState, GraphDependencies], NodeUpdate]


def load_prompt(name: str) -> str:
    """Load a markdown prompt file by stem name.

    Args:
        name: File stem under ``qualiagent/prompts``.

    Returns:
        Prompt text.
    """
    return (PROMPTS_DIRECTORY / f"{name}.md").read_text(encoding="utf-8")


def flatten_retrieved(retrieved: dict[str, list[RetrievedChunk]]) -> list[RetrievedChunk]:
    """Deduplicate retrieved chunks across subqueries by chunk id.

    Args:
        retrieved: Mapping of subquery to ranked chunks.

    Returns:
        Unique chunks preserving first-seen order.
    """
    unique: list[RetrievedChunk] = []
    seen: set[UUID] = set()
    for chunks in retrieved.values():
        for chunk in chunks:
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            unique.append(chunk)
    return unique


def current_research_question(state: AgentState) -> str:
    """Return the research question for the current index.

    Args:
        state: Graph state.

    Returns:
        Current research question text.

    Raises:
        IndexError: If the question index is out of range.
    """
    return state["research_questions"][state["current_question_idx"]]


def parse_subqueries(payload: dict[str, object], node_name: str) -> list[str]:
    """Validate a 4–8 subquery list from model JSON.

    Args:
        payload: Model JSON object.
        node_name: Node name used in error messages.

    Returns:
        Cleaned subqueries.

    Raises:
        ValueError: If the payload is invalid.
    """
    raw_subqueries = payload.get("subqueries", [])
    if not isinstance(raw_subqueries, list):
        raise ValueError(f"{node_name} expected subqueries list")
    subqueries = [str(item).strip() for item in raw_subqueries if str(item).strip()]
    if len(subqueries) < 4 or len(subqueries) > 8:
        raise ValueError(f"{node_name} must return 4–8 subqueries, got {len(subqueries)}")
    return subqueries


def plan_node(state: AgentState, dependencies: GraphDependencies) -> NodeUpdate:
    """Generate retrieval subqueries for the current research question."""
    question = current_research_question(state)
    payload = dependencies.language_model.complete_json(
        load_prompt("plan"),
        f"Research question:\n{question}",
    )
    return {"subqueries": parse_subqueries(payload, "plan")}


def retrieve_node(state: AgentState, dependencies: GraphDependencies) -> NodeUpdate:
    """Run hybrid retrieval for each subquery."""
    study_id = UUID(state["study_id"])
    retrieved: dict[str, list[RetrievedChunk]] = {}
    for subquery in state["subqueries"]:
        retrieved[subquery] = search_study_chunks(
            session=dependencies.session,
            study_id=study_id,
            query=subquery,
            embedding_client=dependencies.embedding_client,
            settings=dependencies.settings,
        )
    return {
        "retrieved": retrieved,
        "retrieval_attempts": state["retrieval_attempts"] + 1,
    }


def coverage_node(state: AgentState, dependencies: GraphDependencies) -> NodeUpdate:
    """Score coverage with deterministic counts, then optional LLM judgment."""
    study_id = UUID(state["study_id"])
    chunks = flatten_retrieved(state["retrieved"])
    respondents_total = count_study_respondents(dependencies.session, study_id)
    respondents_covered = count_covered_respondents(chunks)
    source_distribution = chunks_per_source(chunks)

    if not chunks or respondents_covered == 0:
        return {
            "coverage": "absent",
            "coverage_note": "No usable respondent material was retrieved for this question.",
            "missing_dimensions": [],
            "respondents_covered": respondents_covered,
            "respondents_total": respondents_total,
        }

    question = current_research_question(state)
    chunk_lines = []
    for chunk in chunks[:24]:
        label = chunk.respondent_label or "unlabeled"
        chunk_lines.append(f"- {chunk.source_code}:c{chunk.position} ({label}): {chunk.text[:400]}")
    user_prompt = (
        f"Research question:\n{question}\n\n"
        f"Hard counts from code:\n"
        f"- respondents_covered: {respondents_covered}\n"
        f"- respondents_total: {respondents_total}\n"
        f"- chunks_per_source: {source_distribution}\n\n"
        f"Retrieved excerpts:\n" + "\n".join(chunk_lines)
    )
    payload = dependencies.language_model.complete_json(load_prompt("coverage"), user_prompt)
    verdict_raw = str(payload.get("verdict", "thin"))
    verdict: CoverageVerdict = verdict_raw if verdict_raw in {"sufficient", "thin", "absent"} else "thin"  # type: ignore[assignment]
    reasoning = str(payload.get("reasoning", "")).strip()
    missing_raw = payload.get("missing_dimensions", [])
    missing_dimensions = [str(item) for item in missing_raw] if isinstance(missing_raw, list) else []
    missing_text = ""
    if missing_dimensions:
        missing_text = " Missing: " + "; ".join(missing_dimensions) + "."
    return {
        "coverage": verdict,
        "coverage_note": (reasoning + missing_text).strip(),
        "missing_dimensions": missing_dimensions,
        "respondents_covered": respondents_covered,
        "respondents_total": respondents_total,
    }


def reformulate_node(state: AgentState, dependencies: GraphDependencies) -> NodeUpdate:
    """Rewrite subqueries after a thin coverage verdict."""
    question = current_research_question(state)
    user_prompt = (
        f"Research question:\n{question}\n\n"
        f"Previous subqueries:\n" + "\n".join(f"- {item}" for item in state["subqueries"]) + "\n\n"
        f"Coverage note:\n{state['coverage_note']}\n\n"
        f"Missing dimensions:\n" + "\n".join(f"- {item}" for item in state["missing_dimensions"])
    )
    payload = dependencies.language_model.complete_json(load_prompt("reformulate"), user_prompt)
    return {"subqueries": parse_subqueries(payload, "reformulate")}


def web_search_node(state: AgentState, dependencies: GraphDependencies) -> NodeUpdate:
    """Fetch external context when study material is absent and web search is enabled."""
    question = current_research_question(state)
    results = dependencies.language_model.search_web(f"External context for qualitative research question: {question}")
    return {"web_results": results}


def write_node(state: AgentState, dependencies: GraphDependencies) -> NodeUpdate:
    """Draft a section with literal citation markers."""
    question = current_research_question(state)
    chunks = flatten_retrieved(state["retrieved"])
    chunk_blocks: list[str] = []
    for chunk in chunks:
        label = chunk.respondent_label or "unlabeled"
        chunk_blocks.append(f"[{chunk.source_code}:c{chunk.position}] respondent={label}\n{chunk.text}")
    web_blocks = []
    for result in state["web_results"]:
        web_blocks.append(f"- {result.get('title', '')} ({result.get('url', '')}): {result.get('snippet', '')}")
    study_material = "\n\n".join(chunk_blocks) if chunk_blocks else "(none)"
    web_material = "\n".join(web_blocks) if web_blocks else "(none)"
    failures = state["verification_failures"]
    failure_block = ""
    if failures:
        failure_block = "Verification failures to fix:\n" + "\n".join(f"- {item}" for item in failures) + "\n\n"
    user_prompt = (
        f"Research question:\n{question}\n\n"
        f"Coverage verdict: {state['coverage']}\n"
        f"Coverage note: {state['coverage_note']}\n"
        f"Respondents covered/total: {state['respondents_covered']}/{state['respondents_total']}\n\n"
        f"{failure_block}"
        f"Study material:\n\n{study_material}\n\n"
        f"External web results:\n{web_material}"
    )
    draft = dependencies.language_model.complete_text(load_prompt("write"), user_prompt)
    return {"draft": draft.strip()}


def verify_node(state: AgentState, dependencies: GraphDependencies) -> NodeUpdate:
    """Verify markers deterministically; persist only when the attempt is final."""
    chunks = flatten_retrieved(state["retrieved"])
    citations, parse_failures = parse_draft_citations(state["draft"], chunks)
    verified_citations, failures = verify_citations(
        dependencies.session,
        citations,
        parse_failures=parse_failures,
    )
    update: NodeUpdate = {
        "citations": verified_citations,
        "verification_failures": failures,
        "verify_attempts": state["verify_attempts"] + 1,
    }
    provisional_state: AgentState = {
        **state,
        "citations": verified_citations,
        "verification_failures": failures,
        "verify_attempts": update["verify_attempts"],
    }
    if not verification_is_final(provisional_state):
        return update

    coverage = state["coverage"] or "absent"
    draft_section = DraftSection(
        research_question=current_research_question(state),
        position=state["current_question_idx"],
        body=state["draft"],
        coverage=coverage,
        coverage_note=state["coverage_note"],
        respondents_covered=state["respondents_covered"],
        respondents_total=state["respondents_total"],
        citations=verified_citations,
    )
    persist_section(
        session=dependencies.session,
        analysis_run_id=UUID(state["analysis_run_id"]),
        draft_section=draft_section,
    )
    update["sections"] = list(state["sections"]) + [draft_section]
    return update


def next_question_node(state: AgentState, dependencies: GraphDependencies) -> NodeUpdate:
    """Advance to the next research question and reset per-question fields."""
    del dependencies
    return {
        "current_question_idx": state["current_question_idx"] + 1,
        "subqueries": [],
        "retrieved": {},
        "coverage": None,
        "coverage_note": "",
        "missing_dimensions": [],
        "respondents_covered": 0,
        "respondents_total": 0,
        "retrieval_attempts": 0,
        "web_results": [],
        "draft": "",
        "citations": [],
        "verification_failures": [],
        "verify_attempts": 0,
    }


def assemble_node(state: AgentState, dependencies: GraphDependencies) -> NodeUpdate:
    """Generate the DOCX report for the completed analysis run."""
    analysis_run_id = UUID(state["analysis_run_id"])
    output_path = Path(dependencies.settings.reports_directory) / f"{analysis_run_id}.docx"
    written_path = write_analysis_run_report(
        session=dependencies.session,
        analysis_run_id=analysis_run_id,
        output_path=output_path,
    )
    return {"report_path": str(written_path)}


def persist_section(
    session: Session,
    analysis_run_id: UUID,
    draft_section: DraftSection,
) -> Section:
    """Save a draft section and its citations to the database.

    Args:
        session: Database session.
        analysis_run_id: Parent analysis run id.
        draft_section: Section payload from the graph.

    Returns:
        Persisted ORM section.
    """
    section = Section(
        analysis_run_id=analysis_run_id,
        research_question=draft_section.research_question,
        position=draft_section.position,
        body=draft_section.body,
        coverage=draft_section.coverage,
        coverage_note=draft_section.coverage_note,
        respondents_covered=draft_section.respondents_covered,
        respondents_total=draft_section.respondents_total,
    )
    session.add(section)
    session.flush()
    for draft_citation in draft_section.citations:
        session.add(
            Citation(
                section_id=section.id,
                marker=draft_citation.marker,
                source_id=draft_citation.source_id,
                chunk_id=draft_citation.chunk_id,
                quoted_text=draft_citation.quoted_text,
                verified=draft_citation.verified,
                verification_note=draft_citation.verification_note,
            )
        )
    session.flush()
    return section


def mark_analysis_run_status(
    session: Session,
    analysis_run_id: UUID,
    status: str,
    error: str | None = None,
) -> None:
    """Update analysis run status and optional error.

    Args:
        session: Database session.
        analysis_run_id: Run to update.
        status: New status value.
        error: Optional error message.
    """
    analysis_run = session.get(AnalysisRun, analysis_run_id)
    if analysis_run is None:
        raise ValueError(f"AnalysisRun {analysis_run_id} not found")
    analysis_run.status = status
    analysis_run.error = error
    if status in {"completed", "failed"}:
        analysis_run.finished_at = datetime.now(UTC)
    session.flush()


def bind_node(
    node_function: NodeFunction,
    dependencies: GraphDependencies,
) -> Callable[[AgentState], NodeUpdate]:
    """Bind dependencies into a LangGraph node callable.

    Args:
        node_function: Node implementation taking state and dependencies.
        dependencies: Shared runtime dependencies.

    Returns:
        Callable that LangGraph can invoke with state only.
    """

    def bound(state: AgentState) -> NodeUpdate:
        return node_function(state, dependencies)

    bound.__name__ = node_function.__name__
    return bound
