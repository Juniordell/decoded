.PHONY: up down psql api web dev types

COMPOSE := docker compose -f infra/compose.yaml

# Sobe só a infraestrutura, sem a api
up:
	$(COMPOSE) up -d postgres qdrant redis

# Sobe tudo, incluindo o container da api (teste de build)
up-all:
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

mlflow:
	cd apps/api && poetry run mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000

eval:
	cd apps/api && poetry run python evals/runner.py

variance:
	cd apps/api && poetry run python optimization/measure_variance.py --runs 5

eval-sections:
	cd apps/api && poetry run python evals/runner.py

eval-modes:
	cd apps/api && poetry run python evals/modes_runner.py

eval-all: eval-sections eval-modes
	cd apps/api && poetry run python evals/gate.py

gate:
	cd apps/api && poetry run python evals/gate.py

prefect-server:
	cd apps/api && poetry run prefect server start

prefect-worker:
	cd apps/api && set -a && . ./.env && set +a && poetry run prefect worker start --pool decoded-pool

prefect-deploy:
	cd apps/api && poetry run prefect deploy --all

run-ingestion:
	cd apps/api && poetry run prefect deployment run 'decoded-ingestion/ingestion-hourly'

run-weekly-dry:
	cd apps/api && poetry run prefect deployment run 'decoded-weekly/weekly-cycle' --param skip_send=true

run-weekly:
	cd apps/api && poetry run prefect deployment run 'decoded-weekly/weekly-cycle'

prefect-prod:
	fly proxy 4200:4200 --app decoded-worker