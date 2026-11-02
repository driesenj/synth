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
// Driver for the two gate outputs.
//
// Marblesy port: t1, t2 and t3 on D2, D3 and D4 (hal.h), into the x2.5
// gate stages.

#ifndef MARBLES_DRIVERS_GATE_OUTPUTS_H_
#define MARBLES_DRIVERS_GATE_OUTPUTS_H_

#include "stmlib/stmlib.h"

#include "marbles/io_buffer.h"

#include "hal.h"

namespace marbles {

class GateOutputs {
 public:
  GateOutputs() { }
  ~GateOutputs() { }
  
  void Init() {
    marblesy::hal::InitGpio();
  }
  
  inline void Write(IOBuffer::Slice s) {
    uint32_t gates = 0;
    for (size_t i = 0; i < kNumGateOutputs; ++i) {
      if (s.block->gate_output[i][s.frame_index]) {
        gates |= 1 << i;
      }
    }
    marblesy::hal::WriteGates(gates);
  }
  

 private:
  DISALLOW_COPY_AND_ASSIGN(GateOutputs);
};

}  // namespace marbles

#endif  // MARBLES_DRIVERS_GATE_OUTPUTS_H_
