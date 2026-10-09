"""Question mining: turn forum post titles into a ranked bank of real user questions.

Agencies write question-based articles from what people actually ask on PTT, Dcard and social media.
This module keeps the titles that are questions, strips forum prefixes, tags search intent,
and groups near-duplicate wordings so each real question is counted once with its frequency.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from .textnorm import jaccard, norm

PREFIX_RE = re.compile(r"^\s*(re\s*:\s*|fw\s*:\s*)*(\[[^\]]{1,6}\]|【[^】]{1,6}】)?\s*", re.I)
QUESTION_RE = re.compile(r"[?？]|嗎|呢|怎麼|如何|多少|哪|推薦|比較|值得|請問|求|有人|是否|可以|差別|差異|會不會|有沒有|能不能")

INTENT_RULES = [  # first match wins
    ("transactional", r"價格|價錢|費用|多少錢|報價|優惠|預約|方案|便宜"),
    ("commercial", r"推薦|比較|評價|心得|哪[家間個]|值得|差別|差異|vs|最好|ptt|dcard"),
    ("navigational", r"官網|地址|電話|營業時間|怎麼去|登入"),
]


def clean_title(title: str) -> str:
    return PREFIX_RE.sub("", title or "").strip()


def is_question(title: str) -> bool:
    return bool(QUESTION_RE.search(title))


def intent(text: str) -> str:
    t = norm(text)
    return next((label for label, pat in INTENT_RULES if re.search(pat, t)), "informational")


@dataclass
class QuestionCluster:
    representative: str
    intent: str
    members: list[str] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)

    @property
    def size(self) -> int:
        return len(self.members)


def mine(titles: list[tuple[str, str]], threshold: float = 0.4) -> list[QuestionCluster]:
    """titles: (title, source) pairs. Returns clusters, most-asked first.

    Greedy clustering on character-bigram Jaccard similarity against every member of a cluster:
    simple, deterministic, no model download. It merges rewordings (會痛嗎 / 會很痛嗎) but not
    synonyms with different characters (副作用有哪些 / 會有副作用嗎); embeddings would catch those.
    The threshold was chosen on the demo data; tune it on a labeled sample for a new domain.
    """
    clusters: list[QuestionCluster] = []
    for raw, source in titles:
        q = clean_title(raw)
        if not q or not is_question(q):
            continue
        score = lambda c: max(jaccard(q, m) for m in c.members)  # noqa: E731
        best = max(clusters, key=score, default=None)
        if best is not None and score(best) >= threshold:
            best.members.append(q)
            best.sources.add(source)
        else:
            clusters.append(QuestionCluster(q, intent(q), [q], {source}))
    for c in clusters:  # the shortest wording is usually the clearest heading for an article
        c.representative = min(c.members, key=len)
        c.intent = intent(" ".join(c.members))
    return sorted(clusters, key=lambda c: (-c.size, c.representative))


def read_titles(path: str | Path) -> list[tuple[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [(r["title"], r.get("source", "")) for r in csv.DictReader(f)]
