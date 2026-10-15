# CleanRoom MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use the repository's existing test command and keep each milestone independently runnable.

**Goal:** Build a reproducible local CleanRoom MVP that audits a selected repository against the eight blueprint checks and presents evidence-backed results in a browser.

**Architecture:** A Python 3.11 FastAPI service owns repository inspection, audit persistence, JSON/HTML reports, and optional Docker verification. A Vite React/TypeScript client calls the API and renders a dashboard, audit form, check results, and logs. The analyzer is deliberately deterministic and treats missing tooling as `UNVERIFIED` rather than silently passing.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, pytest, React, TypeScript, Vite, Docker (optional at runtime).

## Global Constraints

- Keep all project dependencies and configuration inside this repository.
- Use no secrets; `.env.example` contains placeholders only.
- Never execute audited repository scripts directly on the host.
- Docker verification is isolated, network-disabled, resource-limited, and reported as `UNVERIFIED` when Docker is unavailable.
- One offline test command must be available as `make test`.

## Milestones

1. Implement the deterministic analyzer, eight checks, safe evidence redaction, report serialization, API endpoints, and fixture tests.
2. Add the browser UI for starting an audit, viewing status/results/logs, and downloading reports.
3. Add Docker/reproducibility files, README, fixtures, and run the complete offline test command.
