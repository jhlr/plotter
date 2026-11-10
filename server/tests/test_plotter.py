"""The plain-Python API students use without an LLM: same methods the MCP server exposes."""
import json
from pathlib import Path

import pytest

from penarm import Plotter
from penarm.errors import Unreachable


BENT_RIGHT_ARM = {"page_w": 230.0, "page_h": 330.0, "base_x": 117.0, "base_y": 12.7, "offset1": 4.5, "offset2": 0.0,
                  "sign1": 0.987, "sign2": 0.913, "l1": 108.1, "l2": 114.2}


def test_a_script_can_draw_in_the_simulator_and_blocks_until_done() -> None:
    with Plotter() as p:
        assert p.canvas_info()["simulated"] is True
        out = p.draw_shape("heart", cx=80, cy=20, size=30)
        assert out["status"] == "done"
        assert p.get_state()["servo_deg"] == p.link.pos  # type: ignore[attr-defined]


def test_dry_run_previews_without_moving() -> None:
    p = Plotter()
    out = p.draw_shape("star", cx=80, cy=17, size=24, dry_run=True)
    assert out["dry_run"] is True and out["inside_canvas"] is True
    assert p.link.history == []  # type: ignore[attr-defined]


def test_plain_errors_are_raised_for_scripts() -> None:
    with pytest.raises(Unreachable, match="fit"):
        Plotter().draw_shape("circle", cx=80, cy=20, size=500)
    with pytest.raises(ValueError, match="unknown shape"):
        Plotter().draw_shape("dodecahedron", cx=80, cy=20, size=10)


def test_arc_and_line() -> None:
    p = Plotter()
    top = p.draw_arc(80, 10, 20, 0, 180, dry_run=True)["bbox_mm"]
    assert abs(top[1] - 10) < 0.5 and abs(top[3] - 30) < 0.5  # type: ignore[index]  # half circle: y from 10 to 10 + r
    assert p.draw_line(40, 15, 90, 25, dry_run=True)["inside_canvas"] is True
    assert p.draw_arc(80, 10, 20, 0, 90)["status"] == "done"


def test_a_horn_mounted_for_the_wrong_elbow_side_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps({"params": BENT_RIGHT_ARM}))  # offset2 = 0: servo 2 only reaches positive joint 2 (elbow bent right); the code always bends left
    monkeypatch.setenv("PENARM_CALIBRATION", str(path))
    with pytest.raises(Unreachable, match="remount"):
        Plotter()
