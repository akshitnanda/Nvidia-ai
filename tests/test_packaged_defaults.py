from pathlib import Path

from app.models.settings import packaged_config_dir, resolve_config_dir


def _normalized_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")


def test_packaged_defaults_match_repo_config() -> None:
    root = Path(__file__).resolve().parents[1]
    source_dir = root / "config"
    packaged_dir = packaged_config_dir()

    source_files = sorted(path.relative_to(source_dir) for path in source_dir.rglob("*") if path.is_file())
    packaged_files = sorted(
        path.relative_to(packaged_dir)
        for path in packaged_dir.rglob("*")
        if path.is_file() and path.name != "__init__.py"
    )

    assert packaged_files == source_files
    for relative_path in source_files:
        assert _normalized_text(packaged_dir / relative_path) == _normalized_text(source_dir / relative_path)


def test_resolve_config_dir_falls_back_to_packaged_defaults(tmp_path: Path) -> None:
    resolved = resolve_config_dir(tmp_path, Path("config"))

    assert resolved == packaged_config_dir()
    assert (resolved / "agents.yaml").exists()
