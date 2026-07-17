export PATH := $(HOME)/.n/bin:$(PATH)

.PHONY: bootstrap install dev dev-api dev-frontend lint format typecheck test eval eval-dspy db-push frontend up-build up down logs logs-temporal logs-langfuse clean

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
	cd frontend && npm run dev

frontend:
	cd frontend && npm run dev

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy api_gateway ai_worker maps_bridge website_bridge shared
	cd frontend && npm run lint

format:
	uv run ruff format .

typecheck:
	@echo "not implemented yet"

test:
	uv run pytest
	cd frontend && node node_modules/.bin/vitest --run

eval:
	@mkdir -p evals/results
	@test -f .env || (echo "Missing .env — copy from .env.example" && exit 1)
	npx promptfoo@0.120.19 eval -c evals/promptfooconfig.yaml --env-file .env --output evals/results/latest.json; \
	pf_exit=$$?; \
	uv run python evals/scripts/metrics.py evals/results/latest.json; \
	exit $$pf_exit

eval-dspy:
	@mkdir -p evals/results
	@test -f .env || (echo "Missing .env — copy from .env.example" && exit 1)
	PYTHONPATH=$(CURDIR) uv run python evals/dspy_eval.py $(ARGS)

db-push:
	cd frontend && npx prisma db push --accept-data-loss
	cd frontend && npx prisma generate

up-build:
	docker compose up --build -d

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

logs-temporal:
	docker compose logs -f temporal temporal-ui

logs-langfuse:
	docker compose logs -f langfuse langfuse-worker

clean:
	@echo "not implemented yet"
