"""Desktop application orchestration."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import webview

from bedding_order_parser.desktop.app_logging import configure_logging
from bedding_order_parser.desktop.desktop_api import DesktopApi
from bedding_order_parser.desktop.instance_lock import (
    SingleInstanceError,
    SingleInstanceLock,
)
from bedding_order_parser.desktop.resource_paths import (
    ApplicationPaths,
    ResourceConfigurationError,
    local_app_root,
    resolve_application_paths,
    validate_startup_paths,
)
from bedding_order_parser.desktop.server_controller import (
    ServerController,
    ServerStartupError,
)


APP_TITLE = "订单解析助手"
LOGGER = logging.getLogger("bedding_order_parser.desktop")


class DesktopWindowError(RuntimeError):
    """Raised when the native desktop window cannot be created."""


class DesktopApplication:
    """Own the lock, HTTP service, WebView window, and shutdown sequence."""

    def __init__(self) -> None:
        self.paths: ApplicationPaths | None = None
        self.lock: SingleInstanceLock | None = None
        self.controller: ServerController | None = None
        self.window = None
        self._shutdown_started = False
        self._started_at = time.perf_counter()

    def run(self) -> int:
        try:
            fallback_root = local_app_root()
            configure_logging(fallback_root / "logs" / "app.log")
            self.paths = resolve_application_paths()
            os.environ.setdefault("HF_HOME", str(self.paths.model_cache))
            self.lock = SingleInstanceLock(
                fallback_path=self.paths.state_root / "desktop.lock"
            )
            self.lock.acquire()
            validate_startup_paths(self.paths)
            self.controller = ServerController(self.paths)
            url = self.controller.start()
            self._write_runtime_state(url)
            return self._run_webview(url)
        except SingleInstanceError as exc:
            LOGGER.info("Desktop instance already running")
            _show_error(str(exc))
            return 2
        except (
            ResourceConfigurationError,
            ServerStartupError,
            DesktopWindowError,
        ) as exc:
            LOGGER.exception("Desktop startup validation failed")
            _show_error(str(exc))
            return 3
        except Exception:
            LOGGER.exception("Unexpected desktop startup failure")
            _show_error("订单解析助手启动失败，请查看本地日志。")
            return 4
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        try:
            if self.controller is not None:
                self.controller.stop()
        except Exception:
            LOGGER.exception("Failed to stop local HTTP service")
        if self.paths is not None:
            (self.paths.state_root / "runtime.json").unlink(missing_ok=True)
        if self.lock is not None:
            self.lock.release()

    def _run_webview(self, url: str) -> int:
        api = DesktopApi(self.controller.service)
        try:
            self.window = webview.create_window(
                APP_TITLE,
                url=url,
                js_api=api,
                width=1440,
                height=900,
                min_size=(1180, 720),
                background_color="#ffffff",
            )
            api.attach_window(self.window)
            self.window.events.closing += self._on_closing
            webview.start(
                gui="edgechromium",
                icon=str(self.paths.asset_root.parent / "desktop" / "resources" / "app.ico"),
                debug=False,
            )
            return 0
        except Exception:
            LOGGER.exception("WebView2 could not start")
            raise DesktopWindowError(
                "桌面窗口启动失败，请确认 Microsoft Edge WebView2 可用。"
            )

    def _on_closing(self) -> bool:
        active_jobs = self.controller.service.active_jobs()
        active_ai = self.controller.service.active_ai_advisories()
        if not active_jobs and not active_ai:
            return True
        if active_ai and not active_jobs:
            message = (
                "当前仍有一条AI建议正在生成，关闭可能中断结果保存，且已产生的"
                "Token费用无法撤回。确定关闭吗？"
            )
        else:
            message = (
                "当前仍有订单正在解析，关闭后该任务将被标记为中断。确定关闭吗？"
            )
        confirmed = self.window.create_confirmation_dialog(
            APP_TITLE,
            message,
        )
        if not confirmed:
            return False
        if active_jobs:
            self.controller.service.interrupt_active_jobs()
        return True

    def _write_runtime_state(self, url: str) -> None:
        path = self.paths.state_root / "runtime.json"
        temp = path.with_suffix(".tmp")
        payload = {
            "pid": os.getpid(),
            "url": url,
            "startup_seconds": round(time.perf_counter() - self._started_at, 3),
            "runtime_identity": self.controller.runtime_identity.to_public_dict(),
        }
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, path)


def _show_error(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_TITLE, message)
        root.destroy()
    except Exception:
        logging.getLogger("bedding_order_parser.desktop").error(message)


def main() -> int:
    if sys.platform == "win32":
        try:
            ctypes = __import__("ctypes")
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    return DesktopApplication().run()
