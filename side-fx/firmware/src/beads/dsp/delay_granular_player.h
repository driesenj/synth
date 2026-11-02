// Copyright 2017 Emilie Gillet.
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
// Granular player.
//
// Side FXy: changed for BEADSY (lines marked "Side FXy"):
//   - at most kMaxGrains (10) grains instead of 32, so that the worst case
//     (dense, long, overlapping grains read from SDRAM) fits the CPU share
//     of one Side FXy slot. GranularPlayer::SortGrainList fades the 4
//     grains nearest their end at every new grain, so with 10 a grain
//     lives at most about 7.5 grain intervals (Beads: about 30): at 5 Hz
//     1.4 s instead of 3.3 s, at 20 Hz 0.37 s instead of 1.5 s, at 60 Hz
//     0.13 s instead of 0.5 s. Raise it (16 .. 24) as far as the CPU
//     measured on the Seed allows.

#ifndef BEADS_DSP_DELAY_GRANULAR_PLAYER_H_
#define BEADS_DSP_DELAY_GRANULAR_PLAYER_H_

#include "stmlib/stmlib.h"

#include "beads/dsp/delay_grain.h"
#include "beads/dsp/granular_player.h"

namespace beads {

const int kMaxGrains = 10;  // Side FXy: was 32.

class DelayGranularPlayer : public GranularPlayer<DelayGrain, kMaxGrains> {  // Side FXy
 public:
  DelayGranularPlayer() { }
  ~DelayGranularPlayer() { }
  
  template<typename DelayLineType>
  inline void Render(
      const DelayLineType* delay_line,
      const TriggerGenerator::Output& trigger,
      const Parameters& p,
      FloatFrame* out) {
    if (trigger.trigger) {
      const float duration = p.size.value();
      const bool reverse = duration < 0.3333333f;

      float amplitude, pan;
      ComputeGrainAmplitudeAndPan(trigger, p, &amplitude, &pan);
      
      const int safety = DelayGrain::head_crossing_safety_zone + 1;
      const int max_delay = delay_line->duration() - 2 * safety;

      new_grain()->Start(
          delay_line,
          p.time.value() * float(max_delay) + float(safety),
          (reverse ? -1.0f : 1.0f) * p.pitch.pitch_value(),
          ComputeGrainDuration(duration),
          p.shape.value(),
          amplitude, pan,
          trigger.fractional_sample);
      SortGrainList(p.monophonic_mode);
    }

    for (int i = 0; i < NUM_GRAINS; ++i) {
      grain_[i].Render<HEAD_CROSSING_POLICY_STOP, true>(delay_line, out);
    }

    Tick();  // Required to estimate the timing between grains.
  }

 private:
  DISALLOW_COPY_AND_ASSIGN(DelayGranularPlayer);
};

}  // namespace beads

#endif  // BEADS_DSP_DELAY_GRANULAR_PLAYER_H_
