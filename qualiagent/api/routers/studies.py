"""Study CRUD endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from qualiagent.dependencies import get_db
from qualiagent.models import Study as StudyModel
from qualiagent.schemas import Study, StudyCreate, StudyUpdate

router = APIRouter(prefix="/studies", tags=["studies"])

DatabaseSession = Annotated[Session, Depends(get_db)]


def get_study_or_404(session: Session, study_id: UUID) -> StudyModel:
    """Load a study or raise 404.

    Args:
        session: Database session.
        study_id: Study identifier.

    Returns:
        Matching study row.

    Raises:
        HTTPException: When the study does not exist.
    """
    study = session.get(StudyModel, study_id)
    if study is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study not found")
    return study


@router.post("", response_model=Study, status_code=status.HTTP_201_CREATED)
def create_study(payload: StudyCreate, session: DatabaseSession) -> StudyModel:
    """Create a new study."""
    study = StudyModel(
        name=payload.name,
        research_questions=payload.research_questions,
        web_search_enabled=payload.web_search_enabled,
    )
    session.add(study)
    session.flush()
    session.refresh(study)
    return study


@router.get("", response_model=list[Study])
def list_studies(session: DatabaseSession) -> list[StudyModel]:
    """List all studies, newest first."""
    return list(session.scalars(select(StudyModel).order_by(StudyModel.created_at.desc())).all())


@router.get("/{study_id}", response_model=Study)
def get_study(study_id: UUID, session: DatabaseSession) -> StudyModel:
    """Get one study by id."""
    return get_study_or_404(session, study_id)


@router.patch("/{study_id}", response_model=Study)
def update_study(
    study_id: UUID,
    payload: StudyUpdate,
    session: DatabaseSession,
) -> StudyModel:
    """Update study name, research questions, or web-search flag."""
    study = get_study_or_404(session, study_id)
    if payload.name is not None:
        study.name = payload.name
    if payload.research_questions is not None:
        study.research_questions = payload.research_questions
    if payload.web_search_enabled is not None:
        study.web_search_enabled = payload.web_search_enabled
    session.flush()
    session.refresh(study)
    return study


@router.delete("/{study_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_study(study_id: UUID, session: DatabaseSession) -> None:
    """Delete a study and cascaded sources."""
    study = get_study_or_404(session, study_id)
    session.delete(study)
    session.flush()
