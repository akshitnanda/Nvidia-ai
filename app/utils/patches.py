from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path


@dataclass(slots=True)
class PreviewChange:
    path: Path
    action: str
    diff: str
    risky: bool


def build_unified_diff(path: Path, before: str, after: str) -> str:
    return "\n".join(
        unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{path.as_posix()}",
            tofile=f"b/{path.as_posix()}",
            lineterm="",
        )
    )


def extract_json_block(text: str) -> dict:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")
    return json.loads(text[start : end + 1])

