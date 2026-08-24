from __future__ import annotations

import multiprocessing
import os
import socket
import time
from pathlib import Path

import pytest
from openpyxl import Workbook

from bedding_order_parser.ai_full_order.contracts import AI_BUSINESS_FIELD_NAMES
from bedding_order_parser.ai_full_order.fake_provider import FakeFullOrderProvider
from bedding_order_parser.ai_full_order.orchestration import formal_line_number_from_request
from bedding_order_parser.ai_full_order.preprocessing import preprocess_workbook
from bedding_order_parser.ai_full_order.reliability import (
    ChunkRunState,
    ChunkStateRecord,
    OfflineReliabilityStore,
    OfflineReliableOrchestrator,
    RunDisposition,
    StateTransitionError,
    TransientProviderError,
    build_cache_identity,
    canonical_manifest_sha256,
)
from bedding_order_parser.ai_full_order.resolution import adapt_python_shadow_records


def _write_book(path: Path, *, two_scopes: bool = False) -> None:
    workbook = Workbook()
    first = workbook.active
    _write_sheet(first, "PI-A", "1")
    if two_scopes:
        second = workbook.create_sheet("PI-B")
        _write_sheet(second, "PI-B", "2")
    workbook.save(path)


def _write_sheet(sheet, title: str, number: str) -> None:
    sheet.title = title
    sheet.append(["No.", "Item", "Specification", "Qty"])
    sheet.append([number, "Duvet Cover", "White cotton", "12"])


def _shadow(preprocessed):
    request = preprocessed.to_request_dict()
    formal = [
        {
            **{field: "" for field in AI_BUSINESS_FIELD_NAMES},
            "行号": formal_line_number_from_request(record, request["evidence_catalog"]),
        }
        for record in request["records"]
    ]
    return adapt_python_shadow_records(preprocessed, formal)


def _run(store_root: Path, preprocessed, provider, *, key: str = "client-1", identity=None, **kwargs):
    return OfflineReliableOrchestrator(OfflineReliabilityStore(store_root), **kwargs.pop("settings", {})).run(
        preprocessed,
        provider,
        _shadow(preprocessed),
        client_idempotency_key=key,
        business_key="business:synthetic-order",
        cache_identity=identity,
        **kwargs,
    )


class FaultProvider(FakeFullOrderProvider):
    def __init__(self, faults: list[str] | None = None, scenario: str = "normal") -> None:
        super().__init__(scenario)
        self.faults = list(faults or [])

    def extract(self, request):
        self.extraction_call_count += 1
        if self.faults:
            kind = self.faults.pop(0)
            if kind == "transient":
                raise TransientProviderError("simulated timeout")
            if kind == "timeout":
                raise TimeoutError("simulated timeout")
        self.extraction_call_count -= 1
        return super().extract(request)


class ProcessCountingProvider(FakeFullOrderProvider):
    def __init__(self, counter_path: str) -> None:
        super().__init__()
        self.counter_path = counter_path

    def extract(self, request):
        with open(self.counter_path, "a", encoding="utf-8") as handle:
            handle.write("call\n")
            handle.flush()
            os.fsync(handle.fileno())
        time.sleep(0.2)
        return super().extract(request)


def _process_worker(book_path: str, store_root: str, counter_path: str, start, results) -> None:
    preprocessed = preprocess_workbook(book_path)
    start.wait(5)
    result = _run(Path(store_root), preprocessed, ProcessCountingProvider(counter_path), key="shared-client")
    results.put(result.disposition.value)


def test_cache_key_is_stable_and_every_contract_version_invalidates(tmp_path: Path) -> None:
    path = tmp_path / "book.xlsx"
    _write_book(path)
    preprocessed = preprocess_workbook(path)
    manifest = __import__(
        "bedding_order_parser.ai_full_order.orchestration", fromlist=["build_chunk_manifest"]
    ).build_chunk_manifest(preprocessed)
    first = build_cache_identity(manifest)

    assert first.cache_key == build_cache_identity(manifest).cache_key
    assert canonical_manifest_sha256(manifest) == canonical_manifest_sha256(tuple(reversed(manifest)))
    for name in (
        "provider", "model", "extraction_schema_version", "prompt_version",
        "preprocessor_version", "normalization_rules_version",
    ):
        values = first.__dict__.copy()
        values[name] = values[name] + "-changed"
        assert first.cache_key != type(first)(**values).cache_key


def test_validated_cache_and_idempotency_reuse_one_fake_call(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "book.xlsx"
    _write_book(path)
    preprocessed = preprocess_workbook(path)
    provider = FakeFullOrderProvider()
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: pytest.fail("network forbidden"))

    first = _run(tmp_path / "state", preprocessed, provider)
    second = _run(tmp_path / "state", preprocessed, provider)

    assert first.disposition is RunDisposition.EXECUTED
    assert second.disposition is RunDisposition.CACHED
    assert first.execution_id == second.execution_id
    assert provider.extraction_call_count == 1
    assert provider.network_call_count == 0


def test_changed_version_does_not_reuse_cache(tmp_path: Path) -> None:
    path = tmp_path / "book.xlsx"
    _write_book(path)
    preprocessed = preprocess_workbook(path)
    provider = FakeFullOrderProvider()
    first = _run(tmp_path / "state", preprocessed, provider, key="v1")
    changed = build_cache_identity(first.manifest, prompt_version="2.0")
    second = _run(tmp_path / "state", preprocessed, provider, key="v2", identity=changed)

    assert first.cache_key != second.cache_key
    assert provider.extraction_call_count == 2


def test_two_independent_process_instances_have_only_one_leader(tmp_path: Path) -> None:
    book = tmp_path / "book.xlsx"
    counter = tmp_path / "calls.txt"
    _write_book(book)
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    processes = [
        context.Process(target=_process_worker, args=(str(book), str(tmp_path / "state"), str(counter), start, results))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0
    dispositions = {results.get(timeout=2), results.get(timeout=2)}

    assert counter.read_text(encoding="utf-8").splitlines() == ["call"]
    assert dispositions <= {"executed", "cached", "in_progress"}


def test_healthy_lease_is_not_stolen_expired_lease_recovers_and_follower_waits_bounded(tmp_path: Path) -> None:
    store = OfflineReliabilityStore(tmp_path / "state")
    healthy = store.lease("same", 1_000)
    follower = store.lease("same", 1_000)
    assert healthy.try_acquire()
    assert not follower.try_acquire()
    healthy.release()

    stale = store.lease("expired", 1)
    assert stale.try_acquire()
    time.sleep(0.02)
    recovered = store.lease("expired", 1)
    assert recovered.try_acquire()
    recovered.release()

    path = tmp_path / "book.xlsx"
    _write_book(path)
    preprocessed = preprocess_workbook(path)
    identity = build_cache_identity(
        __import__("bedding_order_parser.ai_full_order.orchestration", fromlist=["build_chunk_manifest"]).build_chunk_manifest(preprocessed)
    )
    held = store.lease(identity.cache_key, 1_000)
    assert held.try_acquire()
    started = time.monotonic()
    result = _run(tmp_path / "state", preprocessed, FakeFullOrderProvider(), key="wait", wait_timeout_ms=25)
    elapsed = time.monotonic() - started
    held.release()

    assert result.disposition is RunDisposition.IN_PROGRESS
    assert elapsed < 0.5


def test_recovery_only_executes_unvalidated_chunks_and_keeps_ready_gate(tmp_path: Path) -> None:
    path = tmp_path / "book.xlsx"
    _write_book(path, two_scopes=True)
    preprocessed = preprocess_workbook(path)
    first_provider = FakeFullOrderProvider()
    interrupted = _run(
        tmp_path / "state", preprocessed, first_provider, interrupt_after_validated_chunks=1,
    )
    resumed_provider = FakeFullOrderProvider()
    resumed = _run(tmp_path / "state", preprocessed, resumed_provider)

    assert interrupted.disposition is RunDisposition.INTERRUPTED
    assert interrupted.batch.ready_for_downstream is False
    assert "missing_chunks" in interrupted.batch.reasons
    assert first_provider.extraction_call_count == 1
    assert resumed.disposition is RunDisposition.EXECUTED
    assert resumed_provider.extraction_call_count == 1
    assert resumed.batch.ready_for_downstream


def test_deterministic_failure_is_not_retried_and_transient_attempts_are_bounded(tmp_path: Path) -> None:
    path = tmp_path / "book.xlsx"
    _write_book(path)
    preprocessed = preprocess_workbook(path)
    deterministic = FaultProvider(scenario="extra_field")
    first = _run(tmp_path / "deterministic", preprocessed, deterministic)
    second = _run(tmp_path / "deterministic", preprocessed, deterministic)
    assert first.disposition is RunDisposition.ISOLATED
    assert second.disposition is RunDisposition.ISOLATED
    assert deterministic.extraction_call_count == 1
    forced = _run(
        tmp_path / "deterministic", preprocessed, deterministic, force_deterministic_retry=True,
    )
    assert forced.disposition is RunDisposition.ISOLATED
    assert deterministic.extraction_call_count == 2
    repeated_force = _run(
        tmp_path / "deterministic", preprocessed, deterministic, force_deterministic_retry=True,
    )
    assert repeated_force.disposition is RunDisposition.ISOLATED
    assert deterministic.extraction_call_count == 2

    transient = FaultProvider(["transient", "timeout"])
    for index in range(3):
        _run(tmp_path / "transient", preprocessed, transient, key=f"transient-{index}")
    assert transient.extraction_call_count == 2


def test_interrupted_running_state_becomes_recoverable(tmp_path: Path) -> None:
    path = tmp_path / "book.xlsx"
    _write_book(path)
    preprocessed = preprocess_workbook(path)
    provider = FakeFullOrderProvider()
    result = _run(tmp_path / "state", preprocessed, provider)
    store = OfflineReliabilityStore(tmp_path / "state")
    item = result.manifest[0]
    state = store.read_state(result.cache_key, item.chunk_id)
    assert state is not None

    # A persisted running state from a stopped process is converted before recovery.
    state_path = store.state_path(result.cache_key, item.chunk_id)
    state_path.write_text(
        __import__("json").dumps(ChunkStateRecord(
            result.cache_key, item.chunk_id, ChunkRunState.RUNNING, 1, "dead", 1,
        ).to_dict()),
        encoding="utf-8",
    )
    resumed = _run(tmp_path / "state", preprocessed, FakeFullOrderProvider(), key="recover")
    assert resumed.disposition is RunDisposition.EXECUTED


def test_atomic_write_retries_and_terminal_or_corrupt_state_is_never_success(tmp_path: Path, monkeypatch) -> None:
    store = OfflineReliabilityStore(tmp_path / "state")
    pending = ChunkStateRecord("key", "chunk", ChunkRunState.PENDING, updated_at_ms=1)
    import bedding_order_parser.ai_full_order.reliability as reliability

    original_replace = reliability.os.replace
    failures = {"count": 0}

    def occupied(source, target):
        if failures["count"] == 0:
            failures["count"] += 1
            raise PermissionError("simulated windows occupation")
        return original_replace(source, target)

    monkeypatch.setattr(reliability.os, "replace", occupied)
    store.write_state(pending)
    assert failures["count"] == 1
    store.write_state(ChunkStateRecord("key", "chunk", ChunkRunState.RUNNING, 1, updated_at_ms=2))
    store.write_state(ChunkStateRecord("key", "chunk", ChunkRunState.SUCCEEDED, 1, updated_at_ms=3))
    store.write_state(ChunkStateRecord("key", "chunk", ChunkRunState.VALIDATED, 1, updated_at_ms=4, validated_output={}))
    with pytest.raises(StateTransitionError):
        store.write_state(ChunkStateRecord("key", "chunk", ChunkRunState.RUNNING, 2, updated_at_ms=5))

    path = tmp_path / "book.xlsx"
    _write_book(path)
    preprocessed = preprocess_workbook(path)
    manifest = __import__("bedding_order_parser.ai_full_order.orchestration", fromlist=["build_chunk_manifest"]).build_chunk_manifest(preprocessed)
    identity = build_cache_identity(manifest)
    corrupt = OfflineReliabilityStore(tmp_path / "corrupt")
    corrupt_path = corrupt.state_path(identity.cache_key, manifest[0].chunk_id)
    corrupt_path.parent.mkdir(parents=True)
    corrupt_path.write_text("{not json", encoding="utf-8")
    result = _run(tmp_path / "corrupt", preprocessed, FakeFullOrderProvider(), key="corrupt")
    assert result.disposition is RunDisposition.ISOLATED
    assert result.outcomes[0].error_code == "state_corrupt"
    assert result.provider_calls == 0
