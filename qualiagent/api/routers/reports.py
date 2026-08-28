"""Report endpoints for analysis sections and DOCX download."""

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from qualiagent.api.routers.analysis import get_analysis_run_or_404
from qualiagent.dependencies import get_db
from qualiagent.models import Section as SectionModel
from qualiagent.report import build_analysis_run_report
from qualiagent.schemas import Section

router = APIRouter(tags=["reports"])

DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/analysis-runs/{analysis_run_id}/sections", response_model=list[Section])
def list_sections(analysis_run_id: UUID, session: DatabaseSession) -> list[SectionModel]:
    """List sections and citations for an analysis run."""
    get_analysis_run_or_404(session, analysis_run_id)
    return list(
        session.scalars(
            select(SectionModel)
            .where(SectionModel.analysis_run_id == analysis_run_id)
            .options(selectinload(SectionModel.citations))
            .order_by(SectionModel.position)
        ).all()
    )


@router.get("/analysis-runs/{analysis_run_id}/report.docx")
def download_report(analysis_run_id: UUID, session: DatabaseSession) -> Response:
    """Build and download the DOCX report for an analysis run."""
    analysis_run = get_analysis_run_or_404(session, analysis_run_id)
    if analysis_run.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Report is available only for completed runs",
        )
    try:
        content = build_analysis_run_report(session, analysis_run_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    filename = Path(f"qualiagent-{analysis_run_id}.docx").name
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
