class FreightWatchError(Exception):
    """Base class for all expected, user-facing errors."""


class DataValidationError(FreightWatchError):
    """Input file is missing, has wrong columns, or (in strict mode) has bad rows."""
