#!/usr/bin/env bash
# Roll back to image stored in /opt/app/previous_image.txt (written by blue_green_deploy.sh)
set -euo pipefail

PREV_FILE="${PREV_FILE:-/opt/app/previous_image.txt}"
NAME_BLUE="${NAME_BLUE:-app-blue}"
PRIMARY_PORT="${PRIMARY_PORT:-3000}"

if [[ ! -f "$PREV_FILE" ]]; then
  echo "No previous image file at $PREV_FILE"
  exit 1
fi

IMAGE="$(cat "$PREV_FILE")"
echo "Rolling back to $IMAGE"
docker pull "$IMAGE" || true
docker rm -f "$NAME_BLUE" 2>/dev/null || true
docker run -d --name "$NAME_BLUE" --restart unless-stopped \
  -p "${PRIMARY_PORT}:3000" \
  -e NODE_ENV=production \
  "$IMAGE"
echo "Rollback complete"
