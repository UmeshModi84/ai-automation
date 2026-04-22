"""Centralized chat.completions.create with graceful handling of quota / rate limits."""
from __future__ import annotations

from typing import Any

from openai import APIStatusError, OpenAI, RateLimitError

from github_utils import append_step_summary


def chat_completion(client: OpenAI, *, task_label: str, **kwargs: Any) -> Any | None:
    """
    Call OpenAI chat completions. On 429 / insufficient_quota / RateLimitError, emit a GitHub
    Actions warning and return None so callers can exit 0 (CI green) until billing is fixed.
    """
    try:
        return client.chat.completions.create(**kwargs)
    except RateLimitError as e:
        _quota_warning(task_label, e)
        return None
    except APIStatusError as e:
        if getattr(e, "status_code", None) == 429:
            _quota_warning(task_label, e)
            return None
        raise
    except Exception as e:
        err = str(e).lower()
        if "insufficient_quota" in err or "429" in err or "rate limit" in err:
            _quota_warning(task_label, e)
            return None
        raise


def _quota_warning(task_label: str, e: Exception) -> None:
    msg = (
        f"{task_label}: OpenAI returned quota or rate limit — {e}. "
        "Add payment method / credits: https://platform.openai.com/account/billing"
    )
    print(f"::warning::{msg}", flush=True)
    append_step_summary(
        f"### {task_label} (skipped — OpenAI billing / quota)\n\n{msg}\n"
    )
