"""Lifecycle controller for the existing standard-library HTTP server."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from bedding_order_parser.desktop.resource_paths import ApplicationPaths
from bedding_order_parser.desktop.ai_full_order_composition import (
    DesktopV2DownstreamFactory,
)
from bedding_order_parser.desktop.runtime_identity import build_runtime_identity
from bedding_order_parser.web.app import WebServer, create_server
from bedding_order_parser.web.services import JobService


class ServerStartupError(RuntimeError):
    """Raised when the local-only server cannot become healthy."""


class ServerController:
    """Start, health-check, and stop the Gate 4A HTTP server."""

    def __init__(
        self,
        paths: ApplicationPaths,
        *,
        preferred_port: int = 8000,
        health_timeout: float = 15.0,
        service: JobService | None = None,
        ai_enhanced_settings: Any | None = None,
        ai_enhanced_transport: Any | None = None,
        ai_enhanced_downstream_factory: Any | None = None,
    ) -> None:
        self.paths = paths
        self.preferred_port = preferred_port
        self.health_timeout = health_timeout
        downstream_factory = ai_enhanced_downstream_factory or DesktopV2DownstreamFactory(paths)
        self.service = service or JobService(
            root=paths.task_root,
            store_path=paths.material_store,
            index_dir=paths.index_dir,
            dictionary_rules_path=paths.rules_path,
            dictionary_styles_path=paths.styles_path,
            ai_enhanced_settings=ai_enhanced_settings,
            ai_enhanced_transport=ai_enhanced_transport,
            ai_enhanced_downstream_factory=downstream_factory,
            desktop_mode=True,
        )
        self.runtime_identity = build_runtime_identity(
            project_root=paths.project_root or paths.app_root,
            asset_root=paths.asset_root,
        )
        self.server: WebServer | None = None
        self.thread: threading.Thread | None = None
        self.url = ""
        self._stop_lock = threading.Lock()
        self._stopped = False

    def start(self) -> str:
        if self._stopped:
            raise ServerStartupError("本地服务已经停止，无法重新启动。")
        if self.server is not None:
            return self.url
        try:
            try:
                server = create_server(
                    host="127.0.0.1",
                    port=self.preferred_port,
                    service=self.service,
                    asset_root=self.paths.asset_root,
                    runtime_identity=self.runtime_identity.to_public_dict(),
                )
            except OSError:
                server = create_server(
                    host="127.0.0.1",
                    port=0,
                    service=self.service,
                    asset_root=self.paths.asset_root,
                    runtime_identity=self.runtime_identity.to_public_dict(),
                )
            self.server = server
            host, port = server.server_address
            self.url = f"http://{host}:{port}"
            self.thread = threading.Thread(
                target=server.serve_forever,
                name="bedding-local-http",
                daemon=True,
            )
            self.thread.start()
            self._wait_until_healthy()
            return self.url
        except Exception as exc:
            self.stop()
            if isinstance(exc, ServerStartupError):
                raise
            raise ServerStartupError("本地服务启动失败。") from exc

    def stop(self) -> None:
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True
            server = self.server
            thread = self.thread
            self.service.stop_accepting()
            if server is not None:
                server.shutdown()
                server.server_close()
            self.service.close()
            if thread is not None and thread.is_alive():
                thread.join(timeout=5)
            self.server = None
            self.thread = None
            self.url = ""

    def _wait_until_healthy(self) -> None:
        deadline = time.monotonic() + self.health_timeout
        health_url = f"{self.url}/health"
        while time.monotonic() < deadline:
            if self.thread is not None and not self.thread.is_alive():
                break
            try:
                with urlopen(health_url, timeout=1) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if response.status == 200 and payload.get("status") == "ok":
                    return
            except (OSError, URLError, json.JSONDecodeError):
                time.sleep(0.1)
        raise ServerStartupError("本地服务健康检查超时。")
