#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo 'Usage: bash scripts/smoke_native.sh NEW_OUTPUT_DIRECTORY' >&2
  exit 2
fi

if ! command -v docker >/dev/null || ! docker info >/dev/null || ! docker compose version >/dev/null; then
  echo 'Native smoke requires a running Docker daemon and Docker Compose.' >&2
  exit 1
fi

mkdir -- "$1"
output_dir=$(cd -- "$1" && pwd)
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
uv sync --locked
image=$(uv run --locked python -c 'import json; print(json.load(open("validation/parity-plan.proposed-r15.json"))["image"])')
docker pull "$image"
uv run --locked medcalc-bench-verified --output-dir "$output_dir/tasks" --limit 3
PYTHONPATH="$PWD/tests" OPENAI_API_KEY=fake-test-credential-never-sent \
  uv run --locked harbor run --agent-kwarg "code_image=$image" \
  -p "$output_dir/tasks" -a native_stub_agent:StubNativeAgent -m offline-stub \
  -n 2 --max-retries 0 --jobs-dir "$output_dir/jobs" --job-name stub
uv run --locked python scripts/assert_job.py "$output_dir/jobs/stub" --expected-count 3 --reward 0
uv run --locked python scripts/assert_native_stub.py "$output_dir/jobs/stub"
