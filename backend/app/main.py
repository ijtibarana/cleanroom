from __future__ import annotations

from uuid import uuid4
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .analyzer import RepositoryAnalyzer
from .models import AuditRecord, AuditRequest, AuditState, CheckStatus, utc_now
from .reports import record_dict, render_html
from .store import AuditStore

app = FastAPI(title="CleanRoom", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
store = AuditStore()

def _overall(checks) -> CheckStatus:
    statuses = {check.status for check in checks}
    if CheckStatus.FAIL in statuses:
        return CheckStatus.FAIL
    if CheckStatus.UNVERIFIED in statuses:
        return CheckStatus.UNVERIFIED
    return CheckStatus.PASS


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cleanroom-backend"}


@app.post("/api/audits", response_model=AuditRecord, status_code=201)
def create_audit(request: AuditRequest) -> AuditRecord:
    try:
        selected = request.selected_path()
        analyzer = RepositoryAnalyzer(selected, verify_docker=request.verify_docker, verify_tests=request.verify_tests)
        checks, logs, metadata = analyzer.analyze()
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    now = utc_now()
    audit_id = uuid4().hex
    root = analyzer.root
    record = AuditRecord(
        id=audit_id,
        state=AuditState.COMPLETED,
        repository=root.name or str(root),
        repository_path=str(root),
        created_at=now,
        completed_at=utc_now(),
        overall_status=_overall(checks),
        checks=checks,
        logs=logs,
        metadata=metadata,
    )
    return store.put(record)


def _get(audit_id: str) -> AuditRecord:
    record = store.get(audit_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    return record


@app.get("/api/audits/{audit_id}", response_model=AuditRecord)
def get_audit(audit_id: str) -> AuditRecord:
    return _get(audit_id)


@app.get("/api/audits/{audit_id}/logs")
def get_logs(audit_id: str) -> dict:
    record = _get(audit_id)
    return {"audit_id": audit_id, "logs": [log.model_dump(mode="json") for log in record.logs]}


@app.get("/api/audits/{audit_id}/report.json")
def get_json_report(audit_id: str) -> JSONResponse:
    return JSONResponse(content=record_dict(_get(audit_id)))


@app.get("/api/audits/{audit_id}/report.html", response_class=HTMLResponse)
def get_html_report(audit_id: str) -> HTMLResponse:
    return HTMLResponse(content=render_html(_get(audit_id)))


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
