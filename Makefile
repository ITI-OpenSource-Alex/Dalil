.PHONY: up down logs test

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	@echo "Running Gateway Service tests..."
	cd services/gateway && go test ./...
	@echo "Running Speaking Service tests..."
	cd services/speaking && go test ./...
	@echo "Running RAG Service tests..."
	docker compose run --entrypoint "python -m pytest" rag