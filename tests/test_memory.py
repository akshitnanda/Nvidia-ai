from pathlib import Path

from app.memory.store import MemoryStore


def test_memory_store_roundtrip(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.add_entry("decision", "test", "Created the first memory entry.", {"source": "unit-test"})

    entries = store.recent_entries(limit=1)

    assert len(entries) == 1
    assert entries[0]["kind"] == "decision"
    assert entries[0]["metadata"]["source"] == "unit-test"

