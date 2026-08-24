from __future__ import annotations

import socket
import threading
from dataclasses import replace
from pathlib import Path
from urllib.request import urlopen

import pytest

from bedding_order_parser.desktop.resource_paths import (
    ApplicationPaths,
    asset_root,
)
from bedding_order_parser.desktop.server_controller import (
    ServerController,
    ServerStartupError,
)
from bedding_order_parser.web.app import create_server
from bedding_order_parser.web.services import JobService


class DeferredExecutor:
    def submit(self, _function, *_args) -> None:
        return None

    def shutdown(self, **_kwargs) -> None:
        return None


def paths(tmp_path: Path) -> ApplicationPaths:
    app = tmp_path / "local"
    data = tmp_path / "data"
    return ApplicationPaths(
        asset_root=asset_root(frozen=False),
        app_root=app,
        config_path=app / "config" / "app_config.json",
        task_root=app / "tasks",
        log_path=app / "logs" / "app.log",
        cache_root=app / "cache",
        state_root=app / "state",
        project_root=tmp_path,
        data_dir=data,
        material_store=data / "material.sqlite3",
        index_dir=data / "index",
        faiss_index=data / "index" / "duvet_cover.faiss",
        faiss_mapping=data / "index" / "duvet_cover_mapping.jsonl",
        vector_manifest=data / "index" / "vector_index_manifest.json",
        rules_path=data / "reference" / "rules.xlsx",
        styles_path=data / "reference" / "styles.xlsx",
        model_cache=data / "model",
    )


def service_for(tmp_path: Path) -> JobService:
    return JobService(
        tmp_path / "tasks",
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=DeferredExecutor(),
        desktop_mode=True,
    )


def test_controller_starts_health_endpoint_and_stops(tmp_path: Path) -> None:
    controller = ServerController(
        paths(tmp_path),
        preferred_port=0,
        health_timeout=3,
        service=service_for(tmp_path),
    )

    url = controller.start()
    assert url.startswith("http://127.0.0.1:")
    with urlopen(f"{url}/health", timeout=3) as response:
        assert response.status == 200
    thread = controller.thread
    controller.stop()

    assert thread is not None
    assert not thread.is_alive()
    assert controller.server is None
    assert controller.url == ""
    assert controller.thread is None


def test_controller_falls_back_when_preferred_port_is_occupied(
    tmp_path: Path,
) -> None:
    occupied = socket.socket()
    occupied.bind(("127.0.0.1", 0))
    occupied.listen()
    port = occupied.getsockname()[1]
    controller = ServerController(
        paths(tmp_path),
        preferred_port=port,
        health_timeout=3,
        service=service_for(tmp_path),
    )
    try:
        url = controller.start()
        assert not url.endswith(f":{port}")
    finally:
        controller.stop()
        occupied.close()


def test_controller_falls_back_when_web_server_occupies_port(
    tmp_path: Path,
) -> None:
    existing_service = service_for(tmp_path / "existing")
    existing_server = create_server(port=0, service=existing_service)
    existing_thread = threading.Thread(
        target=existing_server.serve_forever,
        daemon=True,
    )
    existing_thread.start()
    occupied_port = existing_server.server_address[1]
    controller = ServerController(
        paths(tmp_path),
        preferred_port=occupied_port,
        health_timeout=3,
        service=service_for(tmp_path / "desktop"),
    )
    try:
        url = controller.start()
        assert not url.endswith(f":{occupied_port}")
    finally:
        controller.stop()
        existing_server.shutdown()
        existing_server.server_close()
        existing_service.close()
        existing_thread.join(timeout=3)


def test_startup_failure_cleans_up_server(tmp_path: Path, monkeypatch) -> None:
    controller = ServerController(
        paths(tmp_path),
        preferred_port=0,
        health_timeout=0.01,
        service=service_for(tmp_path),
    )

    def fail() -> None:
        raise ServerStartupError("health failed")

    monkeypatch.setattr(controller, "_wait_until_healthy", fail)
    with pytest.raises(ServerStartupError):
        controller.start()

    assert controller.server is None
    assert controller.thread is None
    assert controller.url == ""


def test_close_marks_running_job_interrupted(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    job = service.create_job("running.xlsx", b"PK\x03\x04test")
    service._set_progress(job["id"], 20, "解析中", active_stage=1)

    service.close()

    persisted = service.get_job(job["id"])
    assert persisted["status"] == "interrupted"
    assert persisted["current_stage"] == "任务已中断"
    assert service.active_jobs() == []


def test_active_jobs_are_limited_to_current_service_session(
    tmp_path: Path,
) -> None:
    root = tmp_path / "tasks"
    first = JobService(
        root,
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=DeferredExecutor(),
        desktop_mode=True,
    )
    created = first.create_job("stale.xlsx", b"PK\x03\x04test")
    second = JobService(
        root,
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=DeferredExecutor(),
        desktop_mode=True,
    )

    assert [job["id"] for job in first.active_jobs()] == [created["id"]]
    assert second.active_jobs() == []

    first.close()
    second.close()
