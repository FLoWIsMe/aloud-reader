.PHONY: up down logs build dev test lint

# Run Aloud in Docker on http://localhost:8787
up:
	docker compose up --build -d
	@echo "Aloud is starting on http://localhost:8787"

down:
	docker compose down

logs:
	docker compose logs -f aloud

build:
	docker build -t aloud-reader .

# Run without Docker (needs Python 3.12+): python -m venv .venv && .venv/bin/pip install -r requirements.txt
dev:
	ALOUD_DATA_DIR=./data python -m server

test:
	python -m pytest -q

lint:
	ruff check server tests && ruff format --check server tests
