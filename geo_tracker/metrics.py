"""Visibility metrics with honest uncertainty.

AI answers change from run to run, so every rate here is an estimate from a sample.
We report it with a 95% Wilson interval, and only call a change "real" if a two-proportion
z-test says it is unlikely to be noise.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from .config import Brand
from .parse import ParsedAnswer

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95% Wilson score interval for k successes out of n. Sensible even for n=3 or k=0."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def two_proportion_p(k1: int, n1: int, k2: int, n2: int) -> float:
    """Two-sided p-value for 'the rate changed between period 1 and period 2'."""
    if min(n1, n2) == 0:
        return 1.0
    pooled = (k1 + k2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (k2 / n2 - k1 / n1) / se
    return math.erfc(abs(z) / math.sqrt(2))


@dataclass
class Rate:
    k: int
    n: int

    @property
    def value(self) -> float:
        return self.k / self.n if self.n else 0.0

    @property
    def ci(self) -> tuple[float, float]:
        return wilson(self.k, self.n)

    def __str__(self) -> str:
        lo, hi = self.ci
        return f"{self.k}/{self.n} = {self.value:.0%} (95% CI {lo:.0%}-{hi:.0%})"


def valid(answers: list[ParsedAnswer]) -> list[ParsedAnswer]:
    return [a for a in answers if not a.empty]


def mention_rate(answers: list[ParsedAnswer], brand: Brand) -> Rate:
    v = valid(answers)
    return Rate(sum(a.mentioned(brand) for a in v), len(v))


def citation_rate(answers: list[ParsedAnswer], brand: Brand) -> Rate:
    v = valid(answers)
    return Rate(sum(a.cited(brand) for a in v), len(v))


def per_keyword(answers: list[ParsedAnswer], brand: Brand) -> dict[str, dict[str, Rate]]:
    by_kw: dict[str, list[ParsedAnswer]] = defaultdict(list)
    for a in answers:
        by_kw[a.keyword].append(a)
    return {kw: {"mention": mention_rate(lst, brand), "citation": citation_rate(lst, brand)}
            for kw, lst in sorted(by_kw.items())}


def share_of_voice(answers: list[ParsedAnswer], brands: list[Brand]) -> dict[str, float]:
    """Of all brand mentions among the tracked brands, what share belongs to each."""
    counts = {b.name: sum(a.mentioned(b) for a in valid(answers)) for b in brands}
    total = sum(counts.values())
    return {name: (c / total if total else 0.0) for name, c in counts.items()}


def top_cited_domains(answers: list[ParsedAnswer], n: int = 10) -> list[tuple[str, int]]:
    return Counter(d for a in valid(answers) for d in a.cited_domains).most_common(n)


@dataclass
class Change:
    before: Rate
    after: Rate
    p_value: float

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05

    def describe(self) -> str:
        delta = self.after.value - self.before.value
        verdict = "real change (p<0.05)" if self.significant else "could be noise"
        return f"{self.before.value:.0%} -> {self.after.value:.0%} ({delta:+.0%}), p={self.p_value:.2f}: {verdict}"


def compare(before: Rate, after: Rate) -> Change:
    return Change(before, after, two_proportion_p(before.k, before.n, after.k, after.n))
