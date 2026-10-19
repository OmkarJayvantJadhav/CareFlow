"""Prompt token budgeting (NFR-10, docs §12).

Token counts are estimated without a tokenizer: about 4 characters per token
for Latin text and about 2 for Devanagari, which Llama-style tokenizers split
more finely. The estimate errs on the high side so prompts stay under the
provider's tokens-per-minute limits.
"""

import json

MESSAGE_OVERHEAD = 4
MIN_TOOL_RESULT_CHARS = 300


def estimate_text(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return ascii_chars // 4 + (len(text) - ascii_chars) // 2 + 1


def estimate_message(message: dict) -> int:
    total = MESSAGE_OVERHEAD + estimate_text(message.get("content") or "")
    for call in message.get("tool_calls") or []:
        total += estimate_text(call["function"]["name"]) + estimate_text(call["function"]["arguments"])
    return total


def estimate_tools(tools: list[dict]) -> int:
    return estimate_text(json.dumps(tools, separators=(",", ":")))


def estimate_prompt(messages: list[dict], tools: list[dict]) -> int:
    return sum(estimate_message(m) for m in messages) + estimate_tools(tools)


def fit_to_budget(system: dict, history: list[dict], turn: list[dict], tools: list[dict], budget: int) -> list[dict]:
    """Assemble system + as much recent history as fits + the current turn.

    The current turn is always kept; if it alone is too large, its longest tool
    results are shortened until the prompt fits (or cannot shrink further).
    """
    fixed = estimate_message(system) + estimate_tools(tools)
    turn = [dict(m) for m in turn]

    def turn_cost() -> int:
        return sum(estimate_message(m) for m in turn)

    while fixed + turn_cost() > budget:
        tool_messages = [
            m for m in turn if m.get("role") == "tool" and len(m.get("content") or "") > MIN_TOOL_RESULT_CHARS
        ]
        if not tool_messages:
            break
        longest = max(tool_messages, key=lambda m: len(m["content"]))
        longest["content"] = (
            longest["content"][: max(MIN_TOOL_RESULT_CHARS, len(longest["content"]) // 2)] + "…(truncated)"
        )

    remaining = budget - fixed - turn_cost()
    kept: list[dict] = []
    for message in reversed(history):
        cost = estimate_message(message)
        if cost > remaining:
            break
        kept.append(message)
        remaining -= cost
    kept.reverse()
    # A tool result is meaningless without the assistant message that requested it.
    while kept and kept[0].get("role") == "tool":
        kept.pop(0)
    return [system, *kept, *turn]
