from __future__ import annotations

import hashlib
import importlib

import pytest

from feme.db import Database


def _db(tmp_path) -> Database:
    db = Database(str(tmp_path / "auth.sqlite"))
    db.init()
    return db


def _load_api(monkeypatch, tmp_path, *, readonly_key: str = "", admin_key: str = ""):
    monkeypatch.setenv("FEME_DB_BACKEND", "sqlite")
    monkeypatch.setenv("FEME_DB_PATH", str(tmp_path / "api.sqlite"))
    monkeypatch.delenv("FEME_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FEME_API_KEY_READONLY", readonly_key)
    monkeypatch.setenv("FEME_API_KEY_ADMIN", admin_key)
    monkeypatch.setenv("FEME_API_KEY_VIEWER", "")
    monkeypatch.setenv("FEME_API_KEY_REVIEWER", "")
    monkeypatch.setenv("FEME_API_KEY_EDITOR", "")
    monkeypatch.setenv(
        "FEME_API_AUTH_REQUIRED",
        "true" if (readonly_key or admin_key) else "false",
    )

    config = importlib.import_module("feme.config")
    importlib.reload(config)
    api = importlib.import_module("feme.api")
    return importlib.reload(api)


def _load_api_with_roles(
    monkeypatch,
    tmp_path,
    *,
    viewer_key: str = "",
    reviewer_key: str = "",
    editor_key: str = "",
    admin_key: str = "",
):
    monkeypatch.setenv("FEME_DB_BACKEND", "sqlite")
    monkeypatch.setenv("FEME_DB_PATH", str(tmp_path / "api.sqlite"))
    monkeypatch.delenv("FEME_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FEME_API_KEY_READONLY", "")
    monkeypatch.setenv("FEME_API_KEY_VIEWER", viewer_key)
    monkeypatch.setenv("FEME_API_KEY_REVIEWER", reviewer_key)
    monkeypatch.setenv("FEME_API_KEY_EDITOR", editor_key)
    monkeypatch.setenv("FEME_API_KEY_ADMIN", admin_key)
    monkeypatch.setenv(
        "FEME_API_AUTH_REQUIRED",
        "true" if (viewer_key or reviewer_key or editor_key or admin_key) else "false",
    )

    config = importlib.import_module("feme.config")
    importlib.reload(config)
    api = importlib.import_module("feme.api")
    return importlib.reload(api)


def test_api_write_endpoints_require_admin_key(tmp_path, monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")

    api = _load_api(
        monkeypatch,
        tmp_path,
        readonly_key="read-only-key",
        admin_key="admin-key",
    )

    db = _db(tmp_path)
    original_db = api.database
    api.database = db
    try:
        client = fastapi_testclient.TestClient(api.app)

        health = client.get("/health")
        assert health.status_code == 200

        missing = client.post(
            "/ingest/governed",
            json={"text": "Auth check", "project_id": "auth"},
        )
        assert missing.status_code == 401
        assert missing.json()["detail"] == "missing_api_key"

        readonly = client.post(
            "/ingest/governed",
            headers={"X-FEME-API-Key": "read-only-key"},
            json={"text": "Auth check", "project_id": "auth"},
        )
        assert readonly.status_code == 403
        assert readonly.json()["detail"] == "insufficient_api_scope"

        admin = client.post(
            "/ingest/governed",
            headers={"X-FEME-API-Key": "admin-key"},
            json={"text": "Auth check", "project_id": "auth"},
        )
        assert admin.status_code == 200
        assert "evidence_id" in admin.json()

        readonly_search = client.post(
            "/search",
            headers={"X-FEME-API-Key": "read-only-key"},
            json={"query": "auth", "project_id": "auth", "top_k": 5},
        )
        assert readonly_search.status_code == 200

        with db.connect() as con:
            rows = con.execute("""
                SELECT path, required_role, resolved_role, decision, detail, principal_hash
                FROM api_request_audit
                ORDER BY created_at
                """).fetchall()
        assert rows
        assert any(
            r["path"] == "/ingest/governed"
            and r["decision"] == "denied"
            and r["detail"] == "missing_api_key"
            and r["required_role"] == "editor"
            for r in rows
        )
        assert any(
            r["path"] == "/ingest/governed"
            and r["decision"] == "denied"
            and r["detail"] == "insufficient_api_scope"
            and r["resolved_role"] == "viewer"
            for r in rows
        )
        assert any(
            r["path"] == "/ingest/governed"
            and r["decision"] == "allowed"
            and r["resolved_role"] == "admin"
            and r["principal_hash"] == hashlib.sha256(b"admin-key").hexdigest()[:16]
            for r in rows
        )
    finally:
        api.database = original_db


def test_api_write_endpoints_allow_legacy_mode_without_keys(tmp_path, monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")

    api = _load_api(monkeypatch, tmp_path)

    db = _db(tmp_path)
    original_db = api.database
    api.database = db
    try:
        client = fastapi_testclient.TestClient(api.app)
        response = client.post(
            "/ingest/governed",
            json={"text": "Legacy mode", "project_id": "auth"},
        )
        assert response.status_code == 200
        assert "evidence_id" in response.json()
    finally:
        api.database = original_db


def test_api_role_scopes_viewer_reviewer_editor_admin(tmp_path, monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")

    api = _load_api_with_roles(
        monkeypatch,
        tmp_path,
        viewer_key="viewer-key",
        reviewer_key="reviewer-key",
        editor_key="editor-key",
        admin_key="admin-key",
    )

    db = _db(tmp_path)
    original_db = api.database
    api.database = db
    try:
        client = fastapi_testclient.TestClient(api.app)

        viewer_search = client.post(
            "/search",
            headers={"X-FEME-API-Key": "viewer-key"},
            json={"query": "auth", "project_id": "auth", "top_k": 5},
        )
        assert viewer_search.status_code == 200

        viewer_review_pending = client.get(
            "/review/pending",
            headers={"X-FEME-API-Key": "viewer-key"},
        )
        assert viewer_review_pending.status_code == 403
        assert viewer_review_pending.json()["detail"] == "insufficient_api_scope"

        reviewer_pending = client.get(
            "/review/pending",
            headers={"X-FEME-API-Key": "reviewer-key"},
        )
        assert reviewer_pending.status_code == 200

        reviewer_ingest = client.post(
            "/ingest/governed",
            headers={"X-FEME-API-Key": "reviewer-key"},
            json={"text": "scope check", "project_id": "auth"},
        )
        assert reviewer_ingest.status_code == 403
        assert reviewer_ingest.json()["detail"] == "insufficient_api_scope"

        editor_ingest = client.post(
            "/ingest/governed",
            headers={"X-FEME-API-Key": "editor-key"},
            json={"text": "scope check", "project_id": "auth"},
        )
        assert editor_ingest.status_code == 200

        editor_backup = client.post(
            "/backup",
            headers={"X-FEME-API-Key": "editor-key"},
        )
        assert editor_backup.status_code == 403
        assert editor_backup.json()["detail"] == "insufficient_api_scope"

        admin_backup = client.post(
            "/backup",
            headers={"X-FEME-API-Key": "admin-key"},
        )
        assert admin_backup.status_code == 200

        with db.connect() as con:
            rows = con.execute("""
                SELECT path, required_role, resolved_role, decision, detail
                FROM api_request_audit
                ORDER BY created_at
                """).fetchall()
        assert any(
            r["path"] == "/search"
            and r["required_role"] == "viewer"
            and r["resolved_role"] == "viewer"
            and r["decision"] == "allowed"
            for r in rows
        )
        assert any(
            r["path"] == "/review/pending"
            and r["required_role"] == "reviewer"
            and r["resolved_role"] == "viewer"
            and r["decision"] == "denied"
            and r["detail"] == "insufficient_api_scope"
            for r in rows
        )
        assert any(
            r["path"] == "/backup"
            and r["required_role"] == "admin"
            and r["resolved_role"] == "admin"
            and r["decision"] == "allowed"
            for r in rows
        )
    finally:
        api.database = original_db
