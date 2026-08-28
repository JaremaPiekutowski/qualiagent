"""Tests for conditional graph edges and stage-6 loops."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from qualiagent.config import Settings
from qualiagent.graph.edges import (
    route_after_coverage,
    route_after_next_question,
    route_after_verify,
)
from qualiagent.graph.run import run_main_path
from qualiagent.graph.state import AgentState
from qualiagent.ingest.source_ingest import ingest_source
from qualiagent.models import Section, Study
from tests.stub_embedding import StubEmbeddingClient
from tests.stub_language_model import StubLanguageModelClient
from tests.test_source_ingest import write_sample_docx, write_sample_pdf, write_sample_txt


def _empty_state(**overrides: object) -> AgentState:
    state: AgentState = {
        "study_id": "00000000-0000-0000-0000-000000000001",
        "analysis_run_id": "00000000-0000-0000-0000-000000000002",
        "research_questions": ["Q1", "Q2"],
        "current_question_idx": 0,
        "subqueries": [],
        "retrieved": {},
        "coverage": None,
        "coverage_note": "",
        "missing_dimensions": [],
        "respondents_covered": 0,
        "respondents_total": 0,
        "retrieval_attempts": 0,
        "web_enabled": False,
        "web_results": [],
        "draft": "",
        "citations": [],
        "verification_failures": [],
        "verify_attempts": 0,
        "sections": [],
        "report_path": "",
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def test_route_after_coverage_branches() -> None:
    assert route_after_coverage(_empty_state(coverage="sufficient")) == "write"
    assert route_after_coverage(_empty_state(coverage="thin", retrieval_attempts=1)) == "reformulate"
    assert route_after_coverage(_empty_state(coverage="thin", retrieval_attempts=2)) == "write"
    assert route_after_coverage(_empty_state(coverage="absent", web_enabled=True)) == "web_search"
    assert route_after_coverage(_empty_state(coverage="absent", web_enabled=False)) == "write"


def test_route_after_verify_and_next_question() -> None:
    assert route_after_verify(_empty_state(verification_failures=["bad"], verify_attempts=1)) == "write"
    assert route_after_verify(_empty_state(verification_failures=["bad"], verify_attempts=2)) == "next_question"
    assert route_after_verify(_empty_state(verification_failures=[], verify_attempts=1)) == "next_question"
    assert route_after_next_question(_empty_state(current_question_idx=1)) == "plan"
    assert route_after_next_question(_empty_state(current_question_idx=2)) == "assemble"


def _ingest_three_sources(
    session: Session,
    study: Study,
    settings: Settings,
    embedding_client: StubEmbeddingClient,
    tmp_path: Path,
) -> None:
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


def test_thin_coverage_reformulates_then_writes(
    session: Session,
    settings: Settings,
    embedding_client: StubEmbeddingClient,
    tmp_path: Path,
) -> None:
    study = Study(
        name="Thin coverage study",
        research_questions=["Jak respondenci postrzegają zmianę organizacyjną?"],
        web_search_enabled=False,
    )
    session.add(study)
    session.flush()
    _ingest_three_sources(session, study, settings, embedding_client, tmp_path)

    language_model = StubLanguageModelClient(coverage_verdicts=["thin", "sufficient"])
    final_state = run_main_path(
        session=session,
        study_id=study.id,
        settings=settings,
        embedding_client=embedding_client,
        language_model=language_model,
    )

    assert language_model.reformulate_calls == 1
    assert len(final_state["sections"]) == 1
    section = session.execute(select(Section)).scalars().all()
    assert len(section) == 1


def test_verify_retries_once_on_bad_marker(
    session: Session,
    settings: Settings,
    embedding_client: StubEmbeddingClient,
    tmp_path: Path,
) -> None:
    study = Study(
        name="Verify retry study",
        research_questions=["Jak respondenci postrzegają zmianę organizacyjną?"],
        web_search_enabled=False,
    )
    session.add(study)
    session.flush()
    _ingest_three_sources(session, study, settings, embedding_client, tmp_path)

    language_model = StubLanguageModelClient(invalid_first_write=True)
    final_state = run_main_path(
        session=session,
        study_id=study.id,
        settings=settings,
        embedding_client=embedding_client,
        language_model=language_model,
    )

    assert language_model.write_calls == 2
    assert len(final_state["sections"]) == 1
    assert all(citation.verified for citation in final_state["sections"][0].citations)


def test_absent_with_web_search_adds_external_context(
    session: Session,
    settings: Settings,
    embedding_client: StubEmbeddingClient,
) -> None:
    study = Study(
        name="Absent web study",
        research_questions=["Jak wygląda kontekst rynkowy zmiany?"],
        web_search_enabled=True,
    )
    session.add(study)
    session.flush()

    language_model = StubLanguageModelClient()
    final_state = run_main_path(
        session=session,
        study_id=study.id,
        settings=settings,
        embedding_client=embedding_client,
        language_model=language_model,
    )

    assert final_state["sections"]
    assert "Kontekst zewnętrzny" in final_state["sections"][0].body
    assert final_state["sections"][0].coverage == "absent"


def test_two_research_questions_produce_two_sections(
    session: Session,
    settings: Settings,
    embedding_client: StubEmbeddingClient,
    tmp_path: Path,
) -> None:
    study = Study(
        name="Multi question study",
        research_questions=[
            "Jak respondenci postrzegają zmianę organizacyjną?",
            "Jakiego wsparcia brakowało podczas wdrożenia?",
        ],
        web_search_enabled=False,
    )
    session.add(study)
    session.flush()
    _ingest_three_sources(session, study, settings, embedding_client, tmp_path)

    language_model = StubLanguageModelClient()
    final_state = run_main_path(
        session=session,
        study_id=study.id,
        settings=settings,
        embedding_client=embedding_client,
        language_model=language_model,
    )

    assert len(final_state["sections"]) == 2
    sections = session.execute(select(Section).order_by(Section.position)).scalars().all()
    assert len(sections) == 2
    assert sections[0].research_question == study.research_questions[0]
    assert sections[1].research_question == study.research_questions[1]
