from __future__ import annotations

import html
import json
from typing import Any

from .models import AuditRecord


def record_dict(record: AuditRecord) -> dict[str, Any]:
    """Return the same JSON shape used by the API and report exports."""
    return record.model_dump(mode="json")


def render_html(record: AuditRecord) -> str:
    data = record_dict(record)
    rows: list[str] = []
    for check in data["checks"]:
        evidence = "\n".join(check["evidence"]) or "No evidence recorded."
        files = ", ".join(check["files"]) or "-"
        rows.append(
            "<section class='check'>"
            f"<h2><span class='status {html.escape(check['status'].lower())}'>"
            f"{html.escape(check['status'])}</span> {html.escape(check['name'])}</h2>"
            f"<p>{html.escape(check['summary'])}</p>"
            f"<p><strong>Files:</strong> {html.escape(files)}</p>"
            f"<pre>{html.escape(evidence)}</pre>"
            f"<p><strong>Recommendation:</strong> {html.escape(check['recommendation'] or 'None')}</p>"
            "</section>"
        )
    payload = html.escape(json.dumps(data, indent=2, sort_keys=True))
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>CleanRoom audit</title>
<style>body{font:16px system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#17202a}
.check{border:1px solid #d5dbe0;border-radius:8px;padding:1rem;margin:1rem 0}.status{font-size:.75rem;padding:.2rem .4rem;border-radius:4px}
.pass{background:#d9f5df;color:#126329}.fail{background:#ffdcdc;color:#8e1c1c}.unverified{background:#fff0c2;color:#6b4c00}.skipped{background:#e7e9ec;color:#4b5563}
pre{background:#f5f6f7;padding:1rem;white-space:pre-wrap;overflow:auto}code{font-size:.85em}</style></head>
<body><h1>CleanRoom audit</h1>
<p><strong>Repository:</strong> %s<br><strong>Overall:</strong> %s<br><strong>Audit ID:</strong> %s</p>
%s
<details><summary>JSON report</summary><pre>%s</pre></details>
</body></html>""" % (
        html.escape(data["repository"]),
        html.escape(data["overall_status"]),
        html.escape(data["id"]),
        "\n".join(rows),
        payload,
    )
