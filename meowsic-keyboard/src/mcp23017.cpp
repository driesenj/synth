#include <Arduino.h>
#include <Wire.h>

#include "config.h"
#include "mcp23017.h"

namespace mcp {

bool writeReg(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(MCP_ADDR);
    Wire.write(reg);
    Wire.write(val);
    return Wire.endTransmission() == 0;
}

bool readReg(uint8_t reg, uint8_t &val) {
    Wire.beginTransmission(MCP_ADDR);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;   // repeated start
    if (Wire.requestFrom((int)MCP_ADDR, (int)1) != 1) return false;
    val = Wire.read();
    return true;
}

bool configure() {
    // If the chip somehow came up with BANK = 1, address 0x05 is IOCON there
    // and this write puts it back into BANK = 0. In BANK = 0 the same write
    // lands on GPINTENB, i.e. "port B interrupts off", which is what we want
    // anyway. Cheap insurance against a half-reset chip.
    bool ok = writeReg(0x05, 0x00);

    ok &= writeReg(REG_IOCON,    0x00);  // BANK=0, sequential, no mirror
    ok &= writeReg(REG_GPINTENA, 0x00);  // no interrupt-on-change
    ok &= writeReg(REG_GPINTENB, 0x00);

    // Open-drain emulation. The latch must be written before the direction
    // register, otherwise the first column assertion drives whatever was in it.
    // Which physical port this lands on is set by COLS_ON_PORT_A in config.h.
    ok &= writeReg(REG_COL_OLAT,  0x00); // asserted column outputs a 0
    ok &= writeReg(REG_COL_IODIR, 0xFF); // all columns Hi-Z for now
    ok &= writeReg(REG_COL_GPPU,  0x00); // no pull-ups on the strobes

    ok &= writeReg(REG_ROW_IODIR, 0xFF); // returns are inputs
    ok &= writeReg(REG_ROW_GPPU,  0xFF); // 100k internal pull-ups. Do not add
                                         // external 10k - it eats the contact
                                         // resistance margin (section 9.1)
    ok &= writeReg(REG_ROW_IPOL,  0xFF); // a closed contact now reads as 1

    return ok;
}

bool begin() {
    Wire.begin(PIN_SDA, PIN_SCL, I2C_HZ);
    Wire.setTimeOut(20);                 // ms, so a stuck bus cannot hang the scan

    Wire.beginTransmission(MCP_ADDR);
    if (Wire.endTransmission() != 0) return false;

    return configure();
}

}  // namespace mcp
