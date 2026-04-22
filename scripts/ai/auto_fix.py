#!/usr/bin/env python3
"""
Attempt automatic fixes (eslint --fix), write patch, optional self-heal CI re-run.
Structured JSON logs on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from structured_logging import get_logger, log_json

logger = get_logger("ai.auto_fix")


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--app-dir", type=Path, default=Path("app"))
    p.add_argument("--patch-out", type=Path, default=Path("auto-fix.patch"))
    p.add_argument(
        "--self-heal",
        action="store_true",
        help="After fix, re-run CI script once if CI_SELF_HEAL=1 and --ci-script set",
    )
    p.add_argument("--ci-script", type=Path, help="e.g. scripts/ci/run_node_ci.sh")
    p.add_argument("--output-json", type=Path, default=Path("ci-artifacts/auto_fix_report.json"))
    args = p.parse_args()

    app = args.app_dir.resolve()
    root = Path.cwd()
    report: dict = {"patch_written": False, "self_heal_rerun": False, "self_heal_exit": None}

    if not (app / "package.json").is_file():
        log_json(logger, "auto_fix_error", error="no_package_json", path=str(app))
        return 1

    code, log = run(["npm", "install"], app)
    if code != 0:
        log_json(logger, "npm_install_failed", exit=code)
        print(log, file=sys.stderr)
        return code

    code, log = run(["npm", "run", "lint:fix"], app)
    report["lint_fix_exit"] = code
    print(log)
    if code != 0:
        log_json(logger, "lint_fix_nonzero", exit=code)

    code, diff_out = run(["git", "diff", "--", "app/"], root)
    if code != 0:
        log_json(logger, "git_diff_failed", stderr=diff_out[:2000])
        return code

    if diff_out.strip():
        args.patch_out.write_text(diff_out, encoding="utf-8")
        report["patch_written"] = True
        log_json(logger, "patch_written", path=str(args.patch_out))

    if args.self_heal and os.environ.get("CI_SELF_HEAL") == "1" and args.ci_script and args.ci_script.is_file():
        env = os.environ.copy()
        env["SKIP_AI_PRELUDE"] = "1"
        log_json(logger, "self_heal_rerun_start", script=str(args.ci_script))
        proc = subprocess.run(
            ["bash", str(args.ci_script)],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )
        report["self_heal_rerun"] = True
        report["self_heal_exit"] = proc.returncode
        (root / "ci-artifacts").mkdir(parents=True, exist_ok=True)
        (root / "ci-artifacts" / "self_heal_rerun.log").write_text(
            (proc.stdout or "") + "\n---\n" + (proc.stderr or ""), encoding="utf-8", errors="replace"
        )
        log_json(logger, "self_heal_rerun_done", exit=proc.returncode)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "report": str(args.output_json), **report}))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and report.get("patch_written"):
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Auto-fix\n\nESLint auto-fix — see `auto-fix.patch` / `ci-artifacts/auto_fix_report.json`.\n")

    if report.get("self_heal_exit") is not None:
        return int(report["self_heal_exit"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
