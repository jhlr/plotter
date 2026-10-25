// Pen-plotter arm firmware (ESP32 or Arduino Uno, see config.h): 2 servos + 2 feedback pots, line protocol over USB serial.
//   ?            -> "OK penarm 1 adcmax=<4095|1023> boot=<id>"  (the id changes on every restart)
//   W <seconds>  -> release (detach) the servos after that long without commands; 0 = never   -> "OK"
//   V <deg/s>    -> set max servo speed            -> "OK"
//   A <s1> <s2>  -> go to servo angles (deg, 0-180), ramped; "OK" once reached
//   R            -> "R <adc1> <adc2> <s1> <s2>"    (raw ADC, 0..adcmax; current servo angles)
// Boots at HOME, or on the Uno at the last resting pose saved in EEPROM (see PERSIST_POSE in config.h).
#include "config.h"
#if PERSIST_POSE
#include <EEPROM.h>
#endif

constexpr float HOME1 = 90.0f;
constexpr float HOME2 = 90.0f;
constexpr uint32_t STEP_MS = 10;

Servo servo1, servo2;
float cur[2] = {HOME1, HOME2};
float tgt[2] = {HOME1, HOME2};
float maxSpeed = 60.0f;  // deg/s
bool ackPending = false;
bool moving = false;
uint32_t lastStep = 0;
uint16_t bootNumber = 0;
uint32_t idleLimitMs = 0;  // 0 = never release
uint32_t lastCommandMs = 0;
bool attached = false;
String line;

#if PERSIST_POSE
struct Pose {
  uint16_t magic;
  float a, b;
};
constexpr uint16_t POSE_MAGIC = 0x50A1;
constexpr int POSE_ADDR = 0;
constexpr uint32_t POSE_SAVE_IDLE_MS = 500;  // save only once the arm has rested, not on every step (EEPROM wear)
bool poseDirty = false;
uint32_t arrivedAt = 0;

void loadPose() {
  Pose p;
  EEPROM.get(POSE_ADDR, p);
  if (p.magic == POSE_MAGIC && p.a >= 0 && p.a <= 180 && p.b >= 0 && p.b <= 180) {  // blank EEPROM / NaN: HOME
    cur[0] = tgt[0] = p.a;
    cur[1] = tgt[1] = p.b;
  }
}

void savePoseWhenIdle() {
  if (!poseDirty || moving || millis() - arrivedAt < POSE_SAVE_IDLE_MS) return;
  EEPROM.put(POSE_ADDR, Pose{POSE_MAGIC, cur[0], cur[1]});  // put() only rewrites bytes that changed
  poseDirty = false;
}
#endif

int toMicros(float deg) {
  return PULSE_MIN_US + (int)lroundf((PULSE_MAX_US - PULSE_MIN_US) * deg / 180.0f);
}

void attachServos() {
  servo1.attach(PIN_SERVO1, PULSE_MIN_US, PULSE_MAX_US);
  servo2.attach(PIN_SERVO2, PULSE_MIN_US, PULSE_MAX_US);
  attached = true;
}

void releaseWhenIdle() {
  // A silent host (crashed, unplugged, forgotten) should not leave the servos buzzing and the pen pressing the paper.
  if (attached && idleLimitMs && !ackPending && millis() - lastCommandMs > idleLimitMs) {
    servo1.detach();
    servo2.detach();
    attached = false;
  }
}

void writeServos() {
  // writeMicroseconds, not write(): write() takes whole degrees and turns smooth ramps into 1-degree steps
  servo1.writeMicroseconds(toMicros(cur[0]));
  servo2.writeMicroseconds(toMicros(cur[1]));
}

void stepMotion() {
  uint32_t now = millis();
  if (now - lastStep < STEP_MS) return;
  float dt = (now - lastStep) / 1000.0f;
  lastStep = now;
  float maxStep = maxSpeed * dt;
  moving = false;
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
#if PERSIST_POSE
    poseDirty = true;
    arrivedAt = now;
#endif
  }
}

void handle(const String& cmd) {
  lastCommandMs = millis();
  if (cmd == "?") {
    Serial.print("OK penarm 1 adcmax=");
    Serial.print(ADC_MAX);
    Serial.print(" boot=");
    Serial.println(bootNumber);
  } else if (cmd.startsWith("W ")) {
    long sec = cmd.substring(2).toInt();
    if (sec < 0 || sec > 86400) { Serial.println("ERR idle"); return; }
    idleLimitMs = (uint32_t)sec * 1000UL;
    Serial.println("OK");
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
    if (!attached) {  // woke up from an idle release: resume exactly where the arm was
      writeServos();
      attachServos();
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
  Serial.begin(PENARM_BAUD);
  boardInit();
#if PERSIST_POSE
  loadPose();
#endif
  bootNumber = bootId();
  attachServos();
  writeServos();
  lastStep = millis();
  lastCommandMs = lastStep;
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
  releaseWhenIdle();
#if PERSIST_POSE
  savePoseWhenIdle();
#endif
}
