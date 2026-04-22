const request = require("supertest");
const { app } = require("../src/index");

describe("API", () => {
  test("GET /health returns ok", async () => {
    const res = await request(app).get("/health");
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("ok");
    expect(typeof res.body.uptime).toBe("number");
  });

  test("GET / returns service info", async () => {
    const res = await request(app).get("/");
    expect(res.status).toBe(200);
    expect(res.body.service).toBe("ai-cicd-sample-app");
  });

  test("GET /metrics exposes prometheus format", async () => {
    const res = await request(app).get("/metrics");
    expect(res.status).toBe(200);
    expect(res.text).toContain("process_cpu");
  });

  test("GET /ai-dashboard returns HTML", async () => {
    const res = await request(app).get("/ai-dashboard");
    expect(res.status).toBe(200);
    expect(res.headers["content-type"]).toMatch(/html/);
    expect(res.text).toContain("AI");
  });

  test("GET /api/ai-dashboard/config returns JSON", async () => {
    const res = await request(app).get("/api/ai-dashboard/config");
    expect(res.status).toBe(200);
    expect(res.body.service).toBe("ai-cicd-sample-app");
    expect(res.body).toHaveProperty("grafanaUrl");
    expect(res.body).toHaveProperty("workflowFile");
  });
});
