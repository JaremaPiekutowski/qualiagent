"""LangGraph checkpointer helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse, urlunparse

from langgraph.checkpoint.memory import InMemorySaver

from qualiagent.config import Settings, get_settings

_shared_memory_checkpointer: InMemorySaver | None = None


def sqlalchemy_url_to_psycopg(database_url: str) -> str:
    """Convert a SQLAlchemy Postgres URL to a plain psycopg URL.

    Args:
        database_url: SQLAlchemy URL, possibly with ``+psycopg``.

    Returns:
        ``postgresql://`` URL suitable for LangGraph PostgresSaver.
    """
    parsed = urlparse(database_url)
    scheme = parsed.scheme.split("+", maxsplit=1)[0]
    if scheme not in {"postgresql", "postgres"}:
        raise ValueError(f"Unsupported database URL scheme for checkpointer: {parsed.scheme}")
    return urlunparse(parsed._replace(scheme="postgresql"))


def get_shared_memory_checkpointer() -> InMemorySaver:
    """Return a process-wide in-memory checkpointer for local HITL without Postgres.

    Returns:
        Shared ``InMemorySaver`` instance.
    """
    global _shared_memory_checkpointer
    if _shared_memory_checkpointer is None:
        _shared_memory_checkpointer = InMemorySaver()
    return _shared_memory_checkpointer


@contextmanager
def open_checkpointer(settings: Settings | None = None) -> Iterator[Any]:
    """Yield a LangGraph checkpointer for HITL persistence.

    Uses Postgres when enabled, otherwise a shared in-memory saver.

    Args:
        settings: Optional settings override.

    Yields:
        Checkpointer instance.
    """
    resolved = settings or get_settings()
    if not resolved.use_postgres_checkpointer:
        yield get_shared_memory_checkpointer()
        return

    from langgraph.checkpoint.postgres import PostgresSaver

    connection_string = sqlalchemy_url_to_psycopg(resolved.database_url)
    with PostgresSaver.from_conn_string(connection_string) as checkpointer:
        checkpointer.setup()
        yield checkpointer
