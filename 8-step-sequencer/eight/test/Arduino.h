// Just enough of the Arduino core to run eight.ino on a PC (host_test.cpp).
// Time stands still until the test moves `fakeMillis`; pins are arrays the
// test reads and writes.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

typedef uint8_t byte;

const int HIGH = 1, LOW = 0;
const int INPUT = 0, OUTPUT = 1, INPUT_PULLUP = 2, RISING = 3;
const int A0 = 54, A1 = 55, A2 = 56, A3 = 57, A4 = 58, A5 = 59, A6 = 60, A7 = 61,
          A8 = 62, A9 = 63, A10 = 64, A11 = 65, A12 = 66, A13 = 67, A14 = 68, A15 = 69;
const int PINS = 70;

extern unsigned long fakeMillis;
extern int pinLevel[PINS];
extern int pinModes[PINS];
extern int analogLevel[PINS];
extern void (*isr[PINS])();

inline unsigned long millis() { return fakeMillis; }
inline unsigned long micros() { return fakeMillis * 1000; }
inline void pinMode(int pin, int mode) { pinModes[pin] = mode; if (mode == INPUT_PULLUP) pinLevel[pin] = HIGH; }
inline int digitalRead(int pin) { return pinLevel[pin]; }
inline void digitalWrite(int pin, int level) { pinLevel[pin] = level; }
inline int analogRead(int pin) { return analogLevel[pin]; }
inline int digitalPinToInterrupt(int pin) { return pin; }
inline void attachInterrupt(int n, void (*f)(), int) { isr[n] = f; }
inline void noInterrupts() {}
inline void interrupts() {}
inline long random(long n) { return std::rand() % n; }
inline void randomSeed(unsigned long seed) { std::srand(seed); }
using std::abs;
using std::min;
#define constrain(x, lo, hi) ((x) < (lo) ? (lo) : (x) > (hi) ? (hi) : (x))     // a macro, as in the core

struct FakeSerial {
  void begin(long) {}
  template <class T> void print(T) {}
  template <class T> void println(T) {}
};
extern FakeSerial Serial;

struct FakeWire {
  void begin() {}
};
extern FakeWire Wire;
