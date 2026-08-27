"""SQLAlchemy ORM models for studies, sources, and analysis results."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class Study(Base):
    """A qualitative research study with questions and uploaded sources."""

    __tablename__ = "studies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    research_questions: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    web_search_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    sources: Mapped[list[Source]] = relationship(
        back_populates="study",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    analysis_runs: Mapped[list[AnalysisRun]] = relationship(
        back_populates="study",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Source(Base):
    """An uploaded file (transcript or document) belonging to a study."""

    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("study_id", "source_code", name="uq_sources_study_source_code"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("studies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_code: Mapped[str] = mapped_column(String(16), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    respondent_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    study: Mapped[Study] = relationship(back_populates="sources")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Chunk.position",
    )


class Chunk(Base):
    """A text segment of a source with embedding and full-text search fields."""

    __tablename__ = "chunks"
    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
        Index(
            "ix_chunks_search_vector_gin",
            "search_vector",
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1024),
        nullable=True,
    )
    search_vector: Mapped[object | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', text)", persisted=True),
        nullable=True,
    )

    source: Mapped[Source] = relationship(back_populates="chunks")
    citations: Mapped[list[Citation]] = relationship(back_populates="chunk")


class AnalysisRun(Base):
    """One execution of the analysis graph for a study."""

    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("studies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    study: Mapped[Study] = relationship(back_populates="analysis_runs")
    sections: Mapped[list[Section]] = relationship(
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Section.position",
    )


class Section(Base):
    """A report section answering one research question within a run."""

    __tablename__ = "sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    research_question: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    coverage: Mapped[str] = mapped_column(String(32), nullable=False)
    coverage_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    respondents_covered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    respondents_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="sections")
    citations: Mapped[list[Citation]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Citation(Base):
    """A verified literal quote marker pointing at a source chunk."""

    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    marker: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quoted_text: Mapped[str] = mapped_column(Text, nullable=False)
    verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    section: Mapped[Section] = relationship(back_populates="citations")
    chunk: Mapped[Chunk] = relationship(back_populates="citations")
    source: Mapped[Source] = relationship()
