"""Embedding adapters for material vector indexing."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence

import numpy as np

from bedding_order_parser.exceptions import BeddingOrderParserError


class EmbeddingModelError(BeddingOrderParserError):
    """Raised when an embedding model cannot satisfy the index contract."""


class EmbeddingAdapter(Protocol):
    """Small injectable contract used by index builds and offline tests."""

    model_name: str
    revision: str
    device: str
    dimension: int

    def encode(self, texts: Sequence[str], *, batch_size: int) -> np.ndarray:
        """Return normalized float32 embeddings in input order."""


class SentenceTransformerEmbeddingAdapter:
    """Local sentence-transformers adapter with normalized embeddings."""

    def __init__(
        self,
        model_name: str,
        *,
        device: str = "cpu",
        revision: str | None = None,
        local_files_only: bool = False,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - dependency contract
            raise EmbeddingModelError(
                "sentence-transformers is required for material embeddings."
            ) from exc

        load_source = (
            _cached_snapshot_path(model_name, revision)
            if local_files_only and revision
            else None
        )
        try:
            self._model = SentenceTransformer(
                str(load_source or model_name),
                device=device,
                revision=None if load_source else revision,
                local_files_only=local_files_only,
            )
        except Exception as exc:
            raise EmbeddingModelError(
                f"Unable to load embedding model {model_name!r}: {exc}"
            ) from exc

        self.model_name = model_name
        self.device = device
        self.dimension = int(self._model.get_embedding_dimension() or 0)
        if self.dimension <= 0:
            raise EmbeddingModelError(
                f"Embedding model returned an invalid dimension: {self.dimension}"
            )
        self.revision = _resolve_revision(self._model, revision)
        self.cache_path = _resolve_cache_path(
            self._model,
            model_name=model_name,
            revision=self.revision,
        )

    def encode(self, texts: Sequence[str], *, batch_size: int) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        try:
            vectors = self._model.encode(
                list(texts),
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        except Exception as exc:
            raise EmbeddingModelError(f"Embedding generation failed: {exc}") from exc
        return np.asarray(vectors, dtype=np.float32)


def _resolve_cache_path(
    model: object,
    *,
    model_name: str,
    revision: str,
) -> str:
    for value in _model_paths(model):
        path = Path(value)
        if path.exists():
            return str(path)
    snapshot = _cached_snapshot_path(model_name, revision)
    if snapshot is not None:
        return str(snapshot)
    return ""


def _resolve_revision(model: object, requested_revision: str | None) -> str:
    for module in getattr(model, "_modules", {}).values():
        auto_model = getattr(module, "auto_model", None)
        config = getattr(auto_model, "config", None)
        commit_hash = getattr(config, "_commit_hash", None)
        if commit_hash:
            return str(commit_hash)

    for value in _model_paths(model):
        path = Path(value)
        parts = path.parts
        if "snapshots" in parts:
            snapshot_index = parts.index("snapshots")
            if snapshot_index + 1 < len(parts):
                return parts[snapshot_index + 1]
    return requested_revision or ""


def _model_paths(model: object) -> list[str]:
    paths: list[str] = []
    for module in getattr(model, "_modules", {}).values():
        auto_model = getattr(module, "auto_model", None)
        for candidate in (
            getattr(auto_model, "name_or_path", None),
            getattr(getattr(auto_model, "config", None), "_name_or_path", None),
        ):
            if candidate:
                paths.append(str(candidate))
    return paths


def _cached_snapshot_path(model_name: str, revision: str | None) -> Path | None:
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
    except ImportError:  # pragma: no cover - sentence-transformers dependency
        return None
    snapshot = (
        Path(HF_HUB_CACHE)
        / f"models--{model_name.replace('/', '--')}"
        / "snapshots"
        / str(revision or "")
    )
    return snapshot if revision and snapshot.is_dir() else None
