.PHONY: up down psql api web dev types

COMPOSE := docker compose -f infra/compose.yaml

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

psql:
	$(COMPOSE) exec postgres psql -U decoded -d decoded

api:
	cd apps/api && poetry run uvicorn decoded.main:app --reload --host 0.0.0.0 --port 8000 --app-dir src

web:
	cd apps/web && npm run dev

types:
	cd apps/web && npm run gen:types