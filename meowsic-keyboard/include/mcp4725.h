#pragma once
#include <stdint.h>

// MCP4725 12-bit I2C DAC - one per CV channel, both on the I2C board
// (docs/pinout.md section 2). Register-level, like mcp23017.cpp: nothing here
// knows about volts or semitones. Wire must already be up.
namespace dac {

struct State {
    uint16_t code;        // DAC register, 0..4095
    uint8_t  pd;          // its power-down bits, 0 = normal, else output pulled to GND
    uint16_t eepromCode;  // what the output sits at from power-up
    uint8_t  eepromPd;
    bool     ready;       // no EEPROM write in progress
};

// Fast-mode write of the DAC register, normal power mode: two data bytes,
// ~70 us at 400 kHz. This is the call the firmware makes per note.
bool write(uint8_t addr, uint16_t code);

// Read everything back: 5 bytes.
bool read(uint8_t addr, State &s);

// Program DAC register and EEPROM together, normal power mode, and wait for
// the write to finish (25 ms typical, 50 max). Done once, so the output is a
// known 0 V from power-up rather than whatever the EEPROM held.
bool writeEeprom(uint8_t addr, uint16_t code);

}  // namespace dac
