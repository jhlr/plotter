#pragma once
// Board abstraction: pins, servo library and ADC range for each supported controller.
// Select with the PlatformIO env (esp32 / uno / servotest / servotest_uno); nothing else is board-specific.
#include <Arduino.h>

#if defined(ARDUINO_ARCH_ESP32)
#include <ESP32Servo.h>
constexpr int PIN_SERVO1 = 18;
constexpr int PIN_SERVO2 = 19;
constexpr int PIN_POT1 = 34;  // ADC1, input only
constexpr int PIN_POT2 = 35;
constexpr int ADC_MAX = 4095;  // 12-bit
#define PERSIST_POSE 0
#elif defined(ARDUINO_ARCH_AVR)  // Arduino Uno
#include <Servo.h>
constexpr int PIN_SERVO1 = 9;  // Servo lib takes over Timer1: PWM on 9/10 is unavailable (fine for servos)
constexpr int PIN_SERVO2 = 10;
constexpr int PIN_POT1 = A0;
constexpr int PIN_POT2 = A1;
constexpr int ADC_MAX = 1023;  // 10-bit
// Every port open auto-resets the Uno (the Windows CH340 driver pulses DTR even when told not to). Keep the last
// pose in EEPROM and boot there, instead of snapping to HOME and dragging the pen across the page.
#define PERSIST_POSE 1
#else
#error "Unsupported board: add its pins to src/config.h"
#endif

// 115200 dropped ~40% of reply lines on a CH340 Uno clone (Windows driver 3.9); 57600 had 0 errors in 400.
#ifndef PENARM_BAUD  // override with -DPENARM_BAUD=... (build_flags); the server's SerialLink must match
#define PENARM_BAUD 57600
#endif

constexpr int PULSE_MIN_US = 500;
constexpr int PULSE_MAX_US = 2400;

inline void boardInit() {
#if defined(ARDUINO_ARCH_ESP32)
  analogReadResolution(12);
#endif
}
