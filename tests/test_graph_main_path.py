"""Tests for the linear analysis graph path."""

from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qualiagent.config import Settings
from qualiagent.graph.run import run_main_path
from qualiagent.ingest.source_ingest import ingest_source
from qualiagent.models import AnalysisRun, Citation, Section, Study
from qualiagent.verify import normalize_quote_text, parse_draft_citations
from tests.stub_embedding import StubEmbeddingClient
from tests.stub_language_model import StubLanguageModelClient
from tests.test_source_ingest import write_sample_docx, write_sample_pdf, write_sample_txt


def test_normalize_quote_text_collapses_whitespace_and_quotes() -> None:
    assert normalize_quote_text("  „Hello   world” ") == '"Hello world"'


def test_parse_draft_citations_extracts_marker_and_quote() -> None:
    from qualiagent.schemas import RetrievedChunk

    chunk = RetrievedChunk(
        chunk_id=UUID("00000000-0000-0000-0000-000000000001"),
        source_id=UUID("00000000-0000-0000-0000-000000000010"),
        source_code="S01",
        respondent_label="R01",
        text="Zmiana organizacyjna była odgórna.",
        position=0,
        speaker=None,
        score=1.0,
    )
    draft = 'Jeden respondent mówi: "Zmiana organizacyjna była odgórna." [S01:c0]'
    citations, failures = parse_draft_citations(draft, [chunk])
    assert failures == []
    assert len(citations) == 1
    assert citations[0].marker == "[S01:c0]"
    assert citations[0].quoted_text == "Zmiana organizacyjna była odgórna."
    assert citations[0].chunk_id == chunk.chunk_id


def test_main_path_writes_verified_section(
    session: Session,
    settings: Settings,
    embedding_client: StubEmbeddingClient,
    tmp_path: Path,
) -> None:
    study = Study(
        name="Graph study",
        research_questions=["Jak respondenci postrzegają zmianę organizacyjną?"],
        web_search_enabled=False,
    )
    session.add(study)
    session.flush()

    for file_path, respondent_label in [
        (write_sample_txt(tmp_path), "R01"),
        (write_sample_docx(tmp_path), "R02"),
        (write_sample_pdf(tmp_path), "R03"),
    ]:
        ingest_source(
            session=session,
            study_id=study.id,
            file_path=file_path,
            respondent_label=respondent_label,
            settings=settings,
            embedding_client=embedding_client,
        )
    session.flush()

    language_model = StubLanguageModelClient()
    final_state = run_main_path(
        session=session,
        study_id=study.id,
        question_index=0,
        settings=settings,
        embedding_client=embedding_client,
        language_model=language_model,
    )

    assert final_state["sections"]
    assert final_state["sections"][0].body
    assert final_state["sections"][0].coverage in {"sufficient", "thin", "absent"}
    assert final_state["sections"][0].citations
    assert all(citation.verified for citation in final_state["sections"][0].citations)

    analysis_run = session.execute(select(AnalysisRun).where(AnalysisRun.study_id == study.id)).scalar_one()
    assert analysis_run.status == "completed"
    assert analysis_run.finished_at is not None

    section = session.execute(select(Section).where(Section.analysis_run_id == analysis_run.id)).scalar_one()
    assert section.body == final_state["sections"][0].body
    assert section.research_question == study.research_questions[0]

    citations = session.execute(select(Citation).where(Citation.section_id == section.id)).scalars().all()
    assert len(citations) >= 1
    assert all(citation.verified for citation in citations)
