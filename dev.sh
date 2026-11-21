#!/usr/bin/env bash
set -e

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# Give each server a process group so cleanup also reaches reload workers.
set -m
pids=()
cleanup() {
  if ((${#pids[@]})); then
    kill -TERM -- "${pids[@]/#/-}" 2>/dev/null || true
    wait "${pids[@]}" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

(cd backend && exec uv run uvicorn app.main:app --reload) &
pids+=("$!")
(cd frontend && exec pnpm dev) &
pids+=("$!")

wait -n "${pids[@]}"
