"""Respondent counting rules shared by coverage analysis."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qualiagent.models import Source
from qualiagent.schemas import RetrievedChunk


def respondent_identity(source_id: UUID, respondent_label: str | None) -> str:
    """Build a stable respondent identity key.

    Labeled sources share identity by label. Unlabeled sources each count alone.

    Args:
        source_id: Source UUID.
        respondent_label: Optional respondent label.

    Returns:
        Identity string used for unique respondent counts.
    """
    if respondent_label:
        return f"label:{respondent_label}"
    return f"source:{source_id}"


def count_study_respondents(session: Session, study_id: UUID) -> int:
    """Count unique respondents across all sources in a study.

    Args:
        session: Database session.
        study_id: Study to count.

    Returns:
        Number of unique respondents.
    """
    sources = session.execute(select(Source).where(Source.study_id == study_id)).scalars().all()
    identities = {respondent_identity(source.id, source.respondent_label) for source in sources}
    return len(identities)


def count_covered_respondents(chunks: list[RetrievedChunk]) -> int:
    """Count unique respondents represented in retrieved chunks.

    Args:
        chunks: Retrieved chunks for the current question.

    Returns:
        Number of unique respondents among retrieved chunks.
    """
    identities = {respondent_identity(chunk.source_id, chunk.respondent_label) for chunk in chunks}
    return len(identities)


def chunks_per_source(chunks: list[RetrievedChunk]) -> dict[str, int]:
    """Count retrieved chunks grouped by source code.

    Args:
        chunks: Retrieved chunks.

    Returns:
        Mapping of source code to chunk count.
    """
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk.source_code] = counts.get(chunk.source_code, 0) + 1
    return counts
