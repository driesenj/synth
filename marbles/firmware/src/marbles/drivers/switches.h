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
// Driver for the 6 front panel switches.
//
// Marblesy port: the seven buttons come through a 74HC165 on the SPI bus
// (hal.h), read once per millisecond by Debounce(). pressed_immediate()
// reads it on the spot, for any button.

#ifndef MARBLES_DRIVERS_SWITCHES_H_
#define MARBLES_DRIVERS_SWITCHES_H_

#include "stmlib/stmlib.h"

namespace marbles {
  
enum Switch {
  SWITCH_T_DEJA_VU,
  SWITCH_T_MODEL,
  SWITCH_T_RANGE,
  SWITCH_X_DEJA_VU,
  SWITCH_X_MODE,
  SWITCH_X_RANGE,
  SWITCH_X_EXT,
  SWITCH_LAST
};

class Switches {
 public:
  Switches() { }
  ~Switches() { }
  
  void Init();
  void Debounce();
  
  inline bool released(Switch s) const {
    return switch_state_[s] == 0x7f;
  }
  
  inline bool just_pressed(Switch s) const {
    return switch_state_[s] == 0x80;
  }

  inline bool pressed(Switch s) const {
    return switch_state_[s] == 0x00;
  }
  
  bool pressed_immediate(Switch s) const;

  // Marblesy: the level of button `s` in a 74HC165 reading (1 = released).
  static bool Level(uint8_t reading, Switch s);

  // Marblesy: whether a reading can be real. A 74HC165 that does not answer
  // (no supply, /PL or CP open) reads 0x00, all seven buttons held.
  static bool Plausible(uint8_t reading) {
    return (reading & 0x7f) != 0;
  }
  
 private:
  uint8_t switch_state_[SWITCH_LAST];
  
  DISALLOW_COPY_AND_ASSIGN(Switches);
};

}  // namespace marbles

#endif  // MARBLES_DRIVERS_SWITCHES_H_
