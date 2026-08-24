"""Unicode-safe FAISS serialization for local Windows paths."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import faiss
import numpy as np


def write_faiss_index(index: Any, path: str | Path) -> Path:
    """Serialize through memory so Python owns Unicode path handling."""
    target = Path(path)
    payload = np.asarray(faiss.serialize_index(index), dtype=np.uint8)
    with target.open("wb") as stream:
        stream.write(payload.tobytes())
        stream.flush()
        os.fsync(stream.fileno())
    return target


def read_faiss_index(path: str | Path) -> Any:
    """Deserialize through memory so FAISS never receives a Unicode path."""
    source = Path(path)
    payload = source.read_bytes()
    if not payload:
        raise ValueError(f"FAISS index is empty: {source.name}")
    buffer = np.frombuffer(payload, dtype=np.uint8)
    return faiss.deserialize_index(buffer)
