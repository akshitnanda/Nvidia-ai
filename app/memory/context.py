from __future__ import annotations

from app.memory.store import MemoryStore
import json
from typing import Any


def bounded_context(context: dict[str, Any], max_bytes: int) -> tuple[dict[str, Any], bool]:
    """Keep valid JSON and explicit truncation markers instead of cutting serialized data."""
    def size(value):
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))

    if size(context) <= max_bytes:
        return context, False
    string_limit, collection_limit = max_bytes // 8, 30

    def clip(value):
        if isinstance(value, str):
            encoded = value.encode("utf-8")
            return value if len(encoded) <= string_limit else encoded[:string_limit].decode("utf-8", errors="ignore") + "\n[truncated]"
        if isinstance(value, dict):
            return {key: clip(item) for key, item in list(value.items())[:collection_limit]}
        if isinstance(value, list):
            return [clip(item) for item in value[:collection_limit]]
        return value

    for _ in range(16):
        candidate = clip(context)
        candidate["_context_notice"] = "Context was truncated to the operator byte budget; omitted evidence is not verified."
        if size(candidate) <= max_bytes:
            return candidate, True
        string_limit = max(32, string_limit // 2)
        collection_limit = max(1, collection_limit // 2)
    return {"_context_notice": "Context exceeded the byte budget; inspect artifacts and narrow the task."}, True


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

