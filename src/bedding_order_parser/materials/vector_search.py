"""Search material FAISS indexes and restore codes through explicit mappings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from bedding_order_parser.materials.embedding_model import (
    EmbeddingAdapter,
    SentenceTransformerEmbeddingAdapter,
)
from bedding_order_parser.materials.faiss_io import read_faiss_index
from bedding_order_parser.materials.loader import compute_sha256
from bedding_order_parser.materials.vector_index import (
    ALL_INDEX_NAME,
    ALL_MAPPING_NAME,
    DUVET_INDEX_NAME,
    DUVET_MAPPING_NAME,
    MANIFEST_NAME,
    VectorIndexError,
    _validate_vectors,
)


def search_vector_index(
    index_dir: str | Path,
    query: str,
    *,
    scope: str = "duvet_cover",
    top_k: int = 10,
    adapter: EmbeddingAdapter | None = None,
) -> list[dict[str, Any]]:
    """Return Top-K dense-vector recall results with raw vector_score."""
    if not query.strip():
        raise VectorIndexError("Search query must not be empty.")
    if top_k <= 0:
        raise VectorIndexError("top_k must be greater than zero.")
    if scope not in {"all", "duvet_cover"}:
        raise VectorIndexError(f"Unsupported index scope: {scope}")

    root = Path(index_dir).expanduser().resolve()
    manifest_path = root / MANIFEST_NAME
    manifest = _read_json(manifest_path)
    _validate_manifest(manifest)
    names = (
        (ALL_INDEX_NAME, ALL_MAPPING_NAME, "all_index", "all_mapping")
        if scope == "all"
        else (DUVET_INDEX_NAME, DUVET_MAPPING_NAME, "duvet_index", "duvet_mapping")
    )
    index_path, mapping_path = root / names[0], root / names[1]
    _validate_artifact(index_path, manifest, names[2])
    _validate_artifact(mapping_path, manifest, names[3])

    index = read_faiss_index(index_path)
    mappings = _read_mapping(mapping_path)
    if index.ntotal != len(mappings):
        raise VectorIndexError(
            f"FAISS/mapping count mismatch: {index.ntotal} != {len(mappings)}"
        )

    model_contract = manifest["model"]
    embedding = adapter or SentenceTransformerEmbeddingAdapter(
        str(model_contract["name"]),
        device=str(model_contract["device"]),
        revision=str(model_contract["revision"]) or None,
        local_files_only=True,
    )
    if embedding.model_name != model_contract["name"]:
        raise VectorIndexError(
            "Search embedding model does not match vector index manifest."
        )
    if (
        model_contract.get("revision")
        and embedding.revision != model_contract["revision"]
    ):
        raise VectorIndexError(
            "Search embedding revision does not match vector index manifest."
        )
    if int(embedding.dimension) != int(model_contract["dimension"]):
        raise VectorIndexError(
            "Search embedding dimension does not match vector index manifest."
        )
    if index.d != int(model_contract["dimension"]):
        raise VectorIndexError("FAISS dimension does not match vector index manifest.")

    query_vector = _validate_vectors(
        embedding.encode([query], batch_size=1),
        expected_rows=1,
        expected_dimension=index.d,
    )
    count = min(top_k, int(index.ntotal))
    scores, positions = index.search(query_vector, count)
    results: list[dict[str, Any]] = []
    for rank, (score, position) in enumerate(
        zip(scores[0].tolist(), positions[0].tolist(), strict=True),
        start=1,
    ):
        if position < 0:
            continue
        mapping = mappings[position]
        if mapping["position"] != position:
            raise VectorIndexError(
                f"Mapping position mismatch at FAISS position {position}."
            )
        results.append(
            {
                "rank": rank,
                "material_code": mapping["material_code"],
                "vector_score": float(score),
                "source_row": mapping["source_row"],
                "embedding_text": mapping["embedding_text"],
                "product_category": mapping["product_category"],
                "metadata": mapping["metadata"],
            }
        )
    return results


def _validate_manifest(manifest: dict[str, Any]) -> None:
    model = manifest.get("model", {})
    index = manifest.get("index", {})
    if model.get("normalized") is not True:
        raise VectorIndexError("Manifest requires normalized embeddings.")
    if not model.get("name") or int(model.get("dimension", 0)) <= 0:
        raise VectorIndexError("Manifest embedding model contract is incomplete.")
    if index.get("type") != "IndexFlatIP":
        raise VectorIndexError("Manifest index type is not IndexFlatIP.")
    if index.get("metric") != "inner_product_on_normalized_vectors":
        raise VectorIndexError("Manifest vector metric is unsupported.")


def _validate_artifact(
    path: Path,
    manifest: dict[str, Any],
    artifact_key: str,
) -> None:
    if not path.is_file():
        raise VectorIndexError(f"Vector index artifact does not exist: {path}")
    expected = str(
        manifest.get("artifacts", {}).get(f"{artifact_key}_sha256", "")
    )
    if not expected or compute_sha256(path) != expected:
        raise VectorIndexError(f"Vector index artifact SHA-256 mismatch: {path.name}")


def _read_mapping(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise VectorIndexError(
                    f"Invalid mapping JSONL at line {line_number}: {exc}"
                ) from exc
            if row.get("position") != len(rows):
                raise VectorIndexError(
                    f"Mapping positions are not continuous at line {line_number}."
                )
            code = str(row.get("material_code", ""))
            if not code or code in seen_codes:
                raise VectorIndexError(
                    f"Invalid or duplicate mapping material code: {code!r}"
                )
            seen_codes.add(code)
            rows.append(row)
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VectorIndexError(f"Unable to read vector index manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise VectorIndexError("Vector index manifest must be a JSON object.")
    return payload
