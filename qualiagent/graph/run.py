"""Create an AnalysisRun and execute or resume the analysis graph."""

from collections.abc import Iterator
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from langgraph.types import Command
from sqlalchemy.orm import Session

from qualiagent.config import Settings, get_settings
from qualiagent.graph.build import build_main_path_graph, thread_config
from qualiagent.graph.nodes import GraphDependencies, mark_analysis_run_status
from qualiagent.graph.state import AgentState
from qualiagent.ingest.embedding import EmbeddingClient, VoyageEmbeddingClient
from qualiagent.language_model import AnthropicLanguageModelClient, LanguageModelClient
from qualiagent.models import AnalysisRun, Study

ResumeAction = Literal["approve", "revise"]


def create_analysis_run(session: Session, study_id: UUID) -> AnalysisRun:
    """Insert a new analysis run for a study.

    Args:
        session: Database session.
        study_id: Study being analyzed.

    Returns:
        Persisted analysis run in ``running`` status.
    """
    analysis_run = AnalysisRun(
        study_id=study_id,
        thread_id=str(uuid4()),
        status="running",
    )
    session.add(analysis_run)
    session.flush()
    return analysis_run


def initial_agent_state(
    study: Study,
    analysis_run: AnalysisRun,
    question_index: int = 0,
) -> AgentState:
    """Build the initial graph state for one research question.

    Args:
        study: Study ORM row.
        analysis_run: Analysis run ORM row.
        question_index: Index of the research question to answer.

    Returns:
        Initial ``AgentState``.
    """
    if not study.research_questions:
        raise ValueError("Study has no research questions")
    if question_index < 0 or question_index >= len(study.research_questions):
        raise IndexError(f"question_index {question_index} out of range")
    return {
        "study_id": str(study.id),
        "analysis_run_id": str(analysis_run.id),
        "research_questions": list(study.research_questions),
        "current_question_idx": question_index,
        "subqueries": [],
        "retrieved": {},
        "coverage": None,
        "coverage_note": "",
        "missing_dimensions": [],
        "respondents_covered": 0,
        "respondents_total": 0,
        "retrieval_attempts": 0,
        "web_enabled": study.web_search_enabled,
        "web_results": [],
        "draft": "",
        "citations": [],
        "verification_failures": [],
        "verify_attempts": 0,
        "sections": [],
        "report_path": "",
    }


def build_graph_dependencies(
    session: Session,
    settings: Settings,
    embedding_client: EmbeddingClient | None = None,
    language_model: LanguageModelClient | None = None,
) -> GraphDependencies:
    """Assemble graph dependencies for a run.

    Args:
        session: Database session.
        settings: Application settings.
        embedding_client: Optional embedding override.
        language_model: Optional language-model override.

    Returns:
        Bound graph dependencies.
    """
    return GraphDependencies(
        session=session,
        settings=settings,
        embedding_client=embedding_client or VoyageEmbeddingClient(settings),
        language_model=language_model or AnthropicLanguageModelClient(settings),
    )


def graph_is_interrupted(graph: Any, config: dict[str, dict[str, str]]) -> bool:
    """Return whether the compiled graph is paused before a node.

    Args:
        graph: Compiled LangGraph.
        config: Thread config.

    Returns:
        True when tasks are waiting (HITL interrupt).
    """
    snapshot = graph.get_state(config)
    return bool(snapshot.next)


def apply_run_status_from_graph(
    session: Session,
    analysis_run_id: UUID,
    graph: Any,
    config: dict[str, dict[str, str]],
) -> str:
    """Mark the analysis run completed or awaiting approval from graph state.

    Args:
        session: Database session.
        analysis_run_id: Analysis run id.
        graph: Compiled graph.
        config: Thread config.

    Returns:
        New status string.
    """
    if getattr(graph, "checkpointer", None) is None:
        mark_analysis_run_status(session, analysis_run_id, "completed")
        return "completed"
    if graph_is_interrupted(graph, config):
        mark_analysis_run_status(session, analysis_run_id, "awaiting_approval")
        return "awaiting_approval"
    mark_analysis_run_status(session, analysis_run_id, "completed")
    return "completed"


def stream_graph_updates(
    graph: Any,
    inputs: Any,
    config: dict[str, dict[str, str]],
) -> Iterator[dict[str, Any]]:
    """Yield node-update events from a graph stream.

    Args:
        graph: Compiled LangGraph.
        inputs: Initial state, ``None`` to resume, or a ``Command``.
        config: Thread config.

    Yields:
        Event dicts with ``node`` and ``update`` keys.
    """
    for chunk in graph.stream(inputs, config=config, stream_mode="updates"):
        if not isinstance(chunk, dict):
            continue
        for node_name, update in chunk.items():
            yield {"node": node_name, "update": update}


def run_main_path(
    session: Session,
    study_id: UUID,
    question_index: int = 0,
    settings: Settings | None = None,
    embedding_client: EmbeddingClient | None = None,
    language_model: LanguageModelClient | None = None,
    checkpointer: Any | None = None,
) -> AgentState:
    """Run the analysis graph for research questions starting at ``question_index``.

    Creates a new ``AnalysisRun``, executes the graph through all remaining questions
    (or until a HITL interrupt), and updates run status. Does not commit the session.

    Args:
        session: Database session.
        study_id: Study to analyze.
        question_index: Research question index.
        settings: Optional settings override.
        embedding_client: Optional embedding client override.
        language_model: Optional language model override.
        checkpointer: Optional checkpointer; required when interrupts are enabled.

    Returns:
        Graph state after invoke (may be interrupted before write).
    """
    resolved_settings = settings or get_settings()
    study = session.get(Study, study_id)
    if study is None:
        raise ValueError(f"Study {study_id} not found")

    analysis_run = create_analysis_run(session, study_id)
    dependencies = build_graph_dependencies(
        session=session,
        settings=resolved_settings,
        embedding_client=embedding_client,
        language_model=language_model,
    )
    graph = build_main_path_graph(
        dependencies,
        checkpointer=checkpointer,
        interrupt_before_write=resolved_settings.interrupt_before_write,
    )
    state = initial_agent_state(study, analysis_run, question_index=question_index)
    config = thread_config(analysis_run.thread_id)
    try:
        final_state = cast(AgentState, graph.invoke(state, config=config))
        apply_run_status_from_graph(session, analysis_run.id, graph, config)
        return final_state
    except Exception as error:
        mark_analysis_run_status(session, analysis_run.id, "failed", error=str(error))
        raise


def resume_analysis_run(
    session: Session,
    analysis_run: AnalysisRun,
    action: ResumeAction = "approve",
    subqueries: list[str] | None = None,
    settings: Settings | None = None,
    embedding_client: EmbeddingClient | None = None,
    language_model: LanguageModelClient | None = None,
    checkpointer: Any | None = None,
) -> AgentState:
    """Resume an interrupted analysis run.

    Args:
        session: Database session.
        analysis_run: Existing run in ``awaiting_approval``.
        action: ``approve`` continues to write; ``revise`` re-runs retrieve.
        subqueries: Required when ``action='revise'``.
        settings: Optional settings override.
        embedding_client: Optional embedding client override.
        language_model: Optional language model override.
        checkpointer: Checkpointer that holds the thread state.

    Returns:
        Graph state after resume.
    """
    if checkpointer is None:
        raise ValueError("checkpointer is required to resume an analysis run")
    resolved_settings = settings or get_settings()
    dependencies = build_graph_dependencies(
        session=session,
        settings=resolved_settings,
        embedding_client=embedding_client,
        language_model=language_model,
    )
    graph = build_main_path_graph(
        dependencies,
        checkpointer=checkpointer,
        interrupt_before_write=True,
    )
    config = thread_config(analysis_run.thread_id)
    mark_analysis_run_status(session, analysis_run.id, "running")
    try:
        if action == "revise":
            if not subqueries:
                raise ValueError("subqueries are required when revising")
            payload: Any = Command(update={"subqueries": subqueries}, goto="retrieve")
        else:
            payload = None
        final_state = cast(AgentState, graph.invoke(payload, config=config))
        apply_run_status_from_graph(session, analysis_run.id, graph, config)
        return final_state
    except Exception as error:
        mark_analysis_run_status(session, analysis_run.id, "failed", error=str(error))
        raise
