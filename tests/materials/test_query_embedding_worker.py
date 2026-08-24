from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Sequence

import numpy as np
import pytest

from bedding_order_parser.materials import query_embedding_runner as runner
from bedding_order_parser.materials.query_embedding_runner import (
    QueryEmbeddingProcessError,
    QueryEmbeddingTimeout,
    encode_queries_isolated,
)
from bedding_order_parser.materials.query_embedding_worker import (
    DEVICE,
    DIMENSION,
    MODEL_NAME,
    MODEL_REVISION,
    QueryEmbeddingWorkerError,
    run_worker,
)


class FakeAdapter:
    model_name = MODEL_NAME
    revision = MODEL_REVISION
    device = DEVICE
    dimension = DIMENSION
    calls: list[tuple[list[str], int]] = []

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    def encode(self, texts: Sequence[str], *, batch_size: int) -> np.ndarray:
        self.calls.append((list(texts), batch_size))
        vector = np.zeros((len(texts), DIMENSION), dtype=np.float32)
        for index in range(len(texts)):
            vector[index, index] = 1.0
        return vector


def request_payload(texts: list[str]) -> dict:
    return {
        "schema_version": "1.0",
        "model_name": MODEL_NAME,
        "revision": MODEL_REVISION,
        "device": DEVICE,
        "normalize": True,
        "dimension": DIMENSION,
        "queries": [
            {"query_id": str(index), "query_text": text}
            for index, text in enumerate(texts)
        ],
    }


def test_worker_writes_ordered_normalized_float32_vectors(tmp_path: Path) -> None:
    FakeAdapter.calls = []
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    vectors = tmp_path / "vectors.npy"
    request.write_text(json.dumps(request_payload(["first", "second"])), encoding="utf-8")

    metadata = run_worker(
        request, response, vectors, adapter_factory=FakeAdapter
    )
    array = np.load(vectors, allow_pickle=False)

    assert metadata["status"] == "completed"
    assert metadata["query_ids"] == ["0", "1"]
    assert metadata["shape"] == [2, DIMENSION]
    assert metadata["dtype"] == "float32"
    assert metadata["completed_query_count"] == 2
    assert metadata["last_completed_query_id"] == "1"
    assert array.dtype == np.float32
    assert array.shape == (2, DIMENSION)
    assert np.allclose(np.linalg.norm(array, axis=1), 1.0)
    assert FakeAdapter.calls == [(["first", "second"], 2)]
    assert metadata["timings"]["model_load_seconds"] >= 0
    assert metadata["timings"]["encoding_seconds"] >= 0
    assert metadata["timings"]["vector_write_seconds"] >= 0
    assert metadata["timings"]["total_seconds"] == metadata["elapsed_seconds"]
    assert not list(tmp_path.glob("*.tmp"))


def test_worker_splits_large_query_sets_into_bounded_microbatches(tmp_path: Path) -> None:
    FakeAdapter.calls = []
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    vectors = tmp_path / "vectors.npy"
    texts = [f"query-{index}" for index in range(10)]
    request.write_text(json.dumps(request_payload(texts)), encoding="utf-8")

    metadata = run_worker(request, response, vectors, adapter_factory=FakeAdapter)

    assert metadata["completed_query_count"] == 10
    assert [len(call[0]) for call in FakeAdapter.calls] == [8, 2]
    assert [call[1] for call in FakeAdapter.calls] == [8, 2]


def test_worker_rejects_wrong_schema_without_loading_adapter(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    vectors = tmp_path / "vectors.npy"
    payload = request_payload(["first"])
    payload["schema_version"] = "wrong"
    request.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(QueryEmbeddingWorkerError, match="schema_version"):
        run_worker(request, response, vectors, adapter_factory=FakeAdapter)

    assert not vectors.exists()


def test_worker_source_has_no_faiss_or_sqlite_dependency() -> None:
    source = Path(
        sys.modules[
            "bedding_order_parser.materials.query_embedding_worker"
        ].__file__
    ).read_text(encoding="utf-8")

    assert "vector_index" not in source
    assert "faiss" not in source.lower()
    assert "sqlite" not in source.lower()


def test_worker_command_uses_python_module_in_source_runtime(tmp_path: Path) -> None:
    executable = tmp_path / "python.exe"
    command = runner._build_worker_command(
        executable,
        tmp_path / "request.json",
        tmp_path / "response.json",
        tmp_path / "vectors.npy",
        frozen=False,
    )

    assert command[:3] == [
        str(executable),
        "-m",
        "bedding_order_parser.materials.query_embedding_worker",
    ]


def test_worker_command_uses_frozen_entrypoint_switch(tmp_path: Path) -> None:
    executable = tmp_path / "订单解析助手.exe"
    command = runner._build_worker_command(
        executable,
        tmp_path / "request.json",
        tmp_path / "response.json",
        tmp_path / "vectors.npy",
        frozen=True,
    )

    assert command[:2] == [str(executable), "--embedding-worker"]


def _write_fake_worker(tmp_path: Path, mode: str) -> Path:
    script = tmp_path / f"fake_worker_{mode}.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import argparse, json, os, time
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--request")
            parser.add_argument("--response")
            parser.add_argument("--vectors")
            parser.add_argument("--pid-file")
            args = parser.parse_args()
            Path(args.pid_file).write_text(str(os.getpid()), encoding="utf-8")
            request = json.loads(Path(args.request).read_text(encoding="utf-8"))
            ids = [item["query_id"] for item in request["queries"]]
            mode = {mode!r}
            response = {{
                "schema_version": "1.0",
                "status": "starting" if mode == "no_ack" else "running",
                "stage": "encoding_queries",
                "worker_pid": os.getpid(), "started_at": "start",
                "completed_at": "", "query_ids": ids, "shape": [],
                "dtype": "", "normalized": True,
                "vector_file": Path(args.vectors).name,
                "completed_query_count": 0,
                "last_completed_query_id": "",
                "active_query_id": "0",
                "error_type": "", "error_summary": "",
                "traceback_summary": [],
                "timings": {{
                    "model_load_seconds": 0.1,
                    "encoding_seconds": 0.2,
                    "vector_write_seconds": 0.01,
                    "total_seconds": 0.4
                }}
            }}
            Path(args.response).write_text(json.dumps(response), encoding="utf-8")
            if mode == "no_ack":
                time.sleep(10)
            if mode in ("sleep", "cancel"):
                time.sleep(10)
            attempt_file = Path(args.pid_file).with_suffix(".attempt")
            attempt = (
                int(attempt_file.read_text(encoding="utf-8")) + 1
                if attempt_file.exists()
                else 1
            )
            attempt_file.write_text(str(attempt), encoding="utf-8")
            if mode == "transient" and attempt == 1:
                import sys
                sys.stderr.write("opaque transient exit\\n")
                raise SystemExit(3)
            if mode == "python_error":
                import sys
                response.update(
                    status="failed", error_type="FakeEncodeError",
                    error_summary="fake encode failure"
                )
                Path(args.response).write_text(json.dumps(response), encoding="utf-8")
                sys.stderr.write("fake encode failure\\n")
                raise SystemExit(2)
            if mode == "mid_error":
                response.update(completed_query_count=1, last_completed_query_id="0")
                Path(args.response).write_text(json.dumps(response), encoding="utf-8")
                raise SystemExit(3)
            if mode == "nonzero":
                raise SystemExit(3)
            import numpy as np
            rows = len(ids)
            shape = (rows, int(request["dimension"]))
            array = np.zeros(shape, dtype=np.float32)
            array[:, 0] = 1.0
            if mode == "dtype":
                array = array.astype(np.float64)
            if mode == "nan":
                array[0, 0] = np.nan
            if mode == "corrupt":
                Path(args.vectors).write_bytes(b"not-a-numpy-array")
            elif mode != "missing":
                with Path(args.vectors).open("wb") as handle:
                    np.save(handle, array, allow_pickle=False)
            if mode == "shape":
                response["shape"] = [rows, int(request["dimension"]) - 1]
            else:
                response["shape"] = list(array.shape)
            response.update(status="completed", completed_at="done", dtype=str(array.dtype))
            response.update(
                stage="completed", completed_query_count=rows,
                last_completed_query_id=ids[-1], active_query_id=""
            )
            Path(args.response).write_text(json.dumps(response), encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    return script


def _install_fake_command(
    monkeypatch, script: Path, pid_file: Path
) -> None:
    def command(executable, request, response, vectors):
        del executable
        return [
            sys.executable,
            str(script),
            "--request",
            str(request),
            "--response",
            str(response),
            "--vectors",
            str(vectors),
            "--pid-file",
            str(pid_file),
        ]

    monkeypatch.setattr(runner, "_build_worker_command", command)


def test_runner_completes_after_worker_exit_and_cleans_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    pid_file = tmp_path / "pid.txt"
    _install_fake_command(
        monkeypatch, _write_fake_worker(tmp_path, "ok"), pid_file
    )

    result = encode_queries_isolated(
        ["one", "two"],
        model_name=MODEL_NAME,
        revision=MODEL_REVISION,
        device=DEVICE,
        dimension=DIMENSION,
        normalize=True,
        runtime_root=runtime,
        startup_timeout=2,
        total_timeout=5,
        poll_interval=0.01,
    )

    assert result.worker_pid == int(pid_file.read_text(encoding="utf-8"))
    assert result.vectors.shape == (2, DIMENSION)
    assert result.vectors.dtype == np.float32
    assert result.diagnostics["attempts"][0]["worker_timings"] == {
        "model_load_seconds": 0.1,
        "encoding_seconds": 0.2,
        "vector_write_seconds": 0.01,
        "total_seconds": 0.4,
    }
    assert list(runtime.iterdir()) == []


def test_runner_timeout_terminates_exact_worker_and_cleans(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    pid_file = tmp_path / "pid.txt"
    _install_fake_command(
        monkeypatch, _write_fake_worker(tmp_path, "sleep"), pid_file
    )
    stopped: list[int] = []
    original = runner._request_and_stop

    def recording_stop(process, *args, **kwargs):
        stopped.append(kwargs.get("worker_pid") or process.pid)
        return original(process, *args, **kwargs)

    monkeypatch.setattr(runner, "_request_and_stop", recording_stop)
    with pytest.raises(QueryEmbeddingTimeout, match="total timeout"):
        encode_queries_isolated(
            ["one"],
            model_name=MODEL_NAME,
            revision=MODEL_REVISION,
            device=DEVICE,
            dimension=DIMENSION,
            normalize=True,
            runtime_root=runtime,
            startup_timeout=1,
            total_timeout=0.5,
            cancel_grace_timeout=0.01,
            poll_interval=0.01,
        )

    assert stopped == [int(pid_file.read_text(encoding="utf-8"))]
    assert list(runtime.iterdir()) == []


def test_runner_startup_timeout_terminates_exact_worker_and_cleans(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    pid_file = tmp_path / "pid.txt"
    _install_fake_command(
        monkeypatch, _write_fake_worker(tmp_path, "no_ack"), pid_file
    )
    stopped: list[int] = []
    original = runner._request_and_stop

    def recording_stop(process, *args, **kwargs):
        stopped.append(kwargs.get("worker_pid") or process.pid)
        return original(process, *args, **kwargs)

    monkeypatch.setattr(runner, "_request_and_stop", recording_stop)
    with pytest.raises(QueryEmbeddingTimeout, match="startup timeout"):
        encode_queries_isolated(
            ["one"],
            model_name=MODEL_NAME,
            revision=MODEL_REVISION,
            device=DEVICE,
            dimension=DIMENSION,
            normalize=True,
            runtime_root=runtime,
            startup_timeout=0.3,
            total_timeout=5,
            cancel_grace_timeout=0.01,
            poll_interval=0.01,
        )

    assert stopped == [int(pid_file.read_text(encoding="utf-8"))]
    assert list(runtime.iterdir()) == []


def test_runner_cancel_terminates_exact_worker(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    pid_file = tmp_path / "pid.txt"
    _install_fake_command(
        monkeypatch, _write_fake_worker(tmp_path, "cancel"), pid_file
    )
    cancel_started = time.monotonic()
    stopped: list[int] = []
    original = runner._request_and_stop

    def recording_stop(process, *args, **kwargs):
        stopped.append(kwargs.get("worker_pid") or process.pid)
        return original(process, *args, **kwargs)

    def cancel_check() -> None:
        if time.monotonic() - cancel_started >= 0.3:
            raise RuntimeError("cancelled by test")

    monkeypatch.setattr(runner, "_request_and_stop", recording_stop)
    with pytest.raises(RuntimeError, match="cancelled by test"):
        encode_queries_isolated(
            ["one"],
            model_name=MODEL_NAME,
            revision=MODEL_REVISION,
            device=DEVICE,
            dimension=DIMENSION,
            normalize=True,
            runtime_root=runtime,
            cancel_check=cancel_check,
            startup_timeout=1,
            total_timeout=5,
            cancel_grace_timeout=0.01,
            poll_interval=0.01,
        )

    assert stopped == [int(pid_file.read_text(encoding="utf-8"))]
    assert list(runtime.iterdir()) == []


def test_runner_retries_one_opaque_pre_encode_exit(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    diagnostics_path = tmp_path / "diagnostics.json"
    pid_file = tmp_path / "pid.txt"
    _install_fake_command(
        monkeypatch, _write_fake_worker(tmp_path, "transient"), pid_file
    )
    monkeypatch.setattr(runner, "RETRY_DELAY_SECONDS", 0.0)

    result = encode_queries_isolated(
        ["one", "two"],
        model_name=MODEL_NAME,
        revision=MODEL_REVISION,
        device=DEVICE,
        dimension=DIMENSION,
        normalize=True,
        runtime_root=runtime,
        diagnostics_path=diagnostics_path,
        startup_timeout=2,
        total_timeout=5,
        poll_interval=0.01,
    )

    assert result.diagnostics["attempt_count"] == 2
    assert result.diagnostics["retry_count"] == 1
    assert result.diagnostics["retry_reason"] == (
        "unexpected_process_exit_before_first_query"
    )
    assert result.diagnostics["attempts"][0]["process_return_code"] == 3
    assert result.diagnostics["attempts"][1]["status"] == "completed"
    assert json.loads(diagnostics_path.read_text(encoding="utf-8")) == (
        result.diagnostics
    )
    assert list(runtime.iterdir()) == []


def test_runner_stops_after_one_retry_for_repeated_opaque_exit(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    diagnostics_path = tmp_path / "diagnostics.json"
    _install_fake_command(
        monkeypatch, _write_fake_worker(tmp_path, "nonzero"), tmp_path / "pid.txt"
    )
    monkeypatch.setattr(runner, "RETRY_DELAY_SECONDS", 0.0)

    with pytest.raises(QueryEmbeddingProcessError) as caught:
        encode_queries_isolated(
            ["one", "two"],
            model_name=MODEL_NAME,
            revision=MODEL_REVISION,
            device=DEVICE,
            dimension=DIMENSION,
            normalize=True,
            runtime_root=runtime,
            diagnostics_path=diagnostics_path,
            startup_timeout=2,
            total_timeout=5,
            poll_interval=0.01,
        )

    diagnostics = caught.value.diagnostics
    assert diagnostics["status"] == "failed"
    assert diagnostics["attempt_count"] == 2
    assert diagnostics["retry_count"] == 1
    assert all(
        attempt["process_return_code"] == 3
        and attempt["worker_exit_confirmed"] is True
        for attempt in diagnostics["attempts"]
    )
    assert json.loads(diagnostics_path.read_text(encoding="utf-8")) == diagnostics
    assert list(runtime.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows process-state contract")
def test_windows_exited_worker_is_not_reported_alive_or_reterminated() -> None:
    process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])
    assert process.wait(timeout=5) == 3

    assert runner._process_is_alive(process.pid) is False
    runner._terminate_exact_pid(process.pid)


@pytest.mark.parametrize("mode", ["python_error", "mid_error"])
def test_runner_does_not_retry_deterministic_or_mid_query_failure(
    mode: str, tmp_path: Path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    diagnostics_path = tmp_path / "diagnostics.json"
    _install_fake_command(
        monkeypatch, _write_fake_worker(tmp_path, mode), tmp_path / "pid.txt"
    )
    monkeypatch.setattr(runner, "RETRY_DELAY_SECONDS", 0.0)

    with pytest.raises(QueryEmbeddingProcessError) as caught:
        encode_queries_isolated(
            ["one", "two"],
            model_name=MODEL_NAME,
            revision=MODEL_REVISION,
            device=DEVICE,
            dimension=DIMENSION,
            normalize=True,
            runtime_root=runtime,
            diagnostics_path=diagnostics_path,
            startup_timeout=2,
            total_timeout=5,
            poll_interval=0.01,
        )

    diagnostics = caught.value.diagnostics
    assert diagnostics["attempt_count"] == 1
    assert diagnostics["retry_count"] == 0
    assert diagnostics["status"] == "failed"
    if mode == "python_error":
        attempt = diagnostics["attempts"][0]
        assert attempt["failure_kind"] == "python_exception"
        assert attempt["error_type"] == "FakeEncodeError"
        assert "fake encode failure" in attempt["stderr_summary"]
    else:
        assert diagnostics["attempts"][0]["completed_query_count"] == 1
    assert json.loads(diagnostics_path.read_text(encoding="utf-8")) == diagnostics
    assert list(runtime.iterdir()) == []


@pytest.mark.parametrize(
    "mode", ["missing", "corrupt", "shape", "dtype", "nan"]
)
def test_runner_rejects_invalid_worker_outputs(
    mode: str, tmp_path: Path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    _install_fake_command(
        monkeypatch,
        _write_fake_worker(tmp_path, mode),
        tmp_path / "pid.txt",
    )

    with pytest.raises(QueryEmbeddingProcessError):
        encode_queries_isolated(
            ["one"],
            model_name=MODEL_NAME,
            revision=MODEL_REVISION,
            device=DEVICE,
            dimension=DIMENSION,
            normalize=True,
            runtime_root=runtime,
            startup_timeout=2,
            total_timeout=5,
            poll_interval=0.01,
        )

    assert list(runtime.iterdir()) == []
