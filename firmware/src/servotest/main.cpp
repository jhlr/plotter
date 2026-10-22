// Servo movement test (ESP32 or Uno, see config.h). Open the serial monitor (115200) and type:
//   1 <0-180>   move servo 1        2 <0-180>   move servo 2
//   c           center both (90)    s           slow sweep of both, then back to 90
//   r           print both pots (raw ADC)
#include "../config.h"

Servo servo[2];
int angle[2] = {90, 90};
String line;

void setAngle(int i, int a) {
  angle[i] = constrain(a, 0, 180);
  servo[i].write(angle[i]);
  Serial.print("servo ");
  Serial.print(i + 1);
  Serial.print(" -> ");
  Serial.print(angle[i]);
  Serial.println(" deg");
}

void sweep() {
  for (int a = 90; a <= 150; a++) { servo[0].write(a); servo[1].write(a); delay(15); }
  for (int a = 150; a >= 30; a--) { servo[0].write(a); servo[1].write(a); delay(15); }
  for (int a = 30; a <= 90; a++) { servo[0].write(a); servo[1].write(a); delay(15); }
  angle[0] = angle[1] = 90;
  Serial.println("sweep done");
}

void handle(const String& cmd) {
  int n, a;
  if (sscanf(cmd.c_str(), "%d %d", &n, &a) == 2 && (n == 1 || n == 2)) setAngle(n - 1, a);
  else if (cmd == "c") { setAngle(0, 90); setAngle(1, 90); }
  else if (cmd == "s") sweep();
  else if (cmd == "r") {
    Serial.print("pots: ");
    Serial.print(analogRead(PIN_POT1));
    Serial.print(' ');
    Serial.println(analogRead(PIN_POT2));
  }
  else Serial.println("commands: '1 90', '2 90', c, s, r");
}

void setup() {
  Serial.begin(115200);
  boardInit();
  servo[0].attach(PIN_SERVO1, PULSE_MIN_US, PULSE_MAX_US);
  servo[1].attach(PIN_SERVO2, PULSE_MIN_US, PULSE_MAX_US);
  servo[0].write(90);
  servo[1].write(90);
  Serial.println("servo test ready: both at 90 deg");
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
}
