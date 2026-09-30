"""Persist terminal workflow state, including failures before a result exists."""

from functools import wraps
from typing import Any, Callable


def tracked(mode: str) -> Callable:
    def decorate(method: Callable) -> Callable:
        @wraps(method)
        def run(self: Any, *args: Any, **kwargs: Any) -> Any:
            task = str(kwargs.get("task") or (args[0] if args and isinstance(args[0], str) else mode))
            self.run_logger.start(mode, task, self.settings.nvidia_provider_mode)
            try:
                result = method(self, *args, **kwargs)
            except BaseException as exc:
                self.run_logger.finish(error=exc)
                raise
            self.run_logger.finish(result=result)
            return result
        return run
    return decorate
