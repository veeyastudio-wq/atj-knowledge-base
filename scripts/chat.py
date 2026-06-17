"""
scripts/chat.py

Test harness for the ATJ orchestration loop. Validates that case memory
retrieval, knowledge base retrieval, and the Claude API work together in a
single conversational turn. This is a CLI validation tool, not the production
interface, the production interface comes later in the build sequence.

Usage:
    python scripts/chat.py
"""

import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

sys.path.insert(0, str(Path(__file__).parent))

from memory import initialise_memory, retrieve_memory, write_memory
from retrieve import retrieve
from response_check import check_response, FALLBACK_RESPONSE

load_dotenv()

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system_prompt.md"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1500
KB_TOP_K = 4  # kept deliberately tight, see context engineering notes


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


def build_turn_content(user_message: str, memory_context: str, kb_context: str) -> str:
    return (
        f"<case_memory>\n{memory_context}\n</case_memory>\n\n"
        f"<knowledge_base_context>\n{kb_context}\n</knowledge_base_context>\n\n"
        f"<message>\n{user_message}\n</message>"
    )


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

    conversation_history = []

    while True:
        user_message = input("You: ").strip()
        if user_message.lower() in ("exit", "quit"):
            break
        if not user_message:
            continue

        try:
            memories = retrieve_memory(user_identifier, user_message)
        except Exception as exc:
            print(f"[memory retrieval failed: {exc}]")
            memories = []

        try:
            kb_result = retrieve(user_message, top_k=KB_TOP_K)
        except Exception as exc:
            print(f"[knowledge base retrieval failed: {exc}]")
            kb_result = {}

        memory_context = format_memory_context(memories)
        kb_context = format_kb_context(kb_result)

        if memories:
            print(f"[case_memory — {len(memories)} item(s) retrieved]")
            for m in memories:
                print(f"  {m['created_at']} | {m['role']} | {m['content'][:120]}")
        else:
            print("[case_memory — empty]")

        turn_content = build_turn_content(user_message, memory_context, kb_context)

        messages = conversation_history + [{"role": "user", "content": turn_content}]

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        )
        assistant_text = "".join(
            block.text for block in response.content if block.type == "text"
        )

        check = check_response(
            user_message,
            assistant_text,
            user_identifier=user_identifier,
            session_id=session_id,
        )
        if not check["compliant"]:
            print(f"\n[COMPLIANCE FLAG] {check['reason']}\n")
            displayed_text = FALLBACK_RESPONSE
        else:
            displayed_text = assistant_text

        print(f"\nATJ: {displayed_text}\n")

        conversation_history.append({"role": "user", "content": user_message})
        conversation_history.append({"role": "assistant", "content": displayed_text})

        try:
            write_memory(user_identifier, session_id, user_message, role="user")
            write_memory(user_identifier, session_id, displayed_text, role="assistant")
        except Exception as exc:
            print(f"[memory write failed: {exc}]")


if __name__ == "__main__":
    main()
