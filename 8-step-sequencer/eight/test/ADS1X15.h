// Stand-in for RobTillaart's ADS1X15 library: a conversion of input n returns
// knob[n], ready at once.
#pragma once
#include <cstdint>

const int ADS1X15_MODE_SINGLE = 1;

class ADS1115 {
public:
  explicit ADS1115(int) {}
  bool begin() { return true; }
  void setMode(int) {}
  void requestADC(int channel) { requested = channel; }
  bool isReady() { return true; }
  int16_t getValue() { return knob[requested]; }
  int16_t readADC(int channel) { return knob[channel]; }
  int requested = 0;
  int16_t knob[4] = {0, 0, 0, 0};
};
