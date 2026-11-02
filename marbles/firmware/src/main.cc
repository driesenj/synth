// Copyright 2026 the Marblesy authors. MIT licence, see marbles/firmware/LICENSE.
//
// Marblesy: Mutable Instruments Marbles on a Daisy Seed. The Seed's start-up,
// the bootloader gesture and the main loop; the rest is in marblesy.cc.

#include "daisy_seed.h"

#include "marbles/drivers/dac.h"
#include "marbles/drivers/leds.h"
#include "marbles/drivers/switches.h"

#include "hal.h"
#include "marblesy.h"

using namespace daisy;
using namespace marbles;

DaisySeed hw;

int main(void) {
  hw.Init(true);  // 480 MHz
  marblesy::hal::Init(&hw);

  // The gate stages float until their pins are outputs, the MCP4922s power
  // up shut down (+5.3 V here) and the 74HC595s with random outputs: gates
  // low, outputs to 0 V, LEDs off, first thing.
  marblesy::hal::InitGpio();
  marblesy::hal::InitBus();
  uint16_t codes[kNumDacChannels];
  for (size_t i = 0; i < kNumDacChannels; ++i) {
    codes[i] = static_cast<uint16_t>(kDacOffset);
  }
  Dac dac;
  dac.Write(codes);
  marblesy::hal::WriteLeds(0);

  // t deja vu held at power-up: on Marbles it starts the firmware update
  // (its bootloader); here the Seed restarts into the Daisy bootloader and
  // waits for an upload, so the Seed's own BOOT button behind the panel is
  // not needed. The red/green LEDs show red, green, red, green to confirm
  // it; the bus floats while the bootloader waits, so the pattern may
  // drift, which does not affect the upload.
  System::Delay(1);
  if (marblesy::BootloaderGesture()) {
    uint32_t colors[LED_LAST] = { 0 };
    colors[LED_T_MODEL] = LED_COLOR_RED;
    colors[LED_T_RANGE] = LED_COLOR_GREEN;
    colors[LED_X_CONTROL_MODE] = LED_COLOR_RED;
    colors[LED_X_RANGE] = LED_COLOR_GREEN;
    const uint8_t levels[kNumOutputLeds] = { 0 };
    marblesy::hal::WriteLeds(Leds::Bits(colors, levels, 0));
    marblesy::hal::ResetToBootloader();
  }

  marblesy::Init();
  marblesy::hal::StartInterrupts(&marblesy::IoTick, &marblesy::DspTick);
  marblesy::hal::StartWatchdog();

  while (true) {
    marblesy::Persist();
  }
}
