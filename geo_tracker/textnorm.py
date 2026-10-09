"""Text and URL normalization shared by every module.

Taiwanese web text mixes full-width and half-width characters (ＳＥＯ vs SEO), so everything
that compares strings goes through `norm()` first.
"""
from __future__ import annotations

import re
import unicodedata

# A URL ends at whitespace or at punctuation that cannot be part of it, including full-width
# Chinese punctuation that AI answers put right after links: ，。、；：！？（）【】「」『』《》
_URL_RE = re.compile(r"https?://[^\s)\]>\"'<，。、；：！？（）【】「」『』《》]+", re.I)
_HOST_RE = re.compile(r"^https?://([^/?#:\s]+)", re.I)


def norm(text: str | None) -> str:
    """NFKC (full-width -> half-width), lowercase, collapse whitespace."""
    if not text:
        return ""
    return " ".join(unicodedata.normalize("NFKC", text).lower().split())


def host_of(url: str) -> str:
    """'https://www.Example.com/a?b' -> 'example.com'. Empty string if not a URL."""
    m = _HOST_RE.match(url.strip())
    return m.group(1).lower().removeprefix("www.") if m else ""


def urls_in(text: str | None) -> list[str]:
    """All http(s) URLs in free text, in order of appearance."""
    return _URL_RE.findall(text or "")


def strip_html(html: str | None) -> str:
    html = re.sub(r"<(script|style)\b[\s\S]*?</\1>", " ", html or "", flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#039;", "'")):
        text = text.replace(ent, ch)
    return " ".join(text.split())


def shingles(text: str, k: int = 2) -> set[str]:
    """Character k-grams, ignoring spaces and punctuation (？ vs ?, ： vs :).

    Works for Chinese, which has no word boundaries. Bigrams (k=2) suit short Chinese texts:
    on the demo data, paraphrases scored 0.43-0.63 and different questions 0.12-0.31.
    """
    t = re.sub(r"[\W_]", "", norm(text))  # \W keeps CJK characters and digits, drops punctuation
    return {t[i:i + k] for i in range(max(1, len(t) - k + 1))} if t else set()


def jaccard(a: str, b: str, k: int = 2) -> float:
    sa, sb = shingles(a, k), shingles(b, k)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0
