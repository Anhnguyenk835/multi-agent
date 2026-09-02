#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s <researcher|market-agent|analyst|writer>\n' "$0" >&2
  exit 64
}

require_env() {
  local name=$1
  if [[ -z ${!name:-} ]]; then
    printf '%s must be set\n' "$name" >&2
    exit 64
  fi
}

[[ $# -eq 1 ]] || usage

require_env LLM_GATEWAY_ADMIN_URL
require_env LITELLM_MASTER_KEY

case $1 in
  researcher)
    route=research-fast
    budget=25
    rpm=30
    tpm=60000
    parallel=4
    output_tokens=2000
    ;;
  market-agent)
    route=market-standard
    budget=25
    rpm=20
    # A market run can retain several Exa result sets across tool calls. With
    # two concurrent runs, 40k TPM rejects otherwise valid requests before
    # LiteLLM can call the routed provider.
    tpm=120000
    parallel=2
    output_tokens=1800
    ;;
  analyst)
    route=analysis-standard
    budget=15
    rpm=30
    tpm=60000
    parallel=4
    output_tokens=2000
    ;;
  writer)
    route=brief-streaming
    budget=20
    rpm=30
    tpm=90000
    parallel=4
    output_tokens=3000
    ;;
  *) usage ;;
esac

payload=$(jq -n \
  --arg alias "service-$1" \
  --arg route "$route" \
  --argjson budget "$budget" \
  --argjson rpm "$rpm" \
  --argjson tpm "$tpm" \
  --argjson parallel "$parallel" \
  --argjson output_tokens "$output_tokens" \
  '{
    key_alias: $alias,
    models: [$route],
    max_budget: $budget,
    budget_duration: "30d",
    rpm_limit: $rpm,
    tpm_limit: $tpm,
    max_parallel_requests: $parallel,
    default_estimated_output_tokens: $output_tokens,
    key_type: "llm_api",
    metadata: {owner: "distributed-agents-demo", service: $alias}
  }')

response=$(curl --fail-with-body --silent --show-error \
  --request POST "${LLM_GATEWAY_ADMIN_URL%/}/key/generate" \
  --header "Authorization: Bearer $LITELLM_MASTER_KEY" \
  --header 'Content-Type: application/json' \
  --data "$payload")

# LiteLLM returns a virtual key once. Store the stdout value directly in the
# target service's LLM_GATEWAY_API_KEY secret; it cannot be retrieved later.
printf '%s\n' "$response" | jq --exit-status --raw-output '.key'
