.PHONY: test api frontend-build frontend-test audit

test:
	python3 -m pytest

api:
	python3 -m uvicorn app.main:app --app-dir services/api --reload

frontend-build:
	npm --prefix apps/nova run build

frontend-test:
	npm --prefix apps/nova run test:static

audit:
	python3 scripts/audit-coupling.py
