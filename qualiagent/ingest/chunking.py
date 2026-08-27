"""Split source text into overlapping chunks."""


def split_into_paragraphs(text: str) -> list[str]:
    """Split text into normalized paragraph blocks.

    Args:
        text: Raw document text.

    Returns:
        Non-empty paragraphs with collapsed whitespace.
    """
    paragraphs: list[str] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        cleaned = " ".join(block.split())
        if cleaned:
            paragraphs.append(cleaned)
    return paragraphs


def chunk_text(
    text: str,
    chunk_size_characters: int,
    chunk_overlap_characters: int,
) -> list[str]:
    """Pack paragraphs into chunks with character limits and overlap.

    Args:
        text: Full source text.
        chunk_size_characters: Maximum characters per chunk.
        chunk_overlap_characters: Characters reused from the previous chunk.

    Returns:
        Ordered list of chunk strings.

    Raises:
        ValueError: If size/overlap arguments are invalid.
    """
    if chunk_size_characters <= 0:
        raise ValueError("chunk_size_characters must be positive")
    if chunk_overlap_characters < 0:
        raise ValueError("chunk_overlap_characters must be non-negative")
    if chunk_overlap_characters >= chunk_size_characters:
        raise ValueError("chunk_overlap_characters must be smaller than chunk_size")

    paragraphs = split_into_paragraphs(text)
    if not paragraphs:
        return []

    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size_characters:
            if current_parts:
                chunks.append(" ".join(current_parts))
                current_parts = []
                current_length = 0
            chunks.extend(
                split_long_paragraph(
                    paragraph,
                    chunk_size_characters,
                    chunk_overlap_characters,
                )
            )
            continue

        separator_length = 1 if current_parts else 0
        projected_length = current_length + separator_length + len(paragraph)
        if projected_length <= chunk_size_characters:
            current_parts.append(paragraph)
            current_length = projected_length
            continue

        if current_parts:
            chunks.append(" ".join(current_parts))
        overlap_seed = overlap_tail(" ".join(current_parts), chunk_overlap_characters)
        if overlap_seed:
            current_parts = [overlap_seed, paragraph]
            current_length = len(overlap_seed) + 1 + len(paragraph)
        else:
            current_parts = [paragraph]
            current_length = len(paragraph)

    if current_parts:
        chunks.append(" ".join(current_parts))

    return chunks


def split_long_paragraph(
    paragraph: str,
    chunk_size_characters: int,
    chunk_overlap_characters: int,
) -> list[str]:
    """Split one oversized paragraph into overlapping windows.

    Args:
        paragraph: Paragraph longer than ``chunk_size_characters``.
        chunk_size_characters: Maximum characters per window.
        chunk_overlap_characters: Overlap between consecutive windows.

    Returns:
        List of paragraph slices.
    """
    pieces: list[str] = []
    start = 0
    while start < len(paragraph):
        end = min(start + chunk_size_characters, len(paragraph))
        pieces.append(paragraph[start:end])
        if end >= len(paragraph):
            break
        start = max(0, end - chunk_overlap_characters)
    return pieces


def overlap_tail(text: str, overlap_characters: int) -> str:
    """Return the trailing overlap fragment from text.

    Args:
        text: Previous chunk text.
        overlap_characters: Number of trailing characters to keep.

    Returns:
        Overlap string, or empty when overlap is disabled.
    """
    if overlap_characters <= 0 or not text:
        return ""
    if len(text) <= overlap_characters:
        return text
    return text[-overlap_characters:].lstrip()
