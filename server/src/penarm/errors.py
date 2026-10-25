"""Errors the LLM should see verbatim (via ToolError) so it can adapt."""


class Unreachable(ValueError):
    pass


class VisionError(RuntimeError):
    pass


class Busy(RuntimeError):
    """A drawing job is already running."""


class Cancelled(Exception):
    """Raised inside a job when it is cancelled between waypoints."""
