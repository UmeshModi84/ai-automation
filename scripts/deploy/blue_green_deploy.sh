#!/usr/bin/env bash
#
# Blue-green style deploy on a single host: deploy new image to "green" port,
# health-check, then flip traffic by stopping blue and promoting green to primary port.
# Requires: docker, curl
#
set -euo pipefail

sudo mkdir -p /opt/app 2>/dev/null || mkdir -p /opt/app

IMAGE="${1:?Usage: blue_green_deploy.sh <full-image-ref>}"
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
