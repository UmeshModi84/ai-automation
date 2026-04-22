#!/usr/bin/env python3
"""
Analyze application or Prometheus-exported text logs for anomalies using OpenAI.
Suitable for scheduled jobs or post-deploy smoke checks.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from openai import OpenAI

from openai_chat import chat_completion
from github_utils import append_step_summary, resolve_openai_model, skip_ai_without_api_key
from structured_logging import get_logger, log_json

logger = get_logger("ai.log_analyzer")


def fetch_prometheus_alerts(base_url: str) -> str:
    """Optional: pull active alerts JSON from Prometheus if reachable."""
    url = base_url.rstrip("/") + "/api/v1/alerts"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"[could not fetch alerts: {e}]"


def heuristic_root_cause(log_snippet: str) -> dict:
    """Cheap keyword-based hints when AI is unavailable."""
    hints: list[str] = []
    low = log_snippet.lower()
    if "eslint" in low or "lint" in low:
        hints.append("lint_failure")
    if "jest" in low or ("failing" in low and "test" in low):
        hints.append("test_failure")
    if "enoent" in low or "module not found" in low:
        hints.append("missing_module")
    if "audit" in low and "critical" in low:
        hints.append("npm_audit_critical")
    return {"root_cause_hints": hints or ["unknown"], "confidence": "low"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("log_file", nargs="?", help="Plain-text log file")
    p.add_argument("--prometheus", help="Base URL e.g. http://host:9090 to include alerts")
    p.add_argument(
        "--analysis-json-out",
        type=Path,
        default=Path("ci-artifacts/log_analysis.json"),
        help="Structured output (root_cause, signals, narrative)",
    )
    args = p.parse_args()

    if skip_ai_without_api_key("AI log / metrics analysis"):
        stub = {"status": "skipped_openai_key", "signals": {}}
        args.analysis_json_out.parent.mkdir(parents=True, exist_ok=True)
        args.analysis_json_out.write_text(json.dumps(stub, indent=2), encoding="utf-8")
        return 0

    chunks: list[str] = []
    if args.log_file:
        try:
            with open(args.log_file, encoding="utf-8", errors="replace") as f:
                chunks.append(f"--- logs ---\n{f.read()[:60_000]}")
        except OSError as e:
            print(e, file=sys.stderr)
            return 1
    if args.prometheus:
        raw = fetch_prometheus_alerts(args.prometheus)
        try:
            data = json.loads(raw)
            chunks.append(f"--- prometheus alerts ---\n{json.dumps(data, indent=2)[:20_000]}")
        except json.JSONDecodeError:
            chunks.append(f"--- prometheus raw ---\n{raw[:20_000]}")

    if not chunks:
        print("Provide log_file and/or --prometheus", file=sys.stderr)
        return 1

    blob = "\n\n".join(chunks)
    client = OpenAI()
    resp = chat_completion(
        client,
        task_label="AI log / metrics analysis",
        model=resolve_openai_model(),
        messages=[
            {
                "role": "system",
                "content": "You detect operational anomalies: spikes, errors, security patterns. Be concise.",
            },
            {
                "role": "user",
                "content": "Analyze for anomalies and severity. Output markdown: Summary, Anomalies, Recommended actions.\n\n"
                + blob,
            },
        ],
        temperature=0.2,
        max_tokens=2048,
    )
    analysis: dict = {"signals": {"has_log": bool(args.log_file), "prometheus": bool(args.prometheus)}}
    analysis["heuristic"] = heuristic_root_cause(blob[:20_000])

    if resp is None:
        analysis["narrative"] = None
        analysis["status"] = "skipped_openai"
        args.analysis_json_out.parent.mkdir(parents=True, exist_ok=True)
        args.analysis_json_out.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
        log_json(logger, "log_analysis_written", path=str(args.analysis_json_out))
        return 0
    text = (resp.choices[0].message.content or "").strip()
    analysis["narrative"] = text
    analysis["status"] = "ok"
    out = "## AI log / metrics analysis\n\n" + text
    append_step_summary(out)
    print(out)
    args.analysis_json_out.parent.mkdir(parents=True, exist_ok=True)
    args.analysis_json_out.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    log_json(logger, "log_analysis_written", path=str(args.analysis_json_out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
