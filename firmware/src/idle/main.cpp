// Safe idle: never attaches the servos, so no signal reaches them and the arm stays still.
#include <Arduino.h>

void setup() {
  Serial.begin(57600);
  Serial.println("idle: servos not driven");
}

void loop() {}
