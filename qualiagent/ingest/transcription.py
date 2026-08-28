"""Audio and video transcription clients."""

import logging
import mimetypes
from pathlib import Path
from typing import Protocol

from google import genai

from qualiagent.config import Settings, get_settings

logger = logging.getLogger(__name__)

TRANSCRIPTION_PROMPT = (
    "Transcribe this interview recording into plain text. "
    "Preserve spoken wording as closely as possible. "
    "If speakers are distinguishable, prefix turns with Speaker labels. "
    "Do not summarize. Return only the transcript."
)


class TranscriptionClient(Protocol):
    """Interface for turning media files into transcripts."""

    def transcribe(self, file_path: Path) -> str:
        """Transcribe an audio or video file.

        Args:
            file_path: Path to the media file.

        Returns:
            Plain-text transcript.
        """
        ...


class GeminiTranscriptionClient:
    """Gemini-based transcription via the Files API."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Create a Gemini client.

        Args:
            settings: Optional settings override; defaults to env settings.
        """
        self.settings = settings or get_settings()
        if not self.settings.gemini_api_key:
            raise ValueError("gemini_api_key is required for GeminiTranscriptionClient")
        self.client = genai.Client(api_key=self.settings.gemini_api_key)

    def transcribe(self, file_path: Path) -> str:
        """Upload media to Gemini and request a transcript.

        Args:
            file_path: Path to the media file.

        Returns:
            Plain-text transcript.

        Raises:
            RuntimeError: If Gemini returns an empty transcript.
        """
        mime_type, _encoding = mimetypes.guess_type(str(file_path))
        logger.info(
            "Gemini transcription model=%s file=%s mime=%s",
            self.settings.gemini_model,
            file_path.name,
            mime_type,
        )
        uploaded = self.client.files.upload(file=str(file_path))
        try:
            response = self.client.models.generate_content(
                model=self.settings.gemini_model,
                contents=[uploaded, TRANSCRIPTION_PROMPT],  # type: ignore[arg-type]
            )
            text = (response.text or "").strip()
            if not text:
                raise RuntimeError("Gemini returned an empty transcript")
            return text
        finally:
            uploaded_name = getattr(uploaded, "name", None)
            if uploaded_name:
                self.client.files.delete(name=uploaded_name)


class StubTranscriptionClient:
    """Deterministic transcript stub for tests."""

    def __init__(self, transcript: str = "Stub transcript of the interview.") -> None:
        """Create a stub client.

        Args:
            transcript: Fixed transcript text.
        """
        self.transcript = transcript

    def transcribe(self, file_path: Path) -> str:
        """Return the configured transcript.

        Args:
            file_path: Path to the media file (unused).

        Returns:
            Stub transcript.
        """
        del file_path
        return self.transcript
