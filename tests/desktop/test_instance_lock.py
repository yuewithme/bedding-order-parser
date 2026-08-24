from __future__ import annotations

import uuid

import pytest

from bedding_order_parser.desktop.instance_lock import (
    SingleInstanceError,
    SingleInstanceLock,
)


def test_single_instance_lock_rejects_second_instance(tmp_path) -> None:
    name = f"Local\\BeddingOrderParserTest-{uuid.uuid4().hex}"
    first = SingleInstanceLock(name, fallback_path=tmp_path / "first.lock")
    second = SingleInstanceLock(name, fallback_path=tmp_path / "second.lock")
    first.acquire()
    try:
        with pytest.raises(SingleInstanceError, match="已经在运行"):
            second.acquire()
    finally:
        first.release()

    second.acquire()
    second.release()
