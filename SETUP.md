# AI-Powered CI/CD — Setup Guide

This repository contains a **Node.js** sample app, **GitHub Actions** workflows, **Terraform** for **AWS EC2**, **Docker** + **GHCR**, optional **Prometheus/Grafana**, and **OpenAI**-backed automation (code review, test ideas, failure analysis, log analysis).

## Repository layout

| Path | Purpose |
|------|---------|
| `app/` | Express API, Jest tests, ESLint |
| `.github/workflows/ci-cd.yml` | Main CI/CD: lint, test, build, audit, Semgrep, Docker push, AI jobs, deploy |
| `.github/workflows/optional-auto-fix.yml` | Manual ESLint auto-fix PR |
| `.github/workflows/ai-log-monitoring.yml` | Scheduled / manual AI log & metrics review |
| `scripts/ai/` | Python tools (`openai`, `requests`) |
| `scripts/ci/run_node_ci.sh` | CI runner with `ci-full.log` for AI debugging |
| `scripts/deploy/` | `notify.sh`, `blue_green_deploy.sh`, `rollback.sh` (for VM use) |
| `terraform/` | VPC + public subnet + EC2 (Amazon Linux 2023 + Docker) |
| `monitoring/` | Prometheus scrape config, Grafana datasource + **AI Pipeline** dashboard JSON |
| `app/public/ai-dashboard.html` | In-app **AI Pipeline** web UI (links, version) |
| `docker-compose.monitoring.yml` | Optional full stack on the VM |
| `Dockerfile` | Production image |

## Prerequisites

- **GitHub** account and repository — this project is designed to live in **[UmeshModi84/ai-automation](https://github.com/UmeshModi84/ai-automation)** (clone URL: `https://github.com/UmeshModi84/ai-automation.git`).
- **OpenAI API key** for AI features ([platform.openai.com](https://platform.openai.com/)).
- **AWS account** (for Terraform), or skip infra and run the app locally / elsewhere.
- Optional: **Slack** or **Microsoft Teams** incoming webhook for notifications.

## Step 1 — Push the code

Your GitHub remote: **[https://github.com/UmeshModi84/ai-automation.git](https://github.com/UmeshModi84/ai-automation.git)**

```bash
cd ai-cicd-pipeline
git init
git branch -M main
git add .
git commit -m "Initial AI CI/CD pipeline"   # skip if you already have commits
git remote add origin https://github.com/UmeshModi84/ai-automation.git
git push -u origin main
```

If the remote already has commits (for example only a `readme.md` from GitHub’s “create repo” flow) and `git push` is rejected, either merge histories:

```bash
git pull origin main --allow-unrelated-histories
# resolve any conflicts, then:
git push -u origin main
```

Or, if you intend to **replace** the remote history with this project only (destructive), use `git push --force-with-lease origin main` after confirming no one else depends on that branch.

## Step 2 — GitHub configuration

### Secrets (Settings → Secrets and variables → Actions)

| Secret | Required | Description |
|--------|----------|-------------|
| `OPENAI_API_KEY` | Yes (for AI jobs) | OpenAI API key |
| `DEPLOY_HOST` | For deploy | EC2 public IP or DNS |
| `DEPLOY_USER` | For deploy | SSH user (e.g. `ec2-user`) |
| `DEPLOY_SSH_KEY` | For deploy | Private key (PEM) for SSH |
| `SLACK_WEBHOOK_URL` or `TEAMS_WEBHOOK_URL` | Optional | Incoming webhook URL |

`GITHUB_TOKEN` is provided automatically; workflows use it for GHCR push and PR comments.

### Variables (optional)

| Variable | Example | Description |
|----------|---------|-------------|
| `OPENAI_MODEL` | `gpt-4o-mini` | Override default model |
| `DEPLOY_ENABLED` | `true` | Set to `true` to run the **deploy** job (after adding `DEPLOY_*` secrets). If unset, pushes to `main` still build/push the image but skip SSH deploy. |

### Environments

Create a **`production`** environment (Settings → Environments) if you use the deploy job with protection rules.

## Step 3 — Enable GitHub Container Registry

Workflow pushes to `ghcr.io/<owner>/<repo>:latest` and `:sha`.

- Ensure **Actions** permissions allow **read/write packages** (repo Settings → Actions → General → Workflow permissions: *Read and write permissions*).

For **private** images, log in on the server (see Terraform `ghcr_*` variables) or use a PAT with `read:packages` on the EC2 host.

## Step 4 — Terraform (AWS EC2)

1. Install [Terraform](https://www.terraform.io/) and [AWS CLI](https://aws.amazon.com/cli/) configured with credentials (`aws configure`).

2. Copy and edit variables:

   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # Edit: ssh_public_key, allowed_cidr, app_image, optional ghcr_*
   ```

3. Initialize and apply:

   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

4. Note outputs: `public_ip`, `app_url`, SSH command.

Security: restrict `allowed_cidr` to your IP for SSH in production.

## Step 5 — Deploy SSH target

The **deploy** job (push to `main`) expects:

- Docker installed on the host (Terraform user-data already installs Docker on Amazon Linux 2023).
- Open port **3000** for the app (security group in Terraform allows `3000` from `0.0.0.0/0`; tighten as needed).

The workflow runs **inline** SSH commands (no repo checkout on the server): pull `ghcr.io/...:sha`, save previous image to `/opt/app/previous_image.txt`, run new container, and on deploy failure attempt **rollback** to the previous image.

Add repository **secrets** `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` before relying on deploy.

## Step 6 — Local Node.js checks

If you have Node.js 20+:

```bash
cd app
npm install
npm run lint
npm run test
npm run build
npm audit --audit-level=critical
```

Commit `package-lock.json` after `npm install` if you want **reproducible** installs and switch CI to `npm ci` (optional improvement).

## Step 7 — Optional monitoring stack on the VM

Copy `docker-compose.monitoring.yml` and `monitoring/` to the server (or clone the repo), then:

```bash
export APP_IMAGE=ghcr.io/<org>/<repo>:<tag>
export GRAFANA_ADMIN_PASSWORD='...'
docker compose -f docker-compose.monitoring.yml up -d
```

- App: `http://<ip>:3000`
- **AI dashboard (in-app):** `http://<ip>:3000/ai-dashboard` — operational view of AI automation with links (set env vars below).
- Grafana: `http://<ip>:3001` (change default password) — open folder **AI** → dashboard **AI Pipeline & Application** (HTTP metrics, CPU, memory, **AI dashboard view counter**).
- Prometheus: `http://<ip>:9090`

Point **AI log monitoring** workflow at `http://<ip>:9090` via workflow dispatch input `prometheus_url`.

### AI dashboard environment variables

Set these on the **app** container (compose `environment` or `docker run -e`) so `/ai-dashboard` can link out:

| Variable | Example | Purpose |
|----------|---------|---------|
| `GITHUB_REPO_URL` | `https://github.com/org/repo` | Repository link |
| `GITHUB_ACTIONS_URL` | `https://github.com/org/repo/actions` | Overrides default `{repo}/actions` if needed |
| `GRAFANA_EXTERNAL_URL` | `http://<ip>:3001` | Quick link to Grafana |
| `PROMETHEUS_EXTERNAL_URL` | `http://<ip>:9090` | Quick link to Prometheus |
| `GITHUB_WORKFLOW_FILE` | `.github/workflows/ci-cd.yml` | Path for “View workflow” (default shown) |

JSON API: `GET /api/ai-dashboard/config` returns the same fields for custom frontends.

Prometheus metric **`ai_dashboard_views_total`** increments on each load of `/ai-dashboard` (shown on the Grafana board).

## Step 8 — AI features summary

| Feature | Where |
|---------|--------|
| PR code review | `ai-code-review` job → `scripts/ai/code_review.py` |
| Test ideas | `ai-generate-tests` → `generate_tests.py` + artifact |
| Failed CI analysis | `ai-failure-insights` → `suggest_fixes.py` + Step Summary |
| Log / anomaly analysis | `log_analyzer.py` + `ai-log-monitoring.yml` |
| ESLint auto-fix PR | `optional-auto-fix.yml` + `auto_fix.py` |

## Step 9 — Optional Snyk

Add a Snyk job or use `snyk/actions` with `SNYK_TOKEN` if you prefer Snyk over **npm audit** alone. This repo already fails the pipeline on **critical** npm audit findings.

## Step 10 — Blue/green and scripts on the VM

For **blue/green** on a single host, use `scripts/deploy/blue_green_deploy.sh` after copying it to the server (or clone the repo there). The default GitHub deploy path uses a **single** container named `app` with rollback support; blue/green is an optional enhancement.

## Troubleshooting

- **AI jobs skip or fail**: set `OPENAI_API_KEY`; check billing/limits on the OpenAI account.
- **GHCR push denied**: set workflow permissions to read/write packages; use lowercase image names (workflow lowercases `GITHUB_REPOSITORY`).
- **Deploy SSH fails**: verify security group, key pair, user name (`ec2-user` on AL2023), and that Docker is running on the instance.
- **Semgrep**: requires network on the runner to fetch rules; `semgrep --config auto` may take a few minutes on first run.

## License

Sample code is provided as-is for integration into your own projects.
