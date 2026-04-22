#!/usr/bin/env bash
# Run lint, test, build with full log capture for AI debugging on failure
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/app"
LOG="$ROOT/ci-full.log"
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1
echo "=== npm install ==="
npm install
echo "=== lint ==="
npm run lint
echo "=== test ==="
npm run test
echo "=== build ==="
npm run build
echo "=== npm audit (critical) ==="
npm audit --audit-level=critical
echo "=== done ==="
