// Copyright 2026 the Marblesy authors. MIT licence, see marbles/firmware/LICENSE.
//
// Marblesy: the two MCP4922s (see dac.h).

#include "marbles/drivers/dac.h"

#include "hal.h"

namespace marbles {

namespace {

// Marbles' DAC channel -> MCP4922 (circuit.py): Y on U8 DAC B, X1 on U7 DAC
// A, X2 on U7 DAC B, X3 on U8 DAC A.
const size_t kSlot[kNumDacChannels] = { 3, 0, 1, 2 };

// MCP4922 command bits: DAC B, buffered VREF input, gain 1, active.
const uint16_t kDacB = 0x8000;
const uint16_t kBuffered = 0x4000;
const uint16_t kGain1 = 0x2000;
const uint16_t kActive = 0x1000;

}  // namespace

void Dac::Init() {
  marblesy::hal::InitBus();
}

/* static */
size_t Dac::Slot(size_t channel) {
  return kSlot[channel];
}

/* static */
uint16_t Dac::Word(size_t channel, uint16_t code) {
  // The VREF input is buffered: unbuffered, the four DAC strings would take
  // about 60 uA of the LM4040's feed (see README).
  uint32_t code_12 = (static_cast<uint32_t>(code) + 8) >> 4;
  if (code_12 > 4095) {
    code_12 = 4095;
  }
  const uint16_t select = (kSlot[channel] & 1) ? kDacB : 0;
  return select | kBuffered | kGain1 | kActive | code_12;
}

void Dac::Write(const uint16_t* codes) {
  uint16_t words[kNumDacChannels];
  for (size_t i = 0; i < kNumDacChannels; ++i) {
    words[kSlot[i]] = Word(i, codes[i]);
  }
  marblesy::hal::WriteDacs(words);
}

}  // namespace marbles
