// Copyright 2021 Emilie Gillet.
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
// User data manager.
//
// Plaitsy port: the 4 kB block (custom wavetables or a DX7 bank, sent to the
// TIMBRE input) lives in QSPI flash, with a copy in RAM that the engines
// read: the wavetable engine reads its user waves while it plays, and the
// QSPI flash cannot be read while it is being written. Save() runs in the
// audio callback and only updates the copy; the main loop writes it to
// flash with Persist().

#ifndef PLAITS_USER_DATA_H_
#define PLAITS_USER_DATA_H_

#include "stmlib/stmlib.h"

namespace plaits {

class UserData {
 public:
  enum {
    SIZE = 0x1000
  };

  UserData() { }
  ~UserData() { }

  // Plaitsy: loads the copy from flash; once, before the audio starts.
  static void Init();
  // Plaitsy: called from the main loop; writes a newly received block.
  static void Persist();

  inline const uint8_t* ptr(int slot) const {
    const uint8_t* data = data_;
    if (data[SIZE - 2] == 'U' && data[SIZE - 1] == (' ' + slot)) {
      return data;
    } else {
      return NULL;
    }
  }

  inline bool Save(uint8_t* rx_buffer, int slot) {
    if (slot < rx_buffer[SIZE - 2] || slot > rx_buffer[SIZE - 1]) {
      return false;
    }

    // Tag the data to identify which engine it should be associated to.
    rx_buffer[SIZE - 2] = 'U';
    rx_buffer[SIZE - 1] = ' ' + slot;

    for (int i = 0; i < SIZE; ++i) {
      data_[i] = rx_buffer[i];
    }
    dirty_ = true;
    return true;
  }

 private:
  // Plaitsy: zeros past the block. Plaits 1.2's wavetable loader lets a
  // wave map value of 207 or more select a 16th custom wave that the block
  // does not hold, and reads up to 190 bytes past its end (on Plaits, into
  // the next flash page). Mutable's editor never sends such a map.
  static const int kReadMargin = 256;
  static uint8_t data_[SIZE + kReadMargin] __attribute__((aligned(4)));
  static volatile bool dirty_;
};

}  // namespace plaits

#endif  // PLAITS_USER_DATA_H_
