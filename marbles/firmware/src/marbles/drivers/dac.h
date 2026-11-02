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
// Driver for quad SPI DAC.
//
// Marblesy port: two 12-bit MCP4922s (U7, U8) on the SPI bus instead of
// Marbles' 16-bit DAC8564, written once per sample from the I/O interrupt.
// The rest of the firmware still works in Marbles' 16-bit codes and its
// calibration (code = volts * dac_scale + dac_offset); Word() rounds them to
// 12 bits. Marbles' DAC channel i is cv_output[i]: Process() writes the
// generator's X1, X2, X3 and Y into cv_output[1], [2], [3] and [0], so
// channel 0 is the Y jack whatever the enum below says.

#ifndef MARBLES_DRIVERS_DAC_H_
#define MARBLES_DRIVERS_DAC_H_

#include "stmlib/stmlib.h"

#include "marbles/io_buffer.h"

namespace marbles {

enum DacChannel {
  DAC_CHANNEL_X_1,
  DAC_CHANNEL_X_2,
  DAC_CHANNEL_X_3,
  DAC_CHANNEL_Y,
  DAC_CHANNEL_LAST
};

const size_t kMaxDacBlockSize = 8;
const size_t kNumDacChannels = 4;

// Marblesy's output stage (circuit.py): an inverting summer, Rf 100k, from
// the DAC through 24k and from -2.5 V (the inverted LM4040 reference)
// through 47k; the MCP4922 runs from the same 2.5 V at gain 1. So
// V = 2.5 V * (100k / 47k - 100k / 24k * code / 65536), and the nominal
// calibration, which the reference drops out of at 0 V, is:
const float kDacReference = 2.5f;
const float kDacInputResistor = 24.0e3f;
const float kDacOffsetResistor = 47.0e3f;
const float kDacFeedbackResistor = 100.0e3f;
const float kDacScale = -65536.0f * kDacInputResistor /
    (kDacFeedbackResistor * kDacReference);  // codes per volt, -6291.5
const float kDacOffset =
    65536.0f * kDacInputResistor / kDacOffsetResistor;  // 0 V, 33465.2

class Dac {
 public:
  Dac() { }
  ~Dac() { }
  
  void Init();

  // Sends Marbles' 16-bit codes for channels 0..3 to the DACs and updates
  // the four outputs together.
  void Write(const uint16_t* codes);

  // The MCP4922 command word that sets Marbles' DAC channel `channel` to
  // `code`, and the DAC it goes to (hal::WriteDacs' order: U7 A, U7 B,
  // U8 A, U8 B).
  static uint16_t Word(size_t channel, uint16_t code);
  static size_t Slot(size_t channel);
  
 private:
  DISALLOW_COPY_AND_ASSIGN(Dac);
};

}  // namespace marbles

#endif  // MARBLES_DRIVERS_DAC_H_
