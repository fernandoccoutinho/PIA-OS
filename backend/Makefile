.PHONY: install install-dev run test lint format check migrate docker-up docker-down docker-up-prod docker-down-prod clean check-api-docs generate-changelog

install:
	pip install -r requirements/base.txt

install-dev:
	pip install -r requirements/dev.txt

run:
	uvicorn main:app --reload

test:
	pytest

lint:
	ruff check .

format:
	black .

format-check:
	black --check .

check: lint format-check test

ci:
	bash scripts/run_ci_checks.sh

check-api-docs:
	PYTHONPATH=. python scripts/check_api_docs.py

check-docs:
	PYTHONPATH=. python scripts/check_docs_consistency.py

generate-changelog:
	PYTHONPATH=. python scripts/generate_changelog.py

migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(m)"

docker-up:
	bash deploy/scripts/start.sh dev

docker-down:
	bash deploy/scripts/stop.sh dev --volumes

docker-up-prod:
	bash deploy/scripts/start.sh prod

docker-down-prod:
	bash deploy/scripts/stop.sh prod

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
