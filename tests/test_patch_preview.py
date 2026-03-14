from pathlib import Path

from app.models.runtime import ProposedFileChange
from app.tools.filesystem import FileSystemTool


def test_preview_change_includes_unified_diff(tmp_path: Path) -> None:
    target = tmp_path / "example.txt"
    target.write_text("before\n", encoding="utf-8")

    tool = FileSystemTool(tmp_path, max_file_bytes=100_000)
    preview = tool.preview_change(
        ProposedFileChange(
            path="example.txt",
            action="create_or_update",
            reason="update",
            content="after\n",
        )
    )

    assert "--- a/example.txt" in preview.diff
    assert "+++ b/example.txt" in preview.diff
    assert "-before" in preview.diff
    assert "+after" in preview.diff

