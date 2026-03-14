from __future__ import annotations

from dataclasses import dataclass

from app.utils.patches import PreviewChange


@dataclass(slots=True)
class ApprovalGate:
    auto_apply: bool = False
    interactive: bool = True

    def should_apply(self, previews: list[PreviewChange]) -> bool:
        risky = any(preview.risky for preview in previews)
        large_change = len(previews) > 10
        if self.auto_apply and not risky and not large_change:
            return True
        if not self.interactive:
            return False
        response = input(
            f"Apply {len(previews)} proposed file change(s)"
            f"{' with risk flags' if risky else ''}? [y/N]: "
        ).strip().lower()
        return response in {"y", "yes"}
