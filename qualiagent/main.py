"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qualiagent.api.routers import analysis, reports, sources, studies
from qualiagent.config import get_settings
from qualiagent.console_logging import configure_console_logging
from qualiagent.sql_admin import mount_sql_admin


@asynccontextmanager
async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
    """Configure logging when the API starts.

    Args:
        _application: FastAPI application instance.
    """
    settings = get_settings()
    configure_console_logging(settings.log_level)
    yield


def create_app() -> FastAPI:
    """Build and return the FastAPI application.

    Returns:
        Configured FastAPI app with API routers and SQLAdmin.
    """
    settings = get_settings()
    application = FastAPI(
        title="QualiAgent",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(studies.router)
    application.include_router(sources.router)
    application.include_router(analysis.router)
    application.include_router(reports.router)
    mount_sql_admin(application, settings)
    return application


app = create_app()
