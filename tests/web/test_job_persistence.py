from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import pytest

from bedding_order_parser.web import job_persistence
from bedding_order_parser.web.job_persistence import (
    AtomicJsonWriteError,
    write_json_atomic,
)


def windows_error(code: int) -> PermissionError:
    error = PermissionError("simulated transient file lock")
    error.winerror = code
    return error


def test_atomic_json_retries_winerror_5_then_succeeds(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "job.json"
    target.write_text('{"old": true}\n', encoding="utf-8")
    real_replace = os.replace
    calls = 0
    sleeps: list[float] = []

    def flaky_replace(source, destination):
        nonlocal calls
        calls += 1
        assert target.read_text(encoding="utf-8") == '{"old": true}\n'
        if calls == 1:
            raise windows_error(5)
        real_replace(source, destination)

    monkeypatch.setattr(job_persistence.os, "replace", flaky_replace)
    write_json_atomic(
        target,
        {"status": "processing", "中文": "完整"},
        retry_delays=(0.05,),
        sleep=sleeps.append,
    )

    assert calls == 2
    assert sleeps == [0.05]
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "status": "processing",
        "中文": "完整",
    }
    assert list(tmp_path.glob(".job.json.*.tmp")) == []


def test_atomic_json_retries_winerror_32_with_backoff(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "job.json"
    real_replace = os.replace
    calls = 0
    sleeps: list[float] = []

    def flaky_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls <= 3:
            raise windows_error(32)
        real_replace(source, destination)

    monkeypatch.setattr(job_persistence.os, "replace", flaky_replace)
    write_json_atomic(
        target,
        {"status": "queued"},
        retry_delays=(0.05, 0.10, 0.20),
        sleep=sleeps.append,
    )

    assert calls == 4
    assert sleeps == [0.05, 0.10, 0.20]


def test_atomic_json_retries_winerror_33_then_succeeds(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "job.json"
    real_replace = os.replace
    calls = 0

    def flaky_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise windows_error(33)
        real_replace(source, destination)

    monkeypatch.setattr(job_persistence.os, "replace", flaky_replace)
    write_json_atomic(
        target,
        {"status": "queued"},
        retry_delays=(0,),
        sleep=lambda _delay: None,
    )

    assert calls == 2
    assert json.loads(target.read_text(encoding="utf-8"))["status"] == "queued"


def test_atomic_json_raises_after_bounded_retries_and_preserves_original(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "job.json"
    original = '{"status": "queued"}\n'
    target.write_text(original, encoding="utf-8")
    calls = 0

    def locked_replace(_source, _destination):
        nonlocal calls
        calls += 1
        assert target.read_text(encoding="utf-8") == original
        raise windows_error(32)

    monkeypatch.setattr(job_persistence.os, "replace", locked_replace)
    with pytest.raises(AtomicJsonWriteError, match="6 次尝试") as caught:
        write_json_atomic(
            target,
            {"status": "processing"},
            retry_delays=(0, 0, 0, 0, 0),
            sleep=lambda _delay: None,
        )

    message = str(caught.value)
    assert calls == 6
    assert str(tmp_path) not in message
    assert target.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".job.json.*.tmp")) == []


def test_atomic_json_does_not_retry_non_transient_error(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "job.json"
    calls = 0

    def disk_full(_source, _destination):
        nonlocal calls
        calls += 1
        raise OSError(errno.ENOSPC, "disk full")

    monkeypatch.setattr(job_persistence.os, "replace", disk_full)
    with pytest.raises(OSError) as caught:
        write_json_atomic(
            target,
            {"status": "queued"},
            retry_delays=(0, 0, 0),
            sleep=lambda _delay: None,
        )

    assert caught.value.errno == errno.ENOSPC
    assert calls == 1
    assert not target.exists()
    assert list(tmp_path.glob(".job.json.*.tmp")) == []


def test_cleanup_error_does_not_mask_final_replace_error(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "job.json"
    original_unlink = Path.unlink

    def locked_replace(_source, _destination):
        raise windows_error(5)

    def locked_unlink(_path, *, missing_ok=False):
        del missing_ok
        raise windows_error(32)

    with monkeypatch.context() as patch:
        patch.setattr(job_persistence.os, "replace", locked_replace)
        patch.setattr(Path, "unlink", locked_unlink)
        with pytest.raises(AtomicJsonWriteError, match="2 次尝试"):
            write_json_atomic(
                target,
                {"status": "processing"},
                retry_delays=(0,),
                sleep=lambda _delay: None,
            )

    temporary_files = list(tmp_path.glob(".job.json.*.tmp"))
    assert len(temporary_files) == 1
    original_unlink(temporary_files[0])
