#!/usr/bin/env python3
"""
Static heuristics + optional OpenAI guidance for secrets and obvious vulnerability patterns.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from github_utils import resolve_openai_model
from structured_logging import get_logger, log_json

logger = get_logger("ai.security_scanner")

SECRET_PATTERNS = [
    (r"(?i)(api[_-]?key|secret|password|token|bearer)\s*[:=]\s*['\"]?[a-z0-9_\-]{12,}", "possible_hardcoded_secret"),
    (r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "private_key_block"),
    (r"(?i)ghp_[a-z0-9]{20,}", "github_pat_like"),
    (r"(?i)sk-[a-zA-Z0-9]{20,}", "openai_sk_like"),
    (r"AKIA[0-9A-Z]{16}", "aws_access_key_id_like"),
]


def scan_file(path: Path, root: Path) -> list[dict]:
    findings: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for i, line in enumerate(text.splitlines(), 1):
        for pat, kind in SECRET_PATTERNS:
            if re.search(pat, line):
                findings.append(
                    {
                        "file": str(path.relative_to(root)),
                        "line": i,
                        "kind": kind,
                        "suggestion": "Remove secret; use environment variables or a secret manager.",
                    }
                )
                break
    return findings


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("app"))
    p.add_argument("--output-json", type=Path, default=Path("ci-artifacts/security_scan.json"))
    p.add_argument("--max-files", type=int, default=200)
    p.add_argument("--fail-on-findings", action="store_true", help="Exit 1 if any finding (default: warn only)")
    args = p.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"Root not found: {root}", file=sys.stderr)
        return 1

    findings: list[dict] = []
    count = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "node_modules" in path.parts or "coverage" in path.parts:
            continue
        if path.suffix.lower() not in {".js", ".ts", ".json", ".yml", ".yaml", ".sh", ".env"}:
            continue
        count += 1
        if count > args.max_files:
            break
        findings.extend(scan_file(path, root))

    report = {
        "findings": findings,
        "files_scanned": count,
        "failed": len(findings) > 0,
    }

    if os.environ.get("OPENAI_API_KEY", "").strip() and findings[:5]:
        try:
            from openai import OpenAI

            from openai_chat import chat_completion
        except ImportError:
            pass
        else:
            client = OpenAI()
            resp = chat_completion(
                client,
                task_label="AI security hints",
                model=resolve_openai_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "Given JSON list of static findings, add short remediation bullets. "
                        'Reply JSON: {"remediations":["..."]}',
                    },
                    {"role": "user", "content": json.dumps(findings[:15])},
                ],
                temperature=0.1,
                max_tokens=512,
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
    log_json(logger, "security_scan_done", findings=len(findings), failed=report["failed"])
    print(json.dumps({"ok": True, "output": str(args.output_json), "findings": len(findings)}))
    if args.fail_on_findings and findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
