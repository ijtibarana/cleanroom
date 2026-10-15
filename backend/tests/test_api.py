from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def fixture_repo(root: Path) -> Path:
    (root / ".git" / "refs" / "heads").mkdir(parents=True)
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (root / ".git" / "refs" / "heads" / "main").write_text("0123456789abcdef0123456789abcdef01234567\n")
    (root / "package.json").write_text(json.dumps({"scripts": {"test": "pytest"}}))
    (root / "package-lock.json").write_text("{}\n")
    (root / ".nvmrc").write_text("20\n")
    (root / "Dockerfile").write_text("FROM node:20\n")
    (root / "README.md").write_text("Setup\nRun\nTest: npm test\n")
    (root / ".env.example").write_text("API_KEY=placeholder\n")
    return root


def test_health_and_report_exports_match_api_results(tmp_path: Path):
    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"

    response = client.post("/api/audits", json={"repo_path": str(fixture_repo(tmp_path / "project")), "verify_docker": False, "verify_tests": False})
    assert response.status_code == 201
    audit = response.json()
    audit_id = audit["id"]

    fetched = client.get(f"/api/audits/{audit_id}")
    exported = client.get(f"/api/audits/{audit_id}/report.json")
    assert fetched.status_code == exported.status_code == 200
    assert fetched.json() == exported.json()
    assert {item["id"] for item in fetched.json()["checks"]} == {
        "git", "lockfile", "runtime", "dockerfile", "test-command", "readme", "env-example", "absolute-paths"
    }

    logs = client.get(f"/api/audits/{audit_id}/logs")
    assert logs.status_code == 200
    assert logs.json()["audit_id"] == audit_id
    html = client.get(f"/api/audits/{audit_id}/report.html")
    assert html.status_code == 200
    assert "CleanRoom audit" in html.text
    assert audit_id in html.text


def test_api_rejects_missing_or_non_directory_repository(tmp_path: Path):
    client = TestClient(app)
    assert client.post("/api/audits", json={}).status_code == 422
    assert client.post("/api/audits", json={"repo_path": str(tmp_path / "missing")}).status_code == 400
