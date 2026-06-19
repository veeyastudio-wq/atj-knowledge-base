"""
scripts/generative_ui_spike.py

Phase 2 generative UI spike — tool-use schema test.

Tests whether Claude reliably produces render_timeline and render_checklist
tool_use blocks with the exact schema the frontend expects. Sends 5 varied
prompts against a minimal context (no RAG, no memory, no compliance check).
For each prompt, the raw tool_use block is printed for manual inspection.

Not imported by or connected to any other module in this project.

Usage:
    python3.12 scripts/generative_ui_spike.py
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

SYSTEM = (
    "You are an assistant for people navigating divorce and family court "
    "proceedings in England and Wales. When asked about a process, journey, "
    "or sequence of steps, always use the render_timeline tool. When asked "
    "what someone needs to do or prepare — tasks, documents, steps to complete "
    "before a deadline — always use the render_checklist tool. Use realistic, "
    "accurate content drawn from the England and Wales family court system. "
    "Always call one of the provided tools; do not reply in plain text."
)

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
                "title": {
                    "type": "string",
                    "description": "Short heading for the timeline.",
                },
                "stages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":          {"type": "string"},
                            "label":       {"type": "string"},
                            "status":      {
                                "type": "string",
                                "enum": ["upcoming", "current", "complete"],
                            },
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
                "title": {
                    "type": "string",
                    "description": "Short heading for the checklist.",
                },
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
]

PROMPTS = [
    "What happens after I file for divorce?",
    "What do I need to do before my financial dispute resolution hearing?",
    "Can you show me the financial remedy track from the very start?",
    "What are the steps involved in a C100 child arrangements application?",
    "What documents do I need to bring to my First Appointment?",
]


def run_prompt(client: Anthropic, prompt: str, index: int) -> None:
    sep = "─" * 64
    print(f"\n{sep}")
    print(f"Prompt {index}: {prompt}")
    print(sep)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        tools=TOOLS,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": prompt}],
    )

    tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
    if not tool_use_blocks:
        print(f"[No tool_use block — stop_reason: {response.stop_reason}]")
        return

    for block in tool_use_blocks:
        print(f"\ntool: {block.name}")
        print("input:")
        print(json.dumps(block.input, indent=2, ensure_ascii=False))


def main() -> None:
    client = Anthropic()
    for i, prompt in enumerate(PROMPTS, 1):
        run_prompt(client, prompt, i)
    sep = "─" * 64
    print(f"\n{sep}")
    print(f"Done. {len(PROMPTS)} prompts completed.")
    print(sep)


if __name__ == "__main__":
    main()
