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
// Plaitsy port of plaits/drivers/pots_adc.cc.

#include "plaits/drivers/pots_adc.h"

#include "hal.h"

namespace plaits {

using namespace plaitsy;

namespace {

// 74HC4051 channel of each pot (circuit.py, POTS): picked on the faceplate so
// that no two wiper tracks cross, so not in panel order. Every pot has its
// clockwise end on 3V3A, as on Plaits.
const int kMuxChannel[POTS_ADC_CHANNEL_LAST] = {
  0,  // RV1 FREQUENCY
  1,  // RV2 HARMONICS
  3,  // RV3 TIMBRE
  2,  // RV4 MORPH
  5,  // RV5 TIMBRE attenuverter
  6,  // RV6 FM attenuverter
  4,  // RV7 MORPH attenuverter
};

}  // namespace

void PotsAdc::Init() {
  hal::InitAdc();
  Convert();
}

void PotsAdc::Convert() {
  for (int i = 0; i < POTS_ADC_CHANNEL_LAST; ++i) {
    values_[i] = hal::ReadMux(kMuxChannel[i]);
  }
}

}  // namespace plaits
