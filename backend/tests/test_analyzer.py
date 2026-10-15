from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analyzer import RepositoryAnalyzer
from app.models import CheckStatus


def make_repo(root: Path, *, healthy: bool = True, unsafe: bool = False) -> Path:
    root.mkdir()
    git = root / ".git" / "refs" / "heads"
    git.mkdir(parents=True)
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "main").write_text("0123456789abcdef0123456789abcdef01234567\n")
    (root / "package.json").write_text(json.dumps({"scripts": {"test": "pytest"}}))
    if healthy:
        (root / "package-lock.json").write_text("{}\n")
        (root / ".nvmrc").write_text("20.11.1\n")
        (root / "Dockerfile").write_text("FROM node:20.11.1\n")
        (root / "README.md").write_text("## Setup\nInstall dependencies.\n## Run\nRun it.\n## Test\n`npm test`\n")
        (root / ".env.example").write_text("API_KEY=your-api-key\n")
    else:
        (root / "README.md").write_text("How to run this project.\n")
    if unsafe:
        (root / "notes.txt").write_text("TOKEN=ghp_1234567890abcdefghijkl\nSee /home/alice/private/project\n")
        (root / ".env.example").write_text("API_TOKEN=real-secret-value\n")
    return root


def result_map(root: Path, **options):
    results, logs, metadata = RepositoryAnalyzer(root, **options).analyze()
    return {result.id: result for result in results}, logs, metadata


def test_healthy_fixture_passes_static_checks_and_truthfully_unverifies_docker(tmp_path: Path):
    results, logs, _ = result_map(make_repo(tmp_path / "healthy"), verify_docker=True, verify_tests=True)

    assert results["git"].status is CheckStatus.PASS
    assert results["lockfile"].status is CheckStatus.PASS
    assert results["runtime"].status is CheckStatus.PASS
    assert results["readme"].status is CheckStatus.PASS
    assert results["env-example"].status is CheckStatus.PASS
    assert results["absolute-paths"].status is CheckStatus.PASS
    # The environment may or may not have Docker; either outcome must be explicit.
    assert results["dockerfile"].status in {CheckStatus.PASS, CheckStatus.UNVERIFIED, CheckStatus.FAIL}
    if results["dockerfile"].status is not CheckStatus.PASS:
        assert results["test-command"].status is CheckStatus.UNVERIFIED
        assert any(log.check_id == "dockerfile" for log in logs)


def test_incomplete_fixture_reports_missing_requirements_without_crashing(tmp_path: Path):
    results, _, _ = result_map(make_repo(tmp_path / "incomplete", healthy=False), verify_docker=False, verify_tests=False)

    assert results["lockfile"].status is CheckStatus.FAIL
    assert results["runtime"].status is CheckStatus.FAIL
    assert results["dockerfile"].status is CheckStatus.FAIL
    assert results["test-command"].status is CheckStatus.SKIPPED
    assert results["readme"].status is CheckStatus.FAIL
    assert results["env-example"].status is CheckStatus.FAIL


def test_unsafe_fixture_detects_paths_and_redacts_secret_evidence(tmp_path: Path):
    results, _, _ = result_map(make_repo(tmp_path / "unsafe", unsafe=True), verify_docker=False, verify_tests=False)

    assert results["absolute-paths"].status is CheckStatus.FAIL
    assert results["env-example"].status is CheckStatus.FAIL
    evidence = "\n".join(item for result in results.values() for item in result.evidence)
    assert "ghp_1234567890abcdefghijkl" not in evidence
    assert "real-secret-value" not in evidence


def test_outside_symlink_is_reported_and_not_followed(tmp_path: Path):
    root = make_repo(tmp_path / "symlinked")
    outside = tmp_path / "outside.txt"
    outside.write_text("TOKEN=secret\n")
    (root / "outside-link.txt").symlink_to(outside)

    results, _, _ = result_map(root, verify_docker=False, verify_tests=False)
    assert results["absolute-paths"].status is CheckStatus.FAIL
