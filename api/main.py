"""Web service for "ask the data": POST /ask with {"question": "..."} returns the checked query and its result.

It holds the model's API key, which is set in Render's dashboard (or the local environment), never in the repository:
GEMINI_API_KEY by default, or ANTHROPIC_API_KEY with ASK_PROVIDER=claude. Each visitor may ask a few questions a minute
and a day, and all visitors together have a daily cap, so the free model quota (or a paid key's bill) stays small.
Run locally: uvicorn api.main:app --port 8000   (a copy of the site on localhost calls http://localhost:8000)
"""
import json
import os
import threading
import time
from datetime import date

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pipeline import ask

PER_MINUTE, PER_DAY, ALL_PER_DAY = 8, 50, 300  # questions for one visitor a minute, one visitor a day, everyone a day

asker = ask.Asker(json.loads(ask.DATA.read_text(encoding="utf-8")))
write_sql = ask.PROVIDERS[os.environ.get("ASK_PROVIDER", "gemini")]
app = FastAPI(title="UPI Pulse: ask the data", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["https://anubhavkumarkanth.github.io"],
                   allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?", allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])
_lock, _hits, _day = threading.Lock(), {}, None


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=ask.MAX_QUESTION)


def visitor(request: Request) -> str:
    # shortcut: trusts the first X-Forwarded-For address, which a client can fake; the all-visitor daily cap still holds
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or request.client.host


def over_limit(ip: str, now: float) -> str | None:
    """None if this visitor may ask now (and counts the question); otherwise why not."""
    global _day
    with _lock:
        if _day != date.today():
            _day = date.today()
            _hits.clear()
        mine = _hits.setdefault(ip, [])
        if sum(map(len, _hits.values())) >= ALL_PER_DAY:
            return "The question box has answered all the questions it can today. Try again tomorrow."
        if len(mine) >= PER_DAY:
            return "You have asked today's limit of questions. Try again tomorrow."
        if sum(t > now - 60 for t in mine) >= PER_MINUTE:
            return "That's a lot of questions in one minute. Wait a moment and try again."
        mine.append(now)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ask")
def answer(q: Question, request: Request):
    reason = over_limit(visitor(request), time.time())
    if reason:
        raise HTTPException(429, reason)
    try:
        return asker.ask(q.question, write_sql)
    except ask.Refused as e:
        raise HTTPException(422, str(e)) from None
    except Exception as e:  # the model is busy, out of quota, or its key is missing
        print(f"model error: {type(e).__name__}: {e}", flush=True)
        raise HTTPException(503, "The AI model is not answering right now. Try again in a minute.") from None
