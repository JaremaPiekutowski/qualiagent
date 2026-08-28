"""Hybrid retrieval over chunk embeddings and full-text search."""

from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from qualiagent.config import Settings, get_settings
from qualiagent.ingest.embedding import EmbeddingClient, VoyageEmbeddingClient
from qualiagent.models import Chunk, Source
from qualiagent.schemas import RetrievedChunk


def reciprocal_rank_fusion(
    ranked_lists: list[list[UUID]],
    rrf_constant: int = 60,
) -> list[tuple[UUID, float]]:
    """Merge ranked result lists with Reciprocal Rank Fusion.

    Args:
        ranked_lists: Ordered chunk id lists from each retriever.
        rrf_constant: Smoothing constant ``k`` in ``1 / (k + rank)``.

    Returns:
        Chunk ids with fused scores, highest first.
    """
    scores: dict[UUID, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rrf_constant + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def study_chunks_query(study_id: UUID) -> Select[tuple[Chunk, Source]]:
    """Base select joining chunks to sources for one study.

    Args:
        study_id: Study whose sources are searchable.

    Returns:
        SQLAlchemy select of ``(Chunk, Source)`` rows.
    """
    return select(Chunk, Source).join(Source, Chunk.source_id == Source.id).where(Source.study_id == study_id)


def search_by_vector(
    session: Session,
    study_id: UUID,
    query_embedding: list[float],
    top_k: int,
) -> list[UUID]:
    """Rank study chunks by cosine distance to the query embedding.

    Args:
        session: Database session.
        study_id: Study scope.
        query_embedding: Query vector.
        top_k: Maximum number of ids to return.

    Returns:
        Chunk ids ordered from nearest to farthest.
    """
    statement = (
        study_chunks_query(study_id)
        .where(Chunk.embedding.is_not(None))
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    rows = session.execute(statement).all()
    return [chunk.id for chunk, _source in rows]


def search_by_full_text(
    session: Session,
    study_id: UUID,
    query: str,
    top_k: int,
) -> list[UUID]:
    """Rank study chunks by Postgres full-text relevance.

    Args:
        session: Database session.
        study_id: Study scope.
        query: Natural-language query.
        top_k: Maximum number of ids to return.

    Returns:
        Chunk ids ordered by ``ts_rank`` descending.
    """
    ts_query = func.plainto_tsquery("simple", query)
    statement = (
        study_chunks_query(study_id)
        .where(Chunk.search_vector.op("@@")(ts_query))
        .order_by(func.ts_rank(Chunk.search_vector, ts_query).desc())
        .limit(top_k)
    )
    rows = session.execute(statement).all()
    return [chunk.id for chunk, _source in rows]


def load_retrieved_chunks(
    session: Session,
    ranked_scores: list[tuple[UUID, float]],
    top_k: int,
) -> list[RetrievedChunk]:
    """Load chunk and source metadata for fused ranking results.

    Args:
        session: Database session.
        ranked_scores: Fused ``(chunk_id, score)`` pairs.
        top_k: Maximum number of results to keep.

    Returns:
        Retrieved chunks with source metadata and RRF scores.
    """
    selected = ranked_scores[:top_k]
    if not selected:
        return []

    chunk_ids = [chunk_id for chunk_id, _score in selected]
    score_by_id = dict(selected)
    statement = select(Chunk, Source).join(Source, Chunk.source_id == Source.id).where(Chunk.id.in_(chunk_ids))
    rows = session.execute(statement).all()
    by_id = {chunk.id: (chunk, source) for chunk, source in rows}

    results: list[RetrievedChunk] = []
    for chunk_id, _score in selected:
        pair = by_id.get(chunk_id)
        if pair is None:
            continue
        chunk, source = pair
        results.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                source_id=source.id,
                source_code=source.source_code,
                respondent_label=source.respondent_label,
                text=chunk.text,
                position=chunk.position,
                speaker=chunk.speaker,
                score=score_by_id[chunk_id],
            )
        )
    return results


def search_study_chunks(
    session: Session,
    study_id: UUID,
    query: str,
    embedding_client: EmbeddingClient | None = None,
    settings: Settings | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Run hybrid vector + full-text retrieval with RRF fusion.

    Args:
        session: Database session.
        study_id: Study to search within.
        query: Natural-language search query.
        embedding_client: Optional embedding client override.
        settings: Optional settings override.
        top_k: Optional result limit override.

    Returns:
        Top chunks with metadata and fused scores.
    """
    resolved_settings = settings or get_settings()
    limit = top_k if top_k is not None else resolved_settings.retrieval_top_k
    client = embedding_client or VoyageEmbeddingClient(resolved_settings)

    query_embedding = client.embed_query(query)
    vector_ids = search_by_vector(session, study_id, query_embedding, limit)
    full_text_ids = search_by_full_text(session, study_id, query, limit)
    fused = reciprocal_rank_fusion(
        [vector_ids, full_text_ids],
        rrf_constant=resolved_settings.rrf_constant,
    )
    return load_retrieved_chunks(session, fused, limit)
