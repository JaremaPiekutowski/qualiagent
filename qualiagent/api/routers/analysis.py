"""Analysis run endpoints: start, list, resume, and SSE progress."""

import json
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from qualiagent.analysis_response import analysis_run_detail
from qualiagent.api.routers.studies import get_study_or_404
from qualiagent.config import Settings, get_settings
from qualiagent.dependencies import get_db, get_embedding_client, get_language_model
from qualiagent.graph.build import build_main_path_graph, thread_config
from qualiagent.graph.checkpointer import open_checkpointer
from qualiagent.graph.nodes import mark_analysis_run_status
from qualiagent.graph.run import (
    apply_run_status_from_graph,
    build_graph_dependencies,
    create_analysis_run,
    graph_is_interrupted,
    initial_agent_state,
    resume_analysis_run,
    stream_graph_updates,
)
from qualiagent.ingest.embedding import EmbeddingClient
from qualiagent.language_model import LanguageModelClient
from qualiagent.models import AnalysisRun as AnalysisRunModel
from qualiagent.schemas import AnalysisEvent, AnalysisResumeRequest, AnalysisRun, AnalysisRunDetail

router = APIRouter(tags=["analysis"])

DatabaseSession = Annotated[Session, Depends(get_db)]
EmbeddingClientDependency = Annotated[EmbeddingClient, Depends(get_embedding_client)]
LanguageModelDependency = Annotated[LanguageModelClient, Depends(get_language_model)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_analysis_run_or_404(session: Session, analysis_run_id: UUID) -> AnalysisRunModel:
    """Load an analysis run or raise 404."""
    analysis_run = session.get(AnalysisRunModel, analysis_run_id)
    if analysis_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")
    return analysis_run


@router.get("/studies/{study_id}/analysis-runs", response_model=list[AnalysisRun])
def list_analysis_runs(study_id: UUID, session: DatabaseSession) -> list[AnalysisRunModel]:
    """List analysis runs for a study, newest first."""
    get_study_or_404(session, study_id)
    return list(
        session.scalars(
            select(AnalysisRunModel)
            .where(AnalysisRunModel.study_id == study_id)
            .order_by(AnalysisRunModel.created_at.desc())
        ).all()
    )


@router.get("/analysis-runs/{analysis_run_id}", response_model=AnalysisRunDetail)
def get_analysis_run(
    analysis_run_id: UUID,
    session: DatabaseSession,
    settings: SettingsDependency,
    embedding_client: EmbeddingClientDependency,
    language_model: LanguageModelDependency,
) -> AnalysisRunDetail:
    """Get one analysis run, including HITL preview when awaiting approval."""
    analysis_run = get_analysis_run_or_404(session, analysis_run_id)
    state = None
    if analysis_run.status == "awaiting_approval":
        with open_checkpointer(settings) as checkpointer:
            dependencies = build_graph_dependencies(session, settings, embedding_client, language_model)
            graph = build_main_path_graph(dependencies, checkpointer=checkpointer, interrupt_before_write=True)
            snapshot = graph.get_state(thread_config(analysis_run.thread_id))
            state = snapshot.values
    return analysis_run_detail(session, analysis_run, state=state)


@router.post(
    "/studies/{study_id}/analysis-runs",
    response_model=AnalysisRunDetail,
    status_code=status.HTTP_201_CREATED,
)
def start_analysis_run(
    study_id: UUID,
    session: DatabaseSession,
    settings: SettingsDependency,
    embedding_client: EmbeddingClientDependency,
    language_model: LanguageModelDependency,
) -> AnalysisRunDetail:
    """Start a new analysis run and execute until interrupt or completion."""
    study = get_study_or_404(session, study_id)
    if not study.research_questions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Study has no research questions",
        )
    analysis_run = create_analysis_run(session, study_id)
    dependencies = build_graph_dependencies(session, settings, embedding_client, language_model)
    with open_checkpointer(settings) as checkpointer:
        graph = build_main_path_graph(
            dependencies,
            checkpointer=checkpointer,
            interrupt_before_write=settings.interrupt_before_write,
        )
        config = thread_config(analysis_run.thread_id)
        state = initial_agent_state(study, analysis_run)
        try:
            final_state = graph.invoke(state, config=config)
            apply_run_status_from_graph(session, analysis_run.id, graph, config)
            session.refresh(analysis_run)
            return analysis_run_detail(session, analysis_run, state=final_state)
        except Exception as error:
            mark_analysis_run_status(session, analysis_run.id, "failed", error=str(error))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(error),
            ) from error


@router.post("/analysis-runs/{analysis_run_id}/resume", response_model=AnalysisRunDetail)
def resume_analysis_run_endpoint(
    analysis_run_id: UUID,
    payload: AnalysisResumeRequest,
    session: DatabaseSession,
    settings: SettingsDependency,
    embedding_client: EmbeddingClientDependency,
    language_model: LanguageModelDependency,
) -> AnalysisRunDetail:
    """Approve or revise an interrupted analysis run."""
    analysis_run = get_analysis_run_or_404(session, analysis_run_id)
    if analysis_run.status != "awaiting_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analysis run is not awaiting approval",
        )
    with open_checkpointer(settings) as checkpointer:
        try:
            final_state = resume_analysis_run(
                session=session,
                analysis_run=analysis_run,
                action=payload.action,
                subqueries=payload.subqueries,
                settings=settings,
                embedding_client=embedding_client,
                language_model=language_model,
                checkpointer=checkpointer,
            )
            session.refresh(analysis_run)
            return analysis_run_detail(session, analysis_run, state=final_state)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(error),
            ) from error


@router.post("/studies/{study_id}/analysis-runs/stream")
def stream_analysis_run(
    study_id: UUID,
    session: DatabaseSession,
    settings: SettingsDependency,
    embedding_client: EmbeddingClientDependency,
    language_model: LanguageModelDependency,
) -> StreamingResponse:
    """Start an analysis run and stream node updates as SSE until interrupt or end."""
    study = get_study_or_404(session, study_id)
    if not study.research_questions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Study has no research questions",
        )

    def event_stream() -> Iterator[str]:
        analysis_run = create_analysis_run(session, study_id)
        session.commit()
        dependencies = build_graph_dependencies(session, settings, embedding_client, language_model)
        with open_checkpointer(settings) as checkpointer:
            graph = build_main_path_graph(
                dependencies,
                checkpointer=checkpointer,
                interrupt_before_write=settings.interrupt_before_write,
            )
            config = thread_config(analysis_run.thread_id)
            state = initial_agent_state(study, analysis_run)
            yield _sse({"type": "run", "analysis_run_id": str(analysis_run.id)})
            try:
                for event in stream_graph_updates(graph, state, config):
                    payload = AnalysisEvent(node=event["node"], keys=list(event["update"].keys()))
                    yield _sse({"type": "node", **payload.model_dump()})
                status_name = apply_run_status_from_graph(session, analysis_run.id, graph, config)
                session.commit()
                interrupted = graph_is_interrupted(graph, config)
                yield _sse(
                    {
                        "type": "done",
                        "status": status_name,
                        "interrupted": interrupted,
                        "analysis_run_id": str(analysis_run.id),
                    }
                )
            except Exception as error:
                mark_analysis_run_status(session, analysis_run.id, "failed", error=str(error))
                session.commit()
                yield _sse({"type": "error", "detail": str(error)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"
