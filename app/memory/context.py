from __future__ import annotations

from app.memory.store import MemoryStore


def render_recent_memory(memory_store: MemoryStore, limit: int = 5) -> str:
    entries = memory_store.recent_entries(limit=limit)
    if not entries:
        return "No prior local project memory."
    lines = []
    for entry in entries:
        lines.append(
            f"[{entry['created_at']}] ({entry['kind']}/{entry['scope']}) {entry['content'][:300]}"
        )
    return "\n".join(lines)

