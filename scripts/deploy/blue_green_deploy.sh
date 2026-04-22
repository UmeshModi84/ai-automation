#!/usr/bin/env bash
#
# Blue-green style deploy on a single host: deploy new image to "green" port,
# health-check, then flip traffic by stopping blue and promoting green to primary port.
# Requires: docker, curl
#
set -euo pipefail

sudo mkdir -p /opt/app 2>/dev/null || mkdir -p /opt/app

IMAGE="${1:?Usage: blue_green_deploy.sh <full-image-ref>}"

# Optional: gate deploy with scripts/ai/deploy_decision_ai.py (JSON from CI or ops).
# export DEPLOY_DECISION_INPUT_JSON=/opt/app/deploy_inputs.json
# Set AI_PIPELINE_ROOT on the server if this script is not inside a full repo checkout.
REPO_ROOT="${AI_PIPELINE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
if [[ -n "${DEPLOY_DECISION_INPUT_JSON:-}" && -f "${DEPLOY_DECISION_INPUT_JSON}" ]] && command -v python3 >/dev/null 2>&1; then
  set +e
  python3 "$REPO_ROOT/scripts/ai/deploy_decision_ai.py" \
    --input-json "$DEPLOY_DECISION_INPUT_JSON" \
    --output-json /opt/app/last_deploy_decision.json \
    --stdout-json
  dec_ec=$?
  set -e
  if [[ "$dec_ec" -eq 3 ]]; then
    echo "deploy_decision_ai: rollback — aborting deploy"
    exit 3
  fi
  if [[ "$dec_ec" -eq 2 ]]; then
    echo "deploy_decision_ai: delay — aborting deploy"
    exit 2
  fi
fi
PRIMARY_PORT="${PRIMARY_PORT:-3000}"
GREEN_PORT="${GREEN_PORT:-3002}"
NAME_BLUE="${NAME_BLUE:-app-blue}"
NAME_GREEN="${NAME_GREEN:-app-green}"

echo "Pulling $IMAGE"
docker pull "$IMAGE"

# Start / refresh green on alternate host port mapping (host:container)
docker rm -f "$NAME_GREEN" 2>/dev/null || true
docker run -d --name "$NAME_GREEN" --restart unless-stopped \
  -p "${GREEN_PORT}:3000" \
  -e NODE_ENV=production \
  -e APP_VERSION="${APP_VERSION:-}" \
  "$IMAGE"

echo "Waiting for health on :$GREEN_PORT"
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${GREEN_PORT}/health" >/dev/null; then
    echo "Green healthy"
    break
  fi
  sleep 2
  if [[ "$i" -eq 30 ]]; then
    echo "Green failed health — rolling back green container"
    docker rm -f "$NAME_GREEN" || true
    exit 1
  fi
done

# Save previous primary image for rollback
if docker inspect "$NAME_BLUE" >/dev/null 2>&1; then
  docker inspect --format='{{.Config.Image}}' "$NAME_BLUE" | tee /opt/app/previous_image.txt >/dev/null || true
fi

docker rm -f "$NAME_BLUE" 2>/dev/null || true
docker run -d --name "$NAME_BLUE" --restart unless-stopped \
  -p "${PRIMARY_PORT}:3000" \
  -e NODE_ENV=production \
  -e APP_VERSION="${APP_VERSION:-}" \
  "$IMAGE"

docker rm -f "$NAME_GREEN" 2>/dev/null || true
echo "Deploy complete — primary on :$PRIMARY_PORT"
