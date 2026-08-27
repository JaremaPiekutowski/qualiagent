"""Source upload and listing endpoints."""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from qualiagent.api.routers.studies import get_study_or_404
from qualiagent.dependencies import get_db, get_embedding_client
from qualiagent.ingest.embedding import EmbeddingClient
from qualiagent.ingest.source_ingest import StudyNotFoundError, ingest_source
from qualiagent.models import Source as SourceModel
from qualiagent.schemas import Source, SourceSummary

router = APIRouter(tags=["sources"])

DatabaseSession = Annotated[Session, Depends(get_db)]
EmbeddingClientDependency = Annotated[EmbeddingClient, Depends(get_embedding_client)]


def get_source_or_404(session: Session, source_id: UUID) -> SourceModel:
    """Load a source or raise 404.

    Args:
        session: Database session.
        source_id: Source identifier.

    Returns:
        Matching source row.

    Raises:
        HTTPException: When the source does not exist.
    """
    source = session.get(SourceModel, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


@router.get("/studies/{study_id}/sources", response_model=list[SourceSummary])
def list_sources(study_id: UUID, session: DatabaseSession) -> list[SourceModel]:
    """List sources for a study without full raw text."""
    get_study_or_404(session, study_id)
    return list(
        session.scalars(
            select(SourceModel).where(SourceModel.study_id == study_id).order_by(SourceModel.source_code)
        ).all()
    )


@router.post(
    "/studies/{study_id}/sources",
    response_model=list[SourceSummary],
    status_code=status.HTTP_201_CREATED,
)
def upload_sources(
    study_id: UUID,
    session: DatabaseSession,
    embedding_client: EmbeddingClientDependency,
    files: Annotated[list[UploadFile], File()],
    respondent_labels: Annotated[list[str] | None, Form()] = None,
) -> list[SourceModel]:
    """Upload and ingest one or more source files for a study.

    Args:
        study_id: Target study.
        files: Uploaded files (txt/pdf/docx in this stage).
        session: Database session.
        embedding_client: Embedding backend used during ingest.
        respondent_labels: Optional labels aligned with ``files`` order.

    Returns:
        Summaries of created sources.
    """
    get_study_or_404(session, study_id)
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one file is required",
        )

    labels = respondent_labels or []
    if labels and len(labels) != len(files):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="respondent_labels length must match files length",
        )

    created_sources: list[SourceModel] = []
    with TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        for index, upload in enumerate(files):
            filename = upload.filename or f"upload_{index}"
            destination = temporary_root / filename
            destination.write_bytes(upload.file.read())
            label = labels[index] if labels else None
            if label == "":
                label = None
            try:
                source = ingest_source(
                    session=session,
                    study_id=study_id,
                    file_path=destination,
                    respondent_label=label,
                    embedding_client=embedding_client,
                )
            except StudyNotFoundError as error:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(error),
                ) from error
            except ValueError as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=str(error),
                ) from error
            created_sources.append(source)

    return created_sources


@router.get("/sources/{source_id}", response_model=Source)
def get_source(source_id: UUID, session: DatabaseSession) -> SourceModel:
    """Get one source including extracted raw text."""
    return get_source_or_404(session, source_id)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: UUID, session: DatabaseSession) -> None:
    """Delete a source and its chunks."""
    source = get_source_or_404(session, source_id)
    session.delete(source)
    session.flush()
