from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from bedding_order_parser.desktop.resource_paths import (
    asset_root,
    local_app_root,
    resolve_application_paths,
    validate_startup_paths,
)


def test_desktop_entry_module_is_importable() -> None:
    from bedding_order_parser.desktop import main

    assert callable(main)


def test_development_asset_root_uses_package_web_directory() -> None:
    root = asset_root(frozen=False)

    assert root.name == "web"
    assert (root / "templates" / "index.html").is_file()


def test_frozen_asset_root_uses_meipass(tmp_path: Path) -> None:
    root = asset_root(frozen=True, meipass=tmp_path)

    assert root == tmp_path / "bedding_order_parser" / "web"


def test_user_data_is_never_written_to_meipass(tmp_path: Path) -> None:
    meipass = tmp_path / "bundle"
    local = tmp_path / "local"
    project = tmp_path / "project"
    paths = resolve_application_paths(
        environment={
            "LOCALAPPDATA": str(local),
            "BEDDING_ORDER_PARSER_PROJECT_ROOT": str(project),
        },
        frozen=True,
        meipass=meipass,
    )

    assert meipass not in paths.task_root.parents
    assert paths.task_root == local / "BeddingOrderParser" / "tasks"
    assert paths.log_path == local / "BeddingOrderParser" / "logs" / "app.log"


def test_environment_paths_override_local_config(tmp_path: Path) -> None:
    local = tmp_path / "local"
    config_path = local / "BeddingOrderParser" / "config" / "app_config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"data_dir": str(tmp_path / "configured")}),
        encoding="utf-8",
    )
    environment_data = tmp_path / "environment"

    paths = resolve_application_paths(
        environment={
            "LOCALAPPDATA": str(local),
            "BEDDING_ORDER_PARSER_DATA_DIR": str(environment_data),
        },
        config_path=config_path,
        frozen=True,
        meipass=tmp_path / "bundle",
    )

    assert paths.data_dir == environment_data


def test_local_application_root_uses_windows_local_app_data(
    tmp_path: Path,
) -> None:
    assert local_app_root({"LOCALAPPDATA": str(tmp_path)}) == (
        tmp_path / "BeddingOrderParser"
    )


def test_desktop_import_does_not_load_matching_runtime() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src"
    script = "\n".join(
        (
            "import sys",
            f"sys.path.insert(0, {str(source_root)!r})",
            "from bedding_order_parser.desktop import main",
            "assert callable(main)",
            "assert 'faiss' not in sys.modules",
            "assert 'torch' not in sys.modules",
            "assert 'sentence_transformers' not in sys.modules",
        )
    )

    completed = subprocess.run(
        [sys.executable, "-I", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr


def test_startup_validation_only_checks_required_paths(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    data = project / "data"
    base = resolve_application_paths(
        environment={
            "LOCALAPPDATA": str(tmp_path / "local"),
            "BEDDING_ORDER_PARSER_PROJECT_ROOT": str(project),
            "BEDDING_ORDER_PARSER_MODEL_CACHE": str(tmp_path / "model"),
        },
        frozen=False,
    )
    paths = replace(base, asset_root=asset_root(frozen=False))
    for file_path in (
        paths.material_store,
        paths.faiss_index,
        paths.faiss_mapping,
        paths.vector_manifest,
        paths.rules_path,
        paths.styles_path,
    ):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"not-read-during-startup")
    paths.model_cache.mkdir(parents=True)

    def fail_if_read(*_args, **_kwargs):
        raise AssertionError("startup validation must not read resource content")

    monkeypatch.setattr(Path, "open", fail_if_read)
    monkeypatch.setattr(Path, "read_text", fail_if_read)
    monkeypatch.setattr(Path, "iterdir", fail_if_read)

    result = validate_startup_paths(paths)

    assert result["mode"] == "startup_existence_only"
    assert result["model_cache_present"] is True
