"""Short-lived worker that only turns query text into normalized vectors."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

from bedding_order_parser.materials.embedding_model import (
    EmbeddingAdapter,
    EmbeddingModelError,
    SentenceTransformerEmbeddingAdapter,
)
from bedding_order_parser.materials.query_embedding_contract import (
    DEVICE,
    DIMENSION,
    MODEL_NAME,
    MODEL_REVISION,
    SCHEMA_VERSION,
    validate_normalized_float32_vectors,
)


class QueryEmbeddingWorkerError(RuntimeError):
    """Raised when a worker request violates the isolated embedding contract."""


class QueryEmbeddingWorkerCancelled(QueryEmbeddingWorkerError):
    """Raised when the parent requests cooperative worker cancellation."""


def run_worker(
    request_path: str | Path,
    response_path: str | Path,
    vectors_path: str | Path,
    *,
    adapter_factory: Callable[..., EmbeddingAdapter] = (
        SentenceTransformerEmbeddingAdapter
    ),
) -> dict[str, Any]:
    """Process one controlled request without reading any business data stores."""
    request_file, response_file, vector_file = _resolve_paths(
        request_path, response_path, vectors_path
    )
    request = _read_json_object(request_file)
    queries = _validate_request(request)
    started_at = _now()
    started = time.perf_counter()
    running = {
        "schema_version": SCHEMA_VERSION,
        "status": "running",
        "stage": "model_loading",
        "worker_pid": os.getpid(),
        "started_at": started_at,
        "completed_at": "",
        "query_ids": [query["query_id"] for query in queries],
        "shape": [],
        "dtype": "",
        "normalized": True,
        "vector_file": vector_file.name,
        "completed_query_count": 0,
        "last_completed_query_id": "",
        "active_query_id": "",
        "error_type": "",
        "error_summary": "",
        "traceback_summary": [],
    }
    _write_json_atomic(response_file, running)
    cancel_file = request_file.parent / "cancel.requested"
    _check_cancel(cancel_file)

    adapter = adapter_factory(
        MODEL_NAME,
        device=DEVICE,
        revision=MODEL_REVISION,
        local_files_only=True,
    )
    _validate_adapter(adapter)
    running = {**running, "stage": "encoding_queries"}
    _write_json_atomic(response_file, running)
    rows: list[np.ndarray] = []
    for query in queries:
        _check_cancel(cancel_file)
        running = {
            **running,
            "active_query_id": query["query_id"],
            "completed_query_count": len(rows),
        }
        _write_json_atomic(response_file, running)
        vector = validate_normalized_float32_vectors(
            adapter.encode([query["query_text"]], batch_size=1),
            expected_rows=1,
            expected_dimension=DIMENSION,
        )
        rows.append(vector[0])
        running = {
            **running,
            "active_query_id": "",
            "completed_query_count": len(rows),
            "last_completed_query_id": query["query_id"],
        }
        _write_json_atomic(response_file, running)
    _check_cancel(cancel_file)

    running = {**running, "stage": "writing_vectors"}
    _write_json_atomic(response_file, running)
    vectors = np.ascontiguousarray(np.vstack(rows), dtype=np.float32)
    _write_vectors_atomic(vector_file, vectors)
    completed = {
        **running,
        "status": "completed",
        "stage": "completed",
        "completed_at": _now(),
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "shape": [int(value) for value in vectors.shape],
        "dtype": str(vectors.dtype),
        "completed_query_count": len(rows),
        "last_completed_query_id": queries[-1]["query_id"],
        "active_query_id": "",
    }
    _write_json_atomic(response_file, completed)
    return completed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--response", required=True)
    parser.add_argument("--vectors", required=True)
    args = parser.parse_args(argv)
    try:
        run_worker(args.request, args.response, args.vectors)
    except BaseException as exc:
        _write_failure_response(Path(args.response), exc)
        _write_stderr_summary(exc)
        return 2
    return 0


def _resolve_paths(
    request_path: str | Path,
    response_path: str | Path,
    vectors_path: str | Path,
) -> tuple[Path, Path, Path]:
    paths = tuple(
        Path(value).expanduser().resolve()
        for value in (request_path, response_path, vectors_path)
    )
    parent = paths[0].parent
    if any(path.parent != parent for path in paths):
        raise QueryEmbeddingWorkerError(
            "Worker request, response and vector files must share "
            "one runtime directory."
        )
    if not paths[0].is_file():
        raise QueryEmbeddingWorkerError("Worker request file is missing.")
    parent.mkdir(parents=True, exist_ok=True)
    return paths


def _validate_request(payload: dict[str, Any]) -> list[dict[str, str]]:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "model_name": MODEL_NAME,
        "revision": MODEL_REVISION,
        "device": DEVICE,
        "normalize": True,
        "dimension": DIMENSION,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise QueryEmbeddingWorkerError(
                f"Worker request has an invalid {key} contract."
            )
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise QueryEmbeddingWorkerError(
            "Worker request queries must be a non-empty list."
        )
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for query in queries:
        if not isinstance(query, dict):
            raise QueryEmbeddingWorkerError(
                "Worker query entries must be objects."
            )
        query_id = query.get("query_id")
        query_text = query.get("query_text")
        if (
            not isinstance(query_id, str)
            or not query_id
            or query_id in seen
            or not isinstance(query_text, str)
            or not query_text
        ):
            raise QueryEmbeddingWorkerError(
                "Worker queries require unique IDs and non-empty text."
            )
        seen.add(query_id)
        normalized.append(
            {"query_id": query_id, "query_text": query_text}
        )
    return normalized


def _validate_adapter(adapter: EmbeddingAdapter) -> None:
    if (
        adapter.model_name != MODEL_NAME
        or adapter.revision != MODEL_REVISION
        or adapter.device != DEVICE
        or int(adapter.dimension) != DIMENSION
    ):
        raise QueryEmbeddingWorkerError(
            "Embedding adapter does not match the approved model contract."
        )


def _check_cancel(cancel_file: Path) -> None:
    if cancel_file.exists():
        raise QueryEmbeddingWorkerCancelled(
            "Embedding worker received a cooperative cancellation request."
        )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QueryEmbeddingWorkerError(
            "Worker request JSON is unreadable."
        ) from exc
    if not isinstance(payload, dict):
        raise QueryEmbeddingWorkerError(
            "Worker request must be a JSON object."
        )
    return payload


def _write_vectors_atomic(path: Path, vectors: np.ndarray) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            np.save(handle, vectors, allow_pickle=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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


def _write_failure_response(path: Path, exc: BaseException) -> None:
    previous = _try_read_response(path)
    error_type = type(exc).__name__
    if isinstance(exc, QueryEmbeddingWorkerCancelled):
        summary = "Embedding worker was cancelled."
        status = "cancelled"
    elif isinstance(exc, (QueryEmbeddingWorkerError, EmbeddingModelError)):
        summary = _sanitize_text(str(exc))
        status = "failed"
    else:
        summary = (
            "Embedding worker failed while generating query vectors."
        )
        status = "failed"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "stage": str(previous.get("stage", "worker_startup")),
        "worker_pid": os.getpid(),
        "started_at": str(previous.get("started_at", "")),
        "completed_at": _now(),
        "query_ids": list(previous.get("query_ids", [])),
        "shape": [],
        "dtype": "",
        "normalized": True,
        "vector_file": str(previous.get("vector_file", "")),
        "completed_query_count": int(
            previous.get("completed_query_count", 0) or 0
        ),
        "last_completed_query_id": str(
            previous.get("last_completed_query_id", "")
        ),
        "active_query_id": str(previous.get("active_query_id", "")),
        "error_type": error_type,
        "error_summary": summary,
        "traceback_summary": _traceback_summary(exc),
    }
    try:
        _write_json_atomic(path.expanduser().resolve(), payload)
    except OSError:
        return


def _try_read_response(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.expanduser().resolve().read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _traceback_summary(exc: BaseException) -> list[dict[str, Any]]:
    return [
        {
            "file": Path(frame.filename).name,
            "line": frame.lineno,
            "function": frame.name,
        }
        for frame in traceback.extract_tb(exc.__traceback__)[-8:]
    ]


def _write_stderr_summary(exc: BaseException) -> None:
    summary = {
        "error_type": type(exc).__name__,
        "error_summary": _sanitize_text(str(exc)),
        "traceback_summary": _traceback_summary(exc),
    }
    try:
        sys.stderr.write(
            json.dumps(summary, ensure_ascii=True, separators=(",", ":"))
            + "\n"
        )
        sys.stderr.flush()
    except OSError:
        return


def _sanitize_text(value: str) -> str:
    text = value.replace(str(Path.home()), "<user-home>")
    text = text.replace(tempfile.gettempdir(), "<temp>")
    return re.sub(r"(?i)[a-z]:\\[^\r\n\"']+", "<path>", text)


def _now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
