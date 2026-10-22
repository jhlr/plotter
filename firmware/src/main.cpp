// Pen-plotter arm firmware (ESP32 or Arduino Uno, see config.h): 2 servos + 2 feedback pots, line protocol over USB serial.
//   ?            -> "OK penarm 1 adcmax=<4095|1023>"
//   V <deg/s>    -> set max servo speed            -> "OK"
//   A <s1> <s2>  -> go to servo angles (deg, 0-180), ramped; "OK" once reached
//   R            -> "R <adc1> <adc2> <s1> <s2>"    (raw ADC, 0..adcmax; current servo angles)
#include "config.h"

constexpr float HOME1 = 90.0f;
constexpr float HOME2 = 90.0f;
constexpr uint32_t STEP_MS = 10;

Servo servo1, servo2;
float cur[2] = {HOME1, HOME2};
float tgt[2] = {HOME1, HOME2};
float maxSpeed = 60.0f;  // deg/s
bool ackPending = false;
uint32_t lastStep = 0;
String line;

void writeServos() {
  servo1.write(cur[0]);
  servo2.write(cur[1]);
}

void stepMotion() {
  uint32_t now = millis();
  if (now - lastStep < STEP_MS) return;
  float dt = (now - lastStep) / 1000.0f;
  lastStep = now;
  float maxStep = maxSpeed * dt;
  bool moving = false;
  for (int i = 0; i < 2; i++) {
    float d = tgt[i] - cur[i];
    if (fabsf(d) > maxStep) {
      cur[i] += d > 0 ? maxStep : -maxStep;
      moving = true;
    } else {
      cur[i] = tgt[i];
    }
  }
  writeServos();
  if (!moving && ackPending) {
    Serial.println("OK");
    ackPending = false;
  }
}

void handle(const String& cmd) {
  if (cmd == "?") {
    Serial.print("OK penarm 1 adcmax=");
    Serial.println(ADC_MAX);
  } else if (cmd.startsWith("V ")) {
    float v = cmd.substring(2).toFloat();
    if (v < 1.0f || v > 300.0f) { Serial.println("ERR speed"); return; }
    maxSpeed = v;
    Serial.println("OK");
  } else if (cmd.startsWith("A ")) {
    // AVR's sscanf has no float support, so split by hand
    int sp = cmd.indexOf(' ', 2);
    float a = cmd.substring(2, sp).toFloat();
    float b = cmd.substring(sp + 1).toFloat();
    if (sp < 0 || a < 0 || a > 180 || b < 0 || b > 180) {
      Serial.println("ERR angles");
      return;
    }
    tgt[0] = a;
    tgt[1] = b;
    ackPending = true;  // "OK" is sent by stepMotion() on arrival
  } else if (cmd == "R") {
    Serial.print("R ");
    Serial.print(analogRead(PIN_POT1));
    Serial.print(' ');
    Serial.print(analogRead(PIN_POT2));
    Serial.print(' ');
    Serial.print(cur[0], 1);
    Serial.print(' ');
    Serial.println(cur[1], 1);
  } else {
    Serial.println("ERR unknown");
  }
}

void setup() {
  Serial.begin(115200);
  boardInit();
  servo1.attach(PIN_SERVO1, PULSE_MIN_US, PULSE_MAX_US);
  servo2.attach(PIN_SERVO2, PULSE_MIN_US, PULSE_MAX_US);
  writeServos();
  lastStep = millis();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      line.trim();
      if (line.length()) handle(line);
      line = "";
    } else if (c != '\r') {
      line += c;
    }
  }
  stepMotion();
}
