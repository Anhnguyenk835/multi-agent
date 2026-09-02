# LiteLLM Gateway Infrastructure

This directory owns the local inference boundary. Agent services call logical
routes through a service-scoped virtual key. Provider credentials, Redis AUTH,
and LiteLLM administration credentials exist only on the gateway runtime.

The local gateway foundation always includes LiteLLM, Postgres, and Redis.
Redis persists its `/data` directory with AOF (`everysec`) and RDB snapshots so
coordination state survives container and host restarts. This is infrastructure
readiness for future cache, queue, session, and lock use cases; none of those
application capabilities are enabled in the current milestone.

## Local Runtime

Copy `.env.example` to `.env`, set provider keys, the LiteLLM master/salt keys,
and a generated `REDIS_PASSWORD`:

```bash
openssl rand -base64 48
docker compose up -d redis db litellm
```

Run from the repository root. Redis is private to the Compose network and uses
AUTH. LiteLLM waits for Redis and Postgres, while the diagnostic UI remains
loopback-only at `http://127.0.0.1:4000/ui`.

The Redis volume is `distributed-agents-demo_litellm-redis-data`. Do not remove
it during a normal restart:

```bash
docker compose restart redis
docker compose restart litellm
```

To intentionally reset all local gateway state, stop the gateway services and
remove both gateway-owned volumes. This deletes LiteLLM keys, usage records,
Redis coordination state, AOF data, and RDB snapshots; it does not touch the
orchestrator database or other service volumes.

```bash
docker compose stop litellm redis db
docker volume rm distributed-agents-demo_litellm-postgres-data
docker volume rm distributed-agents-demo_litellm-redis-data
docker compose up -d redis db litellm
```

Generate fresh virtual keys only after an intentional reset:

```bash
export LLM_GATEWAY_ADMIN_URL=http://127.0.0.1:4000
export LITELLM_MASTER_KEY=<gateway-master-key>
./scripts/provision-virtual-key.sh researcher
```

Store each generated value only as that service's `LLM_GATEWAY_API_KEY`. The
gateway returns the virtual key once; rotation means provisioning a replacement,
updating the service secret, then revoking the old key.

## Current Redis Scope

Redis is configured for LiteLLM coordination: shared key limits, budgets, and
router state. LiteLLM response caching remains explicitly disabled. Semantic
caching, queues, delayed jobs, session state, conversation memory, distributed
locks, MCP/tool controls, and global prompt-injection guardrails are future
phases that can use this durable Redis foundation when their ownership and
correctness rules are defined.

Cloud deployment is intentionally out of scope until the local gateway is
validated end to end.
