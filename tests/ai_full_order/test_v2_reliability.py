from __future__ import annotations

import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from openpyxl import Workbook

from bedding_order_parser.ai_full_order.fake_provider import FakeV2CandidateProvider
from bedding_order_parser.ai_full_order.comparison import COMPARISON_VERSION
from bedding_order_parser.ai_full_order.field_policy import V2DecisionStatus
from bedding_order_parser.ai_full_order.normalization import NORMALIZATION_VERSION
from bedding_order_parser.ai_full_order.orchestration import build_v2_extraction_units
from bedding_order_parser.ai_full_order.preprocessing import EvidenceItem, preprocess_workbook
from bedding_order_parser.ai_full_order.python_shadow import build_deterministic_python_shadow
from bedding_order_parser.ai_full_order.reliability import OfflineReliabilityStore, TransientProviderError
from bedding_order_parser.ai_full_order.reliability_v2 import (
    V2IdempotencyConflictError,
    V2ReliabilityStore,
    V2ReliableOrchestrator,
    V2RunDisposition,
    V2StateTransitionError,
    V2UnitRunState,
    V2UnitStateRecord,
    build_v2_cache_identity,
    canonical_extraction_manifest_sha256,
    extraction_unit_identity_sha256,
)


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: pytest.fail("network forbidden"),
    )


def _write_book(path: Path, *, two_records: bool = False) -> None:
    workbook = Workbook()
    _write_sheet(workbook.active, "PI-A", "1")
    if two_records:
        _write_sheet(workbook.create_sheet(), "PI-B", "2")
    workbook.save(path)


def _write_sheet(sheet, title: str, line_number: str) -> None:
    sheet.title = title
    sheet.append(["", "PROFORMA INVOICE", "", "", "Unit Price (USD)"])
    sheet.append(["BUYER:", "", "", "", ""])
    sheet.append([f"Test Hotel {line_number}", "", "", "", "Contact Person: Aaron Lee"])
    sheet.append(["Delivery date:", "2026-09-30", "", "", ""])
    sheet.append(["No.", "Item", "Size", "Specification", "Qty"])
    sheet.append([line_number, "Duvet Cover", "200*240", "100% cotton white", "12"])


def _context(path: Path):
    preprocessed = preprocess_workbook(path)
    units = build_v2_extraction_units(preprocessed)
    evidence: dict[str, EvidenceItem] = {}
    for unit in units:
        evidence.update({item.evidence_id: item for item in unit.evidence_catalog})
    shadow = build_deterministic_python_shadow(
        path,
        preprocessed,
        target_records=[unit.target for unit in units],
        evidence_catalog=tuple(evidence.values()),
    )
    return preprocessed, units, shadow


def _run(root: Path, preprocessed, shadow, provider, *, key: str = "client-v2", **kwargs):
    return V2ReliableOrchestrator(V2ReliabilityStore(root)).run(
        preprocessed,
        provider,
        shadow,
        client_idempotency_key=key,
        business_key="business:synthetic-v2",
        **kwargs,
    )


def test_v2_cache_identity_is_stable_and_every_version_invalidates(tmp_path: Path) -> None:
    book = tmp_path / "identity.xlsx"
    _write_book(book, two_records=True)
    _preprocessed, units, _shadow = _context(book)
    identity = build_v2_cache_identity(units)

    assert identity.cache_key == build_v2_cache_identity(tuple(reversed(units))).cache_key
    assert identity.normalization_version == NORMALIZATION_VERSION
    assert identity.comparison_version == COMPARISON_VERSION
    assert canonical_extraction_manifest_sha256(units) == canonical_extraction_manifest_sha256(
        tuple(reversed(units))
    )
    for name in (
        "provider",
        "model",
        "contract_version",
        "schema_version",
        "prompt_version",
        "preprocessor_version",
        "context_selection_version",
        "normalization_version",
        "evidence_normalization_version",
        "comparison_version",
        "python_shadow_adapter_version",
        "field_policy_version",
        "provenance_binding_version",
        "canonical_extraction_manifest_sha256",
    ):
        changed = replace(identity, **{name: getattr(identity, name) + "-changed"})
        assert changed.cache_key != identity.cache_key


def test_v1_and_v2_state_lock_and_idempotency_namespaces_do_not_collide(tmp_path: Path) -> None:
    v1 = OfflineReliabilityStore(tmp_path / "state")
    v2 = V2ReliabilityStore(tmp_path / "state")

    assert v1.state_path("cache", "unit") != v2.state_path("cache", "unit")
    assert v1.lock_path("cache") != v2.lock_path("cache")
    assert "v2" in v2.idempotency_path("client").parts


def test_validated_cache_reuses_idempotency_and_reruns_local_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = tmp_path / "cache.xlsx"
    _write_book(book)
    preprocessed, units, shadow = _context(book)
    provider = FakeV2CandidateProvider({"candidates": []})
    import bedding_order_parser.ai_full_order.reliability_v2 as reliability_v2

    original = reliability_v2.bind_v2_candidates
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(reliability_v2, "bind_v2_candidates", counted)
    first = _run(tmp_path / "state", preprocessed, shadow, provider)
    second = _run(tmp_path / "state", preprocessed, shadow, provider)

    assert first.disposition is V2RunDisposition.EXECUTED
    assert second.disposition is V2RunDisposition.CACHED
    assert first.execution_id == second.execution_id
    assert provider.extraction_call_count == len(units) == 1
    assert second.provider_calls == 0
    assert calls >= 2


class _SharedSlowProvider(FakeV2CandidateProvider):
    def __init__(self, counter: list[str], lock: threading.Lock) -> None:
        super().__init__({"candidates": []})
        self.counter = counter
        self.lock = lock

    def extract_v2(self, request):
        with self.lock:
            self.counter.append("call")
        time.sleep(0.15)
        return super().extract_v2(request)


def test_two_independent_v2_orchestrators_have_one_single_flight_leader(tmp_path: Path) -> None:
    book = tmp_path / "concurrent.xlsx"
    _write_book(book)
    preprocessed, _units, shadow = _context(book)
    counter: list[str] = []
    lock = threading.Lock()
    providers = [_SharedSlowProvider(counter, lock), _SharedSlowProvider(counter, lock)]
    barrier = threading.Barrier(2)

    def worker(provider):
        barrier.wait()
        return _run(
            tmp_path / "state",
            preprocessed,
            shadow,
            provider,
            wait_timeout_ms=1_000,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, providers))

    assert counter == ["call"]
    assert {result.disposition for result in results} == {
        V2RunDisposition.EXECUTED,
        V2RunDisposition.CACHED,
    }


def test_healthy_lease_is_not_stolen_and_follower_wait_is_bounded(tmp_path: Path) -> None:
    book = tmp_path / "lease.xlsx"
    _write_book(book)
    preprocessed, units, shadow = _context(book)
    identity = build_v2_cache_identity(units)
    store = V2ReliabilityStore(tmp_path / "state")
    leader = store.lease(identity.cache_key, 2_000)
    follower = store.lease(identity.cache_key, 2_000)
    assert leader.try_acquire()
    assert not follower.try_acquire()

    started = time.monotonic()
    result = _run(
        tmp_path / "state",
        preprocessed,
        shadow,
        FakeV2CandidateProvider({"candidates": []}),
        wait_timeout_ms=20,
    )
    leader.release()

    assert result.disposition is V2RunDisposition.IN_PROGRESS
    assert time.monotonic() - started < 0.5


def test_interruption_and_second_unit_boundary_resume_only_missing_units(tmp_path: Path) -> None:
    book = tmp_path / "resume.xlsx"
    _write_book(book, two_records=True)
    preprocessed, units, shadow = _context(book)
    first_provider = FakeV2CandidateProvider({"candidates": []})
    interrupted = _run(
        tmp_path / "state",
        preprocessed,
        shadow,
        first_provider,
        interrupt_before_unit_order=2,
    )
    resumed_provider = FakeV2CandidateProvider({"candidates": []})
    resumed = _run(tmp_path / "state", preprocessed, shadow, resumed_provider)
    cached_provider = FakeV2CandidateProvider({"candidates": []})
    cached = _run(tmp_path / "state", preprocessed, shadow, cached_provider)

    assert len(units) == 2
    assert interrupted.disposition is V2RunDisposition.INTERRUPTED
    assert not interrupted.batch.ready_for_downstream
    assert first_provider.extraction_call_count == 1
    assert resumed.disposition is V2RunDisposition.EXECUTED
    assert resumed_provider.extraction_call_count == 1
    assert resumed.batch.ready_for_downstream
    assert cached.disposition is V2RunDisposition.CACHED
    assert cached_provider.extraction_call_count == 0


def test_second_recovery_interruption_still_does_not_repeat_validated_units(tmp_path: Path) -> None:
    book = tmp_path / "resume-twice.xlsx"
    _write_book(book, two_records=True)
    preprocessed, _units, shadow = _context(book)
    first = FakeV2CandidateProvider({"candidates": []})
    second = FakeV2CandidateProvider({"candidates": []})
    third = FakeV2CandidateProvider({"candidates": []})

    one = _run(
        tmp_path / "state",
        preprocessed,
        shadow,
        first,
        interrupt_after_completed_units=1,
    )
    two = _run(
        tmp_path / "state",
        preprocessed,
        shadow,
        second,
        interrupt_before_unit_order=2,
    )
    three = _run(tmp_path / "state", preprocessed, shadow, third)

    assert one.disposition is V2RunDisposition.INTERRUPTED
    assert two.disposition is V2RunDisposition.INTERRUPTED
    assert first.extraction_call_count == 1
    assert second.extraction_call_count == 0
    assert third.extraction_call_count == 1
    assert three.batch.ready_for_downstream


def test_terminal_state_write_failure_recovers_without_trusting_unwritten_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = tmp_path / "write-failure.xlsx"
    _write_book(book)
    preprocessed, _units, shadow = _context(book)
    import bedding_order_parser.ai_full_order.reliability_v2 as reliability_v2

    original = reliability_v2._atomic_json
    failed = False

    def fail_terminal(path, value, retries):
        nonlocal failed
        if value.get("state") == "validated" and not failed:
            failed = True
            raise OSError("injected state write interruption")
        return original(path, value, retries)

    monkeypatch.setattr(reliability_v2, "_atomic_json", fail_terminal)
    first_provider = FakeV2CandidateProvider({"candidates": []})
    with pytest.raises(OSError, match="state write interruption"):
        _run(tmp_path / "state", preprocessed, shadow, first_provider)
    resumed_provider = FakeV2CandidateProvider({"candidates": []})
    resumed = _run(tmp_path / "state", preprocessed, shadow, resumed_provider)

    assert failed
    assert first_provider.extraction_call_count == 1
    assert resumed_provider.extraction_call_count == 1
    assert resumed.batch.ready_for_downstream


def test_corrupt_or_identity_mismatched_cache_is_never_trusted(tmp_path: Path) -> None:
    book = tmp_path / "corrupt.xlsx"
    _write_book(book)
    preprocessed, units, shadow = _context(book)
    identity = build_v2_cache_identity(units)
    store = V2ReliabilityStore(tmp_path / "state")
    path = store.state_path(identity.cache_key, units[0].extraction_unit_id)
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")
    provider = FakeV2CandidateProvider({"candidates": []})

    result = _run(tmp_path / "state", preprocessed, shadow, provider)

    assert result.disposition is V2RunDisposition.ISOLATED
    assert result.outcomes[0].error_code == "v2_cache_corrupt"
    assert provider.extraction_call_count == 0

    retry_provider = FakeV2CandidateProvider({"candidates": []})
    retried = _run(
        tmp_path / "state",
        preprocessed,
        shadow,
        retry_provider,
        retry_corrupt_cache=True,
    )
    assert retried.disposition is V2RunDisposition.EXECUTED
    assert retry_provider.extraction_call_count == 1

    valid_path = store.state_path(identity.cache_key, units[0].extraction_unit_id)
    mismatched = json.loads(valid_path.read_text(encoding="utf-8"))
    mismatched["unit_identity_sha256"] = "0" * 64
    valid_path.write_text(json.dumps(mismatched), encoding="utf-8")
    mismatch_provider = FakeV2CandidateProvider({"candidates": []})
    mismatch = _run(tmp_path / "state", preprocessed, shadow, mismatch_provider)
    assert mismatch.disposition is V2RunDisposition.ISOLATED
    assert mismatch.outcomes[0].error_code == "v2_cache_corrupt"
    assert mismatch_provider.extraction_call_count == 0


def test_invalid_python_shadow_evidence_is_rejected_before_provider(tmp_path: Path) -> None:
    book = tmp_path / "invalid-shadow.xlsx"
    _write_book(book)
    preprocessed, _units, shadow = _context(book)
    fields = dict(shadow[0].fields)
    fields["颜色"] = replace(fields["颜色"], evidence_ids=("unknown-evidence",))
    invalid = (replace(shadow[0], fields=fields),)
    provider = FakeV2CandidateProvider({"candidates": []})

    with pytest.raises(Exception, match="shadow candidate provenance"):
        _run(tmp_path / "state", preprocessed, invalid, provider)
    assert provider.extraction_call_count == 0


def test_candidate_content_issue_is_cached_as_reviewable_success(tmp_path: Path) -> None:
    book = tmp_path / "candidate-issue.xlsx"
    _write_book(book)
    preprocessed, units, shadow = _context(book)
    evidence = next(item for item in units[0].evidence_catalog if "cotton" in item.original_text)
    payload = {
        "candidates": [
            {
                "field_name": "包装方式",
                "candidate_value": "invented packaging",
                "evidence_references": [evidence.evidence_id],
                "interpretation": "direct",
                "supporting_quote": "",
            }
        ]
    }
    provider = FakeV2CandidateProvider(payload)
    result = _run(tmp_path / "state", preprocessed, shadow, provider)
    store = V2ReliabilityStore(tmp_path / "state")
    state = store.read_state(result.cache_key, units[0])

    assert result.batch.technical_ready
    assert result.batch.review_required
    assert result.disposition is V2RunDisposition.EXECUTED
    assert state is not None
    assert state.state is V2UnitRunState.VALIDATED_WITH_CONTENT_ISSUE
    decision = result.batch.records[0].decisions["包装方式"]
    assert decision.status is V2DecisionStatus.MISSING
    assert decision.ai_isolated is True


@pytest.mark.parametrize("matching_content_issue", [True, False])
def test_legacy_candidate_isolated_state_is_decided_by_current_revalidation(
    tmp_path: Path, matching_content_issue: bool
) -> None:
    book = tmp_path / "legacy-candidate-state.xlsx"
    _write_book(book)
    preprocessed, units, shadow = _context(book)
    evidence = next(item for item in units[0].evidence_catalog if "cotton" in item.original_text)
    payload = (
        {
            "candidates": [
                {
                    "field_name": "包装方式",
                    "candidate_value": "invented packaging",
                    "evidence_references": [evidence.evidence_id],
                    "interpretation": "direct",
                    "supporting_quote": "",
                }
            ]
        }
        if matching_content_issue
        else {"candidates": []}
    )
    identity = build_v2_cache_identity(units)
    store = V2ReliabilityStore(tmp_path / "legacy-state")
    unit = units[0]
    unit_hash = extraction_unit_identity_sha256(unit)
    store.write_state(
        V2UnitStateRecord(
            identity.cache_key,
            unit.extraction_unit_id,
            unit_hash,
            V2UnitRunState.PENDING,
        )
    )
    store.write_state(
        V2UnitStateRecord(
            identity.cache_key,
            unit.extraction_unit_id,
            unit_hash,
            V2UnitRunState.IN_PROGRESS,
            attempt_count=1,
        )
    )
    store.write_state(
        V2UnitStateRecord(
            identity.cache_key,
            unit.extraction_unit_id,
            unit_hash,
            V2UnitRunState.CANDIDATE_ISOLATED,
            attempt_count=1,
            error_code="v2_candidate_isolated",
            validated_candidates=payload,
            provider_telemetry={
                "provider": "fake_provider",
                "model": "offline-test",
                "request_id": "",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "latency_ms": 0,
                "attempt_count": 1,
            },
        )
    )
    provider = FakeV2CandidateProvider({"candidates": []})
    result = V2ReliableOrchestrator(store).run(
        preprocessed,
        provider,
        shadow,
        client_idempotency_key=f"legacy:{matching_content_issue}",
        business_key="business:legacy-state",
        cache_identity=identity,
    )

    assert provider.extraction_call_count == 0
    if matching_content_issue:
        assert result.disposition is V2RunDisposition.CACHED
        assert result.batch.technical_ready
    else:
        assert result.disposition is V2RunDisposition.ISOLATED
        assert result.outcomes[0].error_code == "v2_cached_revalidation_failure"


def test_hard_evidence_failure_is_persisted_and_not_retried(tmp_path: Path) -> None:
    book = tmp_path / "hard-failure.xlsx"
    _write_book(book)
    preprocessed, _units, shadow = _context(book)
    payload = {
        "candidates": [
            {
                "field_name": "颜色",
                "candidate_value": "white",
                "evidence_references": ["unknown-evidence"],
                "interpretation": "direct",
                "supporting_quote": "",
            }
        ]
    }
    provider = FakeV2CandidateProvider(payload)

    first = _run(tmp_path / "state", preprocessed, shadow, provider)
    second = _run(tmp_path / "state", preprocessed, shadow, provider)

    assert first.disposition is second.disposition is V2RunDisposition.ISOLATED
    assert provider.extraction_call_count == 1
    assert second.outcomes[0].error_code == "v2_hard_contract_or_resolution_failure"


def test_high_review_conflict_revalidates_from_cache_and_keeps_ai_value(tmp_path: Path) -> None:
    book = tmp_path / "blocking.xlsx"
    _write_book(book)
    preprocessed, units, shadow = _context(book)
    evidence = next(item for item in units[0].evidence_catalog if "Aaron Lee" in item.original_text)
    payload = {
        "candidates": [
            {
                "field_name": "客户",
                "candidate_value": "Aaron Lee",
                "evidence_references": [evidence.evidence_id],
                "interpretation": "direct",
                "supporting_quote": "",
            }
        ]
    }
    provider = FakeV2CandidateProvider(payload)

    first = _run(tmp_path / "state", preprocessed, shadow, provider)
    second = _run(tmp_path / "state", preprocessed, shadow, provider)

    assert first.disposition is V2RunDisposition.EXECUTED
    assert second.disposition is V2RunDisposition.CACHED
    assert second.batch.ready_for_downstream
    assert second.batch.technical_ready
    assert second.batch.review_required
    assert second.batch.high_review_count >= 1
    assert second.disposition is V2RunDisposition.CACHED
    decision = second.batch.records[0].decisions["客户"]
    assert decision.value == "Aaron Lee"
    assert decision.selected_source == "ai"
    assert decision.blocking is False
    assert provider.extraction_call_count == 1


class _TransientOnceProvider(FakeV2CandidateProvider):
    def __init__(self) -> None:
        super().__init__({"candidates": []})
        self.failures = 1

    def extract_v2(self, request):
        self.extraction_call_count += 1
        if self.failures:
            self.failures -= 1
            raise TransientProviderError("synthetic timeout")
        self.extraction_call_count -= 1
        return super().extract_v2(request)


def test_transient_failure_is_bounded_and_can_resume(tmp_path: Path) -> None:
    book = tmp_path / "transient.xlsx"
    _write_book(book)
    preprocessed, _units, shadow = _context(book)
    provider = _TransientOnceProvider()
    orchestrator = V2ReliableOrchestrator(
        V2ReliabilityStore(tmp_path / "state"), transient_backoff_ms=0
    )

    first = orchestrator.run(
        preprocessed,
        provider,
        shadow,
        client_idempotency_key="transient-client",
        business_key="business:synthetic-v2",
    )
    second = orchestrator.run(
        preprocessed,
        provider,
        shadow,
        client_idempotency_key="transient-client",
        business_key="business:synthetic-v2",
    )

    assert first.disposition is V2RunDisposition.ISOLATED
    assert second.disposition is V2RunDisposition.EXECUTED
    assert provider.extraction_call_count == 2


def test_atomic_state_retry_and_terminal_state_monotonicity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = tmp_path / "atomic.xlsx"
    _write_book(book)
    _preprocessed, units, _shadow = _context(book)
    unit = units[0]
    store = V2ReliabilityStore(tmp_path / "state")
    cache_key = "cache"
    unit_hash = extraction_unit_identity_sha256(unit)
    import bedding_order_parser.ai_full_order.reliability_v2 as reliability_v2

    original_replace = reliability_v2.os.replace
    failures = 0

    def occupied(source, target):
        nonlocal failures
        if failures == 0:
            failures += 1
            raise PermissionError("simulated Windows occupation")
        return original_replace(source, target)

    monkeypatch.setattr(reliability_v2.os, "replace", occupied)
    store.write_state(
        V2UnitStateRecord(
            cache_key,
            unit.extraction_unit_id,
            unit_hash,
            V2UnitRunState.PENDING,
            updated_at_ms=1,
        )
    )
    store.write_state(
        V2UnitStateRecord(
            cache_key,
            unit.extraction_unit_id,
            unit_hash,
            V2UnitRunState.IN_PROGRESS,
            1,
            updated_at_ms=2,
        )
    )
    validated = V2UnitStateRecord(
        cache_key,
        unit.extraction_unit_id,
        unit_hash,
        V2UnitRunState.VALIDATED,
        1,
        updated_at_ms=3,
        validated_candidates={"candidates": []},
        provider_telemetry={
            "provider": "fake_provider",
            "model": "offline-test",
            "request_id": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latency_ms": 0,
            "attempt_count": 1,
        },
    )
    store.write_state(validated)

    assert failures == 1
    with pytest.raises(V2StateTransitionError):
        store.write_state(
            replace(validated, state=V2UnitRunState.IN_PROGRESS, updated_at_ms=4)
        )


def test_client_idempotency_key_cannot_cross_contract_identity(tmp_path: Path) -> None:
    book = tmp_path / "idempotency.xlsx"
    _write_book(book)
    preprocessed, units, shadow = _context(book)
    first_identity = build_v2_cache_identity(units)
    changed_identity = replace(first_identity, field_policy_version="different")
    provider = FakeV2CandidateProvider({"candidates": []})

    _run(
        tmp_path / "state",
        preprocessed,
        shadow,
        provider,
        cache_identity=first_identity,
    )
    with pytest.raises(V2IdempotencyConflictError):
        _run(
            tmp_path / "state",
            preprocessed,
            shadow,
            provider,
            cache_identity=changed_identity,
        )


def test_v2_state_contains_no_request_response_or_secret_fields(tmp_path: Path) -> None:
    book = tmp_path / "safe-state.xlsx"
    _write_book(book)
    preprocessed, units, shadow = _context(book)
    result = _run(
        tmp_path / "state",
        preprocessed,
        shadow,
        FakeV2CandidateProvider({"candidates": []}),
    )
    state_path = V2ReliabilityStore(tmp_path / "state").state_path(
        result.cache_key, units[0].extraction_unit_id
    )
    raw = json.loads(state_path.read_text(encoding="utf-8"))

    assert set(raw["provider_telemetry"]) == {
        "provider",
        "model",
        "request_id",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "latency_ms",
        "attempt_count",
    }
    assert not ({"request", "response", "authorization", "api_key", "prompt"} & set(raw))
