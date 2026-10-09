"""Collect AI answers for each keyword, several times each.

Adapters:
- ReplayAdapter: reads saved answers from a JSONL file (demos, tests, and re-analysis of published data).
- OpenAICompatibleAdapter: asks any OpenAI-compatible chat API (OpenAI, Gemini, Azure, local servers).

Note: an API answer is not the same as what a user sees in the ChatGPT app or in Google AI Overviews.
For those, use a licensed SERP/AI-answer data provider behind the same `ask()` interface.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from .store import Store

_RETRY_DELAY_RE = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')   # Gemini puts the wait in the body
_DAILY_QUOTA_RE = re.compile(r"PerDay", re.I)                            # e.g. GenerateRequestsPerDayPerProject...


class QuotaExhausted(Exception):
    """The provider's daily quota is used up. Retrying today is pointless; resume after it resets."""


class Adapter(Protocol):
    """Anything with a name and an ask(keyword, run) -> answer text."""

    name: str
    ask: Callable[[str, int], str]


class ReplayAdapter:
    """Answers recorded earlier, one JSON object per line: {"keyword", "run", "text"} (+ optional "engine", "error").

    Rows exported with an error replay as that error, so a re-analysis sees exactly what the original run saw.
    """

    def __init__(self, path: str | Path, name: str | None = None):
        self._answers: dict[tuple[str, int], str] = {}
        self._errors: dict[tuple[str, int], str] = {}
        engines = set()
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = (row["keyword"], int(row["run"]))
            engines.add(row.get("engine", "replay"))
            if row.get("error"):
                self._errors[key] = row["error"]
            else:
                self._answers[key] = row.get("text") or ""
        self.name = name or (engines.pop() if len(engines) == 1 else "replay")

    def ask(self, keyword: str, run: int) -> str:
        if (keyword, run) in self._errors:
            raise RuntimeError(self._errors[(keyword, run)])
        if (keyword, run) not in self._answers:
            raise KeyError(f"no recorded answer for {keyword!r} run {run}")
        return self._answers[(keyword, run)]


class OpenAICompatibleAdapter:
    """POST {base_url}/chat/completions.

    - Sends only the user's question by default (no system prompt), the closest an API gets to a person typing it.
    - temperature=None leaves the provider's default (what its own apps use) instead of inventing one.
    - Retries 429/5xx with backoff and jitter, honoring Retry-After or Gemini's retryDelay.
    - Stops immediately on a *daily* quota error (QuotaExhausted): retrying would only burn time.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None,
                 temperature: float | None = None, system_prompt: str | None = None, max_retries: int = 6,
                 timeout: float = 120, min_interval: float = 1.0, backoff_base: float = 2.0, max_delay: float = 60.0,
                 client: httpx.Client | None = None):
        self.base_url = (base_url or os.environ.get("GEO_LLM_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("GEO_LLM_API_KEY", "")
        self.model = model or os.environ.get("GEO_LLM_MODEL", "")
        if not self.model:
            raise ValueError("set GEO_LLM_MODEL (or pass model=...)")
        self.name = self.model
        self.temperature, self.system_prompt = temperature, system_prompt
        self.max_retries, self.min_interval, self.backoff_base = max_retries, min_interval, backoff_base
        self.max_delay = max_delay   # "model overloaded" (503) spikes last minutes: 2, 4, 8, 16, 32, 60 s
        self.client = client or httpx.Client(timeout=timeout)
        self.headers = {"Authorization": f"Bearer {self.api_key}"}  # key comes from the environment, never from code
        self._last = 0.0

    def _body(self, keyword: str) -> dict:
        messages = [{"role": "system", "content": self.system_prompt}] if self.system_prompt else []
        body: dict = {"model": self.model, "messages": [*messages, {"role": "user", "content": keyword}]}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        return body

    def _retry_delay(self, r: httpx.Response, attempt: int) -> float:
        header = r.headers.get("retry-after", "")
        try:
            return float(header)
        except ValueError:
            pass
        m = _RETRY_DELAY_RE.search(r.text)
        return float(m.group(1)) if m else min(self.max_delay, self.backoff_base * 2 ** attempt)

    def ask(self, keyword: str, run: int) -> str:
        body = self._body(keyword)
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)                      # client-side rate limit
            self._last = time.monotonic()
            r = self.client.post(f"{self.base_url}/chat/completions", json=body, headers=self.headers)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"] or ""
            if r.status_code == 429 and _DAILY_QUOTA_RE.search(r.text):
                raise QuotaExhausted(r.text[:300])
            if r.status_code not in (429, 500, 502, 503, 504) or attempt == self.max_retries:
                # keep the provider's message (invalid key, unknown model, ...): it is what a person needs to fix it
                raise httpx.HTTPStatusError(f"HTTP {r.status_code}: {r.text[:300]}", request=r.request, response=r)
            time.sleep(self._retry_delay(r, attempt) + random.uniform(0, 0.5 * self.backoff_base))  # jitter
        raise RuntimeError("unreachable")


@dataclass
class CollectStats:
    asked: int = 0
    saved: int = 0
    errors: int = 0
    empty: int = 0
    skipped: int = 0            # already collected for this date (resume)
    stopped: str = ""           # set when a daily quota ended the run early


def collect(adapter: Adapter, keywords: list[str], repeats: int, store: Store, collected_on: str,
            resume: bool = True, progress: Callable[[str], None] | None = None,
            max_consecutive_errors: int = 3) -> CollectStats:
    """Ask every keyword `repeats` times. Failures are stored with their error, never dropped.

    With resume=True, answers already stored without error for this date and engine are not asked again,
    so an interrupted run (crash, quota, closed laptop) continues where it stopped.
    After `max_consecutive_errors` failures in a row the run stops: something is wrong (key, quota, network)
    and asking the remaining keywords would only collect more errors.
    """
    stats = CollectStats()
    in_a_row = 0
    done = store.done(collected_on, adapter.name) if resume else set()
    for kw in keywords:
        for run in range(1, repeats + 1):
            if (kw, run) in done:
                stats.skipped += 1
                continue
            stats.asked += 1
            try:
                text = adapter.ask(kw, run)
                store.save(collected_on, adapter.name, kw, run, text)
                stats.saved += 1
                stats.empty += not text.strip()
                in_a_row = 0
            except QuotaExhausted as e:
                stats.stopped = f"daily quota reached: {e}"[:300]
                return stats
            except Exception as e:  # noqa: BLE001 - any failure is recorded, then the run continues
                error = f"{type(e).__name__}: {e}"[:500]
                store.save(collected_on, adapter.name, kw, run, None, error)
                stats.errors += 1
                in_a_row += 1
                if in_a_row >= max_consecutive_errors:
                    stats.stopped = f"{in_a_row} errors in a row, last: {error}"[:300]
                    return stats
            if progress:
                progress(f"{stats.saved + stats.errors + stats.skipped}/{len(keywords) * repeats} {kw} #{run}")
    return stats


def load_keywords(path: str | Path) -> list[str]:
    """One keyword per line; lines starting with # and blank lines are ignored; duplicates removed."""
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    return list(dict.fromkeys(l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")))
