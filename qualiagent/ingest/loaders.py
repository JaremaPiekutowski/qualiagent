"""Load plain text from uploaded source files."""

from pathlib import Path

from docx import Document
from pdfminer.high_level import extract_text

from qualiagent.schemas import SourceKind

SUPPORTED_TEXT_KINDS: frozenset[SourceKind] = frozenset({"pdf", "docx", "txt"})
SUPPORTED_MEDIA_KINDS: frozenset[SourceKind] = frozenset({"audio", "video"})
SUPPORTED_SOURCE_KINDS: frozenset[SourceKind] = SUPPORTED_TEXT_KINDS | SUPPORTED_MEDIA_KINDS


class UnsupportedSourceKindError(ValueError):
    """Raised when a file type cannot be detected or extracted yet."""


def detect_source_kind(filename: str) -> SourceKind:
    """Detect source kind from a file extension.

    Args:
        filename: Original file name, including extension.

    Returns:
        One of the supported ``SourceKind`` values.

    Raises:
        UnsupportedSourceKindError: If the extension is unknown.
    """
    suffix = Path(filename).suffix.lower()
    mapping: dict[str, SourceKind] = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".txt": "txt",
        ".mp3": "audio",
        ".wav": "audio",
        ".m4a": "audio",
        ".mp4": "video",
        ".mov": "video",
        ".webm": "video",
    }
    kind = mapping.get(suffix)
    if kind is None:
        raise UnsupportedSourceKindError(f"Unsupported file extension: {suffix}")
    return kind


def load_text_from_path(path: Path, kind: SourceKind | None = None) -> str:
    """Extract text from a supported document path.

    Args:
        path: Path to the file on disk.
        kind: Optional explicit kind; detected from the name when omitted.

    Returns:
        Extracted plain text.

    Raises:
        UnsupportedSourceKindError: If extraction for this kind is unavailable.
    """
    resolved_kind = kind or detect_source_kind(path.name)
    if resolved_kind not in SUPPORTED_TEXT_KINDS:
        raise UnsupportedSourceKindError(f"Text extraction for kind '{resolved_kind}' is not available yet")
    if resolved_kind == "txt":
        return load_txt(path)
    if resolved_kind == "pdf":
        return load_pdf(path)
    return load_docx(path)


def load_txt(path: Path) -> str:
    """Read a UTF-8 text file.

    Args:
        path: Path to the ``.txt`` file.

    Returns:
        File contents as a string.
    """
    return path.read_text(encoding="utf-8")


def load_pdf(path: Path) -> str:
    """Extract text from a PDF with pdfminer.

    Args:
        path: Path to the ``.pdf`` file.

    Returns:
        Extracted text.
    """
    return extract_text(str(path))


def load_docx(path: Path) -> str:
    """Extract paragraph text from a DOCX file.

    Args:
        path: Path to the ``.docx`` file.

    Returns:
        Non-empty paragraphs joined with blank lines.
    """
    document = Document(str(path))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)
