import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dashboard import create_app
from app.memory.runs import RunStore
from app.models.settings import Settings


def test_dashboard_custom_data_directory_and_partial_artifacts(tmp_path: Path) -> None:
    directory = tmp_path / "custom" / "runs" / "test-run"
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps({"status": "running", "mode": "plan"}))
    (directory / "broken.json").write_text('{"unfinished":')
    (directory / "plan.md").write_text("# A plan")
    (directory / "usage.jsonl").write_text('{"usage":{"total_tokens":30}}\n{"unfinished":')
    client = TestClient(create_app(tmp_path, Settings(_env_file=None, swarm_data_dir=Path("custom"))))
    rows = client.get("/runs?details=true").json()
    assert rows[0]["total_tokens"] == 30
    result = client.get("/runs/test-run")
    assert result.status_code == 200
    assert result.json()["artifacts"]["plan.md"] == "# A plan"
    assert "broken.json" in result.json()["artifact_errors"]
    assert client.get("/runs?limit=0").status_code == 422


@pytest.mark.parametrize("run_id", ["..", "../outside", "a/b", "a\\b", ".hidden"])
def test_run_path_traversal_rejected(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(FileNotFoundError):
        RunStore(tmp_path).get(run_id)


def test_oversized_artifact_does_not_break_run(tmp_path: Path) -> None:
    directory = tmp_path / "runs" / "test-run"
    directory.mkdir(parents=True)
    (directory / "large.txt").write_bytes(b"a" * 1_000_001)
    result = RunStore(tmp_path).get("test-run")
    assert "large.txt" in result["artifact_errors"]
    assert result["artifacts"] == {}


def test_run_listing_pagination(tmp_path: Path) -> None:
    for name in ["a", "b", "c"]:
        (tmp_path / "runs" / name).mkdir(parents=True)
    assert [row["run_id"] for row in RunStore(tmp_path).list(limit=1, offset=1)] == ["b"]


def test_artifact_symlink_is_never_served(tmp_path: Path) -> None:
    directory = tmp_path / "runs" / "test-run"
    directory.mkdir(parents=True)
    outside = tmp_path / "private.txt"
    outside.write_text("PRIVATE")
    try:
        (directory / "link.txt").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires OS permission")
    result = RunStore(tmp_path).get("test-run")
    assert "link.txt" not in result["artifacts"]
    assert "link.txt" in result["artifact_errors"]
