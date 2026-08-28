"""Pydantic schemas used as API and graph contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SourceKind = Literal[
    "audio",
    "video",
    "pdf",
    "docx",
    "txt",
]

SourceStatus = Literal[
    "pending",
    "transcribing",
    "indexed",
    "failed",
]

AnalysisRunStatus = Literal[
    "pending",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
]

CoverageVerdict = Literal[
    "sufficient",
    "thin",
    "absent",
]


class Study(BaseModel):
    """Study payload exposed outside the ORM layer."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    research_questions: list[str]
    web_search_enabled: bool = False
    created_at: datetime


class StudyCreate(BaseModel):
    """Payload for creating a study."""

    name: str = Field(min_length=1, max_length=255)
    research_questions: list[str] = Field(default_factory=list)
    web_search_enabled: bool = False


class StudyUpdate(BaseModel):
    """Partial update for an existing study."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    research_questions: list[str] | None = None
    web_search_enabled: bool | None = None


class Source(BaseModel):
    """Source file metadata and extracted text."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    study_id: UUID
    source_code: str
    filename: str
    kind: SourceKind
    respondent_label: str | None = None
    raw_text: str
    status: SourceStatus
    error: str | None = None


class SourceSummary(BaseModel):
    """Source metadata without the full extracted text."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    study_id: UUID
    source_code: str
    filename: str
    kind: SourceKind
    respondent_label: str | None = None
    status: SourceStatus
    error: str | None = None


class Chunk(BaseModel):
    """Chunk text and ordering without the embedding vector."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    text: str
    position: int
    speaker: str | None = None


class RetrievedChunk(BaseModel):
    """Chunk returned by hybrid retrieval with source metadata and RRF score."""

    chunk_id: UUID
    source_id: UUID
    source_code: str
    respondent_label: str | None
    text: str
    position: int
    speaker: str | None
    score: float


class AnalysisRun(BaseModel):
    """Status and identifiers of one analysis execution."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    study_id: UUID
    thread_id: str
    status: AnalysisRunStatus
    created_at: datetime
    finished_at: datetime | None = None
    error: str | None = None


class Citation(BaseModel):
    """Literal citation tied to a chunk and verification state."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    section_id: UUID
    marker: str
    source_id: UUID
    chunk_id: UUID
    quoted_text: str
    verified: bool
    verification_note: str | None = None


class DraftCitation(BaseModel):
    """Citation parsed from a draft before it is persisted."""

    marker: str
    source_id: UUID
    chunk_id: UUID
    quoted_text: str
    verified: bool = False
    verification_note: str | None = None


class Section(BaseModel):
    """Written answer for one research question, with citations."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_run_id: UUID
    research_question: str
    position: int
    body: str
    coverage: CoverageVerdict
    coverage_note: str
    respondents_covered: int
    respondents_total: int
    citations: list[Citation] = Field(default_factory=list)


class DraftSection(BaseModel):
    """Section payload produced by the graph before database ids exist."""

    research_question: str
    position: int
    body: str
    coverage: CoverageVerdict
    coverage_note: str
    respondents_covered: int
    respondents_total: int
    citations: list[DraftCitation] = Field(default_factory=list)


class RetrievedChunkSummary(BaseModel):
    """Compact retrieved chunk for HITL preview."""

    chunk_id: UUID
    source_code: str
    respondent_label: str | None
    position: int
    text_preview: str
    score: float


class AnalysisApprovalPreview(BaseModel):
    """State shown to the researcher before the write node."""

    research_question: str
    subqueries: list[str]
    coverage: CoverageVerdict | None
    coverage_note: str
    respondents_covered: int
    respondents_total: int
    missing_dimensions: list[str]
    retrieved: dict[str, list[RetrievedChunkSummary]]


class AnalysisRunDetail(BaseModel):
    """Analysis run with optional HITL preview and section count."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    study_id: UUID
    thread_id: str
    status: AnalysisRunStatus
    created_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    section_count: int = 0
    report_path: str | None = None
    approval_preview: AnalysisApprovalPreview | None = None


class AnalysisResumeRequest(BaseModel):
    """Resume payload after interrupt_before write."""

    action: Literal["approve", "revise"] = "approve"
    subqueries: list[str] | None = None


class AnalysisEvent(BaseModel):
    """One streamed graph progress event."""

    node: str
    keys: list[str] = Field(default_factory=list)
