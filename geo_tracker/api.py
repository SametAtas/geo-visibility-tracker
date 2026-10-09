"""HTTP API so automation tools (n8n's HTTP Request node, Apps Script, anything) can use the analysis.

Run:  uvicorn geo_tracker.api:app --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from . import metrics as m
from .config import Brand
from .parse import parse_answer
from .questions import intent as question_intent

app = FastAPI(title="geo-visibility-tracker", version="0.1.0")


class BrandIn(BaseModel):
    name: str
    domain: str
    aliases: list[str] = []

    def to_brand(self) -> Brand:
        return Brand(self.name, self.domain.lower(), tuple(self.aliases))


class AnswerIn(BaseModel):
    keyword: str
    run: int = 1
    engine: str = "unknown"
    text: str | None = None


class AnalyzeIn(BaseModel):
    client: BrandIn
    competitors: list[BrandIn] = []
    answers: list[AnswerIn] = Field(min_length=1)


class IntentIn(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=5000)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/analyze")
def analyze(body: AnalyzeIn) -> dict:
    client = body.client.to_brand()
    brands = [client, *(c.to_brand() for c in body.competitors)]
    parsed = [parse_answer(a.keyword, a.engine, a.run, a.text, brands) for a in body.answers]

    def rate(r: m.Rate) -> dict:
        lo, hi = r.ci
        return {"k": r.k, "n": r.n, "rate": round(r.value, 4), "ci95": [round(lo, 4), round(hi, 4)]}

    return {
        "valid_answers": len(m.valid(parsed)),
        "empty_answers": sum(p.empty for p in parsed),
        "mention_rate": rate(m.mention_rate(parsed, client)),
        "citation_rate": rate(m.citation_rate(parsed, client)),
        "share_of_voice": {k: round(v, 4) for k, v in m.share_of_voice(parsed, brands).items()},
        "per_keyword": {kw: {k: rate(r) for k, r in v.items()} for kw, v in m.per_keyword(parsed, client).items()},
        "top_cited_domains": m.top_cited_domains(parsed),
    }


@app.post("/intent")
def intent(body: IntentIn) -> dict:
    return {"results": [{"query": q, "intent": question_intent(q)} for q in body.queries]}
