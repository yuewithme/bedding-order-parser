"""Dependency-light contract shared by the isolated embedding processes."""

from __future__ import annotations

import numpy as np


SCHEMA_VERSION = "1.0"
MODEL_NAME = "BAAI/bge-m3"
MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
DEVICE = "cpu"
DIMENSION = 1024


def validate_normalized_float32_vectors(
    vectors: np.ndarray,
    *,
    expected_rows: int,
    expected_dimension: int,
) -> np.ndarray:
    """Validate the exact lightweight vector handoff contract."""
    array = np.asarray(vectors)
    if array.dtype != np.float32:
        raise ValueError("Embedding vectors must use float32.")
    if array.shape != (expected_rows, expected_dimension):
        raise ValueError(
            "Embedding shape mismatch: "
            f"expected {(expected_rows, expected_dimension)}, got {array.shape}."
        )
    if not np.isfinite(array).all():
        raise ValueError("Embedding vectors contain NaN or Inf.")
    norms = np.linalg.norm(array, axis=1)
    if not np.isfinite(norms).all() or not np.allclose(
        norms, 1.0, rtol=1e-4, atol=1e-4
    ):
        raise ValueError("Embedding vectors are not normalized.")
    return np.ascontiguousarray(array, dtype=np.float32)
