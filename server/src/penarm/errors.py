"""Errors the LLM should see verbatim (via ToolError) so it can adapt."""


class Unreachable(ValueError):
    pass


class VisionError(RuntimeError):
    pass
