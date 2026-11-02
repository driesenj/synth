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
// Driver for all the LEDs.
//
// Marblesy port: see leds.h.

#include "marbles/drivers/leds.h"

#include <algorithm>

#include "hal.h"

namespace marbles {

using namespace std;

struct LedDefinition {
  int8_t red;    // 74HC595 chain output for the red line, -1 for none
  int8_t green;  // ... and for the green line
};

// circuit.py: bit n is output n of the chain, U9 QA..QH then U10 QA..QH. A
// red/green button lights red with its red line high and its green line
// low, green the other way round.
const LedDefinition led_definition[] = {
  { -1, 0 },  // LED_T_DEJA_VU, D1 on U9 QA
  { 1, 2 },   // LED_T_MODEL, D2 on U9 QB (R), QC (G)
  { 3, 4 },   // LED_T_RANGE, D3 on U9 QD (R), QE (G)
  { -1, 5 },  // LED_X_DEJA_VU, D4 on U9 QF
  { 6, 7 },   // LED_X_CONTROL_MODE, D5 on U9 QG (R), QH (G)
  { 8, 9 },   // LED_X_RANGE, D6 on U10 QA (R), QB (G)
  { -1, 15 }  // LED_X_EXT, D7 on U10 QH
};

// The output LEDs by DAC channel: Y (D14) on U10 QG, X1 (D15) on QF, X2
// (D16) on QE, X3 (D17) on QC.
const int8_t output_led_bit[kNumOutputLeds] = { 14, 13, 12, 10 };

namespace {

volatile uint32_t frame_colors[LED_LAST];
volatile uint8_t frame_output_levels[kNumOutputLeds];

}  // namespace

void Leds::Init() {
  marblesy::hal::InitBus();
  Clear();
  fill(&output_levels_[0], &output_levels_[kNumOutputLeds], 0);
  Write();
}

void Leds::Clear() {
  fill(&colors_[0], &colors_[LED_LAST], LED_COLOR_OFF);
}

void Leds::Write() {
  for (int i = 0; i < LED_LAST; ++i) {
    frame_colors[i] = colors_[i];
  }
  for (size_t i = 0; i < kNumOutputLeds; ++i) {
    frame_output_levels[i] = output_levels_[i];
  }
}

/* static */
uint16_t Leds::Bits(
    const uint32_t* colors,
    const uint8_t* output_levels,
    uint32_t phase) {
  uint32_t bits = 0;
  for (int i = 0; i < LED_LAST; ++i) {
    const LedDefinition& d = led_definition[i];
    const bool red = colors[i] & 0x800000;
    const bool green = colors[i] & 0x008000;
    if (d.red < 0) {
      if (green) {
        bits |= 1 << d.green;
      }
    } else if (red && green) {
      bits |= 1 << ((phase & 1) ? d.red : d.green);
    } else if (red) {
      bits |= 1 << d.red;
    } else if (green) {
      bits |= 1 << d.green;
    }
  }
  for (size_t i = 0; i < kNumOutputLeds; ++i) {
    if (output_levels[i] > (phase % kOutputLedLevels)) {
      bits |= 1 << output_led_bit[i];
    }
  }
  return bits;
}

/* static */
uint16_t Leds::ShiftRegisterBits(uint32_t phase) {
  uint32_t colors[LED_LAST];
  uint8_t output_levels[kNumOutputLeds];
  for (int i = 0; i < LED_LAST; ++i) {
    colors[i] = frame_colors[i];
  }
  for (size_t i = 0; i < kNumOutputLeds; ++i) {
    output_levels[i] = frame_output_levels[i];
  }
  return Bits(colors, output_levels, phase);
}

}  // namespace marbles
