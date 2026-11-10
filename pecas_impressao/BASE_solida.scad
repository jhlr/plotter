// BASE.stl with the triangular lattice in the vertical wall filled solid.
// Wall is x 0..6 mm; the lattice window is y 1.5..14.5, z 8..45.5 (frame is solid beyond it).
union() {
  import("BASE.stl");
  translate([0, 1.5, 8]) cube([6, 13, 37.5]);
}
