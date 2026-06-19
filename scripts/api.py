"""
scripts/api.py

FastAPI HTTP wrapper around the ATJ orchestration loop. Exposes the exact same
call sequence as scripts/chat.py (memory retrieval → RAG retrieval → Claude API
→ compliance check → memory write) as a POST /chat endpoint.

Local development only. No auth. Not deployed anywhere.

--- Running locally ---

Prerequisites: atj-db (port 5432) and atj-neo4j (bolt://localhost:7687) must be
running. Credentials are read from .env — same requirements as scripts/chat.py.

Start the server (from repo root):

    uvicorn scripts.api:app --reload --port 8000

Or from the scripts/ directory:

    cd scripts
    uvicorn api:app --reload --port 8000

Health check:

    curl http://localhost:8000/health

Send a message:

    curl -X POST http://localhost:8000/chat \\
         -H "Content-Type: application/json" \\
         -d '{"user_id": "test_user_001", "message": "What is Form E?"}'

--- Statelessness note ---

Each POST /chat call is one independent turn. There is no in-request conversation
history carried between HTTP requests (unlike the CLI loop in chat.py, which
accumulates history within a single CLI session). Cross-session persistence is
provided by the Neo4j memory layer via retrieve_memory — which is the right
persistence mechanism for an HTTP API. The in-request conversation history the
CLI maintains is an artefact of the REPL pattern, not a requirement of the
underlying orchestration.
"""

import os
import sys
import uuid
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from anthropic import Anthropic
from fastapi import FastAPI
from pydantic import BaseModel

from memory import initialise_memory, retrieve_memory, write_memory, RETRIEVE_MEMORY_LIMIT
from retrieve import retrieve
from response_check import check_response, FALLBACK_RESPONSE
from chat import (
    load_system_prompt,
    format_memory_context,
    format_kb_context,
    build_turn_content,
    MODEL,
    MAX_TOKENS,
    KB_TOP_K,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialise_memory()
    app.state.system_prompt = load_system_prompt()
    app.state.client = Anthropic()
    yield


app = FastAPI(title="ATJ API", lifespan=lifespan)


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    response: str
    compliant: bool
    compliance_reason: str | None
    fallback_triggered: bool
    memory_facts_retrieved: int
    memory_truncated: bool
    session_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = str(uuid.uuid4())

    try:
        memory_result = retrieve_memory(req.user_id, req.message)
        memories = memory_result["facts"]
        mem_truncated = memory_result["truncated"]
    except Exception:
        memories = []
        mem_truncated = False

    try:
        kb_result = retrieve(req.message, top_k=KB_TOP_K)
    except Exception:
        kb_result = {}

    memory_context = format_memory_context(memories)
    if mem_truncated:
        memory_context = (
            f"Note: this user has more stored facts than fit in context. "
            f"Only the {RETRIEVE_MEMORY_LIMIT} most recent are shown. "
            f"Older facts may be relevant.\n\n"
            + memory_context
        )
    kb_context = format_kb_context(kb_result)
    turn_content = build_turn_content(req.message, memory_context, kb_context)

    response = app.state.client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=app.state.system_prompt,
        messages=[{"role": "user", "content": turn_content}],
    )
    assistant_text = "".join(
        block.text for block in response.content if block.type == "text"
    )

    check = check_response(
        req.message,
        assistant_text,
        user_identifier=req.user_id,
        session_id=session_id,
    )

    fallback_triggered = not check["compliant"]
    displayed_text = FALLBACK_RESPONSE if fallback_triggered else assistant_text

    try:
        write_memory(req.user_id, session_id, req.message, role="user")
        write_memory(req.user_id, session_id, displayed_text, role="assistant")
    except Exception:
        pass

    return ChatResponse(
        response=displayed_text,
        compliant=check["compliant"],
        compliance_reason=check.get("reason"),
        fallback_triggered=fallback_triggered,
        memory_facts_retrieved=len(memories),
        memory_truncated=mem_truncated,
        session_id=session_id,
    )
