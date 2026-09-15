#include <Arduino.h>
#include <Wire.h>

#include "mcp4725.h"

// Command formats, from the datasheet:
//
//   fast mode      [0 0 PD1 PD0 D11..D8] [D7..D0]                DAC register only
//   write DAC      [0 1 0 x PD1 PD0 x x] [D11..D4] [D3..D0 x x x x]
//   write DAC+EE   [0 1 1 x PD1 PD0 x x] [D11..D4] [D3..D0 x x x x]
//   read (5 bytes) [RDY POR x x x PD1 PD0 x] [D11..D4] [D3..D0 xxxx]
//                  [x PD1 PD0 x D11..D8 (EEPROM)] [D7..D0 (EEPROM)]

namespace dac {

bool write(uint8_t addr, uint16_t code) {
    code &= 0x0FFF;
    Wire.beginTransmission(addr);
    Wire.write((uint8_t)(code >> 8));    // PD = 00 lands in bits 5:4 as zeros
    Wire.write((uint8_t)(code & 0xFF));
    return Wire.endTransmission() == 0;
}

bool read(uint8_t addr, State &s) {
    if (Wire.requestFrom((int)addr, (int)5) != 5) return false;

    uint8_t b[5];
    for (uint8_t i = 0; i < 5; ++i) b[i] = Wire.read();

    s.ready      = b[0] & 0x80;
    s.pd         = (b[0] >> 1) & 0x03;
    s.code       = ((uint16_t)b[1] << 4) | (b[2] >> 4);
    s.eepromPd   = (b[3] >> 5) & 0x03;
    s.eepromCode = ((uint16_t)(b[3] & 0x0F) << 8) | b[4];
    return true;
}

bool writeEeprom(uint8_t addr, uint16_t code) {
    code &= 0x0FFF;
    Wire.beginTransmission(addr);
    Wire.write(0x60);                              // C2:C0 = 011, PD = 00
    Wire.write((uint8_t)(code >> 4));              // D11..D4
    Wire.write((uint8_t)((code & 0x0F) << 4));     // D3..D0
    if (Wire.endTransmission() != 0) return false;

    // The part NACKs nothing while it programs; RDY in the status byte is the
    // only completion signal. 50 ms is the datasheet maximum.
    for (uint8_t i = 0; i < 20; ++i) {
        delay(5);
        State s;
        if (read(addr, s) && s.ready) return s.eepromCode == code && s.eepromPd == 0;
    }
    return false;
}

}  // namespace dac
