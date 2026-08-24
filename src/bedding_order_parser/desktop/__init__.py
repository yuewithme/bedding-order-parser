"""Windows desktop host for the local Bedding Order Parser web app."""


def main() -> int:
    """Import the desktop runtime only when the entry point is invoked."""
    from bedding_order_parser.desktop.entrypoint import main as run_desktop

    return run_desktop()

__all__ = ["main"]
