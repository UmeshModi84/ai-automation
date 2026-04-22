#!/bin/bash
set -euxo pipefail
# Amazon Linux 2023 — Docker + compose + repo bootstrap for monitoring stack

dnf update -y
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user

# Docker Compose v2 plugin
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

mkdir -p /opt/app
cd /opt/app

# Optional GHCR login for private images
if [ -n "${ghcr_username}" ] && [ -n "${ghcr_token}" ]; then
  echo "${ghcr_token}" | docker login ghcr.io -u "${ghcr_username}" --password-stdin
fi

# Pull initial image (public or after login)
docker pull "${app_image}" || true

# Minimal single-container run until CI deploys full compose from repo
docker rm -f app 2>/dev/null || true
docker run -d --name app --restart unless-stopped -p 3000:3000 \
  -e NODE_ENV=production \
  "${app_image}"

echo "user-data complete"
