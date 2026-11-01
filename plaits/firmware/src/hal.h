// Copyright 2026 the Plaitsy authors. MIT licence, see plaits/firmware/LICENSE.
//
// Plaitsy: the few things the Plaits drivers and the settings store need from
// the board. hal_daisy.cc implements them on the Daisy Seed with libDaisy;
// the host tests implement them with a model of the board (test/hal_fake.cc).
//
// Pins and channel orders follow plaits/hardware/tools/circuit.py and the
// "Daisy Seed pin map" in plaits/docs/design.md.

#ifndef PLAITSY_HAL_H_
#define PLAITSY_HAL_H_

#include <stddef.h>
#include <stdint.h>

namespace daisy {
class DaisySeed;
}

namespace plaitsy {
namespace hal {

// Called once, after DaisySeed::Init(): the flash store uses its QSPI handle.
void Init(daisy::DaisySeed* seed);

// Main loop: shifts the latest LED frame out to the 74HC595s.
void Service();

// Milliseconds since power-up. Readable from the audio callback too.
uint32_t Milliseconds();

// The independent watchdog, as on Plaits: started once the audio runs and
// fed by every audio callback, so a stalled callback restarts the module.
void StartWatchdog();
void FeedWatchdog();

// CV inputs, in the order of the Seed's ADC sequence.
enum AdcInput {
  ADC_MODEL,      // A0
  ADC_TIMBRE,     // A1
  ADC_FM,         // A2
  ADC_MORPH,      // A3
  ADC_HARMONICS,  // A4
  ADC_TRIGGER,    // A5
  ADC_LEVEL,      // A6
  ADC_V_OCT,      // A9
  ADC_INPUT_LAST
};

// The 74HC4051 on A10 (address on D26, D27, D28). Y7 is grounded, so only
// Y0..Y6 are scanned.
const int kNumMuxChannels = 7;

void InitAdc();  // Starts the ADC; later calls do nothing.
uint16_t ReadAdc(AdcInput input);    // 16-bit, 0 V .. 3V3A
uint16_t ReadMux(int channel);       // 16-bit, mux channel 0..6

enum Button {
  BUTTON_A,  // SW1, left (D0)
  BUTTON_B,  // SW2, right (D1)
};

void InitButtons();
bool ButtonPressed(Button button);  // raw pin, no debouncing

void InitProbe();
void WriteProbe(bool high);  // D14, into the TIMBRE, FM, MORPH, TRIG, LEVEL lugs

void InitLeds();  // Later calls do nothing.
// Bit n drives output n of the 74HC595 chain: 0..7 = U9 QA..QH (the reds),
// 8..15 = U10 QA..QH (the greens). Safe to call from the audio callback; the
// frame goes out in Service().
void SetLedShiftRegisters(uint16_t bits);
void WriteButtonLeds(bool a, bool b);  // the LEDs in SW1 / SW2 (D2 / D3)

// The Seed's QSPI flash. Offsets from the start of the chip; erasing works on
// whole 4 kB sectors, at most one per call (libDaisy's 64 kB block erase
// does not return the chip to memory-mapped mode). Not for use from the
// audio callback.
const uint32_t kFlashSectorSize = 0x1000;
void FlashRead(uint32_t offset, void* destination, uint32_t size);
bool FlashErase(uint32_t offset, uint32_t size);
bool FlashWrite(uint32_t offset, const void* data, uint32_t size);

// Masks interrupts, so the main loop can copy state the audio callback writes.
uint32_t EnterCritical();
void ExitCritical(uint32_t state);

}  // namespace hal
}  // namespace plaitsy

#endif  // PLAITSY_HAL_H_
