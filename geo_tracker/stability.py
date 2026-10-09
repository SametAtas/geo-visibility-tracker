"""How much do AI answers change between runs of the same question?

This is why every keyword is asked several times. For each (keyword, brand) pair where the brand
appeared at least once, k of the n runs mentioned it:

- the pair *flips* if 0 < k < n: a single check could have come back "yes" or "no";
- single_check_error = min(k, n - k) / n: the chance that one random run disagrees with the majority of runs.

Per keyword, run_overlap is the mean Jaccard similarity between the sets of brands named in each pair of runs
(1.0 = every run named exactly the same brands).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from statistics import mean

from .config import Brand
from .metrics import valid
from .parse import ParsedAnswer


@dataclass(frozen=True)
class PairCount:
    keyword: str
    brand: str
    k: int      # runs that mentioned the brand
    n: int      # valid runs for the keyword

    @property
    def flips(self) -> bool:
        return 0 < self.k < self.n

    @property
    def single_check_error(self) -> float:
        return min(self.k, self.n - self.k) / self.n if self.n else 0.0


def _by_keyword(answers: list[ParsedAnswer]) -> dict[str, list[ParsedAnswer]]:
    out: dict[str, list[ParsedAnswer]] = defaultdict(list)
    for a in valid(answers):
        out[a.keyword].append(a)
    return dict(sorted(out.items()))


def pair_counts(answers: list[ParsedAnswer], brands: list[Brand]) -> list[PairCount]:
    return [PairCount(kw, b.name, sum(a.mentioned(b) for a in runs), len(runs))
            for kw, runs in _by_keyword(answers).items() for b in brands]


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return 1.0 if not (a or b) else len(a & b) / len(a | b)


def run_overlap(answers: list[ParsedAnswer]) -> dict[str, float]:
    """Mean pairwise Jaccard of the brand sets per keyword (keywords with fewer than 2 valid runs are skipped)."""
    out = {}
    for kw, runs in _by_keyword(answers).items():
        sets = [frozenset(a.mentions) for a in runs]
        if len(sets) >= 2:
            out[kw] = mean(_jaccard(x, y) for x, y in combinations(sets, 2))
    return out


def summarize(answers: list[ParsedAnswer], brands: list[Brand]) -> dict:
    seen = [p for p in pair_counts(answers, brands) if p.k > 0]
    flipping = [p for p in seen if p.flips]
    overlap = run_overlap(answers)
    return {
        "pairs_seen": len(seen),
        "pairs_flipping": len(flipping),
        "flip_share": round(len(flipping) / len(seen), 3) if seen else None,
        "mean_single_check_error": round(mean(p.single_check_error for p in seen), 3) if seen else None,
        "mean_run_overlap": round(mean(overlap.values()), 3) if overlap else None,
        "run_overlap_by_keyword": {k: round(v, 3) for k, v in overlap.items()},
    }
