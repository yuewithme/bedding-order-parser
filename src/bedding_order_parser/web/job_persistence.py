"""Durable, bounded atomic persistence for local web job metadata."""

from __future__ import annotations

import ctypes
import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence


LOGGER = logging.getLogger("bedding_order_parser.web.job_persistence")
REPLACE_RETRY_DELAYS = (0.05, 0.10, 0.20, 0.40, 0.80)
TRANSIENT_WINDOWS_ERRORS = frozenset({5, 32, 33})


class AtomicJsonWriteError(OSError):
    """Raised after a bounded set of transient atomic-replace failures."""


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
    *,
    retry_delays: Sequence[float] = REPLACE_RETRY_DELAYS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Publish one complete UTF-8 JSON object without exposing partial content."""
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}."
        f"{uuid.uuid4().hex}.tmp"
    )
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())

        attempts = 1
        while True:
            try:
                os.replace(temporary, path)
                return
            except OSError as exc:
                if not _is_transient_replace_error(exc):
                    raise
                if attempts > len(retry_delays):
                    summary = _safe_error_summary(exc)
                    LOGGER.error(
                        "Atomic replace failed for %s after %s attempts: %s",
                        path.name,
                        attempts,
                        summary,
                    )
                    raise AtomicJsonWriteError(
                        f"无法保存 {path.name}；原子替换在 {attempts} 次尝试后"
                        f"仍失败（{summary}）。"
                    ) from exc
                delay = retry_delays[attempts - 1]
                LOGGER.warning(
                    "Retrying atomic replace for %s after %s (attempt %s)",
                    path.name,
                    _safe_error_summary(exc),
                    attempts,
                )
                sleep(delay)
                attempts += 1
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as exc:
            LOGGER.warning(
                "Could not remove temporary state file for %s: %s",
                path.name,
                _safe_error_summary(exc),
            )


def process_is_alive(pid: int) -> bool:
    """Return whether a process exists without sending a signal on Windows."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return ctypes.get_last_error() == 5
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_transient_replace_error(exc: OSError) -> bool:
    return isinstance(exc, PermissionError) or getattr(
        exc, "winerror", None
    ) in TRANSIENT_WINDOWS_ERRORS


def _safe_error_summary(exc: OSError) -> str:
    winerror = getattr(exc, "winerror", None)
    if winerror is not None:
        return f"{type(exc).__name__}/WinError {winerror}"
    errno = getattr(exc, "errno", None)
    if errno is not None:
        return f"{type(exc).__name__}/errno {errno}"
    return type(exc).__name__
