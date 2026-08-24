"""Run the query embedding worker in one controlled short-lived subprocess."""

from __future__ import annotations

import ctypes
import json
import math
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from bedding_order_parser.exceptions import BeddingOrderParserError
from bedding_order_parser.materials.query_embedding_contract import (
    SCHEMA_VERSION,
    validate_normalized_float32_vectors,
)


MAX_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 1.0
LOG_SUMMARY_LIMIT = 2000


class QueryEmbeddingProcessError(BeddingOrderParserError):
    """Raised when the isolated query embedding process fails its contract."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


class QueryEmbeddingTimeout(QueryEmbeddingProcessError):
    """Raised when the worker exceeds its startup or total deadline."""


@dataclass(frozen=True)
class IsolatedEmbeddingResult:
    vectors: np.ndarray
    worker_pid: int
    started_at: str
    completed_at: str
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _AttemptResult:
    vectors: np.ndarray
    worker_pid: int
    started_at: str
    completed_at: str
    diagnostics: dict[str, Any]


def encode_queries_isolated(
    query_texts: Sequence[str],
    *,
    model_name: str,
    revision: str,
    device: str,
    dimension: int,
    normalize: bool,
    runtime_root: str | Path | None = None,
    diagnostics_path: str | Path | None = None,
    cancel_check: Callable[[], None] | None = None,
    startup_timeout: float = 30.0,
    total_timeout: float = 300.0,
    cancel_grace_timeout: float = 2.0,
    poll_interval: float = 0.5,
) -> IsolatedEmbeddingResult:
    """Encode queries with one bounded retry for an opaque pre-encode exit."""
    if not query_texts or any(
        not isinstance(text, str) or not text for text in query_texts
    ):
        raise QueryEmbeddingProcessError("Query texts must be non-empty strings.")
    if min(startup_timeout, total_timeout, poll_interval) <= 0:
        raise QueryEmbeddingProcessError(
            "Worker timeouts and poll interval must be positive."
        )
    root = _prepare_runtime_root(runtime_root)
    persisted_path = (
        Path(diagnostics_path).expanduser().resolve()
        if diagnostics_path is not None
        else None
    )
    attempts: list[dict[str, Any]] = []
    retry_reason = ""
    for attempt_number in range(1, MAX_ATTEMPTS + 1):
        try:
            result = _encode_queries_once(
                query_texts,
                model_name=model_name,
                revision=revision,
                device=device,
                dimension=dimension,
                normalize=normalize,
                runtime_root=root,
                cancel_check=cancel_check,
                startup_timeout=startup_timeout,
                total_timeout=total_timeout,
                cancel_grace_timeout=cancel_grace_timeout,
                poll_interval=poll_interval,
            )
        except QueryEmbeddingProcessError as exc:
            attempt = {"attempt": attempt_number, **exc.diagnostics}
            attempts.append(attempt)
            if (
                attempt_number == 1
                and _is_retryable_pre_encode_exit(attempt)
            ):
                retry_reason = "unexpected_process_exit_before_first_query"
                _persist_diagnostics(
                    persisted_path,
                    _aggregate_diagnostics(
                        status="retrying",
                        query_count=len(query_texts),
                        attempts=attempts,
                        retry_reason=retry_reason,
                    ),
                )
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            diagnostics = _aggregate_diagnostics(
                status="failed",
                query_count=len(query_texts),
                attempts=attempts,
                retry_reason=retry_reason,
            )
            _persist_diagnostics(persisted_path, diagnostics)
            exc.diagnostics = diagnostics
            raise

        attempts.append({"attempt": attempt_number, **result.diagnostics})
        diagnostics = _aggregate_diagnostics(
            status="completed",
            query_count=len(query_texts),
            attempts=attempts,
            retry_reason=retry_reason,
        )
        _persist_diagnostics(persisted_path, diagnostics)
        return IsolatedEmbeddingResult(
            vectors=result.vectors,
            worker_pid=result.worker_pid,
            started_at=result.started_at,
            completed_at=result.completed_at,
            diagnostics=diagnostics,
        )

    raise QueryEmbeddingProcessError(
        "Embedding worker exhausted its bounded attempts."
    )


def _encode_queries_once(
    query_texts: Sequence[str],
    *,
    model_name: str,
    revision: str,
    device: str,
    dimension: int,
    normalize: bool,
    runtime_root: Path,
    cancel_check: Callable[[], None] | None,
    startup_timeout: float,
    total_timeout: float,
    cancel_grace_timeout: float,
    poll_interval: float,
) -> _AttemptResult:
    run_dir = Path(
        tempfile.mkdtemp(prefix="run-", dir=runtime_root)
    ).resolve()
    request_path = run_dir / "request.json"
    response_path = run_dir / "response.json"
    vectors_path = run_dir / "vectors.npy"
    cancel_path = run_dir / "cancel.requested"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    query_ids = [str(index) for index in range(len(query_texts))]
    request = {
        "schema_version": SCHEMA_VERSION,
        "model_name": model_name,
        "revision": revision,
        "device": device,
        "normalize": normalize,
        "dimension": dimension,
        "queries": [
            {"query_id": query_id, "query_text": text}
            for query_id, text in zip(query_ids, query_texts, strict=True)
        ],
    }
    _write_json_atomic(request_path, request)
    process: subprocess.Popen[bytes] | None = None
    worker_pid: int | None = None
    response: dict[str, Any] = {}
    started = time.monotonic()
    try:
        executable = _worker_python_executable()
        command = _build_worker_command(
            executable, request_path, response_path, vectors_path
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                creationflags=flags,
                cwd=str(Path(__file__).resolve().parents[3]),
            )
            saw_start = False
            while True:
                try:
                    if cancel_check is not None:
                        cancel_check()
                except BaseException:
                    _request_and_stop(
                        process,
                        cancel_path,
                        cancel_grace_timeout,
                        poll_interval,
                        worker_pid=worker_pid,
                    )
                    raise

                response = _try_read_response(response_path) or response
                response_pid = response.get("worker_pid")
                if isinstance(response_pid, int) and response_pid > 0:
                    worker_pid = response_pid
                if (
                    response.get("worker_pid") == worker_pid
                    and response.get("status")
                    in {"running", "completed", "failed", "cancelled"}
                ):
                    saw_start = True
                return_code = process.poll()
                elapsed = time.monotonic() - started
                if not saw_start and elapsed > startup_timeout:
                    _request_and_stop(
                        process,
                        cancel_path,
                        cancel_grace_timeout,
                        poll_interval,
                        worker_pid=worker_pid,
                    )
                    diagnostics = _failure_diagnostics(
                        process=process,
                        response=response,
                        stdout_path=stdout_path,
                        stderr_path=stderr_path,
                        worker_pid=worker_pid,
                        query_count=len(query_texts),
                        elapsed=elapsed,
                        failure_kind="startup_timeout",
                        timed_out=True,
                    )
                    raise QueryEmbeddingTimeout(
                        "Embedding worker startup timeout expired "
                        "before acknowledgement.",
                        diagnostics=diagnostics,
                    )
                if elapsed > total_timeout:
                    _request_and_stop(
                        process,
                        cancel_path,
                        cancel_grace_timeout,
                        poll_interval,
                        worker_pid=worker_pid,
                    )
                    diagnostics = _failure_diagnostics(
                        process=process,
                        response=response,
                        stdout_path=stdout_path,
                        stderr_path=stderr_path,
                        worker_pid=worker_pid,
                        query_count=len(query_texts),
                        elapsed=elapsed,
                        failure_kind="total_timeout",
                        timed_out=True,
                    )
                    raise QueryEmbeddingTimeout(
                        "Embedding worker exceeded the total timeout.",
                        diagnostics=diagnostics,
                    )
                if return_code is not None:
                    break
                time.sleep(poll_interval)

        response = _try_read_response(response_path) or response
        elapsed = time.monotonic() - started
        if process.returncode != 0:
            diagnostics = _failure_diagnostics(
                process=process,
                response=response,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                worker_pid=worker_pid,
                query_count=len(query_texts),
                elapsed=elapsed,
                failure_kind=_failure_kind(process.returncode, response),
            )
            summary = response.get("error_summary")
            if not isinstance(summary, str) or not summary:
                status = diagnostics.get("windows_exit_status") or str(
                    process.returncode
                )
                summary = (
                    "Embedding worker exited unexpectedly "
                    f"({status}, stage={diagnostics['stage']})."
                )
            raise QueryEmbeddingProcessError(
                _sanitize_text(summary), diagnostics=diagnostics
            )

        try:
            response = _require_completed_response(
                response_path,
                expected_pid=worker_pid,
                query_ids=query_ids,
                vectors_path=vectors_path,
                expected_shape=(len(query_texts), dimension),
                normalize=normalize,
            )
            vectors = _load_and_validate_vectors(
                vectors_path,
                expected_rows=len(query_texts),
                expected_dimension=dimension,
            )
        except QueryEmbeddingProcessError as exc:
            diagnostics = _failure_diagnostics(
                process=process,
                response=response,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                worker_pid=worker_pid,
                query_count=len(query_texts),
                elapsed=elapsed,
                failure_kind="output_contract_validation",
            )
            exc.diagnostics = diagnostics
            raise
        if process.poll() is None:
            raise QueryEmbeddingProcessError(
                "Embedding worker is still running after producing output."
            )
        return _AttemptResult(
            vectors=vectors,
            worker_pid=int(response["worker_pid"]),
            started_at=str(response["started_at"]),
            completed_at=str(response["completed_at"]),
            diagnostics=_success_diagnostics(
                process=process,
                response=response,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                query_count=len(query_texts),
                elapsed=elapsed,
            ),
        )
    finally:
        if process is not None and (
            process.poll() is None
            or (
                worker_pid is not None
                and worker_pid != process.pid
                and _process_is_alive(worker_pid)
            )
        ):
            _request_and_stop(
                process,
                cancel_path,
                cancel_grace_timeout,
                poll_interval,
                worker_pid=worker_pid,
            )
        shutil.rmtree(run_dir, ignore_errors=True)


def _prepare_runtime_root(runtime_root: str | Path | None) -> Path:
    if runtime_root is None:
        root = Path(tempfile.gettempdir()) / "bedding_order_parser_embedding"
    else:
        root = Path(runtime_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _worker_python_executable() -> Path:
    executable = Path(sys.executable).resolve()
    if os.name == "nt" and executable.name.lower() == "pythonw.exe":
        console_python = executable.with_name("python.exe")
        if console_python.is_file():
            return console_python
    return executable


def _build_worker_command(
    executable: Path,
    request_path: Path,
    response_path: Path,
    vectors_path: Path,
    *,
    frozen: bool | None = None,
) -> list[str]:
    frozen_runtime = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    command = [
        str(executable),
        "--embedding-worker" if frozen_runtime else "-m",
    ]
    if not frozen_runtime:
        command.append("bedding_order_parser.materials.query_embedding_worker")
    command.extend(
        [
        "--request",
        str(request_path),
        "--response",
        str(response_path),
        "--vectors",
        str(vectors_path),
        ]
    )
    return command


def _request_and_stop(
    process: subprocess.Popen[bytes],
    cancel_path: Path,
    grace_timeout: float,
    poll_interval: float,
    *,
    worker_pid: int | None,
) -> None:
    launcher_running = process.poll() is None
    worker_running = (
        worker_pid is not None
        and worker_pid != process.pid
        and _process_is_alive(worker_pid)
    )
    if not launcher_running and not worker_running:
        return
    try:
        cancel_path.touch(exist_ok=True)
    except OSError:
        pass
    deadline = time.monotonic() + max(0.0, grace_timeout)
    while time.monotonic() < deadline:
        launcher_running = process.poll() is None
        worker_running = (
            worker_pid is not None
            and worker_pid != process.pid
            and _process_is_alive(worker_pid)
        )
        if not launcher_running and not worker_running:
            return
        time.sleep(min(poll_interval, 0.1))
    if worker_running and worker_pid is not None:
        _terminate_exact_pid(worker_pid)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def _terminate_exact_pid(pid: int) -> None:
    if pid <= 0 or pid == os.getpid():
        raise QueryEmbeddingProcessError(
            "Refusing to terminate an invalid worker PID."
        )
    if os.name == "nt":
        kernel32 = _windows_kernel32()
        process_terminate = 0x0001
        process_query_limited_information = 0x1000
        synchronize = 0x00100000
        still_active = 259
        ctypes.set_last_error(0)
        handle = kernel32.OpenProcess(
            process_terminate | process_query_limited_information | synchronize,
            False,
            pid,
        )
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:
                return
            raise QueryEmbeddingProcessError(
                f"Unable to open embedding worker PID {pid} "
                f"for termination (WinError {error})."
            )
        try:
            exit_code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(
                handle, ctypes.byref(exit_code)
            ) and exit_code.value != still_active:
                return
            ctypes.set_last_error(0)
            if not kernel32.TerminateProcess(handle, 1):
                error = ctypes.get_last_error()
                if kernel32.GetExitCodeProcess(
                    handle, ctypes.byref(exit_code)
                ) and exit_code.value != still_active:
                    return
                raise QueryEmbeddingProcessError(
                    f"Unable to terminate embedding worker PID {pid} "
                    f"(WinError {error})."
                )
            kernel32.WaitForSingleObject(handle, 2000)
        finally:
            kernel32.CloseHandle(handle)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError as exc:
        raise QueryEmbeddingProcessError(
            f"Unable to terminate embedding worker PID {pid}."
        ) from exc


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        kernel32 = _windows_kernel32()
        still_active = 259
        ctypes.set_last_error(0)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            try:
                exit_code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(
                    handle, ctypes.byref(exit_code)
                ):
                    return True
                return exit_code.value == still_active
            finally:
                kernel32.CloseHandle(handle)
        return ctypes.get_last_error() != 87
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _windows_kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = ctypes.c_void_p
    dword = ctypes.c_ulong
    bool_type = ctypes.c_int
    kernel32.OpenProcess.argtypes = (dword, bool_type, dword)
    kernel32.OpenProcess.restype = handle
    kernel32.GetExitCodeProcess.argtypes = (handle, ctypes.POINTER(dword))
    kernel32.GetExitCodeProcess.restype = bool_type
    kernel32.TerminateProcess.argtypes = (handle, dword)
    kernel32.TerminateProcess.restype = bool_type
    kernel32.WaitForSingleObject.argtypes = (handle, dword)
    kernel32.WaitForSingleObject.restype = dword
    kernel32.CloseHandle.argtypes = (handle,)
    kernel32.CloseHandle.restype = bool_type
    return kernel32


def _require_completed_response(
    path: Path,
    *,
    expected_pid: int | None,
    query_ids: list[str],
    vectors_path: Path,
    expected_shape: tuple[int, int],
    normalize: bool,
) -> dict[str, Any]:
    response = _try_read_response(path)
    if response is None or response.get("status") != "completed":
        raise QueryEmbeddingProcessError(
            "Embedding worker did not produce a completed response."
        )
    if expected_pid is None:
        raise QueryEmbeddingProcessError(
            "Embedding worker did not report a traceable PID."
        )
    expected = {
        "schema_version": SCHEMA_VERSION,
        "worker_pid": expected_pid,
        "query_ids": query_ids,
        "shape": list(expected_shape),
        "dtype": "float32",
        "normalized": normalize,
        "vector_file": vectors_path.name,
    }
    for key, value in expected.items():
        if response.get(key) != value:
            raise QueryEmbeddingProcessError(
                f"Embedding worker returned an invalid {key} contract."
            )
    if vectors_path.parent.resolve() != path.parent.resolve():
        raise QueryEmbeddingProcessError(
            "Embedding vector file escaped the controlled runtime directory."
        )
    return response


def _load_and_validate_vectors(
    path: Path, *, expected_rows: int, expected_dimension: int
) -> np.ndarray:
    if not path.is_file():
        raise QueryEmbeddingProcessError(
            "Embedding worker vector output is missing."
        )
    try:
        vectors = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise QueryEmbeddingProcessError(
            "Embedding worker vector output is unreadable."
        ) from exc
    if vectors.dtype != np.float32:
        raise QueryEmbeddingProcessError(
            "Embedding worker vector dtype must be float32."
        )
    try:
        return validate_normalized_float32_vectors(
            vectors,
            expected_rows=expected_rows,
            expected_dimension=expected_dimension,
        )
    except Exception as exc:
        raise QueryEmbeddingProcessError(
            "Embedding worker vector output failed validation."
        ) from exc


def _failure_kind(return_code: int, response: dict[str, Any]) -> str:
    if response.get("status") == "cancelled":
        return "cancelled"
    if response.get("status") == "failed" and response.get("error_type"):
        return "python_exception"
    if os.name == "nt" and (return_code & 0xFFFFFFFF) >= 0x80000000:
        return "windows_abnormal_termination"
    return "unexpected_process_exit"


def _failure_diagnostics(
    *,
    process: subprocess.Popen[bytes],
    response: dict[str, Any],
    stdout_path: Path,
    stderr_path: Path,
    worker_pid: int | None,
    query_count: int,
    elapsed: float,
    failure_kind: str,
    timed_out: bool = False,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "failure_kind": failure_kind,
        "launcher_pid": process.pid,
        "worker_pid": worker_pid,
        "process_return_code": process.returncode,
        "windows_exit_status": _windows_exit_status(process.returncode),
        "worker_exit_confirmed": (
            worker_pid is None or not _process_is_alive(worker_pid)
        ),
        "request_schema_version": SCHEMA_VERSION,
        "response_schema_version": response.get("schema_version", ""),
        "response_status": response.get("status", ""),
        "stage": response.get("stage", "worker_startup"),
        "query_count": query_count,
        "completed_query_count": int(
            response.get("completed_query_count", 0) or 0
        ),
        "last_completed_query_id": str(
            response.get("last_completed_query_id", "")
        ),
        "active_query_id": str(response.get("active_query_id", "")),
        "error_type": str(response.get("error_type", "")),
        "error_summary": _sanitize_text(
            str(response.get("error_summary", ""))
        ),
        "traceback_summary": _sanitize_traceback(
            response.get("traceback_summary")
        ),
        "stderr_summary": _read_log_summary(stderr_path),
        "stdout_summary": _read_log_summary(stdout_path),
        "timed_out": timed_out,
        "cancelled": response.get("status") == "cancelled",
        "externally_terminated": False,
        "safety_monitor_terminated": False,
        "worker_started_at": str(response.get("started_at", "")),
        "worker_completed_at": str(response.get("completed_at", "")),
        "elapsed_seconds": round(elapsed, 6),
        "worker_timings": _safe_worker_timings(response.get("timings")),
    }


def _success_diagnostics(
    *,
    process: subprocess.Popen[bytes],
    response: dict[str, Any],
    stdout_path: Path,
    stderr_path: Path,
    query_count: int,
    elapsed: float,
) -> dict[str, Any]:
    return {
        "status": "completed",
        "failure_kind": "",
        "launcher_pid": process.pid,
        "worker_pid": int(response["worker_pid"]),
        "process_return_code": int(process.returncode or 0),
        "windows_exit_status": _windows_exit_status(process.returncode),
        "worker_exit_confirmed": not _process_is_alive(
            int(response["worker_pid"])
        ),
        "request_schema_version": SCHEMA_VERSION,
        "response_schema_version": response.get("schema_version", ""),
        "response_status": response.get("status", ""),
        "stage": response.get("stage", "completed"),
        "query_count": query_count,
        "completed_query_count": int(
            response.get("completed_query_count", 0)
        ),
        "last_completed_query_id": str(
            response.get("last_completed_query_id", "")
        ),
        "active_query_id": "",
        "error_type": "",
        "error_summary": "",
        "traceback_summary": [],
        "stderr_summary": _read_log_summary(stderr_path),
        "stdout_summary": _read_log_summary(stdout_path),
        "timed_out": False,
        "cancelled": False,
        "externally_terminated": False,
        "safety_monitor_terminated": False,
        "worker_started_at": str(response.get("started_at", "")),
        "worker_completed_at": str(response.get("completed_at", "")),
        "elapsed_seconds": round(elapsed, 6),
        "worker_timings": _safe_worker_timings(response.get("timings")),
    }


def _safe_worker_timings(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key in (
        "model_load_seconds",
        "encoding_seconds",
        "vector_write_seconds",
        "total_seconds",
    ):
        raw = value.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return {}
        number = float(raw)
        if not math.isfinite(number) or number < 0:
            return {}
        result[key] = number
    return result


def _is_retryable_pre_encode_exit(diagnostics: dict[str, Any]) -> bool:
    return (
        diagnostics.get("failure_kind")
        in {"unexpected_process_exit", "windows_abnormal_termination"}
        and diagnostics.get("response_status") not in {"failed", "cancelled"}
        and not diagnostics.get("error_type")
        and diagnostics.get("completed_query_count") == 0
        and diagnostics.get("worker_exit_confirmed") is True
        and diagnostics.get("timed_out") is False
        and diagnostics.get("cancelled") is False
    )


def _aggregate_diagnostics(
    *,
    status: str,
    query_count: int,
    attempts: list[dict[str, Any]],
    retry_reason: str,
) -> dict[str, Any]:
    return {
        "diagnostics_version": "1.0",
        "status": status,
        "query_count": query_count,
        "attempt_count": len(attempts),
        "retry_count": max(0, len(attempts) - 1),
        "retry_reason": retry_reason,
        "attempts": attempts,
    }


def _persist_diagnostics(
    path: Path | None, diagnostics: dict[str, Any]
) -> None:
    if path is None:
        return
    _write_json_atomic(path, diagnostics)


def _windows_exit_status(return_code: int | None) -> str:
    if return_code is None or os.name != "nt":
        return ""
    return f"0x{return_code & 0xFFFFFFFF:08X}"


def _read_log_summary(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return _sanitize_text(text)[-LOG_SUMMARY_LIMIT:]


def _sanitize_traceback(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value[-8:]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "file": Path(str(item.get("file", ""))).name,
                "line": int(item.get("line", 0) or 0),
                "function": str(item.get("function", ""))[:100],
            }
        )
    return rows


def _sanitize_text(value: str) -> str:
    text = value.replace(str(Path.home()), "<user-home>")
    text = text.replace(tempfile.gettempdir(), "<temp>")
    text = re.sub(r"(?i)[a-z]:\\[^\r\n\"']+", "<path>", text)
    return text


def _try_read_response(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
