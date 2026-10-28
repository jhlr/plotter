// Gear on a base disc, with the motor coupling in the same piece. One print, no assembly.
bore    = 5.0;    // tunnel through the whole piece (mm) -- ask: add +0.2 clearance when printing
teeth   = 16;
tip_d   = 20;     // gear tip diameter
root_d  = 17;     // gear root diameter
gear_h  = 7;
base_t  = 1.5;    // base disc thickness
base_d  = 24;    // base disc (outer wall removed)
hub_d   = 10;     // motor coupling boss
hub_h   = 6;
flange_d = 20;    // top flange the hub sits on (same Ø as gear tips -> channel stays open)
flange_t = 2;
$fn = 96;

module gear2d() {
  union() {
    circle(d = root_d);
    for (i = [0 : teeth - 1]) rotate(i * 360 / teeth)
      polygon([[root_d/2 - 0.1, -1.0], [tip_d/2, -0.55], [tip_d/2, 0.55], [root_d/2 - 0.1, 1.0]]);
  }
}

cut = false;   // true = preview cutaway
difference() {
  union() {
    cylinder(d = base_d, h = base_t);                                         // base disc
    translate([0,0,base_t]) linear_extrude(gear_h) gear2d();                  // gear fused to floor
    translate([0,0,base_t + gear_h]) cylinder(d = flange_d, h = flange_t);    // flange
    translate([0,0,base_t + gear_h + flange_t]) cylinder(d = hub_d, h = hub_h); // motor hub
  }
  translate([0,0,-1]) cylinder(d = bore, h = 100, $fn = 64);                  // 5 mm tunnel
  if (cut) translate([-30,-60,-5]) cube([60,60,40]);
}
