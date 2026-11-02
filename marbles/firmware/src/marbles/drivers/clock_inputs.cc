// Copyright 2015 Emilie Gillet.
//
// Author: Emilie Gillet (emilie.o.gillet@gmail.com)
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
// 
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
// 
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.
// 
// See http://creativecommons.org/licenses/MIT/ for more information.
//
// -----------------------------------------------------------------------------
//
// Driver for the two clock inputs and their normalization probe.
//
// Marblesy port: the pins are read and the probe written through hal.h (D0,
// D1 and D15). As on Marbles, the input stages invert: a high clock pulls
// its pin low.

#include "marbles/drivers/clock_inputs.h"

#include "hal.h"

namespace marbles {

using namespace std;
using namespace stmlib;

void ClockInputs::Init() {
  marblesy::hal::InitGpio();
  for (int i = 0; i < CLOCK_INPUT_LAST; ++i) {
    previous_flags_[i] = 0;
    normalization_mismatch_count_[i] = 0;
    normalized_[i] = false;
  }

  normalization_probe_state_ = 0;
  normalization_decision_count_ = 0;
}

void ClockInputs::ReadNormalization(IOBuffer::Block* block) {
  ++normalization_decision_count_;
  if (normalization_decision_count_ >= kProbeSequenceDuration) {
    normalization_decision_count_ = 0;
    for (int i = 0; i < CLOCK_INPUT_LAST; ++i) {
      normalized_[i] = \
          normalization_mismatch_count_[i] < kProbeSequenceDuration / 8;
      normalization_mismatch_count_[i] = 0;
    }
  }
  
  int expected_value = normalization_probe_state_ >> 31;
  for (int i = 0; i < CLOCK_INPUT_LAST; ++i) {
    int read_value = previous_flags_[i] & GATE_FLAG_HIGH;
    normalization_mismatch_count_[i] += read_value ^ expected_value;
    block->input_patched[i] = !normalized_[i];
  }

  normalization_probe_state_ = 1103515245 * normalization_probe_state_ + 12345;
  marblesy::hal::WriteProbe(normalization_probe_state_ >> 31);
}

void ClockInputs::Read(const IOBuffer::Slice& slice, size_t size) {
  const uint32_t pins = marblesy::hal::ReadClockPins();
  for (int i = 0; i < CLOCK_INPUT_LAST; ++i) {
    previous_flags_[i] = ExtractGateFlags(
        previous_flags_[i],
        !(pins & (1 << i)));
    slice.block->input[i][slice.frame_index] = previous_flags_[i];
  }
  
  // Extend gate input data to the next samples.
  for (size_t j = 1; j < size; ++j) {
    for (int i = 0; i < CLOCK_INPUT_LAST; ++i) {
      slice.block->input[i][slice.frame_index + j] = \
          previous_flags_[i] & GATE_FLAG_HIGH;
    }
  }
}

}  // namespace marbles
