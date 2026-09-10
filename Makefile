.PHONY: install lint test generate-contract-reference-proto run-orchestrator run-market-analyst-durable

install:
	uv sync --all-packages --all-groups

lint:
	uv run ruff check .

test:
	uv run --all-packages pytest

generate-contract-reference-proto:
	uv run python -m grpc_tools.protoc --proto_path=packages/contracts/proto --python_out=packages/contracts/src --grpc_python_out=packages/contracts/src packages/contracts/proto/distributed_agent_contracts/competitor/v1/competitor.proto

run-orchestrator:
	uv run --env-file services/orchestrator/.env --package orchestrator opentelemetry-instrument uvicorn orchestrator.main:app --reload

run-market-analyst-durable:
	uv run --package market-analyst --extra dev-server langgraph up --api-version 0.14.0 --config langgraph.market-analyst.json --port 8001 --wait
