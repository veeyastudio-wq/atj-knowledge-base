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

import psycopg2

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

_DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "atj"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
}

from dotenv import load_dotenv

load_dotenv()

from anthropic import Anthropic
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from memory import initialise_memory
from chat import load_system_prompt, run_turn
from case_file import get_conversation_history, get_documents, search_conversation_history


def save_turn(user_id: str, session_id: str, role: str, content: str) -> None:
    try:
        conn = psycopg2.connect(**_DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO conversation_history (user_id, session_id, role, content)"
            " VALUES (%s, %s, %s, %s)",
            (user_id, session_id, role, content),
        )
        conn.commit()
        cur.close()
        conn.close()
    except psycopg2.Error as exc:
        print(f"HISTORY WRITE ERROR: {exc}")


def save_document(
    user_id: str,
    session_id: str,
    document_label: str | None,
    transcribed_text: str,
) -> None:
    try:
        conn = psycopg2.connect(**_DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO document_store"
            " (user_id, session_id, document_label, transcribed_text)"
            " VALUES (%s, %s, %s, %s)",
            (user_id, session_id, document_label, transcribed_text),
        )
        conn.commit()
        cur.close()
        conn.close()
    except psycopg2.Error as exc:
        print(f"DOCUMENT WRITE ERROR: {exc}")


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
    image_data: str | None = None        # base64-encoded image bytes, no data-URL prefix
    image_media_type: str | None = None  # e.g. "image/jpeg", "image/png", "image/webp"


class ToolBlock(BaseModel):
    """Structured output from a single tool_use block returned by the model.

    tool_input carries the full data (stages for render_timeline, items for
    render_checklist) as returned by the model — this is what the frontend
    renders. It is returned over HTTP but is not written to chat_ops.jsonl;
    the log's data-minimisation behaviour (original_draft only on failures)
    is unchanged.
    """
    tool_name: str
    tool_input: dict
    compliant: bool
    compliance_reason: str | None


class ChatResponse(BaseModel):
    response: str
    compliant: bool
    compliance_reason: str | None  # first tool-block failure reason, or None.
    # Note: text-block failure reasons are not separately surfaced here —
    # run_turn() does not return them. fallback_triggered is always accurate;
    # compliance_reason may be None even when compliant=False for text-only
    # failures. Resolving this requires run_turn() to return richer data.
    fallback_triggered: bool
    session_id: str
    tool_blocks: list[ToolBlock]
    sources: list[str]


class CaseFileResponse(BaseModel):
    history: list[dict]
    documents: list[dict]


class SearchResponse(BaseModel):
    results: list[dict]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/case-file", response_model=CaseFileResponse)
def case_file(user_id: str):
    return CaseFileResponse(
        history=get_conversation_history(user_id, limit=100),
        documents=get_documents(user_id, limit=50),
    )


@app.get("/case-file/search", response_model=SearchResponse)
def case_file_search(user_id: str, q: str = ""):
    if not q.strip():
        return SearchResponse(results=[])
    return SearchResponse(results=search_conversation_history(user_id, q))


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    history = _session_store.get(session_id, [])

    # run_turn handles memory retrieval, KB retrieval, the Claude API call with
    # tools, compliance checks on every returned block (text and tool_use),
    # fallback logic, and memory writes. All the logic that was previously
    # duplicated here now lives in one place.
    result = run_turn(
        req.message,
        history,
        app.state.system_prompt,
        app.state.client,
        req.user_id,
        session_id,
        image_data=req.image_data,
        image_media_type=req.image_media_type,
    )

    displayed_text = result["displayed_text"]

    if req.image_data is not None:
        save_document(req.user_id, session_id, None, displayed_text)

    tool_blocks = [
        ToolBlock(
            tool_name=tool_name,
            # Suppress generated content for failing blocks — only compliant
            # content is sent to the client. Mirrors the text field: failing
            # text is swapped for FALLBACK_RESPONSE before serialisation.
            # The full tool_input is retained server-side in run_turn()'s
            # result and in chat_ops.jsonl (original_draft on fail).
            tool_input=tool_input if tool_check["compliant"] else {},
            compliant=tool_check["compliant"],
            compliance_reason=tool_check.get("reason"),
        )
        for tool_name, tool_input, tool_check in result["tool_results"]
    ]

    # Surface the first tool-block failure as the top-level compliance_reason.
    compliance_reason = next(
        (tb.compliance_reason for tb in tool_blocks if not tb.compliant),
        None,
    )

    # Prior history uses raw user messages; context is injected fresh each turn.
    updated = history + [
        {"role": "user", "content": req.message},
        {"role": "assistant", "content": displayed_text},
    ]
    _session_store[session_id] = updated[-(SESSION_HISTORY_LIMIT * 2):]
    save_turn(req.user_id, session_id, "user", req.message)
    save_turn(req.user_id, session_id, "assistant", displayed_text)

    return ChatResponse(
        response=displayed_text,
        compliant=result["compliant"],
        compliance_reason=compliance_reason,
        fallback_triggered=result["fallback_fired"],
        session_id=session_id,
        tool_blocks=tool_blocks,
        sources=result["sources"],
    )


# Serve static/ at / — must be mounted after all API routes so explicit routes
# take priority. html=True makes / serve index.html automatically.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
