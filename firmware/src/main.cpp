// Pen-plotter arm firmware (ESP32 or Arduino Uno, see config.h): 2 servos + 2 feedback pots, line protocol over USB serial.
//   ?            -> "OK penarm 1 adcmax=<4095|1023> boot=<id>"  (the id changes on every restart)
//   W <seconds>  -> release (detach) the servos after that long without commands; 0 = never   -> "OK"
//   V <deg/s>    -> set max servo speed            -> "OK"
//   A <s1> <s2>  -> go to servo angles (deg, 0-180), ramped; "OK" once reached
//   R            -> "R <adc1> <adc2> <s1> <s2>"    (raw ADC, 0..adcmax; current servo angles)
// Execution queue (the board keeps drawing without the host, which only has to stay ahead of it):
//   Q <seq> <s1> <s2> [ms] -> append a waypoint; "OK <free>", "FULL", or "ERR seq <expected>". Idempotent: a resend of the
//                        last accepted <seq> is acknowledged without queueing it twice. [ms] is the time the arm takes to get
//                        there (both servos move together, and the next waypoint starts the instant this one ends, so the
//                        tip keeps a steady speed); never faster than the V limit. Without it the V speed alone sets the time.
//   S            -> "S <next_seq> <executed> <queued> <free> <moving>"   (executed wraps at 65536)
//   X            -> abort: clear the queue (and stop a stored drawing), hold the current pose   -> "OK <next_seq>"
// A drawing kept in EEPROM (Uno): the board plays it on its own, so the host can disconnect after G.
//   PB <a> <b> <n> [ms] -> begin storing: start pose (0.1 deg), n steps, ms per step; "OK <max steps>" or "ERR size <max>"
//   PD <i> <dA> <dB> [...] -> steps from index i (int8 deltas, 0.1 deg; a resend rewrites the same bytes) -> "OK <written>"
//   PE           -> commit (a half-written drawing never plays)      -> "OK <n>"
//   PI           -> "P <n or 0> <startA> <startB> <max steps> <ms per step>"
//   G [loops]    -> ramp to the start pose and play (0 = until X); "OK <n>", "ERR noprog"; A/Q are refused meanwhile
// Boots with the servos released (arm untouched); the first move attaches them, ramping from HOME or, on the Uno,
// from the last resting pose saved in EEPROM (see PERSIST_POSE in config.h).
#include "config.h"
#if PERSIST_POSE
#include <EEPROM.h>
#endif

#if PROGRAM_STEPS > 0
bool progRunning = false;  // a stored drawing is playing
#define PROGRAM_RUNNING progRunning
#else
#define PROGRAM_RUNNING false
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
// Motion is a timed segment: both servos go from `from` to `tgt` over segDur ms, and the next segment starts on the very
// tick this one ends (the leftover time carries over), so a chain of waypoints is one continuous, synchronised move.
float from[2] = {HOME1, HOME2};
uint32_t segStart = 0, segDur = 0;
bool segActive = false;
uint32_t lastStep = 0;
uint16_t bootNumber = 0;
uint32_t idleLimitMs = 0;  // 0 = never release
uint32_t lastCommandMs = 0;
bool attached = false;

struct Waypoint {
  int16_t a, b;  // centi-degrees
  uint16_t ms;   // time to get there (0 = as fast as maxSpeed allows)
};
Waypoint queueBuf[QUEUE_SIZE];
uint16_t qHead = 0, qCount = 0;
uint16_t nextSeq = 0;         // sequence number the next Q must carry
uint16_t executed = 0;        // waypoints reached (wraps at 65536)
bool arrivalPending = false;  // the current target came from the queue and has not been reached yet
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
  if (attached && idleLimitMs && !ackPending && qCount == 0 && !arrivalPending && !PROGRAM_RUNNING &&
      millis() - lastCommandMs > idleLimitMs) {
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

// Start moving to (a, b) at `startAt` (a millis() stamp). The time is the requested ms, but never so short that a servo
// would exceed maxSpeed.
void beginSegment(float a, float b, uint16_t ms, uint32_t startAt) {
  from[0] = cur[0];
  from[1] = cur[1];
  tgt[0] = a;
  tgt[1] = b;
  float d = fmaxf(fabsf(a - cur[0]), fabsf(b - cur[1]));
  uint32_t floorMs = (uint32_t)ceilf(d / maxSpeed * 1000.0f);
  segDur = ms > floorMs ? ms : floorMs;
  segStart = startAt;
  segActive = true;
}

#if PROGRAM_STEPS > 0
// A drawing kept in EEPROM that the board plays on its own: the host stores it once (PB/PD/PE), starts it (G) and may
// disconnect. Header at PROG_ADDR: magic, step count, start pose (0.1 degree), ms per step; then one int8 delta pair per step.
constexpr uint16_t PROG_MAGIC = 0x50C2;
constexpr int PROG_ADDR = 32;
constexpr int PROG_STEPS_ADDR = PROG_ADDR + 10;
bool progForever = false;
uint16_t progLoopsLeft = 0;
uint16_t progIdx = 0, progCount = 0;
int16_t progStartA = 0, progStartB = 0, progA = 0, progB = 0;
uint16_t progMs = 0;
bool progWriting = false;
uint16_t progDeclared = 0, progWritten = 0;

bool progLoad() {
  uint16_t magic;
  EEPROM.get(PROG_ADDR, magic);
  EEPROM.get(PROG_ADDR + 2, progCount);
  EEPROM.get(PROG_ADDR + 4, progStartA);
  EEPROM.get(PROG_ADDR + 6, progStartB);
  EEPROM.get(PROG_ADDR + 8, progMs);
  return magic == PROG_MAGIC && progCount > 0 && progCount <= PROGRAM_STEPS && progStartA >= 0 && progStartA <= 1800 &&
         progStartB >= 0 && progStartB <= 1800;
}

void progRestart(uint32_t startAt) {  // ramps (at maxSpeed) to the start pose; the steps follow
  progIdx = 0;
  progA = progStartA;
  progB = progStartB;
  beginSegment(progA / 10.0f, progB / 10.0f, 0, startAt);
}

// Starts the next step of the stored drawing; false once it has played all its loops.
bool advanceProgram(uint32_t startAt) {
  if (progIdx >= progCount) {
    if (progForever || progLoopsLeft > 1) {
      if (!progForever) progLoopsLeft--;
      progRestart(startAt);
      return true;
    }
    progRunning = false;
    return false;
  }
  int addr = PROG_STEPS_ADDR + 2 * progIdx;
  progA = constrain(progA + (int8_t)EEPROM.read(addr), 0, 1800);
  progB = constrain(progB + (int8_t)EEPROM.read(addr + 1), 0, 1800);
  progIdx++;
  beginSegment(progA / 10.0f, progB / 10.0f, progMs, startAt);
  return true;
}

// Parses the next signed integer of `s` starting at `pos` (spaces skipped); false when there is none.
bool nextInt(const String& s, int& pos, long& out) {
  while (pos < (int)s.length() && s[pos] == ' ') pos++;
  if (pos >= (int)s.length()) return false;
  int end = s.indexOf(' ', pos);
  if (end < 0) end = s.length();
  out = s.substring(pos, end).toInt();
  pos = end;
  return true;
}
#endif

// The segment that just ended was reached: report it, then start whatever comes next at the same instant.
bool startNext(uint32_t startAt) {
  if (arrivalPending) {
    arrivalPending = false;
    executed++;
  }
  if (ackPending) {
    Serial.println("OK");
    ackPending = false;
    return false;
  }
#if PROGRAM_STEPS > 0
  if (progRunning) return advanceProgram(startAt);
#endif
  if (qCount > 0) {
    Waypoint w = queueBuf[qHead];
    qHead = (qHead + 1) % QUEUE_SIZE;
    qCount--;
    beginSegment(w.a / 100.0f, w.b / 100.0f, w.ms, startAt);
    arrivalPending = true;
    return true;
  }
  return false;
}

void stepMotion() {
  uint32_t now = millis();
  if (now - lastStep < STEP_MS) return;
  lastStep = now;
  if (!segActive) {  // idle: a waypoint may have arrived since the last tick
    segActive = startNext(now);
    if (!segActive) {
      moving = false;
      return;
    }
  }
  // Chain finished segments without a pause. The cap only matters if the loop was stalled for a long time.
  for (uint8_t guard = 0; segActive && now - segStart >= segDur; guard++) {
    cur[0] = tgt[0];
    cur[1] = tgt[1];
    uint32_t endAt = segStart + segDur;
    segActive = startNext(guard < 8 ? endAt : now);
#if PERSIST_POSE
    if (!segActive) {
      poseDirty = true;
      arrivedAt = now;
    }
#endif
  }
  if (segActive) {
    float f = (float)(now - segStart) / (float)segDur;
    cur[0] = from[0] + (tgt[0] - from[0]) * f;
    cur[1] = from[1] + (tgt[1] - from[1]) * f;
  }
  moving = segActive;
  writeServos();
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
  } else if (cmd.startsWith("Q ")) {
    // Q <seq> <a> <b> [ms]; AVR's sscanf has no float support, so split by hand
    int s1 = cmd.indexOf(' ', 2);
    int s2 = s1 < 0 ? -1 : cmd.indexOf(' ', s1 + 1);
    if (s1 < 0 || s2 < 0) { Serial.println("ERR queue"); return; }
    int s3 = cmd.indexOf(' ', s2 + 1);
    uint16_t seq = (uint16_t)cmd.substring(2, s1).toInt();
    float a = cmd.substring(s1 + 1, s2).toFloat();
    float b = cmd.substring(s2 + 1, s3 < 0 ? cmd.length() : s3).toFloat();
    long ms = s3 < 0 ? 0 : cmd.substring(s3 + 1).toInt();
    if (a < 0 || a > 180 || b < 0 || b > 180 || ms < 0 || ms > 60000) { Serial.println("ERR angles"); return; }
    if (PROGRAM_RUNNING) { Serial.println("ERR busy"); return; }
    if (seq == (uint16_t)(nextSeq - 1)) {  // the reply to this one was lost and the host resent it
      Serial.print("OK ");
      Serial.println(QUEUE_SIZE - qCount);
      return;
    }
    if (seq != nextSeq) {
      Serial.print("ERR seq ");
      Serial.println(nextSeq);
      return;
    }
    if (qCount >= QUEUE_SIZE) { Serial.println("FULL"); return; }
    if (!attached) {
      writeServos();
      attachServos();
    }
    queueBuf[(qHead + qCount) % QUEUE_SIZE] =
        Waypoint{(int16_t)lroundf(a * 100.0f), (int16_t)lroundf(b * 100.0f), (uint16_t)ms};
    qCount++;
    nextSeq++;
    Serial.print("OK ");
    Serial.println(QUEUE_SIZE - qCount);
  } else if (cmd == "S") {
    Serial.print("S ");
    Serial.print(nextSeq);
    Serial.print(' ');
    Serial.print(executed);
    Serial.print(' ');
    Serial.print(qCount);
    Serial.print(' ');
    Serial.print(QUEUE_SIZE - qCount);
    Serial.print(' ');
    Serial.println(moving || arrivalPending ? 1 : 0);
  } else if (cmd == "X") {
#if PROGRAM_STEPS > 0
    progRunning = false;
#endif
    qCount = 0;
    arrivalPending = false;
    ackPending = false;
    segActive = false;  // hold the pose it is in
    tgt[0] = cur[0];
    tgt[1] = cur[1];
#if PERSIST_POSE
    poseDirty = true;  // the arm rests here now: a reset must not forget it (the host resumes a drawing from this pose)
    arrivedAt = millis();
#endif
    Serial.print("OK ");
    Serial.println(nextSeq);
#if PROGRAM_STEPS > 0
  } else if (cmd.startsWith("PB ")) {  // PB <startA> <startB> <count>: begin storing a drawing (0.1 degree units)
    if (progRunning) { Serial.println("ERR busy"); return; }
    int pos = 3;
    long a, b, n, ms = 0;
    if (!nextInt(cmd, pos, a) || !nextInt(cmd, pos, b) || !nextInt(cmd, pos, n) || a < 0 || a > 1800 || b < 0 || b > 1800 ||
        n < 1) {
      Serial.println("ERR prog");
      return;
    }
    nextInt(cmd, pos, ms);
    if (ms < 0 || ms > 60000) { Serial.println("ERR prog"); return; }
    if (n > PROGRAM_STEPS) { Serial.print("ERR size "); Serial.println(PROGRAM_STEPS); return; }
    EEPROM.put(PROG_ADDR, (uint16_t)0);  // invalid until PE: a half-written drawing never plays
    EEPROM.put(PROG_ADDR + 2, (uint16_t)n);
    EEPROM.put(PROG_ADDR + 4, (int16_t)a);
    EEPROM.put(PROG_ADDR + 6, (int16_t)b);
    EEPROM.put(PROG_ADDR + 8, (uint16_t)ms);
    progWriting = true;
    progDeclared = (uint16_t)n;
    progWritten = 0;
    Serial.print("OK ");
    Serial.println(PROGRAM_STEPS);
  } else if (cmd.startsWith("PD ")) {  // PD <idx> <dA> <dB> [<dA> <dB> ...]: idx <= written so far (a resend rewrites the same bytes)
    int pos = 3;
    long idx, d;
    if (!progWriting || !nextInt(cmd, pos, idx) || idx < 0) { Serial.println("ERR prog"); return; }
    if (idx > progWritten) { Serial.print("ERR idx "); Serial.println(progWritten); return; }
    uint16_t i = (uint16_t)idx;
    while (nextInt(cmd, pos, d)) {
      long e;
      if (!nextInt(cmd, pos, e) || d < -127 || d > 127 || e < -127 || e > 127 || i >= progDeclared) {
        Serial.println("ERR prog");
        return;
      }
      EEPROM.update(PROG_STEPS_ADDR + 2 * i, (uint8_t)(int8_t)d);
      EEPROM.update(PROG_STEPS_ADDR + 2 * i + 1, (uint8_t)(int8_t)e);
      i++;
    }
    if (i > progWritten) progWritten = i;
    Serial.print("OK ");
    Serial.println(progWritten);
  } else if (cmd == "PE") {
    if (!progWriting && progLoad()) {  // the reply to this one was lost and the host resent it
      Serial.print("OK ");
      Serial.println(progCount);
      return;
    }
    if (!progWriting || progWritten != progDeclared) {
      Serial.print("ERR incomplete ");
      Serial.println(progWritten);
      return;
    }
    EEPROM.put(PROG_ADDR, PROG_MAGIC);
    progWriting = false;
    Serial.print("OK ");
    Serial.println(progDeclared);
  } else if (cmd == "PI") {  // P <steps or 0> <startA> <startB> <max>
    bool ok = progLoad();
    Serial.print("P ");
    Serial.print(ok ? progCount : 0);
    Serial.print(' ');
    Serial.print(ok ? progStartA : 0);
    Serial.print(' ');
    Serial.print(ok ? progStartB : 0);
    Serial.print(' ');
    Serial.print(PROGRAM_STEPS);
    Serial.print(' ');
    Serial.println(ok ? progMs : 0);
  } else if (cmd.startsWith("G")) {  // G [loops]: play the stored drawing on the board's own (0 = until X)
    if (qCount > 0 || arrivalPending || progRunning || progWriting) { Serial.println("ERR busy"); return; }
    if (!progLoad()) { Serial.println("ERR noprog"); return; }
    long loops = 1;
    int pos = 1;
    nextInt(cmd, pos, loops);
    if (loops < 0 || loops > 60000) { Serial.println("ERR loops"); return; }
    if (!attached) {
      writeServos();
      attachServos();
    }
    progForever = loops == 0;
    progLoopsLeft = (uint16_t)loops;
    progRunning = true;
    ackPending = false;
    progRestart(millis());
    Serial.print("OK ");
    Serial.println(progCount);
#endif
  } else if (cmd.startsWith("A ")) {
    if (qCount > 0 || arrivalPending || PROGRAM_RUNNING) { Serial.println("ERR busy"); return; }
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
    beginSegment(a, b, 0, millis());
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
  // Boot with the servos released: no pulse is sent until the first move command, so a reset (every port open)
  // never moves the arm. The saved pose is only the estimate the first move ramps from.
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
