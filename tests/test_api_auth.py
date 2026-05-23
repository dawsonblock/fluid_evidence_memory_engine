from __future__ import annotations

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
    monkeypatch.setenv("FEME_API_AUTH_REQUIRED", "true" if (readonly_key or admin_key) else "false")

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
