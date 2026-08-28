"""Tests for hybrid retrieval."""

from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from qualiagent.config import Settings
from qualiagent.ingest.source_ingest import ingest_source
from qualiagent.models import Study
from qualiagent.retrieval import reciprocal_rank_fusion, search_study_chunks
from tests.stub_embedding import StubEmbeddingClient
from tests.test_source_ingest import write_sample_docx, write_sample_pdf, write_sample_txt


def test_reciprocal_rank_fusion_prefers_items_high_in_both_lists() -> None:
    first = UUID("00000000-0000-0000-0000-000000000001")
    second = UUID("00000000-0000-0000-0000-000000000002")
    third = UUID("00000000-0000-0000-0000-000000000003")

    fused = reciprocal_rank_fusion(
        [
            [first, second, third],
            [second, first, third],
        ],
        rrf_constant=60,
    )
    ranked_ids = [chunk_id for chunk_id, _score in fused]
    assert ranked_ids[0] in {first, second}
    assert third in ranked_ids
    assert fused[0][1] >= fused[-1][1]


def test_search_study_chunks_returns_relevant_chunks_with_metadata(
    session: Session,
    settings: Settings,
    embedding_client: StubEmbeddingClient,
    tmp_path: Path,
) -> None:
    study = Study(
        name="Retrieval study",
        research_questions=["Jak respondenci opisują zmianę?"],
        web_search_enabled=False,
    )
    session.add(study)
    session.flush()

    files = [
        (write_sample_txt(tmp_path), "R01"),
        (write_sample_docx(tmp_path), "R02"),
        (write_sample_pdf(tmp_path), "R03"),
    ]
    for file_path, respondent_label in files:
        ingest_source(
            session=session,
            study_id=study.id,
            file_path=file_path,
            respondent_label=respondent_label,
            settings=settings,
            embedding_client=embedding_client,
        )
    session.flush()

    results = search_study_chunks(
        session=session,
        study_id=study.id,
        query="zmiana organizacyjna komunikacja wsparcie",
        embedding_client=embedding_client,
        settings=settings,
        top_k=5,
    )

    assert len(results) >= 1
    assert len(results) <= 5
    for item in results:
        assert item.chunk_id
        assert item.source_id
        assert item.source_code.startswith("S")
        assert item.respondent_label in {"R01", "R02", "R03"}
        assert item.text.strip()
        assert item.score > 0

    top_text = " ".join(item.text.lower() for item in results[:3])
    assert "zmiana" in top_text or "wsparcia" in top_text or "komunikowali" in top_text
