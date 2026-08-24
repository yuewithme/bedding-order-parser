"""Project-specific exceptions."""


class BeddingOrderParserError(Exception):
    """Base class for expected parser errors."""


class InputFileError(BeddingOrderParserError):
    """Raised when an input PI file cannot be read safely."""


class WorkbookStructureError(BeddingOrderParserError):
    """Raised when a workbook does not contain parseable PI rows."""


class OutputFileError(BeddingOrderParserError):
    """Raised when JSON output cannot be written safely."""
