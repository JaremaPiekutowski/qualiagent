"""Orchestrate loading, chunking, embedding, and persisting one source."""

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qualiagent.config import Settings, get_settings
from qualiagent.console_logging import configure_console_logging
from qualiagent.ingest.chunking import chunk_text
from qualiagent.ingest.embedding import EmbeddingClient, VoyageEmbeddingClient, embed_texts
from qualiagent.ingest.loaders import detect_source_kind, load_text_from_path
from qualiagent.models import Chunk, Source, Study

logger = logging.getLogger(__name__)


class StudyNotFoundError(LookupError):
    """Raised when ingest is requested for a missing study."""


def next_source_code(session: Session, study_id: UUID) -> str:
    """Allocate the next stable source code inside a study.

    Args:
        session: Active database session.
        study_id: Study that will own the source.

    Returns:
        Code like ``S01``, ``S02``, based on existing codes.
    """
    existing_codes = session.scalars(select(Source.source_code).where(Source.study_id == study_id)).all()
    highest_number = 0
    for code in existing_codes:
        if code.startswith("S") and code[1:].isdigit():
            highest_number = max(highest_number, int(code[1:]))
    return f"S{highest_number + 1:02d}"


def ingest_source(
    session: Session,
    study_id: UUID,
    file_path: Path,
    respondent_label: str | None = None,
    settings: Settings | None = None,
    embedding_client: EmbeddingClient | None = None,
) -> Source:
    """Ingest one file into a study as an indexed source with chunks.

    Args:
        session: Active database session (caller owns commit/rollback).
        study_id: Target study identifier.
        file_path: Path to the uploaded file.
        respondent_label: Optional respondent label for the source.
        settings: Optional settings override.
        embedding_client: Optional embedding client override for tests.

    Returns:
        Persisted ``Source`` with status ``indexed``.

    Raises:
        StudyNotFoundError: If ``study_id`` does not exist.
        Exception: Re-raised after marking the source as ``failed``.
    """
    resolved_settings = settings or get_settings()
    configure_console_logging(resolved_settings.log_level)

    study = session.get(Study, study_id)
    if study is None:
        raise StudyNotFoundError(f"Study not found: {study_id}")

    kind = detect_source_kind(file_path.name)
    source_code = next_source_code(session, study_id)
    logger.info(
        "Ingesting %s as %s (%s)%s",
        file_path.name,
        source_code,
        kind,
        f", respondent={respondent_label}" if respondent_label else "",
    )

    source = Source(
        study_id=study_id,
        source_code=source_code,
        filename=file_path.name,
        kind=kind,
        respondent_label=respondent_label,
        raw_text="",
        status="pending",
    )
    session.add(source)
    session.flush()

    try:
        logger.info("[%s] Extracting text from %s", source_code, kind.upper())
        raw_text = load_text_from_path(file_path, kind=kind)
        source.raw_text = raw_text
        logger.info("[%s] Extracted %s characters", source_code, len(raw_text))

        logger.info(
            "[%s] Chunking (size=%s, overlap=%s)",
            source_code,
            resolved_settings.chunk_size_characters,
            resolved_settings.chunk_overlap_characters,
        )
        chunk_texts = chunk_text(
            raw_text,
            chunk_size_characters=resolved_settings.chunk_size_characters,
            chunk_overlap_characters=resolved_settings.chunk_overlap_characters,
        )
        logger.info("[%s] Created %s chunks", source_code, len(chunk_texts))

        client = embedding_client or VoyageEmbeddingClient(resolved_settings)
        logger.info("[%s] Embedding %s chunks", source_code, len(chunk_texts))
        embeddings = embed_texts(chunk_texts, client=client)

        if len(embeddings) != len(chunk_texts):
            raise RuntimeError("Embedding count does not match chunk count")

        for position, (chunk_body, embedding) in enumerate(zip(chunk_texts, embeddings, strict=True)):
            if len(embedding) != resolved_settings.voyage_embedding_dimensions:
                raise RuntimeError(
                    "Unexpected embedding dimensions: "
                    f"{len(embedding)} != {resolved_settings.voyage_embedding_dimensions}"
                )
            session.add(
                Chunk(
                    source_id=source.id,
                    text=chunk_body,
                    position=position,
                    speaker=None,
                    embedding=embedding,
                )
            )

        source.status = "indexed"
        source.error = None
        logger.info("[%s] Indexed successfully (%s chunks)", source_code, len(chunk_texts))
    except Exception as error:
        source.status = "failed"
        source.error = str(error)
        session.flush()
        logger.exception("[%s] Ingest failed: %s", source_code, error)
        raise

    session.flush()
    return source
