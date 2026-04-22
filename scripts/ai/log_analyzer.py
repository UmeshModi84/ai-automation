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

from openai import OpenAI

from github_utils import append_step_summary, skip_ai_without_api_key


def fetch_prometheus_alerts(base_url: str) -> str:
    """Optional: pull active alerts JSON from Prometheus if reachable."""
    url = base_url.rstrip("/") + "/api/v1/alerts"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"[could not fetch alerts: {e}]"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("log_file", nargs="?", help="Plain-text log file")
    p.add_argument("--prometheus", help="Base URL e.g. http://host:9090 to include alerts")
    args = p.parse_args()

    if skip_ai_without_api_key("AI log / metrics analysis"):
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
    resp = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
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
    text = (resp.choices[0].message.content or "").strip()
    out = "## AI log / metrics analysis\n\n" + text
    append_step_summary(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
