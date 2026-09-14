#pragma once
#include <stdint.h>

#include "config.h"

// Register addresses, BANK = 0 (power-on default).
enum : uint8_t {
    REG_IODIRA   = 0x00,
    REG_IODIRB   = 0x01,
    REG_IPOLA    = 0x02,
    REG_IPOLB    = 0x03,
    REG_GPINTENA = 0x04,
    REG_GPINTENB = 0x05,
    REG_IOCON    = 0x0A,
    REG_GPPUA    = 0x0C,
    REG_GPPUB    = 0x0D,
    REG_GPIOA    = 0x12,
    REG_GPIOB    = 0x13,
    REG_OLATA    = 0x14,
    REG_OLATB    = 0x15,
};

// ---------------------------------------------------------------------------
//  Role aliases, selected by COLS_ON_PORT_A.
//
//  Everything above the driver addresses the ports by what they are wired to
//  rather than by name, so flipping that one flag in config.h moves the whole
//  scanner. Nothing else in the firmware refers to a lettered register.
//
//  ROW_OLAT is the output latch of the port used for returns. Those pins are
//  inputs, so it drives nothing and is free for the self test to scribble on.
// ---------------------------------------------------------------------------
#if COLS_ON_PORT_A
static constexpr uint8_t REG_COL_IODIR = REG_IODIRA;
static constexpr uint8_t REG_COL_OLAT  = REG_OLATA;
static constexpr uint8_t REG_COL_GPPU  = REG_GPPUA;
static constexpr uint8_t REG_ROW_IODIR = REG_IODIRB;
static constexpr uint8_t REG_ROW_GPPU  = REG_GPPUB;
static constexpr uint8_t REG_ROW_IPOL  = REG_IPOLB;
static constexpr uint8_t REG_ROW_GPIO  = REG_GPIOB;
static constexpr uint8_t REG_ROW_OLAT  = REG_OLATB;
#define COL_PORT_NAME "A"
#define ROW_PORT_NAME "B"
#else
static constexpr uint8_t REG_COL_IODIR = REG_IODIRB;
static constexpr uint8_t REG_COL_OLAT  = REG_OLATB;
static constexpr uint8_t REG_COL_GPPU  = REG_GPPUB;
static constexpr uint8_t REG_ROW_IODIR = REG_IODIRA;
static constexpr uint8_t REG_ROW_GPPU  = REG_GPPUA;
static constexpr uint8_t REG_ROW_IPOL  = REG_IPOLA;
static constexpr uint8_t REG_ROW_GPIO  = REG_GPIOA;
static constexpr uint8_t REG_ROW_OLAT  = REG_OLATA;
#define COL_PORT_NAME "B"
#define ROW_PORT_NAME "A"
#endif

// A typo in either branch above would put both roles on one port, which reads
// as a dead keybed rather than as a build error. Catch it at compile time.
static_assert(REG_COL_IODIR != REG_ROW_IODIR, "port roles collide on IODIR");
static_assert(REG_COL_OLAT != REG_ROW_OLAT, "port roles collide on OLAT");
static_assert(REG_COL_GPPU != REG_ROW_GPPU, "port roles collide on GPPU");
#if COLS_ON_PORT_A
static_assert(REG_COL_IODIR == REG_IODIRA, "strobes should be on port A");
static_assert(REG_ROW_GPIO == REG_GPIOB, "returns should be on port B");
#else
static_assert(REG_COL_IODIR == REG_IODIRB, "strobes should be on port B");
static_assert(REG_ROW_GPIO == REG_GPIOA, "returns should be on port A");
#endif

namespace mcp {

// Brings up I2C and applies the open-drain-emulation register setup from
// design doc section 9.1. Returns false if the chip does not ACK.
bool begin();

// Re-applies the register setup only (I2C already running).
bool configure();

bool writeReg(uint8_t reg, uint8_t val);
bool readReg(uint8_t reg, uint8_t &val);

}  // namespace mcp
