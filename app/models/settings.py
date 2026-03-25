from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    nvidia_api_key: str | None = Field(default=None, alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        alias="NVIDIA_BASE_URL",
    )
    nvidia_local_nim_base_url: str = Field(
        default="http://localhost:8000/v1",
        alias="NVIDIA_LOCAL_NIM_BASE_URL",
    )
    nvidia_provider_mode: str = Field(default="serverless", alias="NVIDIA_PROVIDER_MODE")
    swarm_config_dir: Path = Field(default=Path("config"), alias="SWARM_CONFIG_DIR")
    swarm_data_dir: Path = Field(default=Path("data"), alias="SWARM_DATA_DIR")
    swarm_log_level: str = Field(default="INFO", alias="SWARM_LOG_LEVEL")
    swarm_default_test_command: str = Field(default="pytest -q", alias="SWARM_DEFAULT_TEST_COMMAND")
    swarm_default_lint_command: str = Field(
        default="python -m compileall app tests",
        alias="SWARM_DEFAULT_LINT_COMMAND",
    )
    swarm_auto_apply: bool = Field(default=False, alias="SWARM_AUTO_APPLY")
    swarm_max_file_bytes: int = Field(default=200_000, alias="SWARM_MAX_FILE_BYTES")
    swarm_max_focused_files: int = Field(default=8, alias="SWARM_MAX_FOCUSED_FILES")


def packaged_config_dir() -> Path:
    return (Path(__file__).resolve().parents[1] / "defaults" / "config").resolve()


def resolve_config_dir(root: Path, configured_dir: Path) -> Path:
    candidate = configured_dir if configured_dir.is_absolute() else root / configured_dir
    candidate = candidate.resolve()
    if candidate.exists():
        return candidate

    packaged = packaged_config_dir()
    if packaged.exists():
        return packaged

    raise FileNotFoundError(
        f"Could not find config directory at {candidate} and no packaged defaults were available."
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
