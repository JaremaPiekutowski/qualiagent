"""Tests for media transcription ingest and HITL interrupt/resume."""

from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from sqlalchemy.orm import Session

from qualiagent.config import Settings
from qualiagent.graph.checkpointer import get_shared_memory_checkpointer
from qualiagent.graph.run import resume_analysis_run, run_main_path
from qualiagent.ingest.source_ingest import ingest_source
from qualiagent.ingest.transcription import StubTranscriptionClient
from qualiagent.models import AnalysisRun, Chunk, Study
from tests.stub_embedding import StubEmbeddingClient
from tests.stub_language_model import StubLanguageModelClient
from tests.test_source_ingest import write_sample_txt


def test_ingest_audio_uses_transcription_client(
    session: Session,
    settings: Settings,
    embedding_client: StubEmbeddingClient,
    tmp_path: Path,
) -> None:
    study = Study(name="Audio study", research_questions=["Q?"], web_search_enabled=False)
    session.add(study)
    session.flush()

    audio_path = tmp_path / "interview.mp3"
    audio_path.write_bytes(b"fake-audio-bytes")
    transcript = "Zmiana była trudna. Brakowało wsparcia zespołu."

    source = ingest_source(
        session=session,
        study_id=study.id,
        file_path=audio_path,
        respondent_label="R01",
        settings=settings,
        embedding_client=embedding_client,
        transcription_client=StubTranscriptionClient(transcript),
    )

    assert source.kind == "audio"
    assert source.status == "indexed"
    assert source.raw_text == transcript
    chunks = session.execute(select(Chunk).where(Chunk.source_id == source.id)).scalars().all()
    assert len(chunks) >= 1


def test_interrupt_before_write_and_approve_resume(
    session: Session,
    settings: Settings,
    embedding_client: StubEmbeddingClient,
    tmp_path: Path,
) -> None:
    hitl_settings = settings.model_copy(update={"interrupt_before_write": True})
    study = Study(
        name="HITL study",
        research_questions=["Jak respondenci postrzegają zmianę organizacyjną?"],
        web_search_enabled=False,
    )
    session.add(study)
    session.flush()
    ingest_source(
        session=session,
        study_id=study.id,
        file_path=write_sample_txt(tmp_path),
        respondent_label="R01",
        settings=hitl_settings,
        embedding_client=embedding_client,
    )

    checkpointer = InMemorySaver()
    language_model = StubLanguageModelClient()
    interrupted_state = run_main_path(
        session=session,
        study_id=study.id,
        settings=hitl_settings,
        embedding_client=embedding_client,
        language_model=language_model,
        checkpointer=checkpointer,
    )

    analysis_run = session.execute(select(AnalysisRun).where(AnalysisRun.study_id == study.id)).scalar_one()
    assert analysis_run.status == "awaiting_approval"
    assert interrupted_state["subqueries"]
    assert interrupted_state["coverage"] is not None
    assert not interrupted_state["draft"]

    final_state = resume_analysis_run(
        session=session,
        analysis_run=analysis_run,
        action="approve",
        settings=hitl_settings,
        embedding_client=embedding_client,
        language_model=language_model,
        checkpointer=checkpointer,
    )
    session.refresh(analysis_run)
    assert analysis_run.status == "completed"
    assert final_state["sections"]
    assert final_state["report_path"]


def test_shared_memory_checkpointer_is_singleton() -> None:
    first = get_shared_memory_checkpointer()
    second = get_shared_memory_checkpointer()
    assert first is second
