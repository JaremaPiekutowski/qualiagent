"""Deterministic citation verification against source chunks."""

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qualiagent.models import Chunk, Source
from qualiagent.schemas import DraftCitation, RetrievedChunk


def normalize_quote_text(text: str) -> str:
    """Normalize whitespace and quote characters for exact substring checks.

    Args:
        text: Raw quoted or chunk text.

    Returns:
        Normalized string suitable for exact containment checks.
    """
    replacements = {
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "«": '"',
        "»": '"',
        "\u2018": "'",
        "\u2019": "'",
        "‚": "'",
        "‛": "'",
    }
    normalized = text
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return " ".join(normalized.split())


def format_citation_marker(source_code: str, chunk_position: int) -> str:
    """Build a citation marker from source code and chunk position.

    Args:
        source_code: Stable source code such as ``S03``.
        chunk_position: Zero-based chunk position inside the source.

    Returns:
        Marker string like ``[S03:c17]``.
    """
    return f"[{source_code}:c{chunk_position}]"


def parse_draft_citations(
    draft: str,
    retrieved_chunks: list[RetrievedChunk],
) -> tuple[list[DraftCitation], list[str]]:
    """Parse quote+marker pairs from a draft into draft citations.

    Expected pattern: a quoted span followed by ``[S01:c0]``.

    Args:
        draft: Section draft produced by the write node.
        retrieved_chunks: Chunks available for resolving markers.

    Returns:
        Parsed citations and parse failures that should fail verification.
    """
    chunk_by_marker = {format_citation_marker(chunk.source_code, chunk.position): chunk for chunk in retrieved_chunks}
    pattern = re.compile(
        r'(?P<open>[„"«])(?P<quote>.*?)(?P<close>[”"»])\s*'
        r"\[(?P<code>S\d+):c(?P<position>\d+)\]",
        re.DOTALL,
    )
    citations: list[DraftCitation] = []
    failures: list[str] = []
    for match in pattern.finditer(draft):
        quoted_text = match.group("quote").strip()
        marker = format_citation_marker(match.group("code"), int(match.group("position")))
        chunk = chunk_by_marker.get(marker)
        if chunk is None:
            failures.append(f"Unknown marker {marker}")
            continue
        if not quoted_text:
            failures.append(f"Empty quoted text for marker {marker}")
            continue
        citations.append(
            DraftCitation(
                marker=marker,
                source_id=chunk.source_id,
                chunk_id=chunk.chunk_id,
                quoted_text=quoted_text,
            )
        )
    return citations, failures


def verify_citations(
    session: Session,
    citations: list[DraftCitation],
    parse_failures: list[str] | None = None,
) -> tuple[list[DraftCitation], list[str]]:
    """Verify citations with exact substring matching after normalization.

    Args:
        session: Database session used to load chunk texts.
        citations: Parsed draft citations.
        parse_failures: Failures already detected while parsing markers.

    Returns:
        Citations with verification flags set, plus failure messages.
    """
    failures = list(parse_failures or [])
    if not citations:
        return [], failures

    chunk_ids = [citation.chunk_id for citation in citations]
    rows = session.execute(
        select(Chunk, Source).join(Source, Chunk.source_id == Source.id).where(Chunk.id.in_(chunk_ids))
    ).all()
    chunk_by_id: dict[UUID, tuple[Chunk, Source]] = {chunk.id: (chunk, source) for chunk, source in rows}

    verified_citations: list[DraftCitation] = []
    for citation in citations:
        pair = chunk_by_id.get(citation.chunk_id)
        if pair is None:
            note = f"Chunk not found for marker {citation.marker}"
            failures.append(note)
            verified_citations.append(citation.model_copy(update={"verified": False, "verification_note": note}))
            continue

        chunk, source = pair
        expected_marker = format_citation_marker(source.source_code, chunk.position)
        if citation.marker != expected_marker:
            note = f"Marker {citation.marker} does not match chunk {chunk.id}"
            failures.append(note)
            verified_citations.append(citation.model_copy(update={"verified": False, "verification_note": note}))
            continue

        normalized_quote = normalize_quote_text(citation.quoted_text)
        normalized_chunk = normalize_quote_text(chunk.text)
        if not normalized_quote or normalized_quote not in normalized_chunk:
            note = f"Quoted text is not an exact substring of chunk for {citation.marker}"
            failures.append(note)
            verified_citations.append(citation.model_copy(update={"verified": False, "verification_note": note}))
            continue

        verified_citations.append(citation.model_copy(update={"verified": True, "verification_note": None}))

    return verified_citations, failures
