"""Compile the analysis graph with conditional loops."""

from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from qualiagent.graph.edges import (
    route_after_coverage,
    route_after_next_question,
    route_after_verify,
)
from qualiagent.graph.nodes import (
    GraphDependencies,
    assemble_node,
    bind_node,
    coverage_node,
    next_question_node,
    plan_node,
    reformulate_node,
    retrieve_node,
    verify_node,
    web_search_node,
    write_node,
)
from qualiagent.graph.state import AgentState


def build_main_path_graph(
    dependencies: GraphDependencies,
    checkpointer: Any | None = None,
    interrupt_before_write: bool | None = None,
) -> Any:
    """Build the analysis graph with reformulate, web search, verify retry, and question loop.

    Args:
        dependencies: Session, settings, embedding client, and language model.
        checkpointer: Optional LangGraph checkpointer for HITL resume.
        interrupt_before_write: Override for pausing before ``write``.

    Returns:
        Compiled LangGraph runnable.
    """
    builder = StateGraph(AgentState)
    # LangGraph's add_node overloads are stricter than our dependency-bound callables.
    builder.add_node("plan", cast(Any, bind_node(plan_node, dependencies)))
    builder.add_node("retrieve", cast(Any, bind_node(retrieve_node, dependencies)))
    builder.add_node("coverage", cast(Any, bind_node(coverage_node, dependencies)))
    builder.add_node("reformulate", cast(Any, bind_node(reformulate_node, dependencies)))
    builder.add_node("web_search", cast(Any, bind_node(web_search_node, dependencies)))
    builder.add_node("write", cast(Any, bind_node(write_node, dependencies)))
    builder.add_node("verify", cast(Any, bind_node(verify_node, dependencies)))
    builder.add_node("next_question", cast(Any, bind_node(next_question_node, dependencies)))
    builder.add_node("assemble", cast(Any, bind_node(assemble_node, dependencies)))

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "retrieve")
    builder.add_edge("retrieve", "coverage")
    builder.add_conditional_edges(
        "coverage",
        route_after_coverage,
        {
            "write": "write",
            "reformulate": "reformulate",
            "web_search": "web_search",
        },
    )
    builder.add_edge("reformulate", "retrieve")
    builder.add_edge("web_search", "write")
    builder.add_edge("write", "verify")
    builder.add_conditional_edges(
        "verify",
        route_after_verify,
        {
            "write": "write",
            "next_question": "next_question",
        },
    )
    builder.add_conditional_edges(
        "next_question",
        route_after_next_question,
        {
            "plan": "plan",
            "assemble": "assemble",
        },
    )
    builder.add_edge("assemble", END)

    compile_kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    enable_interrupt = (
        interrupt_before_write if interrupt_before_write is not None else dependencies.settings.interrupt_before_write
    )
    if enable_interrupt:
        if checkpointer is None:
            raise ValueError("interrupt_before_write requires a checkpointer")
        compile_kwargs["interrupt_before"] = ["write"]
    return builder.compile(**compile_kwargs)


def thread_config(thread_id: str) -> dict[str, dict[str, str]]:
    """Build LangGraph config for a durable thread.

    Args:
        thread_id: Analysis run thread identifier.

    Returns:
        Config dict with ``thread_id``.
    """
    return {"configurable": {"thread_id": thread_id}}
