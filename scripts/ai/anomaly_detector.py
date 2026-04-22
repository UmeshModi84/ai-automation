#!/usr/bin/env python3
"""
Detect anomalies in Prometheus instant-vector results or simple numeric series (stdin JSON).
Can trigger recommendation: ok | investigate | rollback_candidate.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import urllib.request
from pathlib import Path
from typing import Any

from github_utils import resolve_openai_model
from structured_logging import get_logger, log_json

logger = get_logger("ai.anomaly_detector")


def query_prometheus(base: str, promql: str) -> dict[str, Any]:
    """Run instant query against Prometheus HTTP API."""
    from urllib.parse import quote

    url = f"{base.rstrip('/')}/api/v1/query?query={quote(promql)}"
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def extract_values(result: dict[str, Any]) -> list[float]:
    vals: list[float] = []
    data = result.get("data") or {}
    for item in data.get("result") or []:
        v = (item.get("value") or [None, None])[1]
        if v is not None:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
    return vals


def zscore_anomaly(values: list[float], threshold: float = 3.0) -> tuple[bool, float | None]:
    """Return (is_anomaly, z) for last value vs prior window."""
    if len(values) < 3:
        return False, None
    *hist, last = values
    if not hist:
        return False, None
    mu = statistics.mean(hist)
    sd = statistics.pstdev(hist) or 1e-9
    z = abs(last - mu) / sd
    return z >= threshold, z


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--prometheus", help="Base URL, e.g. http://localhost:9090")
    p.add_argument(
        "--query",
        default='rate(http_request_duration_seconds_count{job="app"}[5m])',
        help="PromQL instant query",
    )
    p.add_argument("--stdin-json-series", action="store_true", help="Read JSON array of numbers from stdin")
    p.add_argument("--output-json", type=Path, default=Path("ci-artifacts/anomaly_report.json"))
    p.add_argument("--z-threshold", type=float, default=3.0)
    args = p.parse_args()

    values: list[float] = []
    raw_meta: dict[str, Any] = {"query": args.query}

    if args.stdin_json_series:
        values = [float(x) for x in json.load(sys.stdin)]
        raw_meta["source"] = "stdin"
    elif args.prometheus:
        raw = query_prometheus(args.prometheus, args.query)
        raw_meta["prometheus_status"] = raw.get("status")
        values = extract_values(raw)
        raw_meta["source"] = "prometheus"
    else:
        print("Provide --prometheus or --stdin-json-series", file=sys.stderr)
        return 1

    anomaly, z = zscore_anomaly(values, args.z_threshold)
    tier = "rollback_candidate" if (anomaly and z and z >= 5) else ("investigate" if anomaly else "ok")

    report: dict[str, Any] = {
        "anomaly": anomaly,
        "z_score": z,
        "tier": tier,
        "samples": len(values),
        "meta": raw_meta,
    }

    if os.environ.get("OPENAI_API_KEY", "").strip() and values:
        try:
            from openai import OpenAI

            from openai_chat import chat_completion
        except ImportError:
            pass
        else:
            client = OpenAI()
            resp = chat_completion(
                client,
                task_label="AI anomaly narrative",
                model=resolve_openai_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "Given numeric series stats, one sentence: ok or concern. JSON only: "
                        '{"narrative":"","recommendation":"ok|investigate|rollback_candidate"}',
                    },
                    {
                        "role": "user",
                        "content": json.dumps({"values_tail": values[-20:], "z": z, "tier": tier}),
                    },
                ],
                temperature=0.1,
                max_tokens=256,
            )
            if resp:
                try:
                    txt = (resp.choices[0].message.content or "").strip()
                    txt = txt.removeprefix("```json").removesuffix("```").strip()
                    report["ai"] = json.loads(txt)
                except (json.JSONDecodeError, AttributeError):
                    pass

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log_json(logger, "anomaly_detector_done", **{k: report[k] for k in ("anomaly", "tier", "z_score") if k in report})
    print(json.dumps({"ok": True, "output": str(args.output_json), **report}))
    if tier == "rollback_candidate":
        return 2
    if tier == "investigate":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
