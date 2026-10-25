"""The MCP tool layer against the simulator: one entry for every drawing tool, dry-run, jobs, readable errors."""
import asyncio
from typing import Any

import pytest

from penarm import server


def call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    result = asyncio.run(server.mcp.call_tool(name, args))
    return dict(getattr(result, "structured_content", None) or {})


def test_dry_run_returns_a_preview_and_does_not_move() -> None:
    before = len(server._link.history)  # type: ignore[attr-defined]
    out = call("draw_shape", {"kind": "circle", "cx": 80, "cy": 20, "size": 20, "dry_run": True})
    assert out["dry_run"] is True and out["inside_canvas"] is True and "O" in out["ascii"] and "<svg" in out["svg"]
    assert len(server._link.history) == before  # type: ignore[attr-defined]


def test_drawing_runs_as_a_job_and_reports_done() -> None:
    out = call("draw_shape", {"kind": "square", "cx": 80, "cy": 20, "size": 12})
    assert out["status"] == "done" and out["progress"].split("/")[0] == out["progress"].split("/")[1]
    assert call("job_status", {})["status"] == "done"


def test_every_trajectory_tool_goes_through_the_same_path() -> None:
    cases: list[tuple[str, dict[str, Any]]] = [
        ("draw_line", {"x1": 40, "y1": 15, "x2": 90, "y2": 25}),
        ("draw_polyline", {"points": [[40, 15], [60, 25], [80, 15]]}),
        ("draw_bezier", {"p0": [40, 15], "p1": [50, 30], "p2": [70, 0], "p3": [80, 15]}),
        ("draw_svg_path", {"d": "M0 0 L40 0 L40 20 Z", "x": 40, "y": 10, "width": 30}),
        ("draw_path", {"ops": [{"op": "move", "to": [0, 0]}, {"op": "arc", "center": [0, 0], "radius": 5,
                                                              "start_deg": 0, "end_deg": 180}],
                       "fit": {"x": 40, "y": 10, "width": 30, "height": 20}}),
    ]
    for name, args in cases:
        assert call(name, {**args, "dry_run": True})["inside_canvas"] is True, name


def test_a_drawing_that_does_not_fit_gets_an_actionable_error() -> None:
    with pytest.raises(Exception, match="fit"):
        call("draw_shape", {"kind": "circle", "cx": 80, "cy": 20, "size": 500})


def test_stop_with_nothing_running_is_harmless() -> None:
    assert call("stop", {}).get("status") in ("idle", "done", "cancelled")
