export PATH := $(HOME)/.n/bin:$(PATH)

.PHONY: bootstrap install dev dev-api dev-frontend lint format typecheck test clean

bootstrap: install
	@[ -f .env ] || cp .env.example .env
	@echo "Bootstrap complete. Edit .env with your credentials."

install:
	uv sync --all-groups
	cd frontend && npm ci

dev:
	@echo "not implemented yet"

dev-api:
	@echo "not implemented yet"

dev-frontend:
	@echo "not implemented yet"

lint:
	uv run ruff check .
	cd frontend && npm run lint

format:
	uv run ruff format .

typecheck:
	@echo "not implemented yet"

test:
	uv run pytest

clean:
	@echo "not implemented yet"
