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
// Marblesy port: the seven LED buttons and four CV output LEDs hang off two
// chained 74HC595s, which the I/O interrupt reloads every 4 samples (8 kHz)
// with ShiftRegisterBits(). The red/green buttons hold an anti-parallel
// pair between two lines, so they cannot show both colours at once: yellow
// alternates red and green at every reload. The output LEDs (Marbles drives
// its own, bicolour ones from the analogue outputs) get 16 brightness levels
// by PWM over 16 reloads, 500 Hz.

#ifndef MARBLES_DRIVERS_LEDS_H_
#define MARBLES_DRIVERS_LEDS_H_

#include "stmlib/stmlib.h"

namespace marbles {
  
enum Led {
  LED_T_DEJA_VU,
  LED_T_MODEL,
  LED_T_RANGE,
  LED_X_DEJA_VU,
  LED_X_CONTROL_MODE,
  LED_X_RANGE,
  LED_X_EXT,
  LED_LAST
};

enum LedColor {
  LED_COLOR_OFF = 0,
  LED_COLOR_RED = 0xff0000,
  LED_COLOR_GREEN = 0x00ff00,
  LED_COLOR_YELLOW = 0xffff00,
};

// Marblesy: brightness of the output LEDs, 0 (off) .. kOutputLedLevels (on).
const uint8_t kOutputLedLevels = 16;
const size_t kNumOutputLeds = 4;  // by DAC channel: Y, X1, X2, X3

class Leds {
 public:
  Leds() { }
  ~Leds() { }
  
  void Init();
  void Write();
  void Clear();
  
  void set(Led led, uint32_t color) {
    colors_[led] = color;
  }

  // Marblesy: the output LED of DAC channel `channel`.
  void set_output(size_t channel, uint8_t level) {
    output_levels_[channel] = level;
  }

  // Marblesy: the 74HC595 bits of the frame last written, for refresh
  // number `phase` (called by the I/O interrupt), and the same for any
  // frame (for the tests).
  static uint16_t ShiftRegisterBits(uint32_t phase);
  static uint16_t Bits(
      const uint32_t* colors,
      const uint8_t* output_levels,
      uint32_t phase);

 private:
  uint32_t colors_[LED_LAST];
  uint8_t output_levels_[kNumOutputLeds];
  
  DISALLOW_COPY_AND_ASSIGN(Leds);
};

}  // namespace marbles

#endif  // MARBLES_DRIVERS_LEDS_H_
