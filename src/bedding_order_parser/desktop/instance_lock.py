"""Per-user single-instance lock for the Windows desktop application."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path


ERROR_ALREADY_EXISTS = 183


class SingleInstanceError(RuntimeError):
    """Raised when another desktop instance is already running."""


class SingleInstanceLock:
    """Windows named mutex with a conservative file fallback."""

    def __init__(
        self,
        name: str = "Local\\BeddingOrderParserDesktop",
        *,
        fallback_path: str | Path | None = None,
    ) -> None:
        self.name = name
        self.fallback_path = Path(
            fallback_path or Path(os.getenv("TEMP", ".")) / f"{name}.lock"
        )
        self._handle: int | None = None
        self._fallback_descriptor: int | None = None

    def acquire(self) -> None:
        if os.name == "nt":
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateMutexW(None, False, self.name)
            if not handle:
                raise SingleInstanceError("无法创建应用单实例锁。")
            if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(handle)
                raise SingleInstanceError("订单解析助手已经在运行。")
            self._handle = int(handle)
            return
        try:
            descriptor = os.open(
                self.fallback_path,
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
                0o600,
            )
        except FileExistsError as exc:
            raise SingleInstanceError("订单解析助手已经在运行。") from exc
        self._fallback_descriptor = descriptor

    def release(self) -> None:
        if self._handle is not None:
            ctypes.windll.kernel32.ReleaseMutex(self._handle)
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
        if self._fallback_descriptor is not None:
            os.close(self._fallback_descriptor)
            self._fallback_descriptor = None
            self.fallback_path.unlink(missing_ok=True)

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, *_args) -> None:
        self.release()
