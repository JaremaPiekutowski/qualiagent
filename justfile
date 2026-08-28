# QualiAgent development recipes

set dotenv-load := false

default:
    @just --list

# Run the same quality checks as CI: ruff, mypy, pytest
check:
    uv run ruff check qualiagent tests
    uv run ruff format --check qualiagent tests
    uv run mypy qualiagent
    uv run pytest tests/ -q
