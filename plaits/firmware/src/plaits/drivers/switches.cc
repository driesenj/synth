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
// Plaitsy port of plaits/drivers/switches.cc.

#include "plaits/drivers/switches.h"

#include <algorithm>

#include "hal.h"

namespace plaits {

using namespace std;
using namespace plaitsy;

void Switches::Init() {
  hal::InitButtons();
  fill(&switch_state_[0], &switch_state_[SWITCH_LAST], 0xff);
}

void Switches::Debounce() {
  for (int i = 0; i < SWITCH_LAST; ++i) {
    // Like the pin: 1 when released.
    const uint8_t level = hal::ButtonPressed(hal::Button(i)) ? 0 : 1;
    switch_state_[i] = (switch_state_[i] << 1) | level;
  }
}

bool Switches::pressed_immediate(Switch s) const {
  return s < SWITCH_LAST && hal::ButtonPressed(hal::Button(s));
}

}  // namespace plaits
