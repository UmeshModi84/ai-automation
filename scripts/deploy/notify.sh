#!/usr/bin/env bash
set -euo pipefail
STATUS="${1:-unknown}"
MESSAGE="${2:-CI notification}"
WEBHOOK_URL="${SLACK_WEBHOOK_URL:-${TEAMS_WEBHOOK_URL:-}}"

if [[ -z "$WEBHOOK_URL" ]]; then
  echo "No SLACK_WEBHOOK_URL or TEAMS_WEBHOOK_URL set; skipping."
  exit 0
fi

export WEBHOOK_URL MESSAGE STATUS
python3 <<'PY'
import json, os, urllib.request
url = os.environ["WEBHOOK_URL"]
text = f"{os.environ['STATUS']}: {os.environ['MESSAGE']}"
body = json.dumps({"text": text}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=15).read()
PY
