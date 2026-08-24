"""Run the desktop application or its isolated worker mode."""

from bedding_order_parser.desktop.entrypoint import main


if __name__ == "__main__":
    raise SystemExit(main())
