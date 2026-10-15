.PHONY: test backend-test frontend-build run

test: backend-test frontend-build

backend-test:
	python3 -m pytest -q backend/tests

frontend-build:
	cd frontend && npm run build

run:
	python3 -m uvicorn app.main:app --app-dir backend --reload --port 8000
