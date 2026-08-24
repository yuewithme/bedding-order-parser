"""Dispatch the desktop host or the frozen embedding worker."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence


EMBEDDING_WORKER_SWITCH = "--embedding-worker"


def dispatch(
    argv: Sequence[str],
    *,
    desktop_main: Callable[[], int] | None = None,
    embedding_worker_main: Callable[[list[str]], int] | None = None,
) -> int:
    """Route one frozen executable without treating it as a Python interpreter."""
    arguments = list(argv)
    if arguments[:1] == [EMBEDDING_WORKER_SWITCH]:
        if embedding_worker_main is None:
            from bedding_order_parser.materials.query_embedding_worker import (
                main as embedding_worker_main,
            )

        return embedding_worker_main(arguments[1:])

    if desktop_main is None:
        from bedding_order_parser.desktop.launcher import main as desktop_main

    return desktop_main()


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch process arguments for source and PyInstaller entry points."""
    return dispatch(sys.argv[1:] if argv is None else argv)


__all__ = ["EMBEDDING_WORKER_SWITCH", "dispatch", "main"]
