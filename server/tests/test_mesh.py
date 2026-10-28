import pytest

from penarm.mesh import CorrectionMesh


def _mesh() -> CorrectionMesh:
    flat = ((0.0, 100.0), (0.0, 0.0))
    return CorrectionMesh(0.0, 0.0, 100.0, 50.0, bottom=((0.0, 100.0), (2.0, 4.0)), top=((0.0, 100.0), (-2.0, -2.0)),
                          left=flat, right=((0.0, 50.0), (6.0, 6.0)))


def test_edges_return_their_measured_error_and_the_interior_blends_them() -> None:
    m = _mesh()
    assert m.error_at(0.0, 0.0) == pytest.approx((0.0, 2.0))
    assert m.error_at(100.0, 0.0) == pytest.approx((6.0, 4.0))
    assert m.error_at(50.0, 25.0) == pytest.approx((3.0, 0.5 * 3.0 + 0.5 * -2.0))  # halfway between bottom and top


def test_aiming_is_shifted_against_the_error() -> None:
    m = _mesh()
    assert m.corrected(100.0, 50.0) == pytest.approx((94.0, 52.0))


def test_outside_the_measured_rectangle_the_correction_is_held_at_the_nearest_edge() -> None:
    m = _mesh()
    assert m.error_at(-30.0, -30.0) == pytest.approx(m.error_at(0.0, 0.0))
    assert m.error_at(300.0, 200.0) == pytest.approx(m.error_at(100.0, 50.0))


def test_json_round_trip() -> None:
    m = _mesh()
    assert CorrectionMesh.from_json(m.to_json()) == m


def test_the_arm_aims_against_the_mesh_error() -> None:
    import os

    from penarm.arm import Arm
    from penarm.config import ArmConfig
    from penarm.kinematics import fk, servos_to_joints
    from penarm.link import SerialLink
    from tests.fakes import FakeBoard

    target_page = (100.0, 120.0)  # a page point both arms can reach

    def landing(mesh: CorrectionMesh | None, name: str) -> tuple[float, float]:
        board = FakeBoard()
        link = SerialLink(f"/dev/fake-{os.getpid()}-mesh-{name}", opener=lambda p, b: board, boot_wait=0.0, time_scale=0.01)
        try:
            arm = Arm(ArmConfig(), link, mesh=mesh)
            arm.draw_strokes([[arm.canvas.from_page(*target_page)]])
            return fk(arm.cfg, *servos_to_joints(arm.cfg, *board.s))
        finally:
            link.close()

    flat = ((0.0, 400.0), (4.0, 4.0))
    zero = ((0.0, 400.0), (0.0, 0.0))
    always_4_high = CorrectionMesh(0.0, 0.0, 300.0, 400.0, bottom=flat, top=flat, left=zero, right=zero)
    plain, aimed = landing(None, "plain"), landing(always_4_high, "aimed")
    assert aimed[0] == pytest.approx(plain[0], abs=0.05) and aimed[1] == pytest.approx(plain[1] - 4.0, abs=0.05)
