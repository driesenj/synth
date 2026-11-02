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
// Driver for the front panel switch.
//
// Marblesy port: see switches.h.

#include "marbles/drivers/switches.h"

#include <algorithm>

#include "hal.h"

namespace marbles {

using namespace std;

// circuit.py: the 74HC165's input Dn reads button SWn+1, which is Switch n
// (D7 is tied low). Each input has a 10k pull-up and its button pulls it to
// ground.
const uint8_t switch_input[] = {
  0,  // SWITCH_T_DEJA_VU, SW1 on D0
  1,  // SWITCH_T_MODE, SW2 on D1
  2,  // SWITCH_T_RANGE, SW3 on D2
  3,  // SWITCH_X_DEJA_VU, SW4 on D3
  4,  // SWITCH_X_MODE, SW5 on D4
  5,  // SWITCH_X_RANGE, SW6 on D5
  6   // SWITCH_X_EXT, SW7 on D6
};

/* static */
bool Switches::Level(uint8_t reading, Switch s) {
  return (reading >> switch_input[s]) & 1;
}

void Switches::Init() {
  marblesy::hal::InitBus();
  fill(&switch_state_[0], &switch_state_[SWITCH_LAST], 0xff);
}

void Switches::Debounce() {
  const uint8_t reading = marblesy::hal::ReadButtons();
  if (!Plausible(reading)) {
    return;  // keep the last state
  }
  for (int i = 0; i < SWITCH_LAST; ++i) {
    switch_state_[i] = (switch_state_[i] << 1) | Level(reading, Switch(i));
  }
}

bool Switches::pressed_immediate(Switch s) const {
  const uint8_t reading = marblesy::hal::ReadButtons();
  return Plausible(reading) && !Level(reading, s);
}

}  // namespace marbles
