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

--- Session history ---

Pass session_id in the request body to continue an existing conversation. If
omitted, a new session_id is generated and returned in the response — the
frontend should persist this and include it on subsequent turns.

Two memory layers operate in parallel:
  Short-term: in-process dict (_session_store), last SESSION_HISTORY_LIMIT turns
    per session_id. Resets on server restart — non-persistent by design for
    local dev.
  Long-term: Neo4j via memory.py. Extracted facts written after every turn,
    retrieved at the start of every turn. Survives restarts.

Prior turns in the messages array carry the raw user message, not the
context-enriched turn_content — context (memory + KB) is injected fresh into
the current turn only, exactly as the CLI harness does.
"""

import asyncio
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Maximum number of prior turns retained per session in the in-memory store.
# Each turn = 2 messages (user + assistant), so the Claude messages array can
# grow to SESSION_HISTORY_LIMIT * 2 + 1 entries before hitting this cap.
SESSION_HISTORY_LIMIT = 10

# Short-term session history store.
# Maps session_id → list of {"role": "user"/"assistant", "content": str}.
# Non-persistent: resets on server restart. Known and accepted limitation for
# local dev — durable session storage is a production concern, not a local one.
_session_store: dict[str, list[dict]] = {}

# Static frontend directory — absolute path so the mount works regardless of
# where uvicorn is invoked from.
STATIC_DIR = Path(__file__).parent.parent / "static"

from dotenv import load_dotenv

load_dotenv()

from anthropic import Anthropic
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
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
    # initialise_memory() calls asyncio.run() internally; run it in a thread
    # so it gets its own event loop rather than conflicting with uvicorn's.
    await asyncio.to_thread(initialise_memory)
    app.state.system_prompt = load_system_prompt()
    app.state.client = Anthropic()
    yield


app = FastAPI(title="ATJ API", lifespan=lifespan)


class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str | None = None


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
    session_id = req.session_id or str(uuid.uuid4())
    history = _session_store.get(session_id, [])

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

    # Prior history uses raw user messages; context is injected fresh each turn.
    messages = history + [{"role": "user", "content": turn_content}]

    response = app.state.client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=app.state.system_prompt,
        messages=messages,
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

    updated = history + [
        {"role": "user", "content": req.message},
        {"role": "assistant", "content": displayed_text},
    ]
    _session_store[session_id] = updated[-(SESSION_HISTORY_LIMIT * 2):]

    return ChatResponse(
        response=displayed_text,
        compliant=check["compliant"],
        compliance_reason=check.get("reason"),
        fallback_triggered=fallback_triggered,
        memory_facts_retrieved=len(memories),
        memory_truncated=mem_truncated,
        session_id=session_id,
    )


# Serve static/ at / — must be mounted after all API routes so explicit routes
# take priority. html=True makes / serve index.html automatically.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
