from qualiagent.ingest.chunking import chunk_text


def test_chunk_text_packs_paragraphs_with_overlap() -> None:
    text = (
        "Pierwszy akapit o zmianie.\n\nDrugi akapit o komunikacji.\n\nTrzeci akapit o oporze zespołu i braku wsparcia."
    )
    chunks = chunk_text(text, chunk_size_characters=60, chunk_overlap_characters=15)
    assert len(chunks) >= 2
    assert all(chunk.strip() for chunk in chunks)


def test_chunk_text_returns_empty_for_blank_input() -> None:
    assert chunk_text("   \n\n  ", chunk_size_characters=100, chunk_overlap_characters=10) == []
