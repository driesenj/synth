// Copyright 2026 the Marblesy authors. MIT licence, see marbles/firmware/LICENSE.
//
// Marblesy host tests: a model of the board behind hal.h.
//
// The model works in jack voltages and knob positions. The CV inputs go
// through Marblesy's input stage (with optional part errors) to the 16-bit
// ADC readings the Seed would take; the MCP4922 words come back out as jack
// voltages through the output stage; the clock inputs see either a patched
// signal or, unpatched, the normalization probe through the switch lug; the
// 74HC595 and 74HC165 are bit images; the QSPI flash is a byte array with
// NOR semantics and an optional power cut after a given number of
// operations.

#ifndef MARBLESY_TEST_HAL_FAKE_H_
#define MARBLESY_TEST_HAL_FAKE_H_

#include <stdint.h>

#include "hal.h"

namespace fake {

// Part tolerances of one module, as fractions (0.01 = +1 %).
struct Parts {
  float cv_rin[marblesy::hal::CV_INPUT_LAST];
  float cv_rf[marblesy::hal::CV_INPUT_LAST];
  float cv_bias;       // the 1.32 V bias divider's ratio
  float vref;          // the LM4040
  float dac_rin[4];    // per output, by MCP4922 slot (U7 A, U7 B, U8 A, U8 B)
  float dac_rref[4];
  float dac_rf[4];
  float dac_gain[4];   // MCP4922 gain error
  float dac_offset[4]; // MCP4922 offset, volts at its output
  float dac_rout[4];   // the 1k after each output stage
  float inverter;      // R43 / R42's ratio, the -2.5 V all four outputs share
};

void Reset();  // everything back to power-up: no cables, knobs at noon
void Reboot();  // the same, but the flash keeps its contents
void SetParts(const Parts& parts);
void NominalParts();

// Inputs.
void SetCv(marblesy::hal::CvInput input, float volts);
void SetPot(marblesy::hal::Pot pot, float position);  // 0 = CCW .. 1 = CW
void SetAdcNoise(float lsb_rms);
// A cable from the output of MCP4922 slot `slot` (0..3: X1, X2, X3, Y) into
// CV input `input`; -1 unplugs it.
void PatchOutput(marblesy::hal::CvInput input, int slot);
// A cable in the clock input (0 = T, 1 = X); with one, `high` is its level.
void PatchClock(int input, bool patched);
void SetClock(int input, bool high);
// Buttons by 74HC165 input (D0..D6).
void SetButton(int input, bool pressed);
void ReleaseAllButtons();

// Outputs.
float OutputVolts(int slot);  // jack voltage of MCP4922 slot 0..3
float OutputVoltsFor(int slot, uint16_t word);  // ... for a command word
// ... at the jack, into a 1V/oct input: 100k to ground.
float LoadedOutputVoltsFor(int slot, uint16_t word);
// A 74HC165 that does not answer (reads 0x00).
void SetButtonsDead(bool dead);
// The next `operations` flash erases or writes fail, without a power cut.
void FailFlashOperations(int operations);
uint16_t DacWord(int slot);   // last command word sent to that slot
uint32_t DacWrites();         // WriteDacs() calls
uint32_t Gates();             // last WriteGates() argument
uint16_t LedBits();           // last WriteLeds() argument
uint32_t LedWrites();
uint32_t ButtonReads();
bool Probe();

// Interrupts and time: one Tick() is one I/O interrupt, then the DSP
// interrupt if it was pended. Milliseconds() follows the ticks.
void Tick();
void Run(uint32_t ticks);
void RunMilliseconds(uint32_t ms);
bool InterruptsStarted();
uint32_t DspRuns();
uint32_t WatchdogFeeds();
bool BootloaderRequested();
void AdvanceTime(uint32_t ms);  // main-loop time without ticks

// Flash.
uint8_t* Flash();
uint32_t FlashSize();
uint32_t FlashErases();
uint32_t FlashWrites();
// The flash stops after this many more erase or write calls (the one that
// trips is cut half way: an erase leaves its sector partly erased, a write
// writes half its bytes). -1 = never.
void CutPowerAfter(int operations);
bool PowerCut();

}  // namespace fake

#endif  // MARBLESY_TEST_HAL_FAKE_H_
