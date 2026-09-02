.PHONY: install lint test generate-contract-reference-proto run-orchestrator

install:
	uv sync --all-packages --all-groups

lint:
	uv run ruff check .

test:
	uv run --all-packages pytest

generate-contract-reference-proto:
	uv run python -m grpc_tools.protoc --proto_path=packages/contracts/proto --python_out=packages/contracts/src --grpc_python_out=packages/contracts/src packages/contracts/proto/distributed_agent_contracts/market/v1/market.proto

run-orchestrator:
	uv run --env-file services/orchestrator/.env --package orchestrator opentelemetry-instrument uvicorn orchestrator.main:app --reload
