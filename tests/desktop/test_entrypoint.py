from __future__ import annotations

from bedding_order_parser.desktop.entrypoint import dispatch


def test_dispatch_runs_desktop_for_normal_launch() -> None:
    calls: list[tuple[str, list[str]]] = []

    result = dispatch(
        [],
        desktop_main=lambda: calls.append(("desktop", [])) or 7,
        embedding_worker_main=lambda argv: calls.append(("worker", argv)) or 9,
    )

    assert result == 7
    assert calls == [("desktop", [])]


def test_dispatch_routes_frozen_embedding_worker_arguments() -> None:
    calls: list[tuple[str, list[str]]] = []

    result = dispatch(
        [
            "--embedding-worker",
            "--request",
            "request.json",
            "--response",
            "response.json",
            "--vectors",
            "vectors.npy",
        ],
        desktop_main=lambda: calls.append(("desktop", [])) or 7,
        embedding_worker_main=lambda argv: calls.append(("worker", argv)) or 9,
    )

    assert result == 9
    assert calls == [
        (
            "worker",
            [
                "--request",
                "request.json",
                "--response",
                "response.json",
                "--vectors",
                "vectors.npy",
            ],
        )
    ]
