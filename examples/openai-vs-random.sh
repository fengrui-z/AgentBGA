#!/usr/bin/env sh
set -eu

# Works with OpenAI or an OpenAI-compatible /chat/completions endpoint.
# Never put a real key in this file; export it in the shell.
: "${OPENAI_API_KEY:?export OPENAI_API_KEY first}"
: "${OPENAI_MODEL:?export OPENAI_MODEL first}"

OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.openai.com/v1}"

./agentbga run \
  --players 2 \
  --controllers openai,random \
  --model "$OPENAI_MODEL" \
  --base-url "$OPENAI_BASE_URL" \
  --jsonl
