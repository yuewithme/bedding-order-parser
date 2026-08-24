import sys
from pathlib import Path

import bedding_order_parser
import openpyxl


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_package_can_be_imported() -> None:
    assert bedding_order_parser.__name__ == "bedding_order_parser"


def test_openpyxl_can_be_imported() -> None:
    assert openpyxl.__name__ == "openpyxl"


def test_python_version_is_312() -> None:
    assert sys.version_info[:2] == (3, 12)


def test_input_directory_exists() -> None:
    assert (PROJECT_ROOT / "data" / "input").is_dir()


def test_output_directory_exists() -> None:
    assert (PROJECT_ROOT / "data" / "output").is_dir()
