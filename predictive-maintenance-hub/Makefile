.PHONY: install dev up down test test-unit test-integration test-frontend lint demo incident
PY ?= python3

install:            ## install Python dev dependencies
	$(PY) -m pip install -r requirements-dev.txt

dev:                ## run API + UI locally with SQLite and demo data (http://localhost:8000)
	SEED_DEMO_DATA=true $(PY) backend/wsgi.py

up:                 ## whole system in containers (app, PostgreSQL, alerter, on-call agent)
	docker compose up --build

down:
	docker compose down -v

test:               ## ALL tests with a single command: backend unit+integration, on-call agent, frontend
	$(PY) -m pytest
	cd frontend && node --test "tests/*.test.js"

test-unit:
	$(PY) -m pytest -m unit
test-integration:
	$(PY) -m pytest -m integration
test-frontend:
	cd frontend && node --test "tests/*.test.js"

demo:               ## send realistic traffic to a running instance
	$(PY) scripts/simulate_traffic.py

incident:           ## break production-like config and watch the on-call agent fix it
	$(PY) scripts/simulate_incident.py
