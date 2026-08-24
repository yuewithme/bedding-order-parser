"""Local HTTP server entry point."""

from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path

from bedding_order_parser.web.routes import WebRequestHandler
from bedding_order_parser.web.services import JobService


DEFAULT_ASSET_ROOT = Path(__file__).resolve().parent


class WebServer(ThreadingHTTPServer):
    """Threaded local server carrying the application service."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        address: tuple[str, int],
        service: JobService,
        *,
        asset_root: Path,
        runtime_identity: dict[str, str] | None = None,
    ) -> None:
        super().__init__(address, WebRequestHandler)
        self.service = service
        self.template_path = asset_root / "templates" / "index.html"
        self.static_root = asset_root / "static"
        self.runtime_identity = dict(runtime_identity or {})


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    service: JobService | None = None,
    asset_root: str | Path | None = None,
    runtime_identity: dict[str, str] | None = None,
) -> WebServer:
    """Create a local-only server; binding is deferred to the caller."""
    assets = Path(asset_root or DEFAULT_ASSET_ROOT).resolve()
    return WebServer(
        (host, port), service or JobService(), asset_root=assets,
        runtime_identity=runtime_identity,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bedding_order_parser.web",
        description="Run the local Bedding Order Parser web interface.",
    )
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = create_server(port=args.port)
    host, port = server.server_address
    print(f"订单解析助手已启动：http://{host}:{port}")
    print("按 Ctrl+C 停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        server.server_close()
        server.service.close()
    return 0
