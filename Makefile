.PHONY: install db run web admin create-admin test lint eval eval-l1 reseed types index

install:
	cd server && uv sync
	cd web && npm install
	cd admin && npm install

db:
	docker compose up -d db

run:
	cd server && uv run uvicorn clinic_bot.api.app:app --reload --port 8000

web:
	cd web && npm run dev

admin:
	cd admin && npm run dev

create-admin:
	cd server && uv run clinic-create-admin --email $(EMAIL)

test:
	cd server && uv run pytest
	cd web && npm test
	cd admin && npm test

lint:
	cd server && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports
	cd web && npm run lint && npm run typecheck
	cd admin && npm run lint && npm run typecheck

eval:
	cd server && uv run python eval/run_red_flag_eval.py

eval-l1:
	cd server && uv run python eval/run_red_flag_eval.py --layer1-only --out eval/results.layer1.md

reseed:
	cd server && uv run clinic-reseed

index:
	cd server && uv run clinic-build-index

types:
	cd server && uv run python -m clinic_bot.conversation.result > ../web/src/ui/ui.schema.json
	cd web && npm run types
