from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from bedding_order_parser.web.app import create_server
from bedding_order_parser.web.services import JobService


class DeferredExecutor:
    def __init__(self) -> None:
        self.submissions: list[tuple[object, tuple[object, ...]]] = []

    def submit(self, function, *args):
        self.submissions.append((function, args))
        return None


@pytest.fixture
def local_server(tmp_path: Path):
    executor = DeferredExecutor()
    service = JobService(
        tmp_path / "web",
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=executor,
    )
    server = create_server(port=0, service=service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}", service, executor
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def read_url(url: str) -> tuple[int, str, bytes]:
    with urlopen(url, timeout=5) as response:
        return response.status, response.headers["Content-Type"], response.read()


def test_home_and_static_assets_are_served(local_server) -> None:
    base_url, _, _ = local_server

    status, content_type, body = read_url(f"{base_url}/")
    css_status, css_type, css_body = read_url(
        f"{base_url}/static/styles.css"
    )
    js_status, js_type, js_body = read_url(f"{base_url}/static/app.js")

    assert status == 200
    assert content_type == "text/html; charset=utf-8"
    assert "订单解析助手".encode() in body
    assert css_status == 200
    assert css_type == "text/css; charset=utf-8"
    assert b".progress-ring" in css_body
    assert js_status == 200
    assert "javascript" in js_type
    assert b"renderHistory" in js_body


def test_upload_endpoint_creates_job_and_starts_background_work(
    local_server,
) -> None:
    base_url, service, executor = local_server
    boundary = "----Gate4ATestBoundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="PI_test.xlsx"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n"
        "\r\n"
    ).encode() + b"PK\x03\x04workbook" + (
        f"\r\n--{boundary}--\r\n"
    ).encode()
    request = Request(
        f"{base_url}/api/jobs",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )

    with urlopen(request, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))

    assert response.status == 201
    assert payload["file_name"] == "PI_test.xlsx"
    assert "ai_allowed" not in payload
    assert len(executor.submissions) == 1
    assert service.get_job(payload["id"])["status"] == "queued"


def test_upload_endpoint_returns_chinese_validation_error(local_server) -> None:
    base_url, _, executor = local_server
    request = Request(
        f"{base_url}/api/jobs",
        data=b"plain",
        method="POST",
        headers={"Content-Type": "text/plain", "Content-Length": "5"},
    )

    with pytest.raises(HTTPError) as caught:
        urlopen(request, timeout=5)

    payload = json.loads(caught.value.read().decode("utf-8"))
    assert caught.value.code == 400
    assert "文件上传方式" in payload["error"]
    assert executor.submissions == []


def test_history_endpoint_returns_created_jobs(local_server) -> None:
    base_url, service, _ = local_server
    service.create_job("history.xlsx", b"PK\x03\x04history")

    status, _, body = read_url(f"{base_url}/api/jobs")
    payload = json.loads(body.decode("utf-8"))

    assert status == 200
    assert payload["jobs"][0]["file_name"] == "history.xlsx"
