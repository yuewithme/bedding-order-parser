"""Verified, resumable local checkpoints for long material embedding builds."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from bedding_order_parser.exceptions import BeddingOrderParserError


CHECKPOINT_SCHEMA_VERSION = "1.0"


class EmbeddingCheckpointError(BeddingOrderParserError):
    """Raised when an existing checkpoint manifest cannot be trusted."""


class EmbeddingCheckpointStore:
    """Persist completed vector windows under one content-addressed identity."""

    def __init__(self, root: str | Path, identity: Mapping[str, Any]) -> None:
        self.root = Path(root).expanduser().resolve()
        self.identity = json.loads(
            json.dumps(
                identity,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        canonical = json.dumps(
            self.identity, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.identity_sha256 = hashlib.sha256(canonical).hexdigest()
        self.run_dir = self.root / self.identity_sha256
        self.manifest_path = self.run_dir / "checkpoint_manifest.json"
        self.reused_chunks = 0
        self.encoded_chunks = 0
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._manifest = self._load_or_initialize_manifest()

    def load(
        self,
        start: int,
        end: int,
        *,
        dimension: int,
    ) -> np.ndarray | None:
        """Return one verified chunk or None when it must be regenerated."""
        key = _chunk_key(start, end)
        entry = self._manifest["chunks"].get(key)
        if not isinstance(entry, dict):
            return None
        file_name = str(entry.get("file", ""))
        expected_name = _chunk_file_name(start, end)
        if file_name != expected_name:
            return None
        path = self.run_dir / expected_name
        if not path.is_file():
            return None
        expected_sha256 = str(entry.get("sha256", ""))
        expected_shape = [end - start, dimension]
        if (
            not expected_sha256
            or entry.get("shape") != expected_shape
            or _sha256(path) != expected_sha256
        ):
            return None
        try:
            array = np.load(path, allow_pickle=False)
        except (OSError, ValueError):
            return None
        if array.shape != tuple(expected_shape) or array.dtype != np.float32:
            return None
        self.reused_chunks += 1
        return np.ascontiguousarray(array, dtype=np.float32)

    def save(self, start: int, end: int, vectors: np.ndarray) -> None:
        """Atomically save one validated float32 chunk and publish its hash."""
        target = self.run_dir / _chunk_file_name(start, end)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        array = np.ascontiguousarray(vectors, dtype=np.float32)
        try:
            with temporary.open("wb") as handle:
                np.save(handle, array, allow_pickle=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

        self._manifest["chunks"][_chunk_key(start, end)] = {
            "file": target.name,
            "sha256": _sha256(target),
            "shape": [int(value) for value in array.shape],
            "dtype": "float32",
        }
        _write_json_atomic(self.manifest_path, self._manifest)
        self.encoded_chunks += 1

    def cleanup_after_success(self) -> bool:
        """Remove only this verified generated checkpoint tree after publication."""
        try:
            shutil.rmtree(self.run_dir)
            if self.root.is_dir() and not any(self.root.iterdir()):
                self.root.rmdir()
        except OSError:
            return False
        return True

    def _load_or_initialize_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            manifest = {
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "identity_sha256": self.identity_sha256,
                "identity": self.identity,
                "chunks": {},
            }
            _write_json_atomic(self.manifest_path, manifest)
            return manifest
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EmbeddingCheckpointError(
                "Embedding checkpoint manifest cannot be read safely."
            ) from exc
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != CHECKPOINT_SCHEMA_VERSION
            or manifest.get("identity_sha256") != self.identity_sha256
            or manifest.get("identity") != self.identity
            or not isinstance(manifest.get("chunks"), dict)
        ):
            raise EmbeddingCheckpointError(
                "Embedding checkpoint manifest identity is invalid."
            )
        return manifest


def _chunk_key(start: int, end: int) -> str:
    return f"{start:08d}:{end:08d}"


def _chunk_file_name(start: int, end: int) -> str:
    return f"vectors-{start:08d}-{end:08d}.npy"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
