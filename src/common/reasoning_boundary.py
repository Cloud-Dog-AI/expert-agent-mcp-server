"""Final-content boundary for private model reasoning."""

from __future__ import annotations

from typing import Any

_PLAIN_REASONING_PREAMBLES = {
    "here's a thinking process:",
    "here is a thinking process:",
}


def strip_private_reasoning_tags(text: Any) -> str:
    """Remove explicit qwen-style private-reasoning blocks without touching prose."""
    value = str(text or "")
    lowered = value.lower()
    out: list[str] = []
    cursor = 0
    while True:
        start = lowered.find("<think>", cursor)
        if start < 0:
            out.append(value[cursor:])
            break
        out.append(value[cursor:start])
        end = lowered.find("</think>", start + len("<think>"))
        if end < 0:
            break
        cursor = end + len("</think>")
    return "".join(out).strip()


def clean_final_content(text: Any) -> str:
    """Remove a known leading prose-CoT preamble only at a report boundary.

    The plain-prose rule is deliberately structural: the exact preamble must be
    the first non-empty line and a Markdown report heading must follow it. The
    same phrase inside a report, or prose without a report heading, is preserved.
    """
    value = strip_private_reasoning_tags(text)
    lines = value.splitlines()
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None:
        return ""
    label = lines[first].strip().strip("*").strip().lower()
    if label not in _PLAIN_REASONING_PREAMBLES:
        return value
    for index in range(first + 1, min(len(lines), first + 81)):
        candidate = lines[index].lstrip()
        if candidate.startswith("# ") or candidate.startswith("## "):
            return "\n".join(lines[index:]).strip()
    return value


__all__ = ["clean_final_content", "strip_private_reasoning_tags"]
