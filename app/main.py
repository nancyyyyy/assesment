"""
FastAPI backend. One streaming chat endpoint that wraps the agent.

Run: uvicorn app.main:app --reload --port 8000
"""
import json
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent import stream_answer

app = FastAPI(title="Northwind Gadgets Support Agent")

# In production, set FRONTEND_ORIGIN to your deployed frontend's URL.
# Defaults to wide-open for local development.
import os
_frontend_origin = os.environ.get("FRONTEND_ORIGIN", "*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend_origin] if _frontend_origin != "*" else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _event_generator(question: str, history: list[dict] | None):
    try:
        for event in stream_answer(question, history):
            yield _sse_event(event)
    except Exception as e:
        yield _sse_event({"type": "error", "message": str(e)})


@app.post("/chat")
def chat(req: ChatRequest):
    return StreamingResponse(
        _event_generator(req.message, req.history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering if deployed behind it
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}
