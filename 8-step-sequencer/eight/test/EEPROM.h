// Stand-in for the AVR EEPROM library: 4 kB, erased (0xFF), counting writes.
#pragma once
#include <cstdint>
#include <cstring>

struct FakeEEPROM {
  FakeEEPROM() { std::memset(mem, 0xFF, sizeof mem); }
  uint8_t read(int address) { return mem[address]; }
  void update(int address, uint8_t value) {
    if (mem[address] != value) {
      mem[address] = value;
      writes++;
    }
  }
  uint8_t mem[4096];
  int writes = 0;
};
extern FakeEEPROM EEPROM;
