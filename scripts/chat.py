"""
scripts/chat.py

Test harness for the ATJ orchestration loop. Validates that case memory
retrieval, knowledge base retrieval, and the Claude API work together in a
single conversational turn. This is a CLI validation tool, not the production
interface, the production interface comes later in the build sequence.

Usage:
    python scripts/chat.py
"""

import re
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

sys.path.insert(0, str(Path(__file__).parent))

from memory import initialise_memory, retrieve_memory, write_memory, RETRIEVE_MEMORY_LIMIT
from retrieve import retrieve
from response_check import check_response, check_tool_use_block, FALLBACK_RESPONSE

load_dotenv()

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system_prompt.md"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048  # raised from 1500 to match spike: combined-track two-call responses need headroom
KB_TOP_K = 4  # kept deliberately tight, see context engineering notes

# Tool schemas — identical to scripts/generative_ui_spike.py; keep in sync manually.
TOOLS = [
    {
        "name": "render_timeline",
        "description": (
            "Render a vertical timeline of stages in a legal process or journey. "
            "Use for questions about what happens next, what a track looks like "
            "from start to finish, or where the user is in a multi-step process."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short heading for the timeline."},
                "stages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":          {"type": "string"},
                            "label":       {"type": "string"},
                            "status":      {"type": "string", "enum": ["upcoming", "current", "complete"]},
                            "description": {"type": "string"},
                            "date":        {"type": "string"},
                        },
                        "required": ["id", "label", "status"],
                    },
                },
            },
            "required": ["title", "stages"],
        },
    },
    {
        "name": "render_checklist",
        "description": (
            "Render a checklist of tasks or required items. Use for questions "
            "about what someone needs to do, prepare, or have ready — before a "
            "hearing, before filing, or at a given stage of proceedings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short heading for the checklist."},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":          {"type": "string"},
                            "label":       {"type": "string"},
                            "done":        {"type": "boolean"},
                            "description": {"type": "string"},
                        },
                        "required": ["id", "label", "done"],
                    },
                },
            },
            "required": ["title", "items"],
        },
    },
    {
        "name": "render_choices",
        "description": (
            "Render a short set of tappable options for the user to choose from. "
            "Use when asking a clarifying question that has a small, known set of "
            "answers — for example, where the user is in a process, what kind of "
            "document they are working on, or which path they want to take next. "
            "Do not use for open-ended questions where free text is more appropriate. "
            "Maximum 4 options."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question being asked. One sentence, plain English."
                },
                "options": {
                    "type": "array",
                    "description": "The choices available. Maximum 4 items.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":    {"type": "string"},
                            "label": {"type": "string", "description": "Short, plain English. Max 6 words."},
                        },
                        "required": ["id", "label"],
                    },
                },
            },
            "required": ["question", "options"],
        },
    },
]

# Appended to the loaded system prompt at call time; keeps system_prompt.md unchanged.
_TOOL_SYSTEM_ADDITION = (
    "\n\n## Visual output tools\n\n"
    "When asked about a process, journey, or sequence of steps, use the render_timeline tool. "
    "When asked what someone needs to do or prepare — tasks, documents, steps to complete "
    "before a deadline — use the render_checklist tool. "
    "If the user's question covers both the financial remedy track and the child arrangements "
    "track, call render_timeline twice in the same response — once for each track as its own "
    "complete, separate timeline. Do not merge both tracks into a single combined timeline. "
    "When asking the user a clarifying question that has a small fixed set of answers — such "
    "as where they are in a process, or which document they are working on — use the "
    "render_choices tool instead of asking the question in plain text. Maximum 4 options. "
    "Do not use render_choices for open-ended questions. "
    "For all other questions, reply in plain text as normal."
)


# Keywords and patterns used to identify time-sensitive memory facts.
# Checked against lowercased fact content; year pattern checked on raw content.
_TS_KEYWORDS = frozenset({
    "hearing", "deadline", "fdr", "fda", "directions",
    "appointment", "filing", "court date",
})
_TS_MONTHS = frozenset({
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
})
_TS_YEAR_RE = re.compile(r"\b20\d{2}\b")


def _time_sensitive_facts(memories: list) -> list[str]:
    """Return content strings of facts that appear to be time-sensitive.

    Scans for date-like signals: month names, 20xx year patterns, and keywords
    for events that occur at a specific point in time. Works only on the content
    strings already stored — does not call the extraction LLM or add fact types.
    """
    results = []
    for m in memories:
        content = m.get("content", "")
        lower = content.lower()
        if (
            any(kw in lower for kw in _TS_KEYWORDS)
            or any(month in lower for month in _TS_MONTHS)
            or bool(_TS_YEAR_RE.search(content))
        ):
            results.append(content)
    return results


def _returning_user_addition(time_sensitive: list[str]) -> str:
    """System prompt addition for a returning user's first turn.

    Only applied when conversation_history is empty and at least one
    time-sensitive fact exists. Instructs the model to surface upcoming
    items naturally — not as a notification or a bulleted list — and to
    follow the user's lead if they open with something different.
    """
    facts_block = "\n".join(f"- {f}" for f in time_sensitive)
    return (
        "\n\n## Returning user — upcoming items\n\n"
        "This is the start of a new conversation with a returning user. "
        "The following items from their case memory appear to be time-sensitive "
        "(a date, deadline, or upcoming event):\n\n"
        f"{facts_block}\n\n"
        "If it fits naturally with how the conversation opens, acknowledge "
        "what's coming up — the way a knowledgeable friend would mention it in "
        "passing, not as a system notification or a bulleted list. Reassuring "
        "and calm in tone. If the user's opening message takes the conversation "
        "in a different direction, follow their lead; don't force these items in."
    )


def load_system_prompt() -> str:
    if not SYSTEM_PROMPT_PATH.exists():
        raise FileNotFoundError(f"System prompt not found at {SYSTEM_PROMPT_PATH}")
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def format_memory_context(memories: list) -> str:
    if not memories:
        return "No prior case memory found for this user."
    return "\n".join(f"- ({m['created_at']}) {m['content']}" for m in memories)


def format_kb_context(kb_result: dict) -> str:
    parts = []
    for layer in ("layer2", "layer1"):
        chunks = kb_result.get(layer, [])
        if not chunks:
            continue
        parts.append(f"--- {layer.upper()} ---")
        for c in chunks:
            parts.append(f"[{c['source_file']}]\n{c['text']}")
    return "\n\n".join(parts) if parts else "No relevant knowledge base content found."


def extract_sources(kb_result: dict) -> list[str]:
    """Return distinct human-readable source titles from retrieved KB chunks.

    Layer 2 chunks carry metadata["title"]; layer 1 chunks carry
    metadata["source"]. Both are clean strings written at ingest time.
    Returned in retrieval order (layer2 first, then layer1), deduplicated.
    Returns [] if retrieval found nothing or metadata is absent.
    """
    seen: set[str] = set()
    sources: list[str] = []
    for layer in ("layer2", "layer1"):
        for chunk in kb_result.get(layer, []):
            meta = chunk.get("metadata") or {}
            if not isinstance(meta, dict):
                continue
            title = meta.get("title") or meta.get("source") or ""
            if title and title not in seen:
                seen.add(title)
                sources.append(title)
    return sources


def build_turn_content(user_message: str, memory_context: str, kb_context: str) -> str:
    return (
        f"<case_memory>\n{memory_context}\n</case_memory>\n\n"
        f"<knowledge_base_context>\n{kb_context}\n</knowledge_base_context>\n\n"
        f"<message>\n{user_message}\n</message>"
    )


def run_turn(
    user_message: str,
    conversation_history: list,
    system_prompt: str,
    client: Anthropic,
    user_identifier: str,
    session_id: str,
    image_data: str | None = None,
    image_media_type: str | None = None,
) -> dict:
    """Execute one conversational turn end-to-end.

    Retrieves memory and KB context, calls the Claude API with tools,
    runs the compliance check on every returned block (text and tool_use),
    handles the fallback, writes memory for the turn, and returns the result.

    Does not mutate conversation_history — the caller appends after this
    returns so the history update is visible at the call site.

    Returns:
        displayed_text  str   text shown to the user (or FALLBACK_RESPONSE)
        compliant       bool  False if any block failed compliance
        fallback_fired  bool  True when displayed_text is FALLBACK_RESPONSE
        tool_results    list  [(tool_name, tool_input, tool_check), ...]
    """
    try:
        memory_result = retrieve_memory(user_identifier, user_message)
        memories = memory_result["facts"]
        mem_truncated = memory_result["truncated"]
    except Exception as exc:
        print(f"[memory retrieval failed: {exc}]")
        memories = []
        mem_truncated = False

    try:
        kb_result = retrieve(user_message, top_k=KB_TOP_K)
    except Exception as exc:
        print(f"[knowledge base retrieval failed: {exc}]")
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
    sources = extract_sources(kb_result)

    if memories:
        print(f"[case_memory — {len(memories)} item(s) retrieved]")
        if mem_truncated:
            print(
                f"[case_memory — WARNING: result truncated at {RETRIEVE_MEMORY_LIMIT} facts, "
                f"older facts excluded from this turn]"
            )
        for m in memories:
            print(f"  {m['created_at']} | {m['role']} | {m['content'][:120]}")
    else:
        print("[case_memory — empty]")

    # On the first turn of a new session, scan for time-sensitive facts and
    # fold a note into the system prompt so the model can open naturally as
    # a returning-user-aware companion. No effect on subsequent turns or on
    # sessions where no time-sensitive facts are found.
    system_to_use = system_prompt + _TOOL_SYSTEM_ADDITION
    if not conversation_history and memories:
        ts = _time_sensitive_facts(memories)
        if ts:
            system_to_use += _returning_user_addition(ts)
            print(f"[returning user — {len(ts)} time-sensitive fact(s) surfaced in system prompt]")

    turn_content = build_turn_content(user_message, memory_context, kb_context)

    # When an image is present, build a multi-block content list so the image
    # is sent inline alongside the text context. The image bytes (base64) live
    # only in this local variable for the duration of the API call; they are
    # never written to disk, never logged, and not included in conversation
    # history (only the text response is stored after this function returns).
    if image_data and image_media_type:
        current_user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_media_type,
                    "data": image_data,
                },
            },
            {"type": "text", "text": turn_content},
        ]
    else:
        current_user_content = turn_content

    messages = conversation_history + [{"role": "user", "content": current_user_content}]

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_to_use,
        tools=TOOLS,
        tool_choice={"type": "auto"},
        messages=messages,
    )

    assistant_text = "".join(
        block.text for block in response.content if block.type == "text"
    )
    tool_use_blocks = [
        (block.name, block.input)
        for block in response.content
        if block.type == "tool_use"
    ]

    # Compliance checks — text block first, then each tool_use block.
    # Tool-use-only responses produce assistant_text="", which would trivially
    # pass a text-only check; tool_use blocks must always be checked explicitly.
    compliant = True
    fail_reason = None

    if assistant_text:
        # When the response also includes tool_use blocks, the text block is
        # typically a short framing sentence. Append a note so the checker does
        # not hallucinate additional content to fill the perceived gap. The note
        # explicitly states that brevity is not a reason to reduce scrutiny —
        # the checker must still flag the text present if it crosses into advice.
        _checker_text = assistant_text
        if tool_use_blocks:
            _checker_text = (
                assistant_text
                + "\n\n[Note for compliance checker: The text above is "
                "intentionally brief — the substantive content for this turn "
                "is being provided separately as one or more structured "
                "timelines or checklists alongside this response. Evaluate "
                "only the literal text given above. Do not generate, imagine, "
                "or attempt to complete additional content that was not given. "
                "Brevity is not a reason to reduce scrutiny: if the text "
                "actually present crosses into advice, flag it as normal.]"
            )
        text_check = check_response(
            user_message,
            _checker_text,
            user_identifier=user_identifier,
            session_id=session_id,
        )
        if text_check["compliant"]:
            print("  [compliance — text: PASS]")
        else:
            print(f"  [compliance — text: FAIL] {text_check['reason']}")
            compliant = False
            fail_reason = text_check["reason"]

    tool_results = []
    for tool_name, tool_input in tool_use_blocks:
        tool_check = check_tool_use_block(
            user_message,
            tool_name,
            tool_input,
            user_identifier=user_identifier,
            session_id=session_id,
            context_block_count=len(tool_use_blocks),
        )
        tool_results.append((tool_name, tool_input, tool_check))
        status = "PASS" if tool_check["compliant"] else f"FAIL: {tool_check['reason']}"
        print(f"  [compliance — {tool_name}: {status}]")
        print(f"  prose sent to checker:")
        for line in tool_check["prose"].splitlines():
            print(f"    {line}")
        if not tool_check["compliant"]:
            compliant = False
            fail_reason = tool_check["reason"]

    if not compliant:
        print(f"\n[COMPLIANCE FLAG] {fail_reason}\n")
        displayed_text = FALLBACK_RESPONSE
    elif tool_results:
        parts = []
        for tool_name, tool_input, _ in tool_results:
            if tool_name == "render_timeline":
                n = len(tool_input.get("stages", []))
                parts.append(f"[timeline: {tool_input.get('title', '?')} — {n} stages]")
            elif tool_name == "render_checklist":
                n = len(tool_input.get("items", []))
                parts.append(f"[checklist: {tool_input.get('title', '?')} — {n} items]")
            else:
                parts.append(f"[{tool_name}]")
        displayed_text = "\n".join(parts)
    elif assistant_text:
        displayed_text = assistant_text
    else:
        print("[warning: response contained no text and no tool_use blocks]")
        displayed_text = FALLBACK_RESPONSE

    try:
        write_memory(user_identifier, session_id, user_message, role="user")
        write_memory(user_identifier, session_id, displayed_text, role="assistant")
    except Exception as exc:
        print(f"[memory write failed: {exc}]")

    return {
        "displayed_text": displayed_text,
        "compliant": compliant,
        "fallback_fired": not compliant,
        "tool_results": tool_results,
        "sources": sources,
    }


def main():
    print("Initialising memory layer...")
    try:
        initialise_memory()
    except Exception as exc:
        print(f"Memory layer failed to initialise: {exc}")
        print("Check NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD in .env and that Neo4j is running.")
        sys.exit(1)

    system_prompt = load_system_prompt()
    client = Anthropic()

    user_identifier = input("Test user identifier (e.g. test_user_001): ").strip() or "test_user_001"
    session_id = str(uuid.uuid4())

    print(f"\nSession started. user={user_identifier} session={session_id}")
    print("Type 'exit' to quit.\n")

    # Conversation history stores the displayed text, not raw tool_use blocks.
    # Tool_use/tool_result pairs in history would require tool_result blocks
    # the test harness does not provide; a text summary is API-safe for
    # subsequent turns and sufficient for this harness.
    conversation_history = []

    while True:
        user_message = input("You: ").strip()
        if user_message.lower() in ("exit", "quit"):
            break
        if not user_message:
            continue

        result = run_turn(
            user_message,
            conversation_history,
            system_prompt,
            client,
            user_identifier,
            session_id,
        )

        displayed_text = result["displayed_text"]
        print(f"\nATJ: {displayed_text}\n")

        conversation_history.append({"role": "user", "content": user_message})
        conversation_history.append({"role": "assistant", "content": displayed_text})


if __name__ == "__main__":
    main()
