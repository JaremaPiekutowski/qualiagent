"""API tests for studies and sources."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from qualiagent.dependencies import get_db, get_embedding_client
from qualiagent.main import app
from tests.conftest import EmbeddingClientFactory
from tests.stub_embedding import StubEmbeddingClient
from tests.test_source_ingest import write_sample_docx, write_sample_pdf, write_sample_txt


@pytest.fixture
def client(
    session: Session,
    make_embedding_client: EmbeddingClientFactory,
) -> Generator[TestClient]:
    def override_get_db() -> Generator[Session]:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    stub_client = make_embedding_client(dimensions=1024)

    def override_get_embedding_client() -> StubEmbeddingClient:
        return stub_client

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_embedding_client] = override_get_embedding_client
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    session.rollback()


def test_openapi_exposes_study_and_source_paths(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/studies" in paths
    assert "/studies/{study_id}" in paths
    assert "/studies/{study_id}/sources" in paths
    assert "/sources/{source_id}" in paths


def test_study_crud_and_source_upload(client: TestClient, tmp_path: Path) -> None:
    create_response = client.post(
        "/studies",
        json={
            "name": "API Demo Study",
            "research_questions": ["Jak wygląda zmiana?"],
            "web_search_enabled": False,
        },
    )
    assert create_response.status_code == 201
    study = create_response.json()
    study_id = study["id"]
    assert study["name"] == "API Demo Study"

    list_response = client.get("/studies")
    assert list_response.status_code == 200
    assert any(item["id"] == study_id for item in list_response.json())

    patch_response = client.patch(
        f"/studies/{study_id}",
        json={
            "research_questions": ["Jak wygląda zmiana?", "Co blokuje wdrożenie?"],
            "web_search_enabled": True,
        },
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["web_search_enabled"] is True
    assert len(patch_response.json()["research_questions"]) == 2

    txt_path = write_sample_txt(tmp_path)
    docx_path = write_sample_docx(tmp_path)
    pdf_path = write_sample_pdf(tmp_path)
    upload_response = client.post(
        f"/studies/{study_id}/sources",
        files=[
            ("files", (txt_path.name, txt_path.read_bytes(), "text/plain")),
            (
                "files",
                (
                    docx_path.name,
                    docx_path.read_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            ),
            ("files", (pdf_path.name, pdf_path.read_bytes(), "application/pdf")),
            ("respondent_labels", (None, "R01")),
            ("respondent_labels", (None, "R02")),
            ("respondent_labels", (None, "R03")),
        ],
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()
    assert len(uploaded) == 3
    assert [item["source_code"] for item in uploaded] == ["S01", "S02", "S03"]
    assert all(item["status"] == "indexed" for item in uploaded)
    assert "raw_text" not in uploaded[0]

    sources_response = client.get(f"/studies/{study_id}/sources")
    assert sources_response.status_code == 200
    assert len(sources_response.json()) == 3

    source_id = uploaded[0]["id"]
    detail_response = client.get(f"/sources/{source_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["raw_text"]
    assert detail_response.json()["respondent_label"] == "R01"

    delete_source_response = client.delete(f"/sources/{source_id}")
    assert delete_source_response.status_code == 204

    delete_study_response = client.delete(f"/studies/{study_id}")
    assert delete_study_response.status_code == 204

    missing = client.get(f"/studies/{study_id}")
    assert missing.status_code == 404
