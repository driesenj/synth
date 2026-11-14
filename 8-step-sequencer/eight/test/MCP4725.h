// Stand-in for RobTillaart's MCP4725 library: keeps the last voltage written.
#pragma once

class MCP4725 {
public:
  explicit MCP4725(int address) : address(address) {}
  bool begin() { return true; }
  void setMaxVoltage(float v) { maxVoltage = v; }
  int setVoltage(float v) { volts = v < 0 ? 0 : v > maxVoltage ? maxVoltage : v; return 0; }
  int address;
  float maxVoltage = 5.0;
  float volts = 0;
};
