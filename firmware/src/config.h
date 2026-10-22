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
#elif defined(ARDUINO_ARCH_AVR)  // Arduino Uno
#include <Servo.h>
constexpr int PIN_SERVO1 = 9;  // Servo lib takes over Timer1: PWM on 9/10 is unavailable (fine for servos)
constexpr int PIN_SERVO2 = 10;
constexpr int PIN_POT1 = A0;
constexpr int PIN_POT2 = A1;
constexpr int ADC_MAX = 1023;  // 10-bit
#else
#error "Unsupported board: add its pins to src/config.h"
#endif

constexpr int PULSE_MIN_US = 500;
constexpr int PULSE_MAX_US = 2400;

inline void boardInit() {
#if defined(ARDUINO_ARCH_ESP32)
  analogReadResolution(12);
#endif
}
