from __future__ import annotations

from threading import RLock

from .models import AuditRecord


class AuditStore:
    """Small process-local store for the MVP API."""

    def __init__(self) -> None:
        self._records: dict[str, AuditRecord] = {}
        self._lock = RLock()

    def put(self, record: AuditRecord) -> AuditRecord:
        with self._lock:
            self._records[record.id] = record
        return record

    def get(self, audit_id: str) -> AuditRecord | None:
        with self._lock:
            return self._records.get(audit_id)
