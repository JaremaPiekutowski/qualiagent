"""SQLAdmin views and authentication for QualiAgent models."""

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse

from qualiagent.config import Settings
from qualiagent.database import engine
from qualiagent.models import AnalysisRun, Chunk, Citation, Section, Source, Study


class AdminAuth(AuthenticationBackend):
    """Simple username/password gate for the SQLAdmin UI."""

    def __init__(self, settings: Settings) -> None:
        """Create auth backend from application settings.

        Args:
            settings: Runtime settings with admin credentials.
        """
        super().__init__(secret_key=settings.admin_secret_key)
        self.admin_username = settings.admin_username
        self.admin_password = settings.admin_password

    async def login(self, request: Request) -> bool:
        """Validate credentials from the login form.

        Args:
            request: Incoming login request.

        Returns:
            True when credentials match configured admin user.
        """
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        if username != self.admin_username or password != self.admin_password:
            return False
        if not self.admin_password:
            return False
        request.session.update({"admin_authenticated": True})
        return True

    async def logout(self, request: Request) -> bool:
        """Clear the admin session.

        Args:
            request: Incoming logout request.

        Returns:
            Always True after clearing the session.
        """
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool | RedirectResponse:
        """Allow access only for authenticated admin sessions.

        Args:
            request: Incoming admin request.

        Returns:
            True when authenticated, otherwise False.
        """
        return bool(request.session.get("admin_authenticated"))


class StudyAdmin(ModelView, model=Study):
    """Admin view for studies."""

    column_list = [
        Study.id,
        Study.name,
        Study.web_search_enabled,
        Study.created_at,
    ]
    column_searchable_list = [Study.name]
    column_sortable_list = [Study.name, Study.created_at]
    form_excluded_columns = [Study.sources, Study.analysis_runs]


class SourceAdmin(ModelView, model=Source):
    """Admin view for sources."""

    column_list = [
        Source.id,
        Source.study_id,
        Source.source_code,
        Source.filename,
        Source.kind,
        Source.respondent_label,
        Source.status,
    ]
    column_searchable_list = [Source.filename, Source.source_code, Source.respondent_label]
    column_sortable_list = [Source.source_code, Source.status, Source.kind]
    form_excluded_columns = [Source.chunks, Source.study]


class ChunkAdmin(ModelView, model=Chunk):
    """Admin view for chunks (embeddings hidden)."""

    column_list = [
        Chunk.id,
        Chunk.source_id,
        Chunk.position,
        Chunk.speaker,
        Chunk.text,
    ]
    column_searchable_list = [Chunk.text, Chunk.speaker]
    column_sortable_list = [Chunk.position]
    form_excluded_columns = [Chunk.embedding, Chunk.search_vector, Chunk.source, Chunk.citations]
    column_details_exclude_list = [Chunk.embedding, Chunk.search_vector]


class AnalysisRunAdmin(ModelView, model=AnalysisRun):
    """Admin view for analysis runs."""

    column_list = [
        AnalysisRun.id,
        AnalysisRun.study_id,
        AnalysisRun.thread_id,
        AnalysisRun.status,
        AnalysisRun.created_at,
        AnalysisRun.finished_at,
    ]
    column_searchable_list = [AnalysisRun.thread_id, AnalysisRun.status]
    column_sortable_list = [AnalysisRun.created_at, AnalysisRun.status]
    form_excluded_columns = [AnalysisRun.study, AnalysisRun.sections]


class SectionAdmin(ModelView, model=Section):
    """Admin view for report sections."""

    column_list = [
        Section.id,
        Section.analysis_run_id,
        Section.position,
        Section.research_question,
        Section.coverage,
        Section.respondents_covered,
        Section.respondents_total,
    ]
    column_searchable_list = [Section.research_question, Section.coverage]
    column_sortable_list = [Section.position, Section.coverage]
    form_excluded_columns = [Section.analysis_run, Section.citations]


class CitationAdmin(ModelView, model=Citation):
    """Admin view for citations."""

    column_list = [
        Citation.id,
        Citation.section_id,
        Citation.marker,
        Citation.source_id,
        Citation.chunk_id,
        Citation.verified,
        Citation.quoted_text,
    ]
    column_searchable_list = [Citation.marker, Citation.quoted_text]
    column_sortable_list = [Citation.verified, Citation.marker]
    form_excluded_columns = [Citation.section, Citation.chunk, Citation.source]


def mount_sql_admin(application: object, settings: Settings) -> Admin:
    """Attach SQLAdmin to the FastAPI application.

    Args:
        application: FastAPI app instance.
        settings: Runtime settings used for auth.

    Returns:
        Configured ``Admin`` instance.
    """
    admin = Admin(
        application,  # type: ignore[arg-type]
        engine,
        title="QualiAgent Admin",
        authentication_backend=AdminAuth(settings),
    )
    admin.add_view(StudyAdmin)
    admin.add_view(SourceAdmin)
    admin.add_view(ChunkAdmin)
    admin.add_view(AnalysisRunAdmin)
    admin.add_view(SectionAdmin)
    admin.add_view(CitationAdmin)
    return admin
