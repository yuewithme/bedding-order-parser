from __future__ import annotations

from types import SimpleNamespace

from bedding_order_parser.desktop import launcher
from bedding_order_parser.desktop.desktop_api import DesktopApi
from bedding_order_parser.desktop.resource_paths import asset_root


class EventHook:
    def __init__(self) -> None:
        self.handler = None

    def __iadd__(self, handler):
        self.handler = handler
        return self


class FakeWindow:
    def __init__(self) -> None:
        self.events = SimpleNamespace(closing=EventHook())
        self.confirmed = True
        self.confirmation_message = ""

    def create_confirmation_dialog(self, _title, message):
        self.confirmation_message = message
        return self.confirmed


def test_webview_uses_dynamic_local_url_and_window_contract(
    tmp_path, monkeypatch
) -> None:
    captured = {}
    window = FakeWindow()
    service = SimpleNamespace(
        active_jobs=lambda: [],
        active_ai_advisories=lambda: [],
    )
    application = launcher.DesktopApplication()
    application.paths = SimpleNamespace(
        asset_root=asset_root(frozen=False)
    )
    application.controller = SimpleNamespace(service=service)

    def create_window(title, **kwargs):
        captured["title"] = title
        captured.update(kwargs)
        return window

    monkeypatch.setattr(launcher.webview, "create_window", create_window)
    monkeypatch.setattr(
        launcher.webview,
        "start",
        lambda **kwargs: captured.update({"start": kwargs}),
    )

    url = "http://127.0.0.1:54321"
    result = application._run_webview(url)

    assert result == 0
    assert captured["title"] == "订单解析助手"
    assert captured["url"] == url
    assert captured["width"] == 1440
    assert captured["height"] == 900
    assert captured["min_size"] == (1180, 720)
    assert captured["start"]["gui"] == "edgechromium"
    assert captured["start"]["debug"] is False
    assert isinstance(captured["js_api"], DesktopApi)
    assert window.events.closing.handler == application._on_closing


def test_closing_during_ai_advisory_requires_explicit_confirmation() -> None:
    application = launcher.DesktopApplication()
    window = FakeWindow()
    window.confirmed = False
    application.window = window
    application.controller = SimpleNamespace(
        service=SimpleNamespace(
            active_jobs=lambda: [],
            active_ai_advisories=lambda: [
                {"state": "running", "record_index": 2}
            ],
        )
    )

    assert application._on_closing() is False
    assert "AI建议正在生成" in window.confirmation_message
    assert "Token费用" in window.confirmation_message


def test_application_always_stops_server_and_releases_lock(
    tmp_path, monkeypatch
) -> None:
    events = []
    paths = SimpleNamespace(
        state_root=tmp_path / "state",
        model_cache=tmp_path / "model",
    )
    paths.state_root.mkdir()

    class FakeLock:
        def __init__(self, **_kwargs) -> None:
            pass

        def acquire(self) -> None:
            events.append("lock.acquire")

        def release(self) -> None:
            events.append("lock.release")

    class FakeController:
        def __init__(self, _paths) -> None:
            self.service = object()

        def start(self) -> str:
            events.append("server.start")
            return "http://127.0.0.1:8000"

        def stop(self) -> None:
            events.append("server.stop")

    monkeypatch.setattr(launcher, "local_app_root", lambda: tmp_path)
    monkeypatch.setattr(launcher, "configure_logging", lambda _path: None)
    monkeypatch.setattr(launcher, "resolve_application_paths", lambda: paths)
    monkeypatch.setattr(
        launcher, "validate_startup_paths", lambda _paths: events.append("validate")
    )
    monkeypatch.setattr(launcher, "SingleInstanceLock", FakeLock)
    monkeypatch.setattr(launcher, "ServerController", FakeController)

    application = launcher.DesktopApplication()
    monkeypatch.setattr(
        application,
        "_write_runtime_state",
        lambda _url: events.append("state.write"),
    )
    monkeypatch.setattr(
        application,
        "_run_webview",
        lambda _url: events.append("window.run") or 0,
    )

    assert application.run() == 0
    assert events == [
        "lock.acquire",
        "validate",
        "server.start",
        "state.write",
        "window.run",
        "server.stop",
        "lock.release",
    ]
