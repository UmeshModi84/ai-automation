#!/usr/bin/env bash
# Run AI prelude (risk, security, PR summary), then lint / test / build / audit with full log capture.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$ROOT/ci-artifacts"

if [[ "${SKIP_AI_PRELUDE:-}" != "1" ]]; then
  cd "$ROOT"
  if git rev-parse HEAD~1 >/dev/null 2>&1; then
    git diff HEAD~1..HEAD >"$ROOT/ci-artifacts/diff.txt" 2>/dev/null || true
  else
    : >"$ROOT/ci-artifacts/diff.txt"
  fi
  python3 "$ROOT/scripts/ai/bug_predictor.py" \
    --diff-file "$ROOT/ci-artifacts/diff.txt" \
    --output-json "$ROOT/ci-artifacts/bug_predict.json" || true
  python3 "$ROOT/scripts/ai/security_scanner.py" \
    --root "$ROOT/app" \
    --output-json "$ROOT/ci-artifacts/security_scan.json" || true
  python3 "$ROOT/scripts/ai/pr_summarizer.py" \
    --diff-file "$ROOT/ci-artifacts/diff.txt" \
    --output-json "$ROOT/ci-artifacts/pr_summary.json" \
    --output-md "$ROOT/ci-artifacts/pr_summary.md" || true
fi

cd "$ROOT/app"
LOG="$ROOT/ci-full.log"
: >"$LOG"
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
