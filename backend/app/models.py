from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNVERIFIED = "UNVERIFIED"
    SKIPPED = "SKIPPED"


class AuditState(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CheckResult(BaseModel):
    id: str
    name: str
    status: CheckStatus
    summary: str
    evidence: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    files: list[str] = Field(default_factory=list)


class VerificationLog(BaseModel):
    check_id: str
    command: str
    status: CheckStatus
    output: str = ""
    exit_code: int | None = None
    duration_ms: int | None = None
    container: str = "unavailable"


class AuditRequest(BaseModel):
    # ``path`` is accepted as a convenience for simple API clients while the
    # canonical field remains repo_path.
    repo_path: str = Field(..., min_length=1)
    path: str | None = Field(default=None, min_length=1)
    verify_docker: bool = True
    verify_tests: bool = True

    @model_validator(mode="before")
    @classmethod
    def accept_path_alias(cls, values):
        if isinstance(values, dict) and not values.get("repo_path") and values.get("path"):
            values = dict(values)
            values["repo_path"] = values["path"]
        return values

    def selected_path(self) -> str:
        return self.repo_path


class AuditRecord(BaseModel):
    id: str
    state: AuditState
    repository: str
    repository_path: str
    created_at: datetime
    completed_at: datetime | None = None
    overall_status: CheckStatus
    checks: list[CheckResult]
    logs: list[VerificationLog] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
