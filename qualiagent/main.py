"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from qualiagent.api.routers import sources, studies
from qualiagent.config import get_settings
from qualiagent.console_logging import configure_console_logging


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
        Configured FastAPI app with study and source routers.
    """
    application = FastAPI(
        title="QualiAgent",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(studies.router)
    application.include_router(sources.router)
    return application


app = create_app()
