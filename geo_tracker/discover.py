"""Find names an AI recommends that are not tracked yet: "who gets mentioned instead of us?"

A heuristic for a human to review, not a named-entity model. Answers written in markdown usually put
recommended names in **bold** at the start of a list item, heading or table cell ("1. **名稱**：..."), or as the
head of a list item ("- 名稱：..."). Section labels such as 優點 or 總結 are dropped with a small stoplist.
Each name is counted once per answer. On real answers it still returns some feature phrases (比價工具), so the
report labels its output as candidates for review.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .config import Brand
from .metrics import valid
from .parse import ParsedAnswer
from .textnorm import norm

# Bold text that *starts* a line, list item, heading or table cell. On real answers, bold text in the middle of a
# sentence was mostly emphasis ("看你的**購物需求**"), not a name.
BOLD_RE = re.compile(r"(?:^|\|)\s*(?:#{1,6}\s*|\d+[.)、]\s*|[-*•]\s+)?\*\*([^*\n]{2,40}?)\*\*", re.M)
ITEM_RE = re.compile(r"^\s*(?:\d+[.)、]|[-*•])\s+([^*:：\n]{2,30}?)\s*[:：]", re.M)
PAREN_RE = re.compile(r"[（(][^）)]*[）)]")
LABEL_WORDS = ("優點", "缺點", "特色", "適合", "總結", "結論", "建議", "注意", "提醒", "小提醒", "補充", "優勢", "劣勢",
               "比較", "如何", "為什麼", "怎麼", "推薦", "選擇", "重點", "總而言之", "簡單來說", "價格", "費用", "評價",
               "服務項目", "小撇步", "關鍵", "步驟", "方法", "原因", "考量", "因素", "以下", "其他", "例如",
               "鑑賞期", "到貨", "退貨", "運費", "保固", "發票")      # the last six: shopping labels seen in real answers


@dataclass(frozen=True)
class Discovered:
    name: str
    answers: int        # valid answers that contain the name at least once
    share: float        # answers / valid answers
    tracked: bool       # matches a brand already in the config


def candidates(text: str) -> set[str]:
    """Candidate names in one answer (original spelling, cleaned)."""
    raw = [m.group(1) for m in BOLD_RE.finditer(text)] + [m.group(1) for m in ITEM_RE.finditer(text)]
    out = set()
    for s in raw:
        s = PAREN_RE.sub("", re.split(r"[:：]", s)[0]).strip(" \t*#-–—.,，。、；;!！?？「」『』")
        if not 2 <= len(s) <= 25 or re.fullmatch(r"[\d\s.,%$NT元]+", s):
            continue
        if any(w in s for w in LABEL_WORDS):
            continue
        out.add(s)
    return out


def discover(answers: list[ParsedAnswer], texts: dict[tuple[str, int], str], brands: list[Brand],
             top: int = 20) -> list[Discovered]:
    """texts maps (keyword, run) to the raw answer text of each parsed answer."""
    v = valid(answers)
    counts: Counter[str] = Counter()
    spelling: dict[str, str] = {}
    for a in v:
        for name in candidates(texts.get((a.keyword, a.run), "")):
            key = norm(name)
            spelling.setdefault(key, name)
            counts[key] += 1
    known = [norm(n) for b in brands for n in b.all_names]
    return [Discovered(spelling[k], c, round(c / len(v), 3), any(n and (n in k or k in n) for n in known))
            for k, c in counts.most_common(top)]
