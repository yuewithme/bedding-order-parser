"""Resolve bundled assets and external business resources."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


APP_DIRECTORY_NAME = "BeddingOrderParser"
CONFIG_FILE_NAME = "app_config.json"


class ResourceConfigurationError(RuntimeError):
    """Raised when required offline resources cannot be located or validated."""


@dataclass(frozen=True)
class ApplicationPaths:
    """All desktop paths, separated into bundled, user, and business resources."""

    asset_root: Path
    app_root: Path
    config_path: Path
    task_root: Path
    log_path: Path
    cache_root: Path
    state_root: Path
    project_root: Path | None
    data_dir: Path
    material_store: Path
    index_dir: Path
    faiss_index: Path
    faiss_mapping: Path
    vector_manifest: Path
    rules_path: Path
    styles_path: Path
    model_cache: Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root(
    *, frozen: bool | None = None, meipass: str | Path | None = None
) -> Path:
    frozen_mode = is_frozen() if frozen is None else frozen
    if frozen_mode:
        value = meipass or getattr(sys, "_MEIPASS", "")
        if not value:
            raise ResourceConfigurationError("打包资源目录不可用。")
        return Path(value).resolve()
    return Path(__file__).resolve().parents[3]


def asset_root(
    *, frozen: bool | None = None, meipass: str | Path | None = None
) -> Path:
    frozen_mode = is_frozen() if frozen is None else frozen
    root = bundle_root(frozen=frozen, meipass=meipass)
    if frozen_mode:
        return root / "bedding_order_parser" / "web"
    return root / "src" / "bedding_order_parser" / "web"


def local_app_root(environment: Mapping[str, str] | None = None) -> Path:
    values = environment if environment is not None else os.environ
    local = values.get("LOCALAPPDATA", "").strip()
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return (base / APP_DIRECTORY_NAME).resolve()


def resolve_application_paths(
    *,
    environment: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
    frozen: bool | None = None,
    meipass: str | Path | None = None,
    create_user_directories: bool = True,
) -> ApplicationPaths:
    """Resolve paths by environment, local config, then development project."""
    values = dict(environment if environment is not None else os.environ)
    app_root = local_app_root(values)
    resolved_config_path = Path(
        config_path or app_root / "config" / CONFIG_FILE_NAME
    ).resolve()
    config = _read_config(resolved_config_path)

    project_value = values.get("BEDDING_ORDER_PARSER_PROJECT_ROOT", "").strip()
    project_value = project_value or str(config.get("project_root", "")).strip()
    project_root = Path(project_value).resolve() if project_value else None
    if project_root is None and not (is_frozen() if frozen is None else frozen):
        project_root = Path(__file__).resolve().parents[3]

    data_value = values.get("BEDDING_ORDER_PARSER_DATA_DIR", "").strip()
    data_value = data_value or str(config.get("data_dir", "")).strip()
    if data_value:
        data_dir = Path(data_value).resolve()
    elif project_root is not None:
        data_dir = (project_root / "data").resolve()
    else:
        raise ResourceConfigurationError(
            "资源配置缺失：请先配置项目数据目录。"
        )

    output_dir = data_dir / "output"
    reference_dir = data_dir / "reference"
    index_dir = _configured_path(
        config, "index_dir", output_dir / "material_vector_index"
    )
    material_store = _configured_path(
        config,
        "material_store",
        output_dir / "material_store" / "material_master.sqlite3",
    )
    faiss_index = _configured_path(
        config, "faiss_index", index_dir / "duvet_cover.faiss"
    )
    faiss_mapping = _configured_path(
        config, "faiss_mapping", index_dir / "duvet_cover_mapping.jsonl"
    )
    vector_manifest = _configured_path(
        config, "vector_manifest", index_dir / "vector_index_manifest.json"
    )
    rules_path = _configured_path(
        config, "rules_path", reference_dir / "PI单提取规则.xlsx"
    )
    styles_path = _configured_path(
        config, "styles_path", reference_dir / "款式表_structured.xlsx"
    )

    model_value = values.get("BEDDING_ORDER_PARSER_MODEL_CACHE", "").strip()
    model_value = model_value or str(config.get("model_cache", "")).strip()
    model_cache = (
        Path(model_value).resolve()
        if model_value
        else (Path.home() / ".cache" / "huggingface").resolve()
    )
    task_root = _configured_path(config, "task_root", app_root / "tasks")
    paths = ApplicationPaths(
        asset_root=asset_root(frozen=frozen, meipass=meipass).resolve(),
        app_root=app_root,
        config_path=resolved_config_path,
        task_root=task_root,
        log_path=(app_root / "logs" / "app.log").resolve(),
        cache_root=(app_root / "cache").resolve(),
        state_root=(app_root / "state").resolve(),
        project_root=project_root,
        data_dir=data_dir,
        material_store=material_store,
        index_dir=index_dir,
        faiss_index=faiss_index,
        faiss_mapping=faiss_mapping,
        vector_manifest=vector_manifest,
        rules_path=rules_path,
        styles_path=styles_path,
        model_cache=model_cache,
    )
    if create_user_directories:
        for directory in (
            paths.config_path.parent,
            paths.task_root,
            paths.log_path.parent,
            paths.cache_root,
            paths.state_root,
        ):
            directory.mkdir(parents=True, exist_ok=True)
    return paths


def validate_startup_paths(paths: ApplicationPaths) -> dict[str, object]:
    """Perform only lightweight existence checks needed to open the UI."""
    required_files = {
        "前端资源": paths.asset_root / "templates" / "index.html",
        "SQLite物料库": paths.material_store,
        "FAISS被套索引": paths.faiss_index,
        "FAISS映射": paths.faiss_mapping,
        "向量清单": paths.vector_manifest,
        "PI规则字典": paths.rules_path,
        "款式字典": paths.styles_path,
    }
    missing = [
        label for label, path in required_files.items() if not path.is_file()
    ]
    if not paths.model_cache.is_dir():
        missing.append("BGE-M3模型缓存")
    if missing:
        raise ResourceConfigurationError(
            "资源配置缺失：" + "、".join(missing) + "。"
        )
    return {
        "checked": True,
        "mode": "startup_existence_only",
        "file_count": len(required_files),
        "model_cache_present": True,
    }


def validate_application_paths(paths: ApplicationPaths) -> dict[str, object]:
    """Perform full validation for an actual material-matching task."""
    required = {
        "前端资源": paths.asset_root / "templates" / "index.html",
        "SQLite物料库": paths.material_store,
        "FAISS被套索引": paths.faiss_index,
        "FAISS映射": paths.faiss_mapping,
        "向量清单": paths.vector_manifest,
        "PI规则字典": paths.rules_path,
        "款式字典": paths.styles_path,
    }
    missing = [label for label, path in required.items() if not path.is_file()]
    if missing:
        raise ResourceConfigurationError(
            "资源配置缺失：" + "、".join(missing) + "。"
        )
    try:
        manifest = json.loads(paths.vector_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceConfigurationError("向量清单无法读取。") from exc

    expected = {
        paths.material_store: manifest.get("source", {}).get(
            "material_store_sha256"
        ),
        paths.faiss_index: manifest.get("artifacts", {}).get(
            "duvet_index_sha256"
        ),
        paths.faiss_mapping: manifest.get("artifacts", {}).get(
            "duvet_mapping_sha256"
        ),
    }
    for path, expected_hash in expected.items():
        if not expected_hash or _sha256(path) != expected_hash:
            raise ResourceConfigurationError(
                f"资源版本校验失败：{path.name} 与向量清单不一致。"
            )

    model = manifest.get("model", {})
    revision = str(model.get("revision", "")).strip()
    if not revision or not _model_revision_exists(paths.model_cache, revision):
        raise ResourceConfigurationError("BGE-M3模型缓存或指定revision缺失。")
    return {
        "model_name": str(model.get("name", "")),
        "model_revision": revision,
        "vector_dimension": int(model.get("dimension", 0)),
        "validated": True,
    }


def public_path_summary(paths: ApplicationPaths) -> dict[str, str]:
    """Return non-secret resource names for diagnostics and tests."""
    return {
        "asset_root": paths.asset_root.name,
        "task_root": paths.task_root.name,
        "material_store": paths.material_store.name,
        "faiss_index": paths.faiss_index.name,
        "faiss_mapping": paths.faiss_mapping.name,
        "vector_manifest": paths.vector_manifest.name,
    }


def _read_config(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceConfigurationError("本地资源配置文件无法读取。") from exc
    if not isinstance(payload, dict):
        raise ResourceConfigurationError("本地资源配置格式不正确。")
    return payload


def _configured_path(
    config: Mapping[str, object], key: str, default: Path
) -> Path:
    value = str(config.get(key, "")).strip()
    return Path(value).resolve() if value else default.resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_revision_exists(model_cache: Path, revision: str) -> bool:
    candidates = (
        model_cache / "hub" / "models--BAAI--bge-m3" / "snapshots" / revision,
        model_cache / "models--BAAI--bge-m3" / "snapshots" / revision,
        model_cache / "snapshots" / revision,
    )
    return any(path.is_dir() and any(path.iterdir()) for path in candidates)
