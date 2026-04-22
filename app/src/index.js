/**
 * Sample Express API with health checks and Prometheus metrics.
 */
const path = require("path");
const express = require("express");
const client = require("prom-client");

// Stateless JSON API (no cookie session auth) — CSRF via browser cookies does not apply.
// nosemgrep: javascript.express.security.audit.express-check-csurf-middleware-usage.express-check-csurf-middleware-usage
const app = express();
const PORT = process.env.PORT || 3000;

const register = new client.Registry();
client.collectDefaultMetrics({ register });

const httpRequestDuration = new client.Histogram({
  name: "http_request_duration_seconds",
  help: "Duration of HTTP requests in seconds",
  labelNames: ["method", "route", "status_code"],
  buckets: [0.001, 0.01, 0.1, 0.5, 1, 2, 5],
});
register.registerMetric(httpRequestDuration);

const aiDashboardViews = new client.Counter({
  name: "ai_dashboard_views_total",
  help: "Page views of the in-app AI pipeline dashboard",
});
register.registerMetric(aiDashboardViews);

app.use(express.json());

app.use((req, res, next) => {
  const end = httpRequestDuration.startTimer();
  res.on("finish", () => {
    end({
      method: req.method,
      route: (req.route && req.route.path) || req.path,
      status_code: String(res.statusCode),
    });
  });
  next();
});

const publicDir = path.join(__dirname, "..", "public");
app.use(express.static(publicDir));

app.get("/health", (_req, res) => {
  res.json({ status: "ok", uptime: process.uptime() });
});

app.get("/", (_req, res) => {
  res.json({
    service: "ai-cicd-sample-app",
    version: process.env.APP_VERSION || "dev",
    aiDashboard: "/ai-dashboard",
  });
});

/** JSON for the AI dashboard page (links to GitHub, Grafana, Prometheus). */
app.get("/api/ai-dashboard/config", (_req, res) => {
  const repo = process.env.GITHUB_REPO_URL || "";
  res.json({
    service: "ai-cicd-sample-app",
    version: process.env.APP_VERSION || "dev",
    repoUrl: repo,
    actionsUrl: process.env.GITHUB_ACTIONS_URL || (repo ? `${repo}/actions` : ""),
    grafanaUrl: process.env.GRAFANA_EXTERNAL_URL || "",
    prometheusUrl: process.env.PROMETHEUS_EXTERNAL_URL || "",
    workflowFile: process.env.GITHUB_WORKFLOW_FILE || ".github/workflows/ci-cd.yml",
  });
});

app.get("/ai-dashboard", (_req, res) => {
  aiDashboardViews.inc();
  // Use { root } so the path is resolved under a fixed directory (Semgrep-friendly).
  res.sendFile("ai-dashboard.html", { root: publicDir });
});

app.get("/metrics", async (_req, res) => {
  res.set("Content-Type", register.contentType);
  res.end(await register.metrics());
});

// Exported for testing
module.exports = { app, register };

if (require.main === module) {
  app.listen(PORT, "0.0.0.0", () => {
    // eslint-disable-next-line no-console
    console.log(`Listening on ${PORT}`);
  });
}
