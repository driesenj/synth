// Copyright 2016 Emilie Gillet.
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
// Utility DSP routines.
//
// Plaitsy port: only kCorrectedSampleRate differs from Plaits 1.2.

#ifndef PLAITS_DSP_DSP_H_
#define PLAITS_DSP_DSP_H_

#include "stmlib/stmlib.h"

namespace plaits {

static const float kSampleRate = 48000.0f;

// Plaits tunes its oscillators to the rate its DAC really runs at: 47872.34 Hz
// on the STM32F373, whose I2S clock comes from a divider on the system clock.
//
// On the Seed, libDaisy clocks SAI1 from PLL3P, 16 MHz / 6 * 295 / 16 =
// 49.1667 MHz, and the HAL rounds the master clock divider for 48 kHz to 4:
// MCLK = 12.2917 MHz, frame clock = MCLK / 256 = 48014.32 Hz. Keeping Plaits'
// figure would leave every model 5 cents sharp.
static const float kCorrectedSampleRate = 48014.32f;
const float a0 = (440.0f / 8.0f) / kCorrectedSampleRate;

const size_t kMaxBlockSize = 24;
const size_t kBlockSize = 12;

}  // namespace plaits

#endif  // PLAITS_DSP_DSP_H_
