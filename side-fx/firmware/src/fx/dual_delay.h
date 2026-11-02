// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: DUAL DELAY. Two 10 s delay lines, L and R, each with its own
// time, a shared saturating feedback with a tone filter in the loop, a
// CROSS from independent lines to full ping-pong, slow chorusing time
// modulation and an output WIDTH.
//
// Parameters:
//   TIME L, TIME R  1 ms .. 10 s, or a note value when synced.
//   FEEDBACK        0 .. 115 % loop gain: above ~87 % the repeats run away
//                   into a dub self-oscillation, held by a soft saturator
//                   (about +-1.4 at most).
//   CROSS           0: each line feeds itself, input L to line L, R to R.
//                   1: ping-pong: the input (L+R)/2 goes into line L only,
//                   L feeds R and R feeds L, so a mono source bounces.
//   TONE            bipolar, in the loop: down from the centre a lowpass
//                   (to 700 Hz) darkens every repeat, up a highpass (to
//                   1.8 kHz) thins them. Centre: flat but for a 20 Hz DC
//                   guard.
//   MOD             slow sine modulation of both times (L and R at
//                   different rates): chorused, slightly seasick repeats.
//   WIDTH           output width: 0 both lines in the middle (mono),
//                   1 line L hard left and line R hard right.
//
// Time changes: a change of less than 20 % of the current time glides
// (rate-limited, so a slowly turned knob bends the repeats' pitch like a
// BBD); a bigger jump (a synced step, a preset, a fast turn) crossfades in
// 30 ms to a second read tap at the new time, so it never clicks.

#ifndef SIDEFX_FX_DUAL_DELAY_H_
#define SIDEFX_FX_DUAL_DELAY_H_

#include "engine/block.h"
#include "fx/dsp_util.h"
#include "fx/dual_delay_line.h"

namespace sidefx {

class DualDelay : public Block {
 public:
  DualDelay() { }
  ~DualDelay() { }

  enum Param {
    TIME_L,
    TIME_R,
    FEEDBACK,
    CROSS,
    TONE,
    MOD,
    WIDTH,
    NUM_PARAMS
  };

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // The loop gain FEEDBACK `value` sets (1.15 at the top).
  static float FeedbackGain(float value);
  // The tone filters' cutoffs at TONE `value`, in Hz.
  static float LowpassHz(float value);
  static float HighpassHz(float value);

 private:
  // One line with its two read taps (the second is used while
  // crossfading to a new time).
  struct Line {
    dsp::DelayLine16 buffer;
    float delay[2];   // samples
    float slope[2];   // delay change per sample in this block
    int active;
    bool fading;
    float fade;       // 0 .. 1 from the active tap to the other
    float lfo_phase;
    dsp::OnePole lowpass;
    dsp::OnePole highpass;
  };

  void UpdateTime(Line* line, float target, size_t size);

  Line line_[2];
  bool primed_;  // the taps start at their targets after Reset()

  // Values at the end of the last block, ramped across the next.
  float feedback_;
  float cross_;
  float width_;
  float depth_[2];
  float lowpass_coefficient_;
  float highpass_coefficient_;
};

}  // namespace sidefx

#endif  // SIDEFX_FX_DUAL_DELAY_H_
