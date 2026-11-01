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
// Plaitsy port of plaits/drivers/leds.cc.

#include "plaits/drivers/leds.h"

#include <algorithm>

#include "hal.h"

namespace plaits {

using namespace std;
using namespace plaitsy;

namespace {

// Shift-register bit of each LED's red and green anode, LED 0 being D1 at the
// top. U9 (bits 0..7 = QA..QH) drives the reds, U10 (bits 8..15) the greens;
// the outputs were picked so no LED track crosses another (circuit.py,
// LED_LINES and SR_OUTS).
const uint8_t kRedBit[kNumLEDs] = { 0, 4, 6, 7, 5, 3, 2, 1 };
const uint8_t kGreenBit[kNumLEDs] = { 12, 10, 9, 8, 11, 13, 14, 15 };

}  // namespace

void Leds::Init() {
  hal::InitLeds();
  button_a_ = button_b_ = false;
  Clear();
}

void Leds::Clear() {
  fill(&colors_[0], &colors_[kNumLEDs], LED_COLOR_OFF);
}

void Leds::Write() {
  uint16_t bits = 0;
  for (int i = 0; i < kNumLEDs; ++i) {
    if (colors_[i] & LED_COLOR_RED) {
      bits |= 1 << kRedBit[i];
    }
    if (colors_[i] & LED_COLOR_GREEN) {
      bits |= 1 << kGreenBit[i];
    }
  }
  hal::SetLedShiftRegisters(bits);
  hal::WriteButtonLeds(button_a_, button_b_);
}

}  // namespace plaits
