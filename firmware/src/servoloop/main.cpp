// Standalone motor test, no computer needed: once powered, both servos move on their own, forever.
// Round: servo 1 alone (60 <-> 120), servo 2 alone (60 <-> 120), both together. Pins: see config.h (D9, D8).
#include "../config.h"

Servo servo[2];

void moveTo(int i, int from, int to) {
  int step = from < to ? 1 : -1;
  for (int a = from; a != to; a += step) { servo[i].write(a); delay(15); }
  servo[i].write(to);
}

void swing(int i) {
  moveTo(i, 90, 60); moveTo(i, 60, 120); moveTo(i, 120, 90);
}

void swingBoth() {
  for (int a = 90; a >= 60; a--) { servo[0].write(a); servo[1].write(a); delay(15); }
  for (int a = 60; a <= 120; a++) { servo[0].write(a); servo[1].write(a); delay(15); }
  for (int a = 120; a >= 90; a--) { servo[0].write(a); servo[1].write(a); delay(15); }
}

void setup() {
  boardInit();
  servo[0].attach(PIN_SERVO1, PULSE_MIN_US, PULSE_MAX_US);
  servo[1].attach(PIN_SERVO2, PULSE_MIN_US, PULSE_MAX_US);
  servo[0].write(90);
  servo[1].write(90);
  delay(1500);
}

void loop() {
  swing(0);
  delay(500);
  swing(1);
  delay(500);
  swingBoth();
  delay(1000);
}
