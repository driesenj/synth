// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: DUAL SHIFT, two pitch shifters with delay and feedback, in the
// spirit of an Eventide H3000's dual shift programs (our own design).
//
// The mono sum feeds two voices, A and B. Each voice writes into its own
// line and reads it back through a pre-delay (DELAY) and a delay-line pitch
// shifter: two taps half a WINDOW apart sweep through the window at
// (1 - ratio) samples per sample, each faded in and out with a sine window
// (sin^2 + cos^2 = 1: equal power). Small windows sound grainy and
// metallic, large ones smooth. FEEDBACK sends the voice's output back into
// its own line through a DC blocker, a gentle lowpass and a soft saturator,
// so repeats climb or fall in pitch with every pass: spirals.
//
// DELAY and WINDOW changes never glide (a gliding read position bends the
// pitch on top of the shift, by octaves for a fast window change): both
// voices crossfade from the old pre-delay and window to the new ones, each
// pair of taps with its own sweep. Changes smaller than an external
// clock's jitter (16 samples + 0.3 % of DELAY, 0.5 % of WINDOW) are left
// alone, so a synced DELAY does not crossfade at every clock pulse.

#ifndef SIDEFX_FX_DUAL_SHIFT_H_
#define SIDEFX_FX_DUAL_SHIFT_H_

#include "engine/block.h"
#include "fx/dsp_util.h"

namespace sidefx {

class DualShift : public Block {
 public:
  enum Param {
    PITCH_A,
    PITCH_B,
    DETUNE,
    DELAY,
    FEEDBACK,
    WINDOW,
    WIDTH,
    NUM_PARAMS
  };

  DualShift() { }
  ~DualShift() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // The parameter mappings, shared with the tests.
  static float PitchSemitones(float value);
  static float DetuneCents(float value);
  static float DelaySeconds(float value, bool synced, float beat_seconds);
  static float WindowSeconds(float value);

 private:
  struct Voice {
    float* line;
    // Tap 0's place in the window of setting [0] (playing) and [1] (faded
    // to), [0, 1); tap 1 is half a window on.
    float phase[2];
    float feedback;  // what goes into the line with the next input sample
    dsp::OnePole lowpass;
    dsp::DcBlocker dc_blocker;
  };

  // The line `pre + offset` samples before the newest one; pre an integer,
  // offset 1 .. window + 2.
  float Read(const float* line, int32_t pre, float offset) const;
  // One setting's two taps, advancing its sweep.
  float Shift(Voice* voice, int setting, float ratio);

  Voice voice_[2];
  size_t write_;

  // Settings: [0] the one playing, [1] the one faded to.
  int32_t pre_delay_[2];  // samples
  float window_[2];       // samples
  float inverse_window_[2];
  bool fading_;
  float fade_;

  float feedback_;  // smoothed loop gain
  float gain_l_[2];
  float gain_r_[2];
  float loop_lowpass_;
  bool primed_;  // false until the first block after Reset() sets the state
};

}  // namespace sidefx

#endif  // SIDEFX_FX_DUAL_SHIFT_H_
